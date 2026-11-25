import math
from io import StringIO
from unittest.mock import Mock, patch

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from api.management.commands.embed_words import BATCH_SIZE
from api.models import EMBEDDING_DIMENSIONS, Category, Word, WordCategory, WordEmbedding
from api.services.embeddings import (
    COMMAND_TIMEOUT,
    EMBEDDING_MODEL,
    EMBEDDINGS_URL,
    embedding_source_text,
)
from api.services.openrouter import OPENROUTER_URL

KEY = override_settings(OPENROUTER_API_KEY="test-openrouter-key")


def _vector(fill: float) -> list[float]:
    return [fill] * EMBEDDING_DIMENSIONS


def _word(**overrides: object) -> Word:
    fields: dict[str, object] = {
        "chinese": "愛",
        "simplified": "爱",
        "pinyin": "ài",
        "english_basic": "to love",
        "hsk_level": 1,
        "example_sentence_english": "I love you.",
    }
    fields.update(overrides)
    return Word.objects.create(**fields)


def _words(count: int) -> list[Word]:
    return [
        _word(
            chinese=f"字{index}",
            pinyin=f"zi{index}",
            english_basic=f"meaning {index}",
            example_sentence_english=f"Example {index}.",
        )
        for index in range(count)
    ]


def _response(
    vectors: list[list[float]],
    *,
    reverse: bool = False,
    status_code: int = 200,
    payload: object | None = None,
) -> Mock:
    response = Mock()
    response.status_code = status_code
    if payload is not None:
        response.json.return_value = payload
        return response
    data = [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)]
    if reverse:
        data.reverse()
    response.json.return_value = {"data": data}
    return response


def _run(*args: object, **options: object) -> str:
    output = StringIO()
    call_command("embed_words", *args, stdout=output, **options)
    return output.getvalue()


@pytest.mark.django_db
def test_source_text_skips_empty_lines_and_omits_the_topic() -> None:
    word = _word(example_sentence_english="")
    food = Category.objects.create(name="Food")
    WordCategory.objects.create(word=word, category=food)

    text = embedding_source_text(word)

    assert text == "Chinese: 愛\nPinyin: ài\nMeaning: to love"
    assert "Food" not in text
    assert "Example:" not in text


@pytest.mark.django_db
@KEY
def test_embed_words_stores_each_vector_on_its_word() -> None:
    first, second = _words(2)
    captured: dict[str, object] = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _response([_vector(0.25), _vector(0.75)], reverse=True)

    with patch("api.services.embeddings.requests.post", side_effect=fake_post):
        output = _run()

    assert captured["url"] == EMBEDDINGS_URL
    assert captured["url"] != OPENROUTER_URL
    assert captured["headers"] == {"Authorization": "Bearer test-openrouter-key"}
    assert captured["timeout"] == COMMAND_TIMEOUT
    assert captured["json"] == {
        "model": EMBEDDING_MODEL,
        "input": [embedding_source_text(first), embedding_source_text(second)],
    }
    assert "Saved 2. Skipped 0 unchanged." in output

    stored_first = WordEmbedding.objects.get(word=first)
    stored_second = WordEmbedding.objects.get(word=second)
    assert stored_first.model_name == EMBEDDING_MODEL
    assert stored_first.source_text == embedding_source_text(first)
    assert list(stored_first.vector) == _vector(0.25)
    assert list(stored_second.vector) == _vector(0.75)
    assert stored_first.updated_at is not None


@pytest.mark.django_db
@KEY
def test_second_run_skips_unchanged_source_text_and_model() -> None:
    _word()
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([_vector(0.5)]),
    ) as post:
        _run()
        output = _run()

    assert post.call_count == 1
    assert "Saved 0. Skipped 1 unchanged." in output
    assert WordEmbedding.objects.count() == 1


@pytest.mark.django_db
@KEY
def test_changed_gloss_or_model_name_replaces_the_row() -> None:
    word = _word()
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([_vector(0.5)]),
    ):
        _run()
    original = WordEmbedding.objects.get(word=word)

    word.english_basic = "to adore"
    word.save(update_fields=["english_basic"])
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([_vector(1)]),
    ) as post:
        _run()

    replaced = WordEmbedding.objects.get(word=word)
    assert post.call_count == 1
    assert replaced.pk == original.pk
    assert replaced.source_text == embedding_source_text(word)
    assert "Meaning: to adore" in replaced.source_text
    assert list(replaced.vector) == _vector(1)

    replaced.model_name = "other/model"
    replaced.save(update_fields=["model_name"])
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([_vector(0.5)]),
    ) as post:
        _run()

    replaced.refresh_from_db()
    assert post.call_count == 1
    assert replaced.model_name == EMBEDDING_MODEL
    assert WordEmbedding.objects.count() == 1


@pytest.mark.django_db
@KEY
def test_failed_second_batch_keeps_the_first_and_rerun_sends_the_rest() -> None:
    words = _words(3)
    calls: list[list[str]] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        texts = json["input"]
        calls.append(texts)
        if len(calls) == 1:
            return _response([_vector(0.25), _vector(0.5)])
        raise requests.Timeout()

    with (
        patch("api.management.commands.embed_words.BATCH_SIZE", 2),
        patch("api.services.embeddings.requests.post", side_effect=fake_post),
    ):
        with pytest.raises(CommandError, match=r"timed out.*Rerun embed_words to resume"):
            _run()

    assert list(WordEmbedding.objects.order_by("word_id").values_list("word_id", flat=True)) == [
        words[0].pk,
        words[1].pk,
    ]
    assert not WordEmbedding.objects.filter(word=words[2]).exists()

    def resume_post(url, headers=None, json=None, timeout=None):
        calls.append(json["input"])
        return _response([_vector(0.75)])

    with (
        patch("api.management.commands.embed_words.BATCH_SIZE", 2),
        patch("api.services.embeddings.requests.post", side_effect=resume_post),
    ):
        _run()

    assert calls[0] == [embedding_source_text(words[0]), embedding_source_text(words[1])]
    assert calls[-1] == [embedding_source_text(words[2])]
    assert list(WordEmbedding.objects.get(word=words[0]).vector) == _vector(0.25)
    assert list(WordEmbedding.objects.get(word=words[2]).vector) == _vector(0.75)


