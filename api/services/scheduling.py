from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from api.models import UserWord

GRADE_HARD = "hard"
GRADE_EASY = "easy"
KNOWN_GRADES = frozenset({GRADE_HARD, GRADE_EASY})


class UserWordNotFoundError(Exception):
    """No UserWord exists for this user and word."""


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
):
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
        return row
