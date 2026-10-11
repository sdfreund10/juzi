from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Category, UserWord, Word, WordCategory
from api.services.accounts import apply_login_email

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
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


def _csrf_headers(client: APIClient) -> dict[str, str]:
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_200_OK
    token = client.cookies["csrftoken"].value
    return {"HTTP_X_CSRFTOKEN": token}


def _login(client: APIClient, user: User, password: str = "s3cret-alice") -> dict[str, str]:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": password},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_200_OK
    return _csrf_headers(client)


def _link(word: Word, category: Category) -> None:
    WordCategory.objects.create(word=word, category=category)


@pytest.fixture
def topic_food(db) -> Category:
    return Category.objects.create(name="Food, Cooking & Dining")


@pytest.fixture
def hsk_one(db) -> Category:
    return Category.objects.create(name="HSK 1")


@pytest.fixture
def seeded_words(topic_food: Category, hsk_one: Category) -> dict[str, Word]:
    beginner = Word.objects.create(
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
    for word in (beginner, intermediate, advanced):
        _link(word, topic_food)
        _link(word, hsk_one)
    return {
        "beginner": beginner,
        "intermediate": intermediate,
        "advanced": advanced,
    }


@pytest.mark.django_db
def test_categories_requires_authentication(client: APIClient) -> None:
    response = client.get(reverse("categories"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_categories_lists_topic_decks_only(
    client: APIClient,
    user: User,
    topic_food: Category,
    hsk_one: Category,
) -> None:
    headers = _login(client, user)
    response = client.get(reverse("categories"), **headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "id": topic_food.id,
            "name": topic_food.name,
            "beginner_count": 0,
            "intermediate_count": 0,
            "advanced_count": 0,
        }
    ]


@pytest.mark.django_db
def test_categories_includes_difficulty_counts(
    client: APIClient,
    user: User,
    topic_food: Category,
    seeded_words: dict[str, Word],
) -> None:
    headers = _login(client, user)
    response = client.get(reverse("categories"), **headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "id": topic_food.id,
            "name": topic_food.name,
            "beginner_count": 1,
            "intermediate_count": 1,
            "advanced_count": 1,
        }
    ]


@pytest.mark.django_db
def test_create_session_requires_authentication(client: APIClient, topic_food: Category) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("sessions-create"),
        {"category_id": topic_food.id, "difficulties": ["beginner"]},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_create_session_filters_difficulty_bands(
    client: APIClient,
    user: User,
    topic_food: Category,
    seeded_words: dict[str, Word],
) -> None:
    headers = _login(client, user)
    response = client.post(
        reverse("sessions-create"),
        {"category_id": topic_food.id, "difficulties": ["beginner", "advanced"]},
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["category"] == {"id": topic_food.id, "name": topic_food.name}
    assert "beginner_count" not in body["category"]
    assert body["difficulties"] == ["beginner", "advanced"]
    assert body["total"] == 2
    word_ids = {card["word_id"] for card in body["cards"]}
    assert word_ids == {seeded_words["beginner"].id, seeded_words["advanced"].id}
    assert all(card["mode"] in UserWord.Mode.values for card in body["cards"])
    assert all(card["prompt"] for card in body["cards"])


@pytest.mark.django_db
def test_create_session_returns_full_matching_set(
    client: APIClient,
    user: User,
    topic_food: Category,
    seeded_words: dict[str, Word],
) -> None:
    headers = _login(client, user)
    response = client.post(
        reverse("sessions-create"),
        {
            "category_id": topic_food.id,
            "difficulties": ["beginner", "intermediate", "advanced"],
        },
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 3
    assert len(body["cards"]) == 3


@pytest.mark.django_db
def test_create_session_excludes_future_due_words(
    client: APIClient,
    user: User,
    topic_food: Category,
    seeded_words: dict[str, Word],
) -> None:
    tomorrow = timezone.localdate() + timedelta(days=1)
    UserWord.objects.create(
        user=user,
        word=seeded_words["beginner"],
        due_on=tomorrow,
    )
    headers = _login(client, user)
    response = client.post(
        reverse("sessions-create"),
        {"category_id": topic_food.id, "difficulties": ["beginner"]},
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "No cards match."}


@pytest.mark.django_db
def test_create_session_empty_when_no_words(
    client: APIClient,
    user: User,
    topic_food: Category,
) -> None:
    headers = _login(client, user)
    response = client.post(
        reverse("sessions-create"),
        {"category_id": topic_food.id, "difficulties": ["beginner"]},
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "No cards match."}


@pytest.mark.django_db
def test_create_session_rejects_unknown_difficulty(
    client: APIClient,
    user: User,
    topic_food: Category,
) -> None:
    headers = _login(client, user)
    response = client.post(
        reverse("sessions-create"),
        {"category_id": topic_food.id, "difficulties": ["expert"]},
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
