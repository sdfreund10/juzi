from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q
from django.utils import timezone

from api.models import Category, UserWord, Word
from django.conf import settings

DIFFICULTY_LEVELS: dict[str, frozenset[int]] = {
    "beginner": frozenset({1, 2, 3}),
    "intermediate": frozenset({4, 5}),
    "advanced": frozenset({6, 7}),
}

KNOWN_DIFFICULTIES = frozenset(DIFFICULTY_LEVELS)


class EmptySessionError(Exception):
    """No due cards match the requested category and difficulty filters."""


@dataclass(frozen=True)
class SessionCard:
    word_id: int
    mode: str
    prompt: str
    answer_chinese: str
    answer_pinyin: str
    answer_english: str
    example_chinese: str
    example_pinyin: str
    example_english: str


@dataclass(frozen=True)
class StudySession:
    category: Category
    difficulties: list[str]
    cards: list[SessionCard]

    @property
    def total(self) -> int:
        return len(self.cards)


def hsk_levels_for_difficulties(difficulties: list[str]) -> set[int]:
    levels: set[int] = set()
    for key in difficulties:
        levels.update(DIFFICULTY_LEVELS[key])
    return levels


def _prompt_for_mode(word: Word, mode: str) -> str:
    if mode == UserWord.Mode.PINYIN_TO_EN:
        return word.pinyin
    if mode == UserWord.Mode.EN_TO_ZH:
        return word.english_basic
    return word.chinese

def _unlocked_modes_for_count(easy_count: int) -> tuple[str, ...]:
    """Derive which study modes are available from word-level easy_count."""
    threshold: int = settings.SCHEDULING_UNLOCK_EASY_COUNT
    modes: list[str] = [UserWord.Mode.PINYIN_TO_EN]
    if easy_count >= threshold:
        modes.append(UserWord.Mode.EN_TO_ZH)
    if easy_count >= 2 * threshold:
        modes.append(UserWord.Mode.ZH_TO_EN)
    return tuple(modes)

def _card_from_user_word(user_word: UserWord) -> SessionCard:
    word = user_word.word
    mode = random.choice(_unlocked_modes_for_count(user_word.easy_count))
    return SessionCard(
        word_id=word.id,
        mode=mode,
        prompt=_prompt_for_mode(word, mode), # may be unused
        answer_chinese=word.chinese,
        answer_pinyin=word.pinyin,
        answer_english=word.english_basic,
        example_chinese=word.example_sentence_traditional,
        example_pinyin=word.example_sentence_pinyin,
        example_english=word.example_sentence_english,
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
        Word.objects.filter(
            categories=category,
            hsk_level__in=levels,
        ).distinct()
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

    due_rows.sort(key=lambda row: _overdue_shuffle_key(row, today=today))
    cards = [_card_from_user_word(row) for row in due_rows]
    return StudySession(
        category=category,
        difficulties=list(difficulties),
        cards=cards,
    )
