from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Category, Learner, UserWord, Word, WordCategory
from api.services.accounts import apply_login_email
from api.services.scheduling import (
    GRADE_EASY,
    GRADE_HARD,
    UserWordNotFoundError,
    interval_days_for_streak,
    rate_user_word,
)
from api.services.sessions import (
    EmptySessionError,
    _card_from_user_word,
    _study_level_for_proficiency,
    _unlocked_modes_for_level,
    build_session,
)

User = get_user_model()


def _make_user(*, email: str, password: str = "s3cret") -> User:
    user = User(username=email, email=email)
    apply_login_email(user, email)
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def user(db) -> User:
    user = _make_user(email="alice@example.com")
    Learner.objects.create(
        user=user,
        proficiency_level=Learner.ProficiencyLevel.NOVICE,
    )
    return user


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


def _csrf_headers(client: APIClient) -> dict[str, str]:
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_200_OK
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def _login(client: APIClient, user: User, password: str = "s3cret") -> dict[str, str]:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": password},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_200_OK
    return _csrf_headers(client)


@pytest.fixture
def topic(db) -> Category:
    return Category.objects.create(name="Food, Cooking & Dining")


@pytest.fixture
def words(topic: Category) -> dict[str, Word]:
    novice = Word.objects.create(
        chinese="愛",
        simplified="爱",
        pinyin="ài",
        english_basic="to love",
        hsk_level=1,
    )
    intermediate = Word.objects.create(
        chinese="圖書館",
        simplified="图书馆",
        pinyin="túshūguǎn",
        english_basic="library",
        hsk_level=4,
    )
    advanced = Word.objects.create(
        chinese="抽象",
        simplified="抽象",
        pinyin="chōuxiàng",
        english_basic="abstract",
        hsk_level=6,
    )
    for word in (novice, intermediate, advanced):
        WordCategory.objects.create(word=word, category=topic)
    return {
        "novice": novice,
        "intermediate": intermediate,
        "advanced": advanced,
    }


@pytest.mark.parametrize(
    ("streak", "expected_days"),
    [
        (1, 1),
        (3, 3),
        (4, 3),
        (6, 7),
        (9, 7),
        (10, 14),
        (20, 14),
    ],
)
def test_interval_days_for_streak(streak: int, expected_days: int) -> None:
    assert interval_days_for_streak(streak) == expected_days


@pytest.mark.parametrize(
    ("study_level", "expected"),
    [
        (0, (UserWord.Mode.PINYIN_TO_EN,)),
        (4, (UserWord.Mode.PINYIN_TO_EN,)),
        (5, (UserWord.Mode.PINYIN_TO_EN, UserWord.Mode.EN_TO_ZH)),
        (9, (UserWord.Mode.PINYIN_TO_EN, UserWord.Mode.EN_TO_ZH)),
        (10, (UserWord.Mode.PINYIN_TO_EN, UserWord.Mode.EN_TO_ZH, UserWord.Mode.ZH_TO_EN)),
    ],
)
def test_unlocked_modes_for_level(study_level: int, expected: tuple[str, ...]) -> None:
    assert _unlocked_modes_for_level(study_level) == expected


@pytest.mark.parametrize(
    ("proficiency", "hsk_level", "expected_floor"),
    [
        (Learner.ProficiencyLevel.NOVICE, 1, 0),
        (Learner.ProficiencyLevel.NOVICE, 7, 0),
        (Learner.ProficiencyLevel.INTERMEDIATE, 1, 5),
        (Learner.ProficiencyLevel.INTERMEDIATE, 3, 5),
        (Learner.ProficiencyLevel.INTERMEDIATE, 4, 0),
        (Learner.ProficiencyLevel.INTERMEDIATE, 6, 0),
        (Learner.ProficiencyLevel.ADVANCED, 1, 10),
        (Learner.ProficiencyLevel.ADVANCED, 3, 10),
        (Learner.ProficiencyLevel.ADVANCED, 4, 5),
        (Learner.ProficiencyLevel.ADVANCED, 6, 5),
        (Learner.ProficiencyLevel.EXPERT, 1, 10),
        (Learner.ProficiencyLevel.EXPERT, 7, 10),
    ],
)
def test_study_level_for_proficiency(
    proficiency: str,
    hsk_level: int,
    expected_floor: int,
) -> None:
    assert _study_level_for_proficiency(proficiency, hsk_level) == expected_floor


