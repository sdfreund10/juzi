from io import StringIO
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from api.models import EMBEDDING_DIMENSIONS, Word, WordEmbedding
from api.services.embeddings import EMBEDDING_MODEL, embedding_source_text

KEY = override_settings(OPENROUTER_API_KEY="test-openrouter-key")


def _vector(*pairs: tuple[int, float]) -> list[float]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    for index, value in pairs:
        values[index] = value
    return values


def _word(**overrides: object) -> Word:
    fields: dict[str, object] = {
        "chinese": "愛",
        "pinyin": "ài",
        "english_basic": "to love",
        "hsk_level": 1,
    }
    fields.update(overrides)
    return Word.objects.create(**fields)


def _store(word: Word, vector: list[float], *, source_text: str | None = None) -> None:
    WordEmbedding.objects.create(
        word=word,
        model_name=EMBEDDING_MODEL,
        source_text=source_text if source_text is not None else embedding_source_text(word),
        vector=vector,
    )


def _embedding_response(vector: list[float]) -> Mock:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{"index": 0, "embedding": vector}]}
    return response


@pytest.mark.django_db
@KEY
def test_search_words_ranks_by_cosine_and_skips_unusable_rows() -> None:
    query = _vector((0, 1.0))
    father = _word(chinese="父親", pinyin="fùqīn", english_basic="father")
    uncle = _word(chinese="叔叔", pinyin="shūshu", english_basic="uncle")
    archived = _word(chinese="爸爸", pinyin="bàba", english_basic="dad", archived_at=timezone.now())
    stale = _word(chinese="岳父", pinyin="yuèfù", english_basic="father-in-law")
    _store(father, _vector((0, 1.0)))
    _store(uncle, _vector((0, 10.0), (1, 10.0)))
    _store(archived, _vector((0, 1.0)))
    _store(stale, _vector((0, 1.0)), source_text="Chinese: stale")

    output = StringIO()
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_embedding_response(query),
    ):
        call_command("search_words", "father", limit=5, stdout=output)

    lines = output.getvalue().splitlines()
    assert lines == [
        "1.000\t父親\tfùqīn\tfather",
        "0.707\t叔叔\tshūshu\tuncle",
    ]
