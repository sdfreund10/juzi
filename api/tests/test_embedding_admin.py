from unittest.mock import Mock, patch

import pytest
import requests
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse

from api.models import EMBEDDING_DIMENSIONS, Word, WordEmbedding
from api.services.embeddings import EMBEDDING_MODEL, embedding_source_text

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


def _form(word: Word, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "chinese": word.chinese,
        "simplified": word.simplified,
        "pinyin": word.pinyin,
        "english_basic": word.english_basic,
        "hsk_level": word.hsk_level,
        "example_sentence_traditional": word.example_sentence_traditional,
        "example_sentence_simplified": word.example_sentence_simplified,
        "example_sentence_pinyin": word.example_sentence_pinyin,
        "example_sentence_english": word.example_sentence_english,
    }
    data.update(overrides)
    return data


def _client() -> Client:
    client = Client()
    client.force_login(
        User.objects.create_superuser("admin@test.com", "admin@test.com", "local-test-password")
    )
    return client


def _embedding_response(fill: float = 0.75) -> Mock:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{"index": 0, "embedding": _vector(fill)}]}
    return response


@pytest.mark.django_db
@KEY
def test_saving_a_source_field_refreshes_that_word() -> None:
    word = _word()
    WordEmbedding.objects.create(
        word=word,
        model_name=EMBEDDING_MODEL,
        source_text=embedding_source_text(word),
        vector=_vector(0.25),
    )
    client = _client()

    with patch(
        "api.services.openrouter.requests.post",
        return_value=_embedding_response(),
    ) as post:
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word, english_basic="to adore"), "_save": "Save"},
        )

    assert response.status_code == 302
    assert post.call_count == 1
    stored = WordEmbedding.objects.get(word=word)
    assert list(stored.vector) == _vector(0.75)
    assert "Meaning: to adore" in stored.source_text


@pytest.mark.django_db
@KEY
def test_unrelated_field_and_archive_do_not_call_the_provider() -> None:
    word = _word()
    WordEmbedding.objects.create(
        word=word,
        model_name=EMBEDDING_MODEL,
        source_text=embedding_source_text(word),
        vector=_vector(0.25),
    )
    client = _client()
    change_url = reverse("admin:api_word_change", args=[word.pk])

    with patch("api.services.openrouter.requests.post") as post:
        simplified = client.post(change_url, {**_form(word, simplified="爱心"), "_save": "Save"})
        word.refresh_from_db()
        archived = client.post(
            change_url,
            {**_form(word, english_basic="to adore"), "_save_and_archive": "Save and archive"},
        )

    assert simplified.status_code == 302
    assert archived.status_code == 302
    post.assert_not_called()
    word.refresh_from_db()
    assert word.simplified == "爱心"
    assert word.archived_at is not None
    assert word.english_basic == "to adore"
    assert list(WordEmbedding.objects.get(word=word).vector) == _vector(0.25)


@pytest.mark.django_db
@KEY
def test_failed_embed_keeps_the_saved_word_and_the_old_vector() -> None:
    word = _word()
    original = embedding_source_text(word)
    WordEmbedding.objects.create(
        word=word,
        model_name=EMBEDDING_MODEL,
        source_text=original,
        vector=_vector(0.25),
    )
    client = _client()

    with patch("api.services.openrouter.requests.post", side_effect=requests.Timeout):
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word, english_basic="to adore"), "_save": "Save"},
        )

    assert response.status_code == 302
    word.refresh_from_db()
    assert word.english_basic == "to adore"
    stored = WordEmbedding.objects.get(word=word)
    assert stored.source_text == original
    assert list(stored.vector) == _vector(0.25)
