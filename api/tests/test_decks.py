from __future__ import annotations

import json
import logging
import math
import re
from unittest.mock import Mock, patch

import pytest
import requests
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    EMBEDDING_DIMENSIONS,
    Category,
    Learner,
    UserWord,
    Word,
    WordCategory,
    WordEmbedding,
)
from api.services.accounts import apply_login_email
from api.services.decks import DECK_MODEL, PROMPT_EMBED_TIMEOUT, SELECTION_TIMEOUT
from api.services.embeddings import EMBEDDING_MODEL, EMBEDDINGS_URL, embedding_source_text
from api.services.openrouter import OPENROUTER_URL

User = get_user_model()
KEY = override_settings(OPENROUTER_API_KEY="test-openrouter-key")


def _make_user(*, email: str, password: str) -> User:
    user = User(username=email, email=email)
    apply_login_email(user, email)
    user.set_password(password)
    user.save()
    Learner.objects.create(user=user, proficiency_level=Learner.ProficiencyLevel.NOVICE)
    return user


def _csrf_headers(client: APIClient) -> dict[str, str]:
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_200_OK
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def _login(client: APIClient, user: User, password: str) -> dict[str, str]:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": password},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_200_OK
    return _csrf_headers(client)


def _word(**overrides: object) -> Word:
    fields: dict[str, object] = {
        "chinese": "茶",
        "pinyin": "chá",
        "english_basic": "tea",
        "hsk_level": 1,
        "example_sentence_english": "I drink tea.",
    }
    fields.update(overrides)
    return Word.objects.create(**fields)


def _vector_at(index: int, value: float) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[index] = value
    return vector


def _store(word: Word, vector: list[float], **overrides: object) -> WordEmbedding:
    fields: dict[str, object] = {
        "word": word,
        "model_name": EMBEDDING_MODEL,
        "source_text": embedding_source_text(word),
        "vector": vector,
    }
    fields.update(overrides)
    return WordEmbedding.objects.create(**fields)


def _embedding_response(vector: list[float], *, status_code: int = 200) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = {"data": [{"index": 0, "embedding": vector}]}
    return response


def _chat_response(
    ids: list[int],
    *,
    name: str = "Parents",
    model: str = DECK_MODEL,
    finish_reason: str = "stop",
    content: object | None = None,
    status_code: int = 200,
) -> Mock:
    response = Mock()
    response.status_code = status_code
    message = json.dumps({"ids": ids, "name": name}) if content is None else content
    response.json.return_value = {
        "model": model,
        "choices": [{"finish_reason": finish_reason, "message": {"content": message}}],
    }
    return response


class _Provider:
    """One stand-in for ``requests.post``.

    Both clients import the same ``requests`` module, so two patches would
    replace one function.
    """

    def __init__(self, query: list[float], chat: Mock) -> None:
        self.query = query
        self.chat = chat
        self.embed_calls: list[dict[str, object]] = []
        self.chat_calls: list[dict[str, object]] = []

    def __call__(self, url: str, headers=None, json=None, timeout=None):
        if url == EMBEDDINGS_URL:
            self.embed_calls.append({"url": url, "json": json, "timeout": timeout})
            return _embedding_response(self.query)
        if url == OPENROUTER_URL:
            self.chat_calls.append({"url": url, "json": json, "timeout": timeout})
            return self.chat
        raise AssertionError(f"unexpected URL {url}")


def _patch_provider(query: list[float], chat: Mock):
    provider = _Provider(query, chat)
    return provider, patch("api.services.embeddings.requests.post", side_effect=provider)


def _post(client: APIClient, headers: dict[str, str], body: dict) -> object:
    return client.post(reverse("decks-create"), body, format="json", **headers)


def _saved_word_ids(category: Category) -> list[int]:
    return list(
        WordCategory.objects.filter(category=category)
        .order_by("id")
        .values_list("word_id", flat=True)
    )


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def alice() -> User:
    return _make_user(email="alice@example.com", password="s3cret-alice")


