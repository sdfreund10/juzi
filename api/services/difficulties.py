from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser

from api.models import Learner, UserWord

DIFFICULTY_LEVELS: dict[str, frozenset[int]] = {
    "beginner": frozenset({1, 2, 3}),
    "intermediate": frozenset({4, 5}),
    "advanced": frozenset({6, 7}),
}

DIFFICULTY_HSK_MAP = {
    Learner.Proficiency.BEGINNER: frozenset({1, 2, 3}),
    Learner.Proficiency.INTERMEDIATE: frozenset({4, 5}),
    Learner.Proficiency.ADVANCED: frozenset({6, 7}),
    Learner.Proficiency.EXPERT: frozenset({8, 9, 10}),
}

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
