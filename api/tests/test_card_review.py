import json
from unittest.mock import Mock, patch

import pytest
import requests
from django.contrib.auth.models import Permission, User
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import Category, UserWord, Word, WordCategory
from api.services.card_review import (
    OPENROUTER_URL,
    REVIEW_MODEL,
    SUGGESTION_FIELDS,
    CardReviewFailed,
    review_card,
    review_input,
)

REVIEW_SETTINGS = override_settings(OPENROUTER_API_KEY="test-openrouter-key")


def _superuser() -> User:
    return User.objects.create_superuser(
        "admin@test.com",
        "admin@test.com",
        "local-test-password",
    )


def _staff_with_word_view() -> User:
    user = User.objects.create_user(
        "viewer@test.com",
        "viewer@test.com",
        "local-test-password",
        is_staff=True,
    )
    user.user_permissions.add(Permission.objects.get(codename="view_word"))
    return user


def _staff_with_word_change() -> User:
    user = User.objects.create_user(
        "editor@test.com",
        "editor@test.com",
        "local-test-password",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename="view_word"),
        Permission.objects.get(codename="change_word"),
    )
    return user


def _word(**overrides: object) -> Word:
    fields = {
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


def _null_suggestions(**overrides: object) -> dict[str, object]:
    suggestions: dict[str, object] = {field: None for field in SUGGESTION_FIELDS}
    suggestions.update(overrides)
    return suggestions


def _review_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "verdict": "issues_found",
        "findings": [
            {
                "aspect": "meaning",
                "explanation": "Gloss is too broad.",
            }
        ],
        "suggestions": _null_suggestions(english_basic="to love (a person)"),
    }
    payload.update(overrides)
    return payload


def _openrouter_response(
    *,
    content: object | None = None,
    model: str = REVIEW_MODEL,
    status_code: int = 200,
    raw_json: object | None = None,
) -> Mock:
    response = Mock()
    response.status_code = status_code
    if raw_json is not None:
        response.json.return_value = raw_json
        return response
    if isinstance(content, (dict, list)):
        message = json.dumps(content)
    else:
        message = content
    response.json.return_value = {
        "model": model,
        "choices": [{"message": {"content": message}}],
    }
    return response


def _word_state(word: Word) -> dict[str, object]:
    word.refresh_from_db()
    return {
        "chinese": word.chinese,
        "simplified": word.simplified,
        "pinyin": word.pinyin,
        "english_basic": word.english_basic,
        "hsk_level": word.hsk_level,
        "example_sentence_traditional": word.example_sentence_traditional,
        "example_sentence_simplified": word.example_sentence_simplified,
        "example_sentence_pinyin": word.example_sentence_pinyin,
        "example_sentence_english": word.example_sentence_english,
        "flagged_by_id": word.flagged_by_id,
        "archived_at": word.archived_at,
        "category_ids": list(word.categories.order_by("id").values_list("id", flat=True)),
    }


def _change_url(word: Word) -> str:
    return reverse("admin:api_word_change", args=[word.pk])


