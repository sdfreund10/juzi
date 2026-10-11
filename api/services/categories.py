from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from api.models import Category
from api.services.sessions import DIFFICULTY_LEVELS

HSK_CATEGORY_PREFIX = "HSK "


def topic_categories_queryset() -> QuerySet[Category]:
    """Topic decks with difficulty-band word counts annotated from DIFFICULTY_LEVELS."""
    return (
        Category.objects.exclude(name__startswith=HSK_CATEGORY_PREFIX)
        .annotate(
            beginner_count=Count(
                "words",
                distinct=True,
                filter=Q(words__hsk_level__in=DIFFICULTY_LEVELS["beginner"]),
            ),
            intermediate_count=Count(
                "words",
                distinct=True,
                filter=Q(words__hsk_level__in=DIFFICULTY_LEVELS["intermediate"]),
            ),
            advanced_count=Count(
                "words",
                distinct=True,
                filter=Q(words__hsk_level__in=DIFFICULTY_LEVELS["advanced"]),
            ),
        )
        .order_by("-beginner_count")
    )


def list_topic_categories() -> list[Category]:
    """Return study topic decks, excluding seeded HSK-level category rows."""
    return list(topic_categories_queryset())
