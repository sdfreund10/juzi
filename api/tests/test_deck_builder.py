import json
from unittest.mock import Mock

import pytest
import requests

from api.models import Category, Word, WordCategory, WordEmbedding
from api.services.deck_builder import DeckBuildError, build_deck
from api.services.embeddings import DIMENSIONS, MODEL_NAME, word_embedding_text

pytestmark = pytest.mark.django_db


def vector(x: float, y: float = 0.0) -> list[float]:
    return [x, y] + [0.0] * (DIMENSIONS - 2)


@pytest.fixture
def words() -> list[Word]:
    words = [
        Word.objects.create(chinese=chinese, pinyin=pinyin, english_basic=meaning, hsk_level=1)
        for chinese, pinyin, meaning in [
            ("字", "zì", "character"),
            ("愛", "ài", "to love"),
            ("圖書館", "túshūguǎn", "library"),
        ]
    ]
    for word, coordinates in zip(words, [(1.0, 0.0), (50.0, 50.0), (-1.0, 0.0)], strict=True):
        WordEmbedding.objects.create(
            word=word,
            model_name=MODEL_NAME,
            source_text=word_embedding_text(word),
            vector=vector(*coordinates),
        )
    return words


def selection_response(word_ids: list[int], name: str = "Practice") -> Mock:
    return Mock(
        json=Mock(
            return_value={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps({"name": name, "word_ids": word_ids})},
                    }
                ],
            }
        )
    )


@pytest.fixture
def post(monkeypatch) -> Mock:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    post = Mock()
    # Only stub the HTTP boundary; exercise real retrieval and database records.
    monkeypatch.setattr(requests, "post", post)
    return post


def configure_responses(post: Mock, word_ids: list[int]) -> None:
    post.side_effect = [
        Mock(json=Mock(return_value={"data": [{"index": 0, "embedding": vector(1.0)}]})),
        selection_response(word_ids),
    ]


def test_retrieves_by_cosine_and_returns_selected_words_without_saving(
    words, post, django_assert_num_queries
) -> None:
    configure_responses(post, [words[1].pk, words[0].pk])

    with django_assert_num_queries(2):
        deck = build_deck(prompt="  words about writing  ", size=2)

    assert deck.name == "Practice"
    assert deck.words == [words[1], words[0]]
    assert not Category.objects.exists()
    assert not WordCategory.objects.exists()
    assert Word.objects.count() == 3
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"]["input"] == ["words about writing"]
    selection_request = post.call_args_list[1].kwargs["json"]
    context = json.loads(selection_request["messages"][1]["content"])
    assert context["prompt"] == "words about writing"
    assert context["size"] == 2
    # Raw dot product would put the second word first, rather than normalize magnitude.
    assert [word["id"] for word in context["candidates"]] == [word.pk for word in words]
    assert context["candidates"][0]["english"] == words[0].english_basic
    assert selection_request["response_format"]["type"] == "json_schema"


def test_caps_and_deduplicates_model_selection(words, post) -> None:
    configure_responses(post, [words[1].pk, words[1].pk, words[0].pk, words[2].pk])

    assert build_deck(prompt="vocabulary", size=2).words == [words[1], words[0]]


@pytest.mark.parametrize("count", [0, 1, 3])
def test_can_return_fewer_words_than_requested(words, post, count) -> None:
    selected = words[:count]
    configure_responses(post, [word.pk for word in selected])

    assert build_deck(prompt="vocabulary", size=10).words == selected


@pytest.mark.parametrize("invalid_embedding", ["stale", "other-model", "short", "zero", "nan"])
def test_excludes_unusable_embeddings(words, post, invalid_embedding) -> None:
    embedding = words[0].embedding
    if invalid_embedding == "stale":
        words[0].english_basic = "changed definition"
        words[0].save()
    elif invalid_embedding == "other-model":
        embedding.model_name = "different-model"
    elif invalid_embedding == "short":
        embedding.vector = [1.0]
    elif invalid_embedding == "zero":
        embedding.vector = vector(0.0)
    else:
        embedding.vector = vector(float("nan"))
    embedding.save()
    configure_responses(post, [words[1].pk])

    assert build_deck(prompt="vocabulary", size=2).words == [words[1]]

    context = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
    assert [word["id"] for word in context["candidates"]] == [words[1].pk, words[2].pk]


def test_bounds_candidate_pool_and_rejects_ids_outside_retrieval(words, post) -> None:
    for _ in range(50):
        word = Word.objects.create(chinese="字", pinyin="zì", english_basic="character")
        WordEmbedding.objects.create(
            word=word,
            model_name=MODEL_NAME,
            source_text=word_embedding_text(word),
            vector=vector(1.0),
        )
    # This word exists but falls outside the top 50 candidates.
    configure_responses(post, [words[2].pk])

    with pytest.raises(DeckBuildError, match="outside the retrieved candidates"):
        build_deck(prompt="vocabulary", size=2)

    context = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
    assert len(context["candidates"]) == 50
    assert words[2].pk not in [word["id"] for word in context["candidates"]]


def test_empty_catalog_returns_empty_draft_without_api_request(post) -> None:
    deck = build_deck(prompt="vocabulary", size=10)

    assert deck.words == []
    post.assert_not_called()


def test_no_usable_candidates_skips_selection(words, post) -> None:
    WordEmbedding.objects.update(source_text="outdated")
    configure_responses(post, [])

    assert build_deck(prompt="vocabulary", size=2).words == []
    assert post.call_count == 1


@pytest.mark.parametrize(
    "prompt,size",
    [("", 2), ("  ", 2), (None, 2), ("words", 0), ("words", -1), ("words", True), ("words", 1.5)],
)
def test_rejects_invalid_input(post, prompt, size) -> None:
    with pytest.raises(ValueError):
        build_deck(prompt=prompt, size=size)
    post.assert_not_called()


def test_requires_api_key_when_embeddings_exist(words, post, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY")

    with pytest.raises(DeckBuildError, match="OPENROUTER_API_KEY"):
        build_deck(prompt="words", size=2)
    post.assert_not_called()


@pytest.mark.parametrize("failure_stage", ["embedding", "selection"])
def test_provider_failure_raises_without_saving(words, post, failure_stage) -> None:
    configure_responses(post, [])
    responses = list(post.side_effect)
    responses[0 if failure_stage == "embedding" else 1] = requests.Timeout("timed out")
    post.side_effect = responses

    with pytest.raises(DeckBuildError, match="timed out"):
        build_deck(prompt="words", size=2)
    assert not Category.objects.exists()


@pytest.mark.parametrize(
    "content",
    ["not json", "null", '{"name":"","word_ids":[]}', '{"name":"Practice","word_ids":[true]}'],
)
def test_rejects_invalid_selection(words, post, content) -> None:
    configure_responses(post, [])
    responses = list(post.side_effect)
    responses[1] = Mock(
        json=Mock(
            return_value={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": content},
                    }
                ]
            }
        )
    )
    post.side_effect = responses

    with pytest.raises(DeckBuildError):
        build_deck(prompt="words", size=2)


def test_truncated_selection_is_an_error(words, post) -> None:
    configure_responses(post, [])
    responses = list(post.side_effect)
    responses[1] = Mock(json=Mock(return_value={"choices": [{"finish_reason": "length"}]}))
    post.side_effect = responses

    with pytest.raises(DeckBuildError, match="did not complete"):
        build_deck(prompt="words", size=2)
