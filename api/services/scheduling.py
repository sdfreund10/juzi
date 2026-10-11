from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class RatedUserWord:
    user_word: UserWord
    unlocked_modes: tuple[str, ...]
    newly_unlocked_modes: tuple[str, ...]


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


def unlocked_modes_for_count(easy_count: int) -> tuple[str, ...]:
    """Derive which study modes are available from word-level easy_count."""
    threshold: int = settings.SCHEDULING_UNLOCK_EASY_COUNT
    modes: list[str] = [UserWord.Mode.PINYIN_TO_EN]
    if easy_count >= threshold:
        modes.append(UserWord.Mode.EN_TO_ZH)
    if easy_count >= 2 * threshold:
        modes.append(UserWord.Mode.ZH_TO_EN)
    return tuple(modes)


def unlocked_modes_for_row(user_word: UserWord) -> tuple[str, ...]:
    return unlocked_modes_for_count(user_word.easy_count)


def rate_user_word(
    *,
    user: AbstractBaseUser,
    word_id: int,
    grade: str,
) -> RatedUserWord:
    """Apply hard/easy to the user's word row and return updated progress."""
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

        before_modes = unlocked_modes_for_row(row)

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

        after_modes = unlocked_modes_for_row(row)
        newly = tuple(mode for mode in after_modes if mode not in before_modes)
        return RatedUserWord(
            user_word=row,
            unlocked_modes=after_modes,
            newly_unlocked_modes=newly,
        )
