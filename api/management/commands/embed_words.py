from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.models import Word
from api.services.embeddings import (
    COMMAND_TIMEOUT,
    EmbeddingFailed,
    embed_texts,
    embedding_is_current,
    embedding_source_text,
    store_embeddings,
)

BATCH_SIZE = 100


class Command(BaseCommand):
    help = "Embed active words whose stored vector is missing or stale."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hsk-level",
            action="append",
            type=int,
            help="Limit this run to one HSK level (1–7). Repeat to include more than one.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of embeddings to generate this run. Unchanged words do not count.",
        )

    def handle(self, *args, **options):
        if not settings.OPENROUTER_API_KEY.strip():
            raise CommandError("OPENROUTER_API_KEY is not set.")

        levels: list[int] | None = options["hsk_level"]
        if levels and any(level not in range(1, 8) for level in levels):
            raise CommandError("--hsk-level must be an integer from 1 to 7.")

        limit: int | None = options["limit"]
        if limit is not None and limit < 1:
            raise CommandError("--limit must be a positive count.")

        queryset = Word.objects.active().order_by("id")
        if levels:
            queryset = queryset.filter(hsk_level__in=levels)
        queryset = queryset.select_related("embedding").defer("embedding__vector")

        pending: list[Word] = []
        skipped = 0
        for word in queryset.iterator(chunk_size=BATCH_SIZE):
            if embedding_is_current(word):
                skipped += 1
                continue
            pending.append(word)
            if limit is not None and len(pending) >= limit:
                break

        saved = 0
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start : start + BATCH_SIZE]
            try:
                vectors = embed_texts(
                    [embedding_source_text(word) for word in batch],
                    timeout=COMMAND_TIMEOUT,
                )
            except EmbeddingFailed as exc:
                raise CommandError(
                    f"{exc} Embeddings saved before this batch were kept. "
                    "Rerun embed_words to resume."
                ) from exc
            store_embeddings(batch, vectors)
            saved += len(batch)

        self.stdout.write(f"Saved {saved}. Skipped {skipped} unchanged.")
