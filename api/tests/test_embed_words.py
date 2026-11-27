from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from api.models import EMBEDDING_DIMENSIONS, Word, WordEmbedding

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


def _response(vectors: list[list[float]], *, reverse: bool = False) -> Mock:
    response = Mock()
    response.status_code = 200
    data = [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)]
    if reverse:
        data.reverse()
    response.json.return_value = {"data": data}
    return response


@pytest.mark.django_db
@KEY
def test_embed_words_stores_each_vector_on_its_word() -> None:
    first = _word(chinese="愛", pinyin="ài", english_basic="to love")
    second = _word(chinese="茶", pinyin="chá", english_basic="tea")

    with patch(
        "api.services.openrouter.requests.post",
        return_value=_response([_vector(0.25), _vector(0.75)], reverse=True),
    ):
        call_command("embed_words")

    assert list(WordEmbedding.objects.get(word=first).vector) == _vector(0.25)
    assert list(WordEmbedding.objects.get(word=second).vector) == _vector(0.75)


@pytest.mark.django_db
@KEY
def test_second_run_skips_unchanged_source_text() -> None:
    _word()
    with patch(
        "api.services.openrouter.requests.post",
        return_value=_response([_vector(0.5)]),
    ) as post:
        call_command("embed_words")
        call_command("embed_words")

    assert post.call_count == 1
    assert WordEmbedding.objects.count() == 1
