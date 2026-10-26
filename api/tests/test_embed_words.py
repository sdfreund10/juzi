from unittest.mock import Mock

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError

from api.management.commands import embed_words
from api.models import Word, WordEmbedding

pytestmark = pytest.mark.django_db


@pytest.fixture
def words() -> list[Word]:
    return [
        Word.objects.create(chinese=chinese, pinyin=pinyin, english_basic=meaning)
        for chinese, pinyin, meaning in [
            ("字", "zì", "character"),
            ("愛", "ài", "to love"),
            ("圖書館", "túshūguǎn", "library"),
        ]
    ]


@pytest.fixture
def post(monkeypatch) -> Mock:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    post = Mock()
    monkeypatch.setattr(embed_words.requests, "post", post)
    return post


def response_for(count: int) -> Mock:
    # Reverse response order to exercise matching by index rather than position.
    return Mock(
        json=Mock(
            return_value={
                "data": [
                    {"index": index, "embedding": [float(index + 1)] * embed_words.DIMENSIONS}
                    for index in reversed(range(count))
                ]
            }
        ),
    )


def test_stores_embeddings_matched_to_words_and_skips_unchanged(words, post) -> None:
    post.return_value = response_for(3)

    call_command("embed_words")

    assert WordEmbedding.objects.count() == 3
    for index, word in enumerate(words):
        embedding = WordEmbedding.objects.get(word=word)
        assert embedding.vector == [float(index + 1)] * embed_words.DIMENSIONS
        assert embedding.model_name == "openai/text-embedding-3-small"
        assert embedding.source_text == f"Chinese: {word.chinese}\nMeaning: {word.english_basic}"
        assert embedding.updated_at is not None

    post.assert_called_once_with(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": "Bearer test-key"},
        json={
            "model": "openai/text-embedding-3-small",
            "input": [f"Chinese: {word.chinese}\nMeaning: {word.english_basic}" for word in words],
            "encoding_format": "float",
            "dimensions": 1536,
        },
        timeout=(10, 60),
    )
    original_timestamps = list(
        WordEmbedding.objects.order_by("word_id").values_list(
            "updated_at",
            flat=True,
        )
    )

    call_command("embed_words")

    assert post.call_count == 1
    assert (
        list(
            WordEmbedding.objects.order_by("word_id").values_list(
                "updated_at",
                flat=True,
            )
        )
        == original_timestamps
    )


@pytest.mark.parametrize("changed_field", ["source_text", "model_name"])
def test_replaces_stale_embedding(words, post, changed_field) -> None:
    word = words[0]
    embedding = WordEmbedding.objects.create(
        word=word,
        source_text=f"Chinese: {word.chinese}\nMeaning: {word.english_basic}",
        model_name=embed_words.MODEL_NAME,
        vector=[0.0] * embed_words.DIMENSIONS,
    )
    setattr(embedding, changed_field, "outdated")
    embedding.save()
    post.return_value = response_for(3)

    call_command("embed_words")

    embedding.refresh_from_db()
    assert WordEmbedding.objects.filter(word=word).count() == 1
    assert embedding.model_name == embed_words.MODEL_NAME
    assert embedding.source_text == f"Chinese: {word.chinese}\nMeaning: {word.english_basic}"
    assert embedding.vector == [1.0] * embed_words.DIMENSIONS


def test_resumes_after_failed_batch(words, post, monkeypatch) -> None:
    monkeypatch.setattr(embed_words, "BATCH_SIZE", 2)
    post.side_effect = [response_for(2), requests.Timeout("request timed out")]

    with pytest.raises(CommandError, match="rerun to resume"):
        call_command("embed_words")

    assert set(WordEmbedding.objects.values_list("word_id", flat=True)) == {
        word.pk for word in words[:2]
    }
    post.side_effect = None
    post.return_value = response_for(1)

    call_command("embed_words")

    assert WordEmbedding.objects.count() == 3
    assert post.call_args.kwargs["json"]["input"] == [
        f"Chinese: {words[2].chinese}\nMeaning: {words[2].english_basic}",
    ]


