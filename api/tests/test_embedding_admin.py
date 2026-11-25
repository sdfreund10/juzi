from unittest.mock import Mock, patch

import pytest
import requests
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import EMBEDDING_DIMENSIONS, Category, Word, WordCategory, WordEmbedding
from api.services.embeddings import ADMIN_TIMEOUT, EMBEDDING_MODEL, embedding_source_text

KEY = override_settings(OPENROUTER_API_KEY="test-openrouter-key")


def _vector(fill: float) -> list[float]:
    return [fill] * EMBEDDING_DIMENSIONS


def _superuser() -> User:
    return User.objects.create_superuser(
        "admin@test.com",
        "admin@test.com",
        "local-test-password",
    )


def _word(**overrides: object) -> Word:
    fields: dict[str, object] = {
        "chinese": "愛",
        "simplified": "爱",
        "pinyin": "ài",
        "english_basic": "to love",
        "hsk_level": 1,
        "example_sentence_traditional": "我愛你。",
        "example_sentence_simplified": "我爱你。",
        "example_sentence_pinyin": "Wǒ ài nǐ.",
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


def _current(word: Word, fill: float = 0.25) -> WordEmbedding:
    return WordEmbedding.objects.create(
        word=word,
        model_name=EMBEDDING_MODEL,
        source_text=embedding_source_text(word),
        vector=_vector(fill),
    )


def _client() -> Client:
    client = Client()
    client.force_login(_superuser())
    return client


def _embedding_response(fill: float = 0.75) -> Mock:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{"index": 0, "embedding": _vector(fill)}]}
    return response


@pytest.mark.django_db
@KEY
def test_adding_a_word_embeds_it_once() -> None:
    client = _client()
    with patch(
        "api.services.embeddings.requests.post",
        return_value=_embedding_response(),
    ) as post:
        response = client.post(
            reverse("admin:api_word_add"),
            {
                "chinese": "水",
                "simplified": "水",
                "pinyin": "shuǐ",
                "english_basic": "water",
                "hsk_level": 1,
                "example_sentence_traditional": "",
                "example_sentence_simplified": "",
                "example_sentence_pinyin": "",
                "example_sentence_english": "A glass of water.",
                "_save": "Save",
            },
        )

    assert response.status_code == 302
    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == ADMIN_TIMEOUT
    word = Word.objects.get(chinese="水")
    stored = WordEmbedding.objects.get(word=word)
    assert post.call_args.kwargs["json"]["input"] == [stored.source_text]
    assert stored.model_name == EMBEDDING_MODEL
    assert stored.source_text == (
        "Chinese: 水\nPinyin: shuǐ\nMeaning: water\nExample: A glass of water."
    )
    assert list(stored.vector) == _vector(0.75)


@pytest.mark.django_db
@KEY
@pytest.mark.parametrize(
    ("field", "value", "line"),
    [
        ("chinese", "愛心", "Chinese: 愛心"),
        ("pinyin", "ài xīn", "Pinyin: ài xīn"),
        ("english_basic", "love", "Meaning: love"),
        ("example_sentence_english", "She loves tea.", "Example: She loves tea."),
    ],
)
def test_saving_a_source_field_embeds_once(field: str, value: str, line: str) -> None:
    word = _word()
    _current(word)
    client = _client()

    with patch(
        "api.services.embeddings.requests.post",
        return_value=_embedding_response(),
    ) as post:
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word, **{field: value}), "_save": "Save"},
        )

    assert response.status_code == 302
    assert post.call_count == 1
    stored = WordEmbedding.objects.get(word=word)
    assert line in stored.source_text
    assert list(stored.vector) == _vector(0.75)
    assert WordEmbedding.objects.count() == 1


@pytest.mark.django_db
@KEY
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("simplified", "爱心"),
        ("hsk_level", 4),
        ("example_sentence_traditional", "我愛茶。"),
        ("example_sentence_simplified", "我爱茶。"),
        ("example_sentence_pinyin", "Wǒ ài chá."),
    ],
)
def test_saving_a_field_outside_the_source_text_does_not_embed(field: str, value: object) -> None:
    word = _word()
    _current(word)
    client = _client()

    with patch("api.services.embeddings.requests.post") as post:
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word, **{field: value}), "_save": "Save"},
        )

    assert response.status_code == 302
    post.assert_not_called()
    word.refresh_from_db()
    assert getattr(word, field) == value
    assert list(WordEmbedding.objects.get(word=word).vector) == _vector(0.25)


@pytest.mark.django_db
@KEY
def test_unflag_does_not_embed() -> None:
    reporter = User.objects.create_user(
        "reporter@test.com", "reporter@test.com", "local-test-password"
    )
    word = _word(flagged_by=reporter, flag_reason=Word.FlagReason.BAD_TRANSLATION)
    _current(word)
    client = _client()

    with patch("api.services.embeddings.requests.post") as post:
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word), "_save_and_unflag": "Save and unflag"},
        )

    assert response.status_code == 302
    post.assert_not_called()
    word.refresh_from_db()
    assert word.flagged_by_id is None
    assert word.flag_reason == ""


