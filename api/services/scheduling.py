from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from api.models import Learner, UserWord

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


def study_level_for(user: AbstractBaseUser) -> str | None:
    try:
        return user.learner.study_level
    except Learner.DoesNotExist:
        return None


def easy_count_floor(study_level: str | None, hsk_level: int) -> int:
    """Minimum easy_count implied by the learner's study level for this HSK band."""
    if study_level is None or study_level == Learner.StudyLevel.NOVICE:
        return 0

    # Imported here to avoid a circular import with sessions.
    from api.services.sessions import DIFFICULTY_LEVELS

    threshold: int = settings.SCHEDULING_UNLOCK_EASY_COUNT
    early = hsk_level in DIFFICULTY_LEVELS["beginner"]

    if study_level == Learner.StudyLevel.INTERMEDIATE:
        return threshold if early else 0
    if study_level == Learner.StudyLevel.ADVANCED:
        return 2 * threshold if early else threshold
    if study_level == Learner.StudyLevel.SUPERIOR:
        return 2 * threshold
    return 0


def unlocked_modes_for_row(user_word: UserWord) -> tuple[str, ...]:
    floor = easy_count_floor(
        study_level_for(user_word.user),
        user_word.word.hsk_level,
    )
    return unlocked_modes_for_count(max(user_word.easy_count, floor))


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
            row = (
                UserWord.objects.select_for_update(of=("self",))
                .select_related("word", "user__learner")
                .get(
                    user=user,
                    word_id=word_id,
                )
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