def _prefer_zh_to_en(modes: tuple[str, ...]) -> str:
    if UserWord.Mode.ZH_TO_EN in modes:
        return UserWord.Mode.ZH_TO_EN
    return modes[0]


def _prefer_en_to_zh(modes: tuple[str, ...]) -> str:
    if UserWord.Mode.EN_TO_ZH in modes:
        return UserWord.Mode.EN_TO_ZH
    return modes[0]


@pytest.mark.django_db
def test_card_from_user_word_novice_only_pinyin_at_zero_easy(
    user: User,
    words: dict[str, Word],
) -> None:
    row = UserWord.objects.create(
        user=user,
        word=words["novice"],
        easy_count=0,
        due_on=timezone.localdate(),
    )
    with patch(
        "api.services.sessions.random.choice",
        side_effect=_prefer_zh_to_en,
    ):
        card = _card_from_user_word(row, Learner.ProficiencyLevel.NOVICE)
    assert card.mode == UserWord.Mode.PINYIN_TO_EN


@pytest.mark.django_db
def test_card_from_user_word_intermediate_unlocks_en_to_zh_on_hsk_1(
    user: User,
    words: dict[str, Word],
) -> None:
    row = UserWord.objects.create(
        user=user,
        word=words["novice"],
        easy_count=0,
        due_on=timezone.localdate(),
    )
    with patch(
        "api.services.sessions.random.choice",
        side_effect=_prefer_en_to_zh,
    ):
        card = _card_from_user_word(row, Learner.ProficiencyLevel.INTERMEDIATE)
    assert card.mode == UserWord.Mode.EN_TO_ZH


@pytest.mark.django_db
def test_card_from_user_word_intermediate_not_zh_to_en_on_hsk_4(
    user: User,
    words: dict[str, Word],
) -> None:
    row = UserWord.objects.create(
        user=user,
        word=words["intermediate"],
        easy_count=0,
        due_on=timezone.localdate(),
    )
    with patch(
        "api.services.sessions.random.choice",
        side_effect=_prefer_zh_to_en,
    ):
        card = _card_from_user_word(row, Learner.ProficiencyLevel.INTERMEDIATE)
    assert card.mode == UserWord.Mode.PINYIN_TO_EN


@pytest.mark.django_db
def test_card_from_user_word_expert_unlocks_zh_to_en_on_hsk_6(
    user: User,
    words: dict[str, Word],
) -> None:
    row = UserWord.objects.create(
        user=user,
        word=words["advanced"],
        easy_count=0,
        due_on=timezone.localdate(),
    )
    with patch(
        "api.services.sessions.random.choice",
        side_effect=_prefer_zh_to_en,
    ):
        card = _card_from_user_word(row, Learner.ProficiencyLevel.EXPERT)
    assert card.mode == UserWord.Mode.ZH_TO_EN


@pytest.mark.django_db
def test_card_from_user_word_uses_easy_count_when_higher_than_floor(
    user: User,
    words: dict[str, Word],
) -> None:
    row = UserWord.objects.create(
        user=user,
        word=words["intermediate"],
        easy_count=10,
        due_on=timezone.localdate(),
    )
    with patch(
        "api.services.sessions.random.choice",
        side_effect=_prefer_zh_to_en,
    ):
        card = _card_from_user_word(row, Learner.ProficiencyLevel.NOVICE)
    assert card.mode == UserWord.Mode.ZH_TO_EN


