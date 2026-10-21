from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q
from django.utils import timezone

from api.models import Category, Learner, UserWord, Word
from api.services.difficulty import hsk_levels_for_difficulties


class EmptySessionError(Exception):
    """No due cards match the requested category and difficulty filters."""


@dataclass(frozen=True)
class SessionCard:
    word_id: int
    mode: str
    answer_chinese: str
    answer_pinyin: str
    answer_english: str
    example_chinese: str
    example_pinyin: str
    example_english: str
    easy_streak: int
    easy_count: int
    due_on: date | None
    last_practiced_at: datetime | None


@dataclass(frozen=True)
class StudySession:
    category: Category
    difficulties: list[str]
    cards: list[SessionCard]

    @property
    def total(self) -> int:
        return len(self.cards)


def _unlocked_modes_for_level(study_level: int) -> tuple[str, ...]:
    """Derive which study modes are available from word-level easy_count."""
    threshold: int = settings.SCHEDULING_UNLOCK_EASY_COUNT
    modes: list[str] = [UserWord.Mode.PINYIN_TO_EN]
    if study_level >= threshold:
        modes.append(UserWord.Mode.EN_TO_ZH)
    if study_level >= 2 * threshold:
        modes.append(UserWord.Mode.ZH_TO_EN)
    return tuple(modes)


def _study_level_for_proficiency(proficiency: Learner.ProficiencyLevel, hsk_level: int) -> int:
    if not proficiency:
        return 0

    threshold: int = settings.SCHEDULING_UNLOCK_EASY_COUNT
    # novices start with nothing unlocked
    if proficiency == Learner.ProficiencyLevel.NOVICE:
        return 0

    # intermediate learners get the english-to-chinese mode unlocked for early HSK levels
    if proficiency == Learner.ProficiencyLevel.INTERMEDIATE:
        if hsk_level <= 3:
            return threshold
        else:
            return 0

    # advanced learners get the character only mode unlocked for early HSK and english-to-chinese
    # for all others levels
    if proficiency == Learner.ProficiencyLevel.ADVANCED:
        if hsk_level <= 3:
            return threshold * 2
        else:
            return threshold

    # expert learners get the character only mode unlocked for all levels
    if proficiency == Learner.ProficiencyLevel.EXPERT:
        return threshold * 2


def _card_from_user_word(user_word: UserWord, proficiency: Learner.ProficiencyLevel) -> SessionCard:
    word = user_word.word
    study_level = max(
        _study_level_for_proficiency(proficiency, user_word.word.hsk_level),
        user_word.easy_count,
    )

    mode = random.choice(_unlocked_modes_for_level(study_level))
    return SessionCard(
        word_id=word.id,
        mode=mode,
        answer_chinese=word.chinese,
        answer_pinyin=word.pinyin,
        answer_english=word.english_basic,
        example_chinese=word.example_sentence_traditional,
        example_pinyin=word.example_sentence_pinyin,
        example_english=word.example_sentence_english,
        easy_streak=user_word.easy_streak,
        easy_count=user_word.easy_count,
        due_on=user_word.due_on,
        last_practiced_at=user_word.last_practiced_at,
    )


def _ensure_user_words(
    *,
    user: AbstractBaseUser,
    words: list[Word],
    as_of: date,
) -> None:
    if not words:
        return
    existing_ids = set(
        UserWord.objects.filter(
            user=user,
            word_id__in=[word.id for word in words],
        ).values_list("word_id", flat=True)
    )
    missing = [
        UserWord(user=user, word=word, due_on=as_of)
        for word in words
        if word.id not in existing_ids
    ]
    if missing:
        # Concurrent session builds can race on the same missing words; ignore
        # uniqueness conflicts so both requests still succeed.
        UserWord.objects.bulk_create(missing, ignore_conflicts=True)


def _overdue_shuffle_key(row: UserWord, *, today: date) -> float:
    """Bias older-due words toward the front while keeping order random-ish."""
    due = row.due_on if row.due_on is not None else date.min
    return -((today - due).days + random.random() * 7)


def build_session(
    *,
    user: AbstractBaseUser,
    category: Category,
    difficulties: list[str],
) -> StudySession:
    """Build a shuffled queue for due words in category × difficulty bands.

    TODO: add custom Sentry tracing around session build; this path can get
    expensive as vocabulary and user_word rows grow.
    """
    levels = hsk_levels_for_difficulties(difficulties)
    words = list(
        Word.objects.active()
        .filter(
            categories=category,
            hsk_level__in=levels,
        )
        .distinct()
    )
    if not words:
        raise EmptySessionError()

    today = timezone.localdate()
    _ensure_user_words(user=user, words=words, as_of=today)

    word_ids = [word.id for word in words]
    due_rows = list(
        UserWord.objects.filter(user=user, word_id__in=word_ids)
        .filter(Q(due_on__isnull=True) | Q(due_on__lte=today))
        .select_related("word")
    )
    if not due_rows:
        raise EmptySessionError()

    try:
        user_proficiency = user.learner.proficiency_level
    except Learner.DoesNotExist:
        user_proficiency = None
    due_rows.sort(key=lambda row: _overdue_shuffle_key(row, today=today))
    cards = [_card_from_user_word(row, user_proficiency) for row in due_rows]
    return StudySession(
        category=category,
        difficulties=list(difficulties),
        cards=cards,
    )
