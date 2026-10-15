from __future__ import annotations

from datetime import timedelta
from typing import TypedDict

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.core import signing
from django.db import transaction
from django.utils import timezone

from api.models import UserWord

GRADE_HARD = "hard"
GRADE_EASY = "easy"
KNOWN_GRADES = frozenset({GRADE_HARD, GRADE_EASY})


class UserWordNotFoundError(Exception):
    """No UserWord exists for this user and word."""


class InvalidUndoTokenError(Exception):
    """The undo token cannot restore this learner's progress."""


class ProgressSnapshot(TypedDict):
    easy_streak: int
    easy_count: int
    due_on: str | None
    last_practiced_at: str | None


UNDO_TOKEN_SALT = "api.rating-undo"


def interval_days_for_streak(streak: int) -> int:
    """Return days until next due for the given easy streak (highest matching floor)."""
    if streak < 1:
        return 0
    intervals: list[tuple[int, int]] = settings.SCHEDULING_STREAK_INTERVALS
    matched = intervals[0][1]
    for minimum, days in intervals:
        if streak >= minimum:
            matched = days
        else:
            break
    return matched


def rate_user_word(
    *,
    user: AbstractBaseUser,
    word_id: int,
    grade: str,
) -> tuple[UserWord, str]:
    """Apply hard/easy to the user's word row."""
    today = timezone.localdate()
    now = timezone.now()

    with transaction.atomic():
        try:
            row = UserWord.objects.select_for_update().get(
                user=user,
                word_id=word_id,
            )
        except UserWord.DoesNotExist as exc:
            raise UserWordNotFoundError from exc

        previous = progress_snapshot(row)

        if grade == GRADE_HARD:
            row.due_on = today
            row.easy_streak = 0
        elif grade == GRADE_EASY:
            row.easy_streak += 1
            row.easy_count += 1
            row.due_on = today + timedelta(days=interval_days_for_streak(row.easy_streak))
        else:
            raise ValueError(f"Unknown grade: {grade}")

        row.last_practiced_at = now
        row.save(
            update_fields=[
                "easy_streak",
                "easy_count",
                "due_on",
                "last_practiced_at",
            ]
        )
        return row, _undo_token(user=user, word_id=word_id, previous=previous)


def progress_snapshot(row: UserWord) -> ProgressSnapshot:
    return {
        "easy_streak": row.easy_streak,
        "easy_count": row.easy_count,
        "due_on": row.due_on.isoformat() if row.due_on else None,
        "last_practiced_at": row.last_practiced_at.isoformat() if row.last_practiced_at else None,
    }


def _undo_token(*, user: AbstractBaseUser, word_id: int, previous: ProgressSnapshot) -> str:
    return signing.dumps(
        {"user_id": user.pk, "word_id": word_id, "previous": previous},
        salt=UNDO_TOKEN_SALT,
        compress=True,
    )


def undo_rating(*, user: AbstractBaseUser, undo_token: str) -> None:
    try:
        payload = signing.loads(
            undo_token,
            salt=UNDO_TOKEN_SALT,
        )
        previous = payload["previous"]
        if payload["user_id"] != user.pk:
            raise InvalidUndoTokenError
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise InvalidUndoTokenError from exc

    with transaction.atomic():
        try:
            row = UserWord.objects.select_for_update().get(user=user, word_id=payload["word_id"])
        except UserWord.DoesNotExist as exc:
            raise InvalidUndoTokenError from exc

        row.easy_streak = previous["easy_streak"]
        row.easy_count = previous["easy_count"]
        row.due_on = previous["due_on"]
        row.last_practiced_at = previous["last_practiced_at"]
        row.save(update_fields=["easy_streak", "easy_count", "due_on", "last_practiced_at"])