@pytest.mark.django_db
def test_rate_hard_resets_streak_keeps_count(user: User, words: dict[str, Word]) -> None:
    today = timezone.localdate()
    row = UserWord.objects.create(
        user=user,
        word=words["novice"],
        easy_streak=4,
        easy_count=7,
        due_on=today + timedelta(days=3),
    )
    rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_HARD,
    )

    row.refresh_from_db()
    assert row.easy_streak == 0
    assert row.easy_count == 7
    assert row.due_on == today
    assert row.last_practiced_at is not None


@pytest.mark.django_db
def test_rate_easy_advances_streak_count_and_due(user: User, words: dict[str, Word]) -> None:
    today = timezone.localdate()
    row = UserWord.objects.create(
        user=user,
        word=words["novice"],
        easy_streak=0,
        easy_count=0,
        due_on=today,
    )

    rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_EASY,
    )

    row.refresh_from_db()
    assert row.easy_streak == 1
    assert row.easy_count == 1
    assert row.due_on == today + timedelta(days=1)
    assert row.last_practiced_at is not None


@pytest.mark.django_db
def test_rate_missing_user_word_raises(user: User, words: dict[str, Word]) -> None:
    with pytest.raises(UserWordNotFoundError):
        rate_user_word(
            user=user,
            word_id=words["novice"].id,
            grade=GRADE_EASY,
        )


@pytest.mark.django_db
def test_build_session_lazily_creates_difficulty_scoped_rows(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    session = build_session(
        user=user,
        category=topic,
        difficulties=["novice"],
    )

    assert session.total == 1
    assert session.cards[0].word_id == words["novice"].id
    assert UserWord.objects.filter(user=user).count() == 1
    row = UserWord.objects.get(user=user, word=words["novice"])
    assert row.due_on == timezone.localdate()
    assert not UserWord.objects.filter(user=user, word=words["intermediate"]).exists()
    assert not UserWord.objects.filter(user=user, word=words["advanced"]).exists()


@pytest.mark.django_db
def test_build_session_one_card_per_word_and_unlocked_mode(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    UserWord.objects.create(
        user=user,
        word=words["novice"],
        easy_count=10,
        due_on=timezone.localdate(),
    )

    with patch("api.services.sessions.random.choice", return_value=UserWord.Mode.ZH_TO_EN):
        session = build_session(
            user=user,
            category=topic,
            difficulties=["novice"],
        )

    assert session.total == 1
    card = session.cards[0]
    assert card.word_id == words["novice"].id
    assert card.mode == UserWord.Mode.ZH_TO_EN


@pytest.mark.django_db
def test_build_session_excludes_future_due(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    UserWord.objects.create(
        user=user,
        word=words["novice"],
        due_on=timezone.localdate() + timedelta(days=1),
    )

    with pytest.raises(EmptySessionError):
        build_session(
            user=user,
            category=topic,
            difficulties=["novice"],
        )


@pytest.mark.django_db
def test_rate_endpoint_requires_authentication(
    client: APIClient,
    words: dict[str, Word],
) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("ratings-create"),
        {"word_id": words["novice"].id, "grade": "easy"},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_rate_endpoint_happy_path(
    client: APIClient,
    user: User,
    words: dict[str, Word],
) -> None:
    today = timezone.localdate()
    UserWord.objects.create(
        user=user,
        word=words["novice"],
        easy_streak=0,
        easy_count=0,
        due_on=today,
    )
    headers = _login(client, user)
    response = client.post(
        reverse("ratings-create"),
        {"word_id": words["novice"].id, "grade": "easy"},
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["user_word"]["word_id"] == words["novice"].id
    assert body["user_word"]["easy_streak"] == 1
    assert body["user_word"]["easy_count"] == 1


@pytest.mark.django_db
def test_rate_endpoint_missing_row(
    client: APIClient,
    user: User,
    words: dict[str, Word],
) -> None:
    headers = _login(client, user)
    response = client.post(
        reverse("ratings-create"),
        {"word_id": words["novice"].id, "grade": "hard"},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Word progress not found."}