@pytest.mark.django_db
@KEY
@pytest.mark.parametrize(
    ("word_count", "payload"),
    [
        (1, {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}),
        (1, {"data": [{"index": 0, "embedding": [math.nan] * EMBEDDING_DIMENSIONS}]}),
        (1, {"data": [{"index": 0, "embedding": [math.inf] * EMBEDDING_DIMENSIONS}]}),
        (
            2,
            {
                "data": [
                    {"index": 0, "embedding": _vector(0.25)},
                    {"index": 0, "embedding": _vector(0.5)},
                ]
            },
        ),
        (2, {"data": [{"index": 0, "embedding": _vector(0.25)}]}),
    ],
)
def test_rejected_batch_saves_nothing(word_count: int, payload: dict[str, object]) -> None:
    _words(word_count)
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([], payload=payload),
    ):
        with pytest.raises(CommandError, match="invalid"):
            _run()

    assert WordEmbedding.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_provider_error_saves_nothing_and_names_the_failure() -> None:
    _word()
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([], status_code=503, payload={"error": "down"}),
    ):
        with pytest.raises(CommandError, match=r"provider returned an error.*Rerun embed_words"):
            _run()

    assert WordEmbedding.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_archived_words_are_skipped_and_keep_an_existing_vector() -> None:
    archived = _word(chinese="舊", pinyin="jiù", english_basic="old", archived_at=timezone.now())
    previous = _vector(0.25)
    WordEmbedding.objects.create(
        word=archived,
        model_name=EMBEDDING_MODEL,
        source_text="Chinese: stale",
        vector=previous,
    )
    active = _word(chinese="新", pinyin="xīn", english_basic="new")

    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([_vector(0.75)]),
    ) as post:
        _run()

    assert post.call_count == 1
    sent = post.call_args.kwargs["json"]["input"]
    assert sent == [embedding_source_text(active)]
    assert list(WordEmbedding.objects.get(word=archived).vector) == previous
    assert WordEmbedding.objects.get(word=active).source_text == embedding_source_text(active)


@pytest.mark.django_db
@KEY
def test_hsk_level_and_limit_restrict_what_this_run_embeds() -> None:
    level_one = _word(chinese="一", pinyin="yī", english_basic="one", hsk_level=1)
    level_two = _word(chinese="二", pinyin="èr", english_basic="two", hsk_level=2)
    level_seven = _word(chinese="七", pinyin="qī", english_basic="seven", hsk_level=7)
    current = embedding_source_text(level_one)
    WordEmbedding.objects.create(
        word=level_one,
        model_name=EMBEDDING_MODEL,
        source_text=current,
        vector=_vector(0.25),
    )

    with patch(
        "api.services.embeddings.requests.post",
        return_value=_response([_vector(0.5)]),
    ) as post:
        output = _run(hsk_level=[1, 7], limit=1)

    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["input"] == [embedding_source_text(level_seven)]
    assert "Saved 1. Skipped 1 unchanged." in output
    assert not WordEmbedding.objects.filter(word=level_two).exists()
    assert WordEmbedding.objects.filter(word=level_seven).exists()
    assert list(WordEmbedding.objects.get(word=level_one).vector) == _vector(0.25)


@pytest.mark.django_db
@KEY
@pytest.mark.parametrize("level", [0, 8])
def test_invalid_hsk_level_does_not_call_the_provider(level: int) -> None:
    _word()
    with patch("api.services.embeddings.requests.post") as post:
        with pytest.raises(CommandError, match="--hsk-level"):
            _run(hsk_level=[level])
    post.assert_not_called()
    assert WordEmbedding.objects.count() == 0


@pytest.mark.django_db
@KEY
@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_limit_does_not_call_the_provider(limit: int) -> None:
    _word()
    with patch("api.services.embeddings.requests.post") as post:
        with pytest.raises(CommandError, match="--limit"):
            _run(limit=limit)
    post.assert_not_called()
    assert WordEmbedding.objects.count() == 0


@pytest.mark.django_db
@override_settings(OPENROUTER_API_KEY="")
def test_missing_key_does_not_call_the_provider_or_write() -> None:
    _word()
    with patch("api.services.embeddings.requests.post") as post:
        with pytest.raises(CommandError, match="OPENROUTER_API_KEY is not set"):
            _run()
    post.assert_not_called()
    assert WordEmbedding.objects.count() == 0


@pytest.mark.django_db
def test_deleting_a_word_deletes_its_embedding() -> None:
    word = _word()
    WordEmbedding.objects.create(
        word=word,
        model_name=EMBEDDING_MODEL,
        source_text=embedding_source_text(word),
        vector=_vector(0.5),
    )

    word.delete()

    assert WordEmbedding.objects.count() == 0


def test_batches_are_100() -> None:
    assert BATCH_SIZE == 100