@pytest.mark.django_db
@KEY
def test_save_and_archive_does_not_embed_even_when_the_gloss_changes() -> None:
    word = _word()
    _current(word)
    client = _client()

    with patch("api.services.embeddings.requests.post") as post:
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word, english_basic="to adore"), "_save_and_archive": "Save and archive"},
        )

    assert response.status_code == 302
    post.assert_not_called()
    word.refresh_from_db()
    assert word.archived_at is not None
    assert word.english_basic == "to adore"
    stored = WordEmbedding.objects.get(word=word)
    assert list(stored.vector) == _vector(0.25)
    assert "Meaning: to love" in stored.source_text


@pytest.mark.django_db
@KEY
def test_save_and_restore_does_not_embed_when_the_text_matches() -> None:
    word = _word(archived_at=timezone.now())
    _current(word)
    client = _client()

    with patch("api.services.embeddings.requests.post") as post:
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word), "_save_and_restore": "Save and restore"},
        )

    assert response.status_code == 302
    post.assert_not_called()
    word.refresh_from_db()
    assert word.archived_at is None
    assert list(WordEmbedding.objects.get(word=word).vector) == _vector(0.25)


@pytest.mark.django_db
@KEY
def test_save_and_restore_embeds_when_the_gloss_also_changes() -> None:
    word = _word(archived_at=timezone.now())
    _current(word)
    client = _client()

    with patch(
        "api.services.embeddings.requests.post",
        return_value=_embedding_response(),
    ) as post:
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word, english_basic="to adore"), "_save_and_restore": "Save and restore"},
        )

    assert response.status_code == 302
    assert post.call_count == 1
    word.refresh_from_db()
    assert word.archived_at is None
    assert word.english_basic == "to adore"
    assert "Meaning: to adore" in WordEmbedding.objects.get(word=word).source_text


@pytest.mark.django_db
@KEY
def test_category_rename_and_word_category_edits_do_not_embed() -> None:
    word = _word()
    other = _word(chinese="茶", pinyin="chá", english_basic="tea")
    food = Category.objects.create(name="Food")
    travel = Category.objects.create(name="Travel")
    membership = WordCategory.objects.create(word=word, category=food)
    client = _client()

    with patch("api.services.embeddings.requests.post") as post:
        renamed = client.post(
            reverse("admin:api_category_change", args=[food.pk]),
            {"name": "Meals"},
        )
        added = client.post(
            reverse("admin:api_wordcategory_add"),
            {"word": other.pk, "category": travel.pk},
        )
        moved = client.post(
            reverse("admin:api_wordcategory_change", args=[membership.pk]),
            {"word": word.pk, "category": travel.pk},
        )

    assert renamed.status_code == 302
    assert added.status_code == 302
    assert moved.status_code == 302
    post.assert_not_called()
    food.refresh_from_db()
    membership.refresh_from_db()
    assert food.name == "Meals"
    assert membership.category_id == travel.pk
    assert WordCategory.objects.filter(word=other, category=travel).exists()
    assert WordEmbedding.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_analyze_card_does_not_embed() -> None:
    word = _word()
    client = _client()
    change_url = reverse("admin:api_word_change", args=[word.pk])

    with (
        patch("api.services.embeddings.requests.post") as embed_post,
        patch("api.services.card_review.requests.post", side_effect=requests.Timeout),
    ):
        response = client.get(f"{change_url}?include_analysis=true")

    assert response.status_code == 200
    embed_post.assert_not_called()
    assert WordEmbedding.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("key", "failure"),
    [
        ("test-openrouter-key", "timeout"),
        ("test-openrouter-key", "status"),
        ("test-openrouter-key", "vector"),
        ("", "key"),
    ],
)
def test_provider_failure_keeps_the_new_gloss_and_the_old_vector(key: str, failure: str) -> None:
    word = _word()
    original = embedding_source_text(word)
    _current(word)
    client = _client()

    def fake_post(url, headers=None, json=None, timeout=None):
        if failure == "timeout":
            raise requests.Timeout()
        if failure == "status":
            response = _embedding_response()
            response.status_code = 503
            return response
        response = _embedding_response()
        response.json.return_value = {"data": [{"index": 0, "embedding": [0.1]}]}
        return response

    with (
        override_settings(OPENROUTER_API_KEY=key),
        patch("api.services.embeddings.requests.post", side_effect=fake_post) as post,
    ):
        response = client.post(
            reverse("admin:api_word_change", args=[word.pk]),
            {**_form(word, english_basic="to adore"), "_save": "Save"},
            follow=True,
        )

    assert response.status_code == 200
    if failure == "key":
        post.assert_not_called()
    word.refresh_from_db()
    assert word.english_basic == "to adore"
    stored = WordEmbedding.objects.get(word=word)
    assert stored.source_text == original
    assert list(stored.vector) == _vector(0.25)
    body = response.content.decode()
    assert "The word was saved and the embedding was not updated." in body
    assert 'class="warning"' in body
    assert 'class="success"' in body
