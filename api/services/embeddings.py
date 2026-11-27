"""Catalog embeddings via OpenRouter."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from api.models import Word, WordEmbedding
from api.services.openrouter import (
    OpenRouterError,
    OpenRouterKeyMissing,
    OpenRouterResponseInvalid,
    OpenRouterTimeout,
    post_json,
)

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
    """Return one vector per text, in input order."""
    try:
        payload = post_json(
            EMBEDDINGS_URL,
            {"model": EMBEDDING_MODEL, "input": texts},
            timeout=timeout,
        )
    except OpenRouterError as exc:
        raise _embedding_failed(exc) from exc
    return _vectors_for_inputs(payload, len(texts))


def _embedding_failed(exc: OpenRouterError) -> EmbeddingFailed:
    if isinstance(exc, OpenRouterKeyMissing):
        message = "OPENROUTER_API_KEY is not set."
    elif isinstance(exc, OpenRouterTimeout):
        message = "The embedding request timed out."
    elif isinstance(exc, OpenRouterResponseInvalid):
        message = "The embedding response was invalid."
    else:
        message = "The embedding provider returned an error."
    return EmbeddingFailed(message)


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
    """Pair each input with the vector OpenAI returned for that index.

    The vector itself is stored as sent. A missing index is a broken response,
    because the batch could not be matched back to the words.
    """
    try:
        by_index = {item["index"]: item["embedding"] for item in payload["data"]}
        return [by_index[index] for index in range(count)]
    except (KeyError, TypeError) as exc:
        raise EmbeddingFailed("The embedding response was invalid.") from exc