@pytest.mark.django_db
def test_build_deck_requires_authentication(client: APIClient) -> None:
    headers = _csrf_headers(client)
    response = _post(client, headers, {"prompt": "tea", "size": 20})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert Category.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_build_deck_rejects_a_blank_prompt_or_a_size_outside_the_three(
    client: APIClient,
    alice: User,
) -> None:
    headers = _login(client, alice, "s3cret-alice")
    with patch("api.services.embeddings.requests.post") as embed:
        for body in (
            {"prompt": "   ", "size": 20},
            {"prompt": "tea", "size": 15},
            {"size": 20},
            {"prompt": "tea"},
        ):
            response = _post(client, headers, body)
            assert response.status_code == status.HTTP_400_BAD_REQUEST
    embed.assert_not_called()
    assert Category.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_cosine_rank_prefers_a_closer_vector_over_a_longer_one(
    client: APIClient,
    alice: User,
) -> None:
    topic = Category.objects.create(name="Food, Cooking & Dining")
    Category.objects.create(name="HSK 1")
    close_low = _word(
        chinese="配偶",
        pinyin="pèi'ǒu",
        english_basic="spouse",
        hsk_level=5,
        example_sentence_english="UNIQUE EXAMPLE SENTENCE",
    )
    far_long = _word(chinese="巨大", pinyin="jùdà", english_basic="huge", hsk_level=4)
    close_high = _word(chinese="父母", pinyin="fùmǔ", english_basic="parents", hsk_level=2)
    for word in (close_low, far_long, close_high):
        WordCategory.objects.create(word=word, category=topic)
        WordCategory.objects.create(word=word, category=Category.objects.get(name="HSK 1"))
    _store(close_low, _vector_at(0, 0.2))
    _store(far_long, [3.0, 4.0, *([0.0] * (EMBEDDING_DIMENSIONS - 2))])
    _store(close_high, _vector_at(0, 0.2))
    before = list(Word.objects.order_by("id").values())

    provider, http = _patch_provider(
        _vector_at(0, 1.0),
        _chat_response([close_low.id, close_high.id]),
    )
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "talk to their parents", "size": 20})

    assert response.status_code == status.HTTP_201_CREATED
    sent = provider.chat_calls[0]["json"]
    candidates = json.loads(sent["messages"][1]["content"])["candidates"]
    assert [item["id"] for item in candidates] == [close_low.id, close_high.id, far_long.id]
    assert candidates[0] == {
        "id": close_low.id,
        "chinese": "配偶",
        "pinyin": "pèi'ǒu",
        "english_basic": "spouse",
        "hsk_level": 5,
        "topic": "Food, Cooking & Dining",
    }
    assert "UNIQUE EXAMPLE SENTENCE" not in sent["messages"][1]["content"]
    assert "HSK 1" not in sent["messages"][1]["content"]
    assert sent["model"] == DECK_MODEL
    assert sent["provider"] == {"allow_fallbacks": False}
    assert "at most 20" in sent["messages"][0]["content"]
    assert "short English name" in sent["messages"][0]["content"]
    schema = sent["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["ids", "name"]
    assert provider.chat_calls[0]["timeout"] == SELECTION_TIMEOUT
    assert provider.embed_calls[0]["timeout"] == PROMPT_EMBED_TIMEOUT
    assert provider.embed_calls[0]["json"]["input"] == ["talk to their parents"]
    assert list(Word.objects.order_by("id").values()) == before
    assert UserWord.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_skipped_rows_never_reach_the_candidate_list(client: APIClient, alice: User) -> None:
    kept = _word(chinese="留", pinyin="liú", english_basic="to keep")
    stale = _word(chinese="舊", pinyin="jiù", english_basic="stale")
    other_model = _word(chinese="模", pinyin="mó", english_basic="model")
    archived = _word(chinese="檔", pinyin="dàng", english_basic="archived")
    archived.archived_at = timezone.now()
    archived.save(update_fields=["archived_at"])
    zero = _word(chinese="零", pinyin="líng", english_basic="zero")
    _store(kept, _vector_at(0, 1.0))
    _store(stale, _vector_at(0, 1.0), source_text="Chinese: yesterday")
    _store(other_model, _vector_at(0, 1.0), model_name="other/model")
    _store(archived, _vector_at(0, 1.0))
    _store(zero, _vector_at(0, 0.0))

    provider, http = _patch_provider(
        _vector_at(0, 1.0),
        _chat_response([kept.id]),
    )
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "keep one", "size": 20})

    assert response.status_code == status.HTTP_201_CREATED
    candidates = json.loads(provider.chat_calls[0]["json"]["messages"][1]["content"])["candidates"]
    assert [item["id"] for item in candidates] == [kept.id]


