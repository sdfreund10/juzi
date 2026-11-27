from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, FilteredRelation, Max, Q, QuerySet

from api.models import Category, Learner
from api.services.difficulty import DIFFICULTY_HSK_LEVEL_MAP

HSK_CATEGORY_PREFIX = "HSK "


def topic_categories_queryset(*, user: AbstractBaseUser) -> QuerySet[Category]:
    """Operator topic decks plus this learner's decks, with band counts.

    Owner-null names that start with ``HSK `` stay hidden. A learner deck
    keeps that prefix and still shows for its owner.
    """
    visible = Q(owner=user) | Q(owner__isnull=True)
    hidden_hsk = Q(owner__isnull=True) & Q(name__startswith=HSK_CATEGORY_PREFIX)
    return (
        Category.objects.filter(visible)
        .exclude(hidden_hsk)
        .annotate(
            active_words=FilteredRelation("words", condition=Q(words__archived_at__isnull=True)),
            user_progress=FilteredRelation(
                "active_words__user_words",
                condition=Q(active_words__user_words__user=user),
            ),
        )
        .annotate(
            novice_count=Count(
                "active_words",
                filter=Q(
                    active_words__hsk_level__in=DIFFICULTY_HSK_LEVEL_MAP[
                        Learner.ProficiencyLevel.NOVICE
                    ]
                ),
            ),
            intermediate_count=Count(
                "active_words",
                filter=Q(
                    active_words__hsk_level__in=DIFFICULTY_HSK_LEVEL_MAP[
                        Learner.ProficiencyLevel.INTERMEDIATE
                    ]
                ),
            ),
            advanced_count=Count(
                "active_words",
                filter=Q(
                    active_words__hsk_level__in=DIFFICULTY_HSK_LEVEL_MAP[
                        Learner.ProficiencyLevel.ADVANCED
                    ]
                ),
            ),
            expert_count=Count(
                "active_words",
                filter=Q(
                    active_words__hsk_level__in=DIFFICULTY_HSK_LEVEL_MAP[
                        Learner.ProficiencyLevel.EXPERT
                    ]
                ),
            ),
            last_practiced_at=Max("user_progress__last_practiced_at"),
        )
        .order_by("-novice_count")
    )


def list_topic_categories(*, user: AbstractBaseUser) -> list[Category]:
    """Return operator topic decks and decks owned by this user."""
    return list(topic_categories_queryset(user=user))