def _client_for(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
@REVIEW_SETTINGS
def test_review_input_sends_content_and_decks_not_people() -> None:
    reporter = User.objects.create_user(
        "reporter@test.com",
        "reporter@test.com",
        "local-test-password",
    )
    learner = User.objects.create_user(
        "alice@test.com",
        "alice@test.com",
        "local-test-password",
    )
    word = _word(flagged_by=reporter)
    food = Category.objects.create(name="Food")
    travel = Category.objects.create(name="Travel")
    WordCategory.objects.create(word=word, category=travel)
    WordCategory.objects.create(word=word, category=food)
    UserWord.objects.create(user=learner, word=word, easy_streak=4, easy_count=6)
    captured: dict[str, object] = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _openrouter_response(content=_review_payload())

    with patch("api.services.card_review.requests.post", side_effect=fake_post):
        review_card(word)

    assert captured["url"] == OPENROUTER_URL
    assert captured["timeout"] == (5, 45)
    assert captured["json"]["model"] == REVIEW_MODEL
    assert captured["json"]["provider"] == {"allow_fallbacks": False}
    sent = json.dumps(captured["json"], ensure_ascii=False)
    assert "愛" in sent
    assert "to love" in sent
    assert "Food" in sent
    assert "Travel" in sent
    assert "reporter@test.com" not in sent
    assert "alice@test.com" not in sent
    assert "flagged_by" not in sent
    assert "easy_streak" not in sent
    assert "archived" not in sent.lower()
    payload = review_input(word)
    assert payload["decks"] == ["Food", "Travel"]
    assert set(payload) == {
        "chinese",
        "simplified",
        "pinyin",
        "english_basic",
        "example_sentence_traditional",
        "example_sentence_simplified",
        "example_sentence_pinyin",
        "example_sentence_english",
        "decks",
    }


@pytest.mark.django_db
@REVIEW_SETTINGS
@pytest.mark.parametrize(
    ("content", "model"),
    [
        ("not-json", REVIEW_MODEL),
        (json.dumps({"verdict": "issues_found"}), REVIEW_MODEL),
        (
            json.dumps(_review_payload(verdict="looks_fine")),
            REVIEW_MODEL,
        ),
        (
            json.dumps(_review_payload(suggestions=_null_suggestions(english_basic="x" * 256))),
            REVIEW_MODEL,
        ),
        (json.dumps(_review_payload()), "anthropic/claude-other"),
    ],
)
def test_review_card_rejects_invalid_provider_payload(content: str, model: str) -> None:
    word = _word()
    with patch(
        "api.services.card_review.requests.post",
        return_value=_openrouter_response(content=content, model=model),
    ):
        with pytest.raises(CardReviewFailed, match="review"):
            review_card(word)


@pytest.mark.django_db
@REVIEW_SETTINGS
def test_review_card_reports_timeouts_and_provider_errors() -> None:
    word = _word()
    with patch("api.services.card_review.requests.post", side_effect=requests.Timeout):
        with pytest.raises(CardReviewFailed, match="timed out"):
            review_card(word)

    with patch(
        "api.services.card_review.requests.post",
        return_value=_openrouter_response(status_code=503, raw_json={"error": "down"}),
    ):
        with pytest.raises(CardReviewFailed, match="provider"):
            review_card(word)


@pytest.mark.django_db
@override_settings(OPENROUTER_API_KEY="")
def test_missing_api_key_is_not_configured() -> None:
    word = _word()
    with patch("api.services.card_review.requests.post") as post:
        with pytest.raises(CardReviewFailed, match="not configured"):
            review_card(word)
    post.assert_not_called()


@pytest.mark.django_db
def test_change_form_offers_analysis_only_to_editors_of_saved_words() -> None:
    word = _word()
    change_url = _change_url(word)
    editor_client = _client_for(_staff_with_word_change())
    viewer_client = _client_for(_staff_with_word_view())
    admin_client = _client_for(_superuser())

    with patch("api.services.card_review.requests.post") as post:
        change_body = editor_client.get(change_url).content.decode()
        add_body = admin_client.get(reverse("admin:api_word_add")).content.decode()
        viewer_body = viewer_client.get(f"{change_url}?include_analysis=true").content.decode()

    post.assert_not_called()
    assert 'href="?include_analysis=true">Analyze card</a>' in change_body
    assert "Analyze card" not in add_body
    assert 'id="card-review"' not in add_body
    assert "Analyze card" not in viewer_body
    assert 'id="card-review"' not in viewer_body


@pytest.mark.django_db
def test_analyze_link_keeps_changelist_filters() -> None:
    word = _word()
    client = _client_for(_staff_with_word_change())

    body = client.get(
        _change_url(word), {"_changelist_filters": "flag_status=flagged"}
    ).content.decode()

    assert "?_changelist_filters=flag_status%3Dflagged&amp;include_analysis=true" in body


@pytest.mark.django_db
@REVIEW_SETTINGS
def test_include_analysis_renders_escaped_review_without_mutating_the_word() -> None:
    reporter = User.objects.create_user(
        "reporter@test.com",
        "reporter@test.com",
        "local-test-password",
    )
    word = _word(flagged_by=reporter, archived_at=timezone.now())
    WordCategory.objects.create(word=word, category=Category.objects.create(name="Food"))
    before = _word_state(word)
    client = _client_for(_superuser())
    script_payload = _review_payload(
        suggestions=_null_suggestions(english_basic="<script>alert(1)</script>")
    )

    with patch(
        "api.services.card_review.requests.post",
        return_value=_openrouter_response(content=script_payload),
    ):
        response = client.get(f"{_change_url(word)}?include_analysis=true")

    body = response.content.decode()
    assert response.status_code == 200
    assert "Issues found" in body
    assert "meaning: Gloss is too broad." in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body
    assert "Keep current value" in body
    assert "<strong>English basic</strong>" in body
    assert "<strong>Chinese</strong>" not in body
    assert "<strong>Pinyin</strong>" not in body
    assert "Refreshing runs a new analysis." in body
    assert _word_state(word) == before


@pytest.mark.django_db
@REVIEW_SETTINGS
def test_remove_verdict_points_active_words_to_archive() -> None:
    active = _word()
    archived = _word(chinese="愛人", archived_at=timezone.now())
    client = _client_for(_superuser())
    removal_payload = _review_payload(
        verdict="remove",
        findings=[{"aspect": "usage", "explanation": "Rare in Taiwan."}],
        suggestions=_null_suggestions(),
    )

    with patch(
        "api.services.card_review.requests.post",
        side_effect=[
            _openrouter_response(content=removal_payload),
            _openrouter_response(content=removal_payload),
        ],
    ):
        active_body = client.get(f"{_change_url(active)}?include_analysis=true").content.decode()
        archived_body = client.get(
            f"{_change_url(archived)}?include_analysis=true"
        ).content.decode()

    assert "Remove card" in active_body
    assert "Use Save and archive to remove it from practice." in active_body
    assert "Remove card" in archived_body
    assert "Use Save and archive" not in archived_body


@pytest.mark.django_db
@REVIEW_SETTINGS
@pytest.mark.parametrize(
    ("provider_response", "message"),
    [
        (_openrouter_response(content="not-json"), "The review response was invalid."),
        (
            _openrouter_response(status_code=502, raw_json={"error": "down"}),
            "The review provider returned an error.",
        ),
        (requests.Timeout(), "The review request timed out."),
    ],
)
def test_include_analysis_shows_failures_with_retry_without_mutating_the_word(
    provider_response: object, message: str
) -> None:
    word = _word()
    before = _word_state(word)
    client = _client_for(_superuser())

    with patch("api.services.card_review.requests.post", side_effect=[provider_response]):
        response = client.get(f"{_change_url(word)}?include_analysis=true")

    body = response.content.decode()
    assert response.status_code == 200
    assert message in body
    assert 'href="?include_analysis=true">Try again</a>' in body
    assert _word_state(word) == before