@pytest.mark.django_db
@KEY
def test_an_id_outside_the_head_saves_nothing(client: APIClient, alice: User) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    before = list(Word.objects.order_by("id").values())
    provider, http = _patch_provider(
        _vector_at(0, 1.0),
        _chat_response([word.id, word.id + 1000]),
    )
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "tea", "size": 20})

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "Could not build a deck. Try again."}
    assert Category.objects.count() == 0
    assert list(Word.objects.order_by("id").values()) == before
    assert provider.chat_calls


@pytest.mark.django_db
@KEY
def test_duplicate_ids_collapse_and_the_list_stops_at_size(
    client: APIClient,
    alice: User,
) -> None:
    words = []
    for index in range(25):
        word = _word(
            chinese=f"字{index}",
            pinyin=f"zi{index}",
            english_basic=f"word {index}",
            hsk_level=(index % 7) + 1,
        )
        _store(word, _vector_at(0, 1.0))
        words.append(word)
    returned = [words[24].id, words[24].id, *[word.id for word in reversed(words[:24])]]
    expected = [word.id for word in reversed(words)][:20]

    _, http = _patch_provider(_vector_at(0, 1.0), _chat_response(returned))
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "a long visit", "size": 20})

    assert response.status_code == status.HTTP_201_CREATED
    category = Category.objects.get()
    assert category.owner_id == alice.id
    assert _saved_word_ids(category) == expected
    assert Word.objects.count() == 25


@pytest.mark.django_db
@KEY
def test_fewer_than_size_still_saves(client: APIClient, alice: User) -> None:
    first = _word(chinese="一", pinyin="yī", english_basic="one", hsk_level=3)
    second = _word(chinese="二", pinyin="èr", english_basic="two", hsk_level=6)
    _store(first, _vector_at(0, 1.0))
    _store(second, _vector_at(0, 1.0))
    _, http = _patch_provider(
        _vector_at(0, 1.0),
        _chat_response([second.id, first.id]),
    )
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "count", "size": 40})

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["name"] == "Parents"
    category = Category.objects.get()
    assert _saved_word_ids(category) == [second.id, first.id]


@pytest.mark.django_db
@KEY
def test_zero_ids_save_nothing(client: APIClient, alice: User) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    _, http = _patch_provider(_vector_at(0, 1.0), _chat_response([]))
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "nothing close", "size": 20})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json() == {"detail": "No matching words."}
    assert Category.objects.count() == 0
    assert WordCategory.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_the_same_model_name_is_suffixed_for_one_learner_and_free_for_another(
    client: APIClient,
    alice: User,
) -> None:
    bob = _make_user(email="bob@example.com", password="s3cret-bob")
    topic = Category.objects.create(name="Food, Cooking & Dining")
    word = _word()
    _store(word, _vector_at(0, 1.0))
    chat = _chat_response([word.id], name="Talk to parents")

    def build(api: APIClient, user: User, password: str, prompt: str) -> dict:
        headers = _login(api, user, password)
        provider, http = _patch_provider(_vector_at(0, 1.0), chat)
        with http:
            response = _post(api, headers, {"prompt": prompt, "size": 20})
        assert response.status_code == status.HTTP_201_CREATED
        assert provider.embed_calls[0]["json"]["input"] == [prompt.strip()]
        return response.json()

    first = build(client, alice, "s3cret-alice", "  talk to their parents")
    second = build(
        APIClient(enforce_csrf_checks=True),
        alice,
        "s3cret-alice",
        "talk to their parents",
    )
    other = build(APIClient(enforce_csrf_checks=True), bob, "s3cret-bob", "talk to their parents")
    assert first["name"] == "Talk to parents"
    assert second["name"] == "Talk to parents 2"
    assert other["name"] == "Talk to parents"

    alice_list = APIClient(enforce_csrf_checks=True)
    alice_rows = alice_list.get(
        reverse("categories"),
        **_login(alice_list, alice, "s3cret-alice"),
    ).json()
    bob_list = APIClient(enforce_csrf_checks=True)
    bob_rows = bob_list.get(reverse("categories"), **_login(bob_list, bob, "s3cret-bob")).json()
    alice_ids = {row["id"] for row in alice_rows}
    bob_ids = {row["id"] for row in bob_rows}
    assert {first["id"], second["id"], topic.id} <= alice_ids
    assert other["id"] not in alice_ids
    assert {other["id"], topic.id} <= bob_ids
    assert first["id"] not in bob_ids
    assert second["id"] not in bob_ids


