import math
import os

import requests
from django.core.management.base import BaseCommand, CommandError

from api.models import Word, WordEmbedding

MODEL_NAME = "openai/text-embedding-3-small"
DIMENSIONS = 1536
BATCH_SIZE = 100


def generate_vectors(api_key: str, texts: list[str]) -> list[list[float]]:
    response = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL_NAME,
            "input": texts,
            "encoding_format": "float",
            "dimensions": DIMENSIONS,
        },
        timeout=(10, 60),
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or len(data) != len(texts):
        raise ValueError("OpenRouter returned an unexpected number of embeddings")

    # Match by response index: providers may return entries out of order.
    vectors = {}
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("OpenRouter returned an invalid embedding entry")
        index = entry.get("index")
        vector = entry.get("embedding")
        if type(index) is not int or index not in range(len(texts)) or index in vectors:
            raise ValueError("OpenRouter returned invalid embedding indices")
        if (
            not isinstance(vector, list)
            or len(vector) != DIMENSIONS
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
        ):
            raise ValueError("OpenRouter returned an invalid embedding vector")
        vectors[index] = vector

    return [vectors[index] for index in range(len(texts))]


class Command(BaseCommand):
    help = "Embed word Chinese and English meanings through OpenRouter (skips unchanged words)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hsk-level",
            type=int,
            nargs="+",
            choices=range(1, 8),
            help="Only embed words at these HSK levels (7 means HSK 7+).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of embeddings to generate, excluding unchanged words.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit is not None and limit <= 0:
            raise CommandError("--limit must be a positive integer")

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise CommandError("OPENROUTER_API_KEY is not set")

        pending = []
        saved = skipped = 0
        words = Word.objects.select_related("embedding").defer("embedding__vector").order_by("id")
        if options["hsk_level"]:
            words = words.filter(hsk_level__in=options["hsk_level"])

        for word in words.iterator(chunk_size=BATCH_SIZE):
            source_text = f"Chinese: {word.chinese}\nMeaning: {word.english_basic}"
            embedding = getattr(word, "embedding", None)
            if (
                embedding is not None
                and embedding.model_name == MODEL_NAME
                and embedding.source_text == source_text
            ):
                skipped += 1
                continue

            pending.append((word.pk, source_text))
            if len(pending) == BATCH_SIZE:
                self.save_batch(api_key, pending)
                saved += len(pending)
                self.stdout.write(f"Saved {saved} embeddings.")
                pending = []

            if limit is not None and saved + len(pending) >= limit:
                break

        if pending:
            self.save_batch(api_key, pending)
            saved += len(pending)

        self.stdout.write(
            self.style.SUCCESS(f"Saved {saved} embeddings; skipped {skipped} unchanged.")
        )

    def save_batch(self, api_key: str, batch: list[tuple[int, str]]) -> None:
        try:
            vectors = generate_vectors(api_key, [source_text for _, source_text in batch])
        except (requests.RequestException, ValueError) as exc:
            raise CommandError(
                f"Embedding batch failed: {exc}. Completed batches are saved; rerun to resume."
            ) from exc

        WordEmbedding.objects.bulk_create(
            [
                WordEmbedding(
                    word_id=word_id,
                    model_name=MODEL_NAME,
                    source_text=source_text,
                    vector=vector,
                )
                for (word_id, source_text), vector in zip(batch, vectors, strict=True)
            ],
            update_conflicts=True,
            unique_fields=["word"],
            update_fields=["model_name", "source_text", "vector", "updated_at"],
        )
