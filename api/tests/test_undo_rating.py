from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import UserWord, Word

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="undo@example.com", password="test")


@pytest.fixture
def client(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def progress(user):
    word = Word.objects.create(chinese="字", pinyin="zì", english_basic="character")
    return UserWord.objects.create(
        user=user,
        word=word,
        easy_streak=6,
        easy_count=12,
        due_on=timezone.localdate() - timedelta(days=2),
        last_practiced_at=timezone.now() - timedelta(days=7),
    )


def rate(client, progress, grade="easy"):
    response = client.post(
        reverse("ratings-create"),
        {"word_id": progress.word_id, "grade": grade},
        format="json",
    )
    assert response.status_code == 200
    return response.json()["undo_token"]


def undo(client, undo_token):
    return client.post(reverse("ratings-undo"), {"undo_token": undo_token}, format="json")


@pytest.mark.parametrize("grade", ["easy", "hard"])
def test_undo_restores_exact_progress_from_response_token(client, progress, grade):
    previous = (
        progress.easy_streak,
        progress.easy_count,
        progress.due_on,
        progress.last_practiced_at,
    )
    undo_token = rate(client, progress, grade)

    assert undo(client, undo_token).status_code == 204

    progress.refresh_from_db()
    assert (
        progress.easy_streak,
        progress.easy_count,
        progress.due_on,
        progress.last_practiced_at,
    ) == previous


def test_each_rating_returns_its_own_undo_token(client, progress):
    first_token = rate(client, progress, "hard")
    second_token = rate(client, progress)

    assert first_token != second_token
    assert undo(client, second_token).status_code == 204
    progress.refresh_from_db()
    assert progress.easy_streak == 0
    assert progress.easy_count == 12


def test_other_user_cannot_use_undo_token(client, progress):
    undo_token = rate(client, progress)
    other = get_user_model().objects.create_user(username="other@example.com")
    client.force_login(other)

    response = undo(client, undo_token)
    assert response.status_code == 400
    progress.refresh_from_db()
    assert progress.easy_count == 13


def test_undo_rejects_modified_token(client, progress):
    undo_token = rate(client, progress)

    assert undo(client, f"{undo_token}x").status_code == 400


def test_undo_requires_authentication():
    assert undo(APIClient(), "not-a-token").status_code == 401


def test_undo_requires_csrf(user, progress, client):
    undo_token = rate(client, progress)
    protected_client = APIClient(enforce_csrf_checks=True)
    protected_client.force_login(user)

    assert undo(protected_client, undo_token).status_code == 403


@pytest.mark.parametrize("body", [{}, {"undo_token": None}])
def test_undo_validates_token(client, body):
    response = client.post(reverse("ratings-undo"), body, format="json")
    assert response.status_code == 400
