from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from api.models import Category, UserWord, Word

DIFFICULTY_LEVELS: dict[str, frozenset[int]] = {
    "beginner": frozenset({1, 2, 3}),
    "intermediate": frozenset({4, 5}),
    "advanced": frozenset({6, 7}),
}

KNOWN_DIFFICULTIES = frozenset(DIFFICULTY_LEVELS)
SESSION_MODE = UserWord.Mode.PINYIN_TO_EN


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


def _card_for_word(word: Word) -> SessionCard:
    return SessionCard(
        word_id=word.id,
        mode=SESSION_MODE,
        prompt=word.pinyin,
        answer_chinese=word.chinese,
        answer_pinyin=word.pinyin,
        answer_english=word.english_basic,
    )


def build_session(
    *,
    user: AbstractBaseUser,
    category: Category,
    difficulties: list[str],
    today: date | None = None,
) -> StudySession:
    """Build a shuffled pinyin→en queue for due words in category × difficulty bands."""
    levels = hsk_levels_for_difficulties(difficulties)
    words = list(
        Word.objects.filter(
            categories=category,
            hsk_level__in=levels,
        ).distinct()
    )
    if not words:
        raise EmptySessionError()

    word_ids = [word.id for word in words]
    as_of = today if today is not None else timezone.localdate()
    # Only rows with a future due date are not due; missing / null / today-or-past count as due.
    not_due_ids = set(
        UserWord.objects.filter(
            user=user,
            mode=SESSION_MODE,
            word_id__in=word_ids,
            due_on__gt=as_of,
        ).values_list("word_id", flat=True)
    )
    due_words = [word for word in words if word.id not in not_due_ids]
    if not due_words:
        raise EmptySessionError()

    cards = [_card_for_word(word) for word in due_words]
    random.shuffle(cards)
    return StudySession(
        category=category,
        difficulties=list(difficulties),
        cards=cards,
    )
