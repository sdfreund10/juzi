from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Learner, Word
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
    user = _make_user(email="alice@example.com", password="s3cret-alice")
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


def _word_payload(word: Word) -> dict:
    return {
        "id": word.id,
        "chinese": word.chinese,
        "pinyin": word.pinyin,
        "english_basic": word.english_basic,
        "example_chinese": word.example_sentence_traditional,
        "example_pinyin": word.example_sentence_pinyin,
        "example_english": word.example_sentence_english,
    }


@pytest.mark.django_db
def test_word_detail_requires_authentication(client: APIClient) -> None:
    word = Word.objects.create(chinese="愛", pinyin="ài", english_basic="to love")
    response = client.get(reverse("words-detail", kwargs={"word_id": word.id}))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_word_detail_returns_fields(client: APIClient, user: User) -> None:
    word = Word.objects.create(
        chinese="愛",
        pinyin="ài",
        english_basic="to love",
        example_sentence_traditional="我愛喝茶。",
        example_sentence_pinyin="Wǒ ài hē chá.",
        example_sentence_english="I like to drink tea.",
    )
    _login(client, user)

    response = client.get(reverse("words-detail", kwargs={"word_id": word.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == _word_payload(word)


@pytest.mark.django_db
def test_word_detail_includes_archived(client: APIClient, user: User) -> None:
    word = Word.objects.create(
        chinese="舊",
        pinyin="jiù",
        english_basic="old",
        archived_at=timezone.now(),
    )
    _login(client, user)

    response = client.get(reverse("words-detail", kwargs={"word_id": word.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == word.id


@pytest.mark.django_db
def test_word_detail_unknown_id(client: APIClient, user: User) -> None:
    _login(client, user)
    response = client.get(reverse("words-detail", kwargs={"word_id": 999999}))
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Word not found."}


@pytest.mark.django_db
def test_words_list_requires_chinese_query(client: APIClient, user: User) -> None:
    _login(client, user)
    response = client.get(reverse("words-list"))
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = client.get(reverse("words-list"), {"chinese": "   "})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_words_list_exact_chinese_match(client: APIClient, user: User) -> None:
    particle = Word.objects.create(
        chinese="的",
        pinyin="de",
        english_basic="possessive particle",
    )
    taxi = Word.objects.create(
        chinese="的",
        pinyin="dī",
        english_basic="taxi",
    )
    Word.objects.create(chinese="得", pinyin="dé", english_basic="to get")
    _login(client, user)

    response = client.get(reverse("words-list"), {"chinese": "的"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [_word_payload(particle), _word_payload(taxi)]


@pytest.mark.django_db
def test_words_list_empty_when_no_match(client: APIClient, user: User) -> None:
    _login(client, user)
    response = client.get(reverse("words-list"), {"chinese": "喵"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []
