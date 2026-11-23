from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import LearnerScore
from api.services.accounts import apply_login_email
from api.services.learner_score import (
    points_for_difficulties,
    get_learner_score,
    record_completion,
)

User = get_user_model()


def _make_user(*, email: str, password: str) -> User:
    user = User(username=email, email=email)
    apply_login_email(user, email)
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def user(db) -> User:
    return _make_user(email="alice@example.com", password="s3cret-alice")


@pytest.fixture
def other_user(db) -> User:
    return _make_user(email="bob@example.com", password="s3cret-bob")


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


def _csrf_headers(client: APIClient) -> dict[str, str]:
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_200_OK
    token = client.cookies["csrftoken"].value
    return {"HTTP_X_CSRFTOKEN": token}


def _login(client: APIClient, user: User, password: str) -> dict[str, str]:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": password},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_200_OK
    return _csrf_headers(client)


@pytest.mark.parametrize(
    ("difficulties", "expected"),
    [
        (["novice"], Decimal("10")),
        (["intermediate"], Decimal("12.5")),
        (["advanced"], Decimal("15")),
        (["expert"], Decimal("20")),
        (["novice", "intermediate"], Decimal("15")),
        (["expert", "novice"], Decimal("22.5")),
    ],
)
def test_points_for_difficulties(difficulties: list[str], expected: Decimal) -> None:
    assert points_for_difficulties(difficulties) == expected


@pytest.mark.django_db
def test_first_novice_completion_creates_row(user: User) -> None:
    row = record_completion(user=user, difficulties=["novice"])

    assert row.date == timezone.localdate()
    assert row.starting_score == Decimal("0")
    assert row.score == Decimal("10")
    assert LearnerScore.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_same_day_second_completion_bumps_score(user: User) -> None:
    record_completion(user=user, difficulties=["novice"])
    row = record_completion(user=user, difficulties=["novice"])

    assert LearnerScore.objects.filter(user=user).count() == 1
    assert row.starting_score == Decimal("0")
    assert row.score == Decimal("20")


@pytest.mark.django_db
def test_new_row_decays_from_yesterday(user: User) -> None:
    today = timezone.localdate()
    LearnerScore.objects.create(
        user=user,
        date=today - timedelta(days=1),
        starting_score=Decimal("0"),
        score=Decimal("20"),
    )

    row = record_completion(user=user, difficulties=["novice"])

    assert row.starting_score == Decimal("15")
    assert row.score == Decimal("25")
    assert LearnerScore.objects.filter(user=user).count() == 2
    earlier = LearnerScore.objects.get(user=user, date=today - timedelta(days=1))
    assert earlier.score == Decimal("20")


@pytest.mark.django_db
def test_new_row_floors_decay_at_zero(user: User) -> None:
    today = timezone.localdate()
    LearnerScore.objects.create(
        user=user,
        date=today - timedelta(days=3),
        starting_score=Decimal("0"),
        score=Decimal("10"),
    )

    row = record_completion(user=user, difficulties=["novice"])

    assert row.starting_score == Decimal("0")
    assert row.score == Decimal("10")


@pytest.mark.django_db
def test_intermediate_and_expert_multipliers(user: User) -> None:
    mixed = record_completion(user=user, difficulties=["novice", "intermediate"])
    assert mixed.score == Decimal("15")

    LearnerScore.objects.all().delete()
    expert = record_completion(user=user, difficulties=["expert"])
    assert expert.score == Decimal("20")


@pytest.mark.django_db
def test_read_writes_no_rows_and_decays_today(user: User) -> None:
    today = timezone.localdate()
    LearnerScore.objects.create(
        user=user,
        date=today - timedelta(days=1),
        starting_score=Decimal("0"),
        score=Decimal("20"),
    )

    snapshot = get_learner_score(user=user, days=3)

    assert LearnerScore.objects.filter(user=user).count() == 1
    assert snapshot.score == Decimal("15")
    assert [point.date for point in snapshot.days] == [
        today - timedelta(days=2),
        today - timedelta(days=1),
        today,
    ]
    assert [point.score for point in snapshot.days] == [
        Decimal("0"),
        Decimal("20"),
        Decimal("15"),
    ]


@pytest.mark.django_db
def test_read_quiet_day_between_rows(user: User) -> None:
    today = timezone.localdate()
    LearnerScore.objects.create(
        user=user,
        date=today - timedelta(days=2),
        starting_score=Decimal("0"),
        score=Decimal("20"),
    )
    LearnerScore.objects.create(
        user=user,
        date=today,
        starting_score=Decimal("10"),
        score=Decimal("20"),
    )

    snapshot = get_learner_score(user=user, days=3)

    assert [point.score for point in snapshot.days] == [
        Decimal("20"),
        Decimal("15"),
        Decimal("20"),
    ]


@pytest.mark.django_db
def test_read_days_window_longer_than_default(user: User) -> None:
    today = timezone.localdate()
    LearnerScore.objects.create(
        user=user,
        date=today - timedelta(days=20),
        starting_score=Decimal("0"),
        score=Decimal("100"),
    )

    snapshot = get_learner_score(user=user, days=21)

    assert len(snapshot.days) == 21
    assert snapshot.days[0].date == today - timedelta(days=20)
    assert snapshot.days[0].score == Decimal("100")
    assert snapshot.score == Decimal("0")


@pytest.mark.django_db
def test_get_learner_score_requires_auth(client: APIClient) -> None:
    response = client.get(reverse("learner-score"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_get_learner_score_is_scoped_to_user(
    client: APIClient, user: User, other_user: User
) -> None:
    today = timezone.localdate()
    LearnerScore.objects.create(
        user=user,
        date=today,
        starting_score=Decimal("0"),
        score=Decimal("10"),
    )
    LearnerScore.objects.create(
        user=other_user,
        date=today,
        starting_score=Decimal("0"),
        score=Decimal("99"),
    )

    headers = _login(client, user, "s3cret-alice")
    response = client.get(reverse("learner-score"), **headers)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["score"] == 10.0
    assert body["days"][-1] == {"date": today.isoformat(), "score": 10.0}
    assert LearnerScore.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_post_completion_creates_and_bumps(
    client: APIClient, user: User
) -> None:
    headers = _login(client, user, "s3cret-alice")

    first = client.post(
        reverse("learner-score-completions"),
        {"difficulties": ["novice"]},
        format="json",
        **headers,
    )
    assert first.status_code == status.HTTP_200_OK
    assert first.json() == {
        "date": timezone.localdate().isoformat(),
        "starting_score": 0.0,
        "score": 10.0,
    }

    second = client.post(
        reverse("learner-score-completions"),
        {"difficulties": ["intermediate"]},
        format="json",
        **headers,
    )
    assert second.status_code == status.HTTP_200_OK
    assert second.json()["score"] == 22.5
    assert LearnerScore.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_post_completion_rejects_unknown_difficulty(
    client: APIClient, user: User
) -> None:
    headers = _login(client, user, "s3cret-alice")
    response = client.post(
        reverse("learner-score-completions"),
        {"difficulties": ["legendary"]},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert LearnerScore.objects.filter(user=user).count() == 0