@pytest.mark.django_db
@KEY
def test_a_repeated_long_title_keeps_the_suffix_inside_100_characters(
    client: APIClient,
    alice: User,
) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    title = "n" * 120
    headers = _login(client, alice, "s3cret-alice")
    names = []
    for _ in range(2):
        _, http = _patch_provider(
            _vector_at(0, 1.0),
            _chat_response([word.id], name=title),
        )
        with http:
            response = _post(client, headers, {"prompt": "a long visit", "size": 60})
        assert response.status_code == status.HTTP_201_CREATED
        names.append(response.json()["name"])
    assert names[0] == "n" * 100
    assert names[1] == f"{'n' * 98} 2"
    assert len(names[1]) == 100


@pytest.mark.django_db
@KEY
def test_the_model_name_collapses_whitespace_and_the_embedding_uses_the_stripped_prompt(
    client: APIClient,
    alice: User,
) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    provider, http = _patch_provider(
        _vector_at(0, 1.0),
        _chat_response([word.id], name="  Visiting   the\nparents  "),
    )
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "  meet   their\nparents  ", "size": 20})

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["name"] == "Visiting the parents"
    assert provider.embed_calls[0]["json"]["input"] == ["meet   their\nparents"]
    situation = json.loads(provider.chat_calls[0]["json"]["messages"][1]["content"])["situation"]
    assert situation == "meet   their\nparents"


@pytest.mark.django_db
@KEY
def test_missing_catalog_or_a_provider_failure_saves_nothing(
    client: APIClient,
    alice: User,
) -> None:
    headers = _login(client, alice, "s3cret-alice")
    with patch("api.services.embeddings.requests.post") as post:
        missing = _post(client, headers, {"prompt": "tea", "size": 20})
    assert missing.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert missing.json() == {"detail": "Could not build a deck. Try again."}
    post.assert_not_called()

    word = _word()
    _store(word, _vector_at(0, 1.0))
    with (
        override_settings(OPENROUTER_API_KEY=""),
        patch("api.services.embeddings.requests.post") as post,
    ):
        no_key = _post(client, headers, {"prompt": "tea", "size": 20})
    assert no_key.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    post.assert_not_called()

    calls: list[str] = []

    def time_out(url: str, headers=None, json=None, timeout=None):
        calls.append(url)
        raise requests.Timeout("slow")

    with patch("api.services.embeddings.requests.post", side_effect=time_out):
        timed_out = _post(client, headers, {"prompt": "tea", "size": 20})
    assert timed_out.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert calls == [EMBEDDINGS_URL]

    def fail_embed(url: str, headers=None, json=None, timeout=None):
        calls.append(url)
        if url == EMBEDDINGS_URL:
            return _embedding_response(_vector_at(0, 1.0), status_code=500)
        raise AssertionError(url)

    calls.clear()
    with patch("api.services.embeddings.requests.post", side_effect=fail_embed):
        bad_embed = _post(client, headers, {"prompt": "tea", "size": 20})
    assert bad_embed.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert calls == [EMBEDDINGS_URL]

    def infinite_embed(url: str, headers=None, json=None, timeout=None):
        calls.append(url)
        if url == EMBEDDINGS_URL:
            return _embedding_response(_vector_at(0, math.inf))
        raise AssertionError(url)

    calls.clear()
    with patch("api.services.embeddings.requests.post", side_effect=infinite_embed):
        infinite = _post(client, headers, {"prompt": "tea", "size": 20})
    assert infinite.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert calls == [EMBEDDINGS_URL]
    assert Category.objects.count() == 0


@pytest.mark.django_db
@KEY
@pytest.mark.parametrize(
    "chat",
    [
        _chat_response([1], finish_reason="length"),
        _chat_response([1], model="openai/gpt-6-luna"),
        _chat_response([1], content=json.dumps({"ids": [1]})),
        _chat_response([1], name="   "),
        _chat_response([1], content=json.dumps({"ids": [1], "name": "Parents", "extra": 1})),
        _chat_response([1], content="not-json"),
        _chat_response([1], status_code=500),
    ],
)
def test_a_bad_selection_response_saves_nothing(
    client: APIClient,
    alice: User,
    chat: Mock,
) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    _, http = _patch_provider(_vector_at(0, 1.0), chat)
    headers = _login(client, alice, "s3cret-alice")
    with http:
        response = _post(client, headers, {"prompt": "tea", "size": 20})
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert Category.objects.count() == 0


