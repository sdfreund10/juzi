"""Catalog embeddings via OpenRouter.

The chat-completions client in ``openrouter.py`` is a different endpoint.
"""

from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from api.models import EMBEDDING_DIMENSIONS, Word, WordEmbedding

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
COMMAND_TIMEOUT = (10, 60)
ADMIN_TIMEOUT = (5, 20)

_SOURCE_LINES = (
    ("Chinese", "chinese"),
    ("Pinyin", "pinyin"),
    ("Meaning", "english_basic"),
    ("Example", "example_sentence_english"),
)


class EmbeddingFailed(Exception):
    """The provider did not return a usable vector."""


class EmbeddingItemSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0)
    embedding = serializers.ListField(
        child=serializers.FloatField(),
        min_length=EMBEDDING_DIMENSIONS,
        max_length=EMBEDDING_DIMENSIONS,
    )


class EmbeddingResponseSerializer(serializers.Serializer):
    data = EmbeddingItemSerializer(many=True)


def embedding_source_text(word: Word) -> str:
    """Text that was, or should be, embedded for this word.

    Empty fields are left out. Category names are not included, so renaming a
    topic does not change the string.
    """
    lines = []
    for label, field_name in _SOURCE_LINES:
        value = getattr(word, field_name)
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def embedding_is_current(word: Word) -> bool:
    try:
        embedding = word.embedding
    except WordEmbedding.DoesNotExist:
        return False
    return (
        embedding.model_name == EMBEDDING_MODEL
        and embedding.source_text == embedding_source_text(word)
    )


def embed_texts(texts: list[str], *, timeout: tuple[float, float]) -> list[list[float]]:
    """Return one 1536-float vector per text, in input order."""
    api_key = settings.OPENROUTER_API_KEY.strip()
    if not api_key:
        raise EmbeddingFailed("OPENROUTER_API_KEY is not set.")

    try:
        response = requests.post(
            EMBEDDINGS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": EMBEDDING_MODEL, "input": texts},
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise EmbeddingFailed("The embedding request timed out.") from exc
    except requests.RequestException as exc:
        raise EmbeddingFailed("The embedding provider returned an error.") from exc

    if response.status_code != 200:
        raise EmbeddingFailed("The embedding provider returned an error.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise EmbeddingFailed("The embedding response was invalid.") from exc

    return _vectors_for_inputs(payload, len(texts))


def store_embeddings(words: list[Word], vectors: list[list[float]]) -> None:
    """Insert or replace the single embedding row for each word."""
    if len(words) != len(vectors):
        raise ValueError("Each word needs one vector.")
    updated_at = timezone.now()
    rows = [
        WordEmbedding(
            word=word,
            model_name=EMBEDDING_MODEL,
            source_text=embedding_source_text(word),
            vector=vector,
            updated_at=updated_at,
        )
        for word, vector in zip(words, vectors, strict=True)
    ]
    WordEmbedding.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["word"],
        update_fields=["model_name", "source_text", "vector", "updated_at"],
    )


def refresh_word_embedding(word: Word) -> None:
    """Embed one active word when its stored source text is missing or stale.

    Archived words are left untouched. Raises EmbeddingFailed when the provider
    call does not produce a vector; the caller keeps the word save.
    """
    if word.archived_at is not None or embedding_is_current(word):
        return
    vector = embed_texts([embedding_source_text(word)], timeout=ADMIN_TIMEOUT)[0]
    store_embeddings([word], [vector])


def _vectors_for_inputs(payload: Any, count: int) -> list[list[float]]:
    serializer = EmbeddingResponseSerializer(data=payload)
    if not serializer.is_valid():
        raise EmbeddingFailed("The embedding response was invalid.")

    items = serializer.validated_data["data"]
    if len(items) != count:
        raise EmbeddingFailed("The embedding response was invalid.")
    by_index = {item["index"]: item["embedding"] for item in items}
    try:
        return [by_index[index] for index in range(count)]
    except KeyError as exc:
        raise EmbeddingFailed("The embedding response was invalid.") from exc
