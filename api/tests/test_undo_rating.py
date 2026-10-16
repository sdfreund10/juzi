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


def rate(client, progress, grade, rated_at):
    response = client.post(
        reverse("ratings-create"),
        {
            "word_id": progress.word_id,
            "grade": grade,
            "last_practiced_at": rated_at.isoformat(),
        },
        format="json",
    )
    assert response.status_code == 200


def undo(client, progress, rated_at, previous):
    return client.post(
        reverse("ratings-undo"),
        {
            "word_id": progress.word_id,
            "last_practiced_at": rated_at.isoformat(),
            "previous": {
                "easy_streak": previous.easy_streak,
                "easy_count": previous.easy_count,
                "due_on": previous.due_on.isoformat() if previous.due_on else None,
                "last_practiced_at": (
                    previous.last_practiced_at.isoformat() if previous.last_practiced_at else None
                ),
            },
        },
        format="json",
    )


def test_undo_restores_frontend_checkpoint(client, progress):
    previous = UserWord.objects.get(pk=progress.pk)
    rated_at = timezone.now().replace(microsecond=123000)
    rate(client, progress, "easy", rated_at)

    assert undo(client, progress, rated_at, previous).status_code == 204

    progress.refresh_from_db()
    assert progress.easy_streak == 6
    assert progress.easy_count == 12
    assert progress.due_on == timezone.localdate() - timedelta(days=2)
    assert progress.last_practiced_at == previous.last_practiced_at


def test_undo_rejects_a_rating_that_is_no_longer_latest(client, progress):
    initial = UserWord.objects.get(pk=progress.pk)
    first_rated_at = timezone.now().replace(microsecond=100000)
    second_rated_at = timezone.now().replace(microsecond=200000)
    rate(client, progress, "hard", first_rated_at)
    rate(client, progress, "easy", second_rated_at)

    assert undo(client, progress, first_rated_at, initial).status_code == 409


def test_other_user_cannot_undo_progress(client, progress):
    previous = UserWord.objects.get(pk=progress.pk)
    rated_at = timezone.now().replace(microsecond=123000)
    rate(client, progress, "easy", rated_at)
    other = get_user_model().objects.create_user(username="other@example.com")
    client.force_login(other)

    assert undo(client, progress, rated_at, previous).status_code == 404
    progress.refresh_from_db()
    assert progress.easy_count == 13


def test_undo_validates_payload(client):
    response = client.post(reverse("ratings-undo"), {}, format="json")
    assert response.status_code == 400
