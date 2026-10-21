from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, Max, Q, QuerySet

from api.models import Category, Learner
from api.services.difficulty import DIFFICULTY_HSK_LEVEL_MAP

HSK_CATEGORY_PREFIX = "HSK "
# Join form of WordQuerySet.active(): annotations cannot call that queryset method.
_ACTIVE_WORD = Q(words__archived_at__isnull=True)


def _active_band_count(levels) -> Count:
    return Count(
        "words",
        distinct=True,
        filter=_ACTIVE_WORD & Q(words__hsk_level__in=levels),
    )


def topic_categories_queryset(*, user: AbstractBaseUser) -> QuerySet[Category]:
    """Topic decks with difficulty-band word counts and per-user last practice."""
    bands = DIFFICULTY_HSK_LEVEL_MAP
    return (
        Category.objects.exclude(name__startswith=HSK_CATEGORY_PREFIX)
        .annotate(
            novice_count=_active_band_count(bands[Learner.ProficiencyLevel.NOVICE]),
            intermediate_count=_active_band_count(bands[Learner.ProficiencyLevel.INTERMEDIATE]),
            advanced_count=_active_band_count(bands[Learner.ProficiencyLevel.ADVANCED]),
            expert_count=_active_band_count(bands[Learner.ProficiencyLevel.EXPERT]),
            last_practiced_at=Max(
                "words__user_words__last_practiced_at",
                filter=_ACTIVE_WORD & Q(words__user_words__user=user),
            ),
        )
        .order_by("-novice_count")
    )


def list_topic_categories(*, user: AbstractBaseUser) -> list[Category]:
    """Return study topic decks, excluding seeded HSK-level category rows."""
    return list(topic_categories_queryset(user=user))