@pytest.mark.django_db
@KEY
def test_an_empty_head_does_not_call_the_chat_model(client: APIClient, alice: User) -> None:
    archived = _word()
    archived.archived_at = timezone.now()
    archived.save(update_fields=["archived_at"])
    _store(archived, _vector_at(0, 1.0))
    headers = _login(client, alice, "s3cret-alice")
    calls: list[str] = []

    def embed_only(url: str, headers=None, json=None, timeout=None):
        calls.append(url)
        if url == EMBEDDINGS_URL:
            return _embedding_response(_vector_at(0, 1.0))
        raise AssertionError(url)

    with patch("api.services.embeddings.requests.post", side_effect=embed_only):
        response = _post(client, headers, {"prompt": "tea", "size": 20})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json() == {"detail": "No matching words."}
    assert calls == [EMBEDDINGS_URL]
    assert Category.objects.count() == 0

    def zero_embed(url: str, headers=None, json=None, timeout=None):
        calls.append(url)
        if url == EMBEDDINGS_URL:
            return _embedding_response(_vector_at(0, 0.0))
        raise AssertionError(url)

    calls.clear()
    with patch("api.services.embeddings.requests.post", side_effect=zero_embed):
        zero_query = _post(client, headers, {"prompt": "tea", "size": 20})
    assert zero_query.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert calls == [EMBEDDINGS_URL]


@pytest.mark.django_db
@KEY
def test_selection_timeout_saves_nothing(client: APIClient, alice: User) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    headers = _login(client, alice, "s3cret-alice")
    calls: list[str] = []

    def time_out_selection(url: str, headers=None, json=None, timeout=None):
        calls.append(url)
        if url == EMBEDDINGS_URL:
            return _embedding_response(_vector_at(0, 1.0))
        raise requests.Timeout("slow")

    with patch("api.services.embeddings.requests.post", side_effect=time_out_selection):
        response = _post(client, headers, {"prompt": "tea", "size": 20})
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert calls == [EMBEDDINGS_URL, OPENROUTER_URL]
    assert Category.objects.count() == 0


_STEP_LINE = re.compile(
    r"^deck (prompt embed|vector search|model pick|save)( failed)? \d+\.\d{3}s$"
)


def _deck_log_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "api.services.decks"]


@pytest.mark.django_db
@KEY
def test_deck_build_logs_each_step_duration(
    client: APIClient,
    alice: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    _, http = _patch_provider(_vector_at(0, 1.0), _chat_response([word.id]))
    headers = _login(client, alice, "s3cret-alice")
    with caplog.at_level(logging.INFO, logger="api.services.decks"), http:
        response = _post(client, headers, {"prompt": "tea", "size": 20})

    assert response.status_code == status.HTTP_201_CREATED
    messages = _deck_log_lines(caplog)
    steps = [message for message in messages if _STEP_LINE.fullmatch(message)]
    assert [message.removeprefix("deck ").rsplit(" ", 1)[0] for message in steps] == [
        "prompt embed",
        "vector search",
        "model pick",
        "save",
    ]
    assert "deck prompt: tea" in messages
    assert f"deck candidates: {word.id}" in messages
    assert f"deck returned: name=Parents ids={word.id}" in messages
    assert "You choose vocabulary cards" not in "\n".join(messages)


@pytest.mark.django_db
@KEY
def test_a_failed_step_logs_its_duration_and_later_steps_do_not_run(
    client: APIClient,
    alice: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    word = _word()
    _store(word, _vector_at(0, 1.0))
    headers = _login(client, alice, "s3cret-alice")

    def time_out_selection(url: str, headers=None, json=None, timeout=None):
        if url == EMBEDDINGS_URL:
            return _embedding_response(_vector_at(0, 1.0))
        raise requests.Timeout("slow")

    with (
        caplog.at_level(logging.INFO, logger="api.services.decks"),
        patch("api.services.embeddings.requests.post", side_effect=time_out_selection),
    ):
        response = _post(client, headers, {"prompt": "tea", "size": 20})

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    messages = _deck_log_lines(caplog)
    steps = [message for message in messages if _STEP_LINE.fullmatch(message)]
    assert [message.removeprefix("deck ").rsplit(" ", 1)[0] for message in steps] == [
        "prompt embed",
        "vector search",
        "model pick failed",
    ]
    assert "deck prompt: tea" in messages
    assert f"deck candidates: {word.id}" in messages
    assert not any(message.startswith("deck returned:") for message in messages)
    assert "You choose vocabulary cards" not in "\n".join(messages)
    assert Category.objects.count() == 0