@pytest.mark.parametrize(
    "invalid_response",
    [
        {"error": {"message": "provider failed"}},
        {"data": []},
        {
            "data": [
                {"index": 0, "embedding": [0.0] * 1536},
                {"index": 0, "embedding": [0.0] * 1536},
                {"index": 2, "embedding": [0.0] * 1536},
            ]
        },
        {"data": [{"index": index, "embedding": [0.0, 1.0]} for index in range(3)]},
        {"data": [{"index": index, "embedding": [float("nan")] * 1536} for index in range(3)]},
    ],
)
def test_rejects_invalid_batch_without_saving(words, post, invalid_response) -> None:
    post.return_value = Mock(json=Mock(return_value=invalid_response))

    with pytest.raises(CommandError, match="Embedding batch failed"):
        call_command("embed_words")

    assert not WordEmbedding.objects.exists()


def test_http_error_preserves_existing_embedding(words, post) -> None:
    embedding = WordEmbedding.objects.create(
        word=words[0],
        model_name="old-model",
        source_text="old input",
        vector=[0.5],
    )
    post.return_value.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")

    with pytest.raises(CommandError, match="401 Unauthorized"):
        call_command("embed_words")

    embedding.refresh_from_db()
    assert embedding.model_name == "old-model"
    assert embedding.vector == [0.5]
    assert WordEmbedding.objects.count() == 1


def test_requires_api_key(post, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY")

    with pytest.raises(CommandError, match="OPENROUTER_API_KEY"):
        call_command("embed_words")

    post.assert_not_called()


@pytest.mark.parametrize("levels", [[2], [2, 7]])
def test_filters_by_hsk_levels(words, post, levels) -> None:
    for word, level in zip(words, [1, 2, 7], strict=True):
        word.hsk_level = level
        word.save()
    post.return_value = response_for(len(levels))

    call_command("embed_words", hsk_level=levels)

    assert set(WordEmbedding.objects.values_list("word_id", flat=True)) == {
        word.pk for word in words if word.hsk_level in levels
    }


@pytest.mark.parametrize("limit", [1, 2, 3, 4])
def test_limits_generated_embeddings_across_batches(words, post, monkeypatch, limit) -> None:
    monkeypatch.setattr(embed_words, "BATCH_SIZE", 2)
    count = min(limit, len(words))
    post.side_effect = [response_for(min(2, count)), response_for(1)]

    call_command("embed_words", limit=limit)

    assert set(WordEmbedding.objects.values_list("word_id", flat=True)) == {
        word.pk for word in words[:count]
    }


def test_limit_excludes_unchanged_words_and_combines_with_hsk_filter(words, post) -> None:
    for word in words:
        word.hsk_level = 2
        word.save()
    words[2].hsk_level = 3
    words[2].save()
    WordEmbedding.objects.create(
        word=words[0],
        model_name=embed_words.MODEL_NAME,
        source_text=f"Chinese: {words[0].chinese}\nMeaning: {words[0].english_basic}",
        vector=[0.5] * embed_words.DIMENSIONS,
    )
    post.return_value = response_for(1)

    call_command("embed_words", hsk_level=[2], limit=1)

    assert set(WordEmbedding.objects.values_list("word_id", flat=True)) == {
        words[0].pk,
        words[1].pk,
    }
    assert post.call_args.kwargs["json"]["input"] == [
        f"Chinese: {words[1].chinese}\nMeaning: {words[1].english_basic}",
    ]


@pytest.mark.parametrize(
    "args",
    [
        ["--limit", "0"],
        ["--limit", "-1"],
        ["--hsk-level", "0"],
        ["--hsk-level", "8"],
    ],
)
def test_rejects_invalid_filters(post, args) -> None:
    with pytest.raises(CommandError):
        call_command("embed_words", *args)

    post.assert_not_called()
