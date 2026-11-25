from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Category, Learner, Word, WordCategory
from api.services.accounts import apply_login_email

User = get_user_model()


def _make_user(*, email: str, password: str) -> User:
    user = User(username=email, email=email)
    apply_login_email(user, email)
    user.set_password(password)
    user.save()
    Learner.objects.create(user=user, proficiency_level=Learner.ProficiencyLevel.NOVICE)
    return user


def _csrf_headers(client: APIClient) -> dict[str, str]:
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_200_OK
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


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


def _word() -> Word:
    return Word.objects.create(
        chinese="茶",
        pinyin="chá",
        english_basic="tea",
        hsk_level=1,
    )


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


@pytest.mark.django_db
def test_learner_names_are_unique_per_owner_and_operator_names_stay_unique() -> None:
    alice = _make_user(email="alice@example.com", password="s3cret-alice")
    bob = _make_user(email="bob@example.com", password="s3cret-bob")
    Category.objects.create(name="Food, Cooking & Dining")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Category.objects.create(name="Food, Cooking & Dining")

    Category.objects.create(name="Food, Cooking & Dining", owner=alice)
    Category.objects.create(name="Food, Cooking & Dining", owner=bob)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Category.objects.create(name="Food, Cooking & Dining", owner=alice)


@pytest.mark.django_db
def test_category_list_shows_owned_decks_and_shared_topics(client: APIClient) -> None:
    alice = _make_user(email="alice@example.com", password="s3cret-alice")
    bob = _make_user(email="bob@example.com", password="s3cret-bob")
    topic = Category.objects.create(name="Food, Cooking & Dining")
    Category.objects.create(name="HSK 1")
    alice_deck = Category.objects.create(name="talk to their parents", owner=alice)
    alice_hsk_titled = Category.objects.create(name="HSK dinner plans", owner=alice)
    bob_deck = Category.objects.create(name="talk to their parents", owner=bob)

    alice_headers = _login(client, alice, "s3cret-alice")
    alice_response = client.get(reverse("categories"), **alice_headers)
    assert alice_response.status_code == status.HTTP_200_OK
    assert {row["id"] for row in alice_response.json()} == {
        topic.id,
        alice_deck.id,
        alice_hsk_titled.id,
    }

    bob_client = APIClient(enforce_csrf_checks=True)
    bob_headers = _login(bob_client, bob, "s3cret-bob")
    bob_response = bob_client.get(reverse("categories"), **bob_headers)
    assert bob_response.status_code == status.HTTP_200_OK
    assert {row["id"] for row in bob_response.json()} == {topic.id, bob_deck.id}


@pytest.mark.django_db
def test_create_session_hides_another_learners_deck(client: APIClient) -> None:
    alice = _make_user(email="alice@example.com", password="s3cret-alice")
    bob = _make_user(email="bob@example.com", password="s3cret-bob")
    word = _word()
    deck = Category.objects.create(name="talk to their parents", owner=alice)
    WordCategory.objects.create(word=word, category=deck)

    bob_headers = _login(client, bob, "s3cret-bob")
    hidden = client.post(
        reverse("sessions-create"),
        {"category_id": deck.id, "difficulties": ["novice"]},
        format="json",
        **bob_headers,
    )
    assert hidden.status_code == status.HTTP_404_NOT_FOUND
    assert hidden.json() == {"detail": "Category not found."}

    alice_client = APIClient(enforce_csrf_checks=True)
    alice_headers = _login(alice_client, alice, "s3cret-alice")
    opened = alice_client.post(
        reverse("sessions-create"),
        {"category_id": deck.id, "difficulties": ["novice"]},
        format="json",
        **alice_headers,
    )
    assert opened.status_code == status.HTTP_200_OK
    assert opened.json()["total"] == 1
