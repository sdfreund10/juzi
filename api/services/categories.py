from __future__ import annotations

from django.db.models import Count, Q

from api.models import Category

HSK_CATEGORY_PREFIX = "HSK "


def list_topic_categories() -> list[Category]:
    """Return study topic decks, excluding seeded HSK-level category rows."""
    return list(
        Category.objects.exclude(name__startswith=HSK_CATEGORY_PREFIX)
        .annotate(
            beginner_count=Count("words", distinct=True, filter=Q(words__hsk_level__in=(1, 2, 3))),
            intermediate_count=Count("words", distinct=True, filter=Q(words__hsk_level__in=(4, 5))),
            advanced_count=Count("words", distinct=True, filter=Q(words__hsk_level__gte=6)),
        )
        .order_by("-beginner_count")
    )
