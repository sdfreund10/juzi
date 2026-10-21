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
    SUGGESTION_FIELDS,
    CardReviewFailed,
    CardReviewNotConfigured,
    review_card,
    review_input,
)

CLAUDE_MODEL = "anthropic/claude-sonnet-4.5"
REVIEW_SETTINGS = override_settings(
    CARD_REVIEW_MODEL=CLAUDE_MODEL,
    OPENROUTER_API_KEY="test-openrouter-key",
)


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
                "practice_directions": ["pinyin_to_en", "zh_to_en"],
            }
        ],
        "suggestions": _null_suggestions(english_basic="to love (a person)"),
    }
    payload.update(overrides)
    return payload


def _openrouter_response(
    *,
    content: object | None = None,
    model: str = CLAUDE_MODEL,
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


def _analyze_url(word: Word) -> str:
    return reverse("admin:api_word_analyze", args=[word.pk])


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
    assert captured["json"]["model"] == CLAUDE_MODEL
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
        "hsk_level",
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
        ("not-json", CLAUDE_MODEL),
        (json.dumps({"verdict": "issues_found"}), CLAUDE_MODEL),
        (
            json.dumps(_review_payload(verdict="looks_fine")),
            CLAUDE_MODEL,
        ),
        (
            json.dumps(_review_payload(suggestions=_null_suggestions(chinese="字" * 65))),
            CLAUDE_MODEL,
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
@pytest.mark.parametrize(
    "model",
    ["", "openai/gpt-4o", "provider/luna-preview"],
)
def test_model_guard_refuses_disallowed_models_without_calling_provider(model: str) -> None:
    word = _word()
    with (
        override_settings(CARD_REVIEW_MODEL=model, OPENROUTER_API_KEY="test-openrouter-key"),
        patch("api.services.card_review.requests.post") as post,
    ):
        with pytest.raises(CardReviewNotConfigured):
            review_card(word)
    post.assert_not_called()


@pytest.mark.django_db
@override_settings(CARD_REVIEW_MODEL=CLAUDE_MODEL, OPENROUTER_API_KEY="")
def test_missing_api_key_is_not_configured() -> None:
    word = _word()
    with patch("api.services.card_review.requests.post") as post:
        with pytest.raises(CardReviewNotConfigured):
            review_card(word)
    post.assert_not_called()


@pytest.mark.django_db
@REVIEW_SETTINGS
def test_analyze_requires_change_permission_and_post() -> None:
    word = _word()
    url = _analyze_url(word)
    viewer = _staff_with_word_view()
    editor = _staff_with_word_change()
    learner = User.objects.create_user(
        "learner@test.com",
        "learner@test.com",
        "local-test-password",
    )

    anonymous = Client()
    anonymous_response = anonymous.post(url)
    assert anonymous_response.status_code == 302
    assert "/admin/login/" in anonymous_response["Location"]

    learner_client = Client()
    learner_client.force_login(learner)
    learner_response = learner_client.post(url)
    assert learner_response.status_code == 302
    assert "/admin/login/" in learner_response["Location"]

    viewer_client = Client()
    viewer_client.force_login(viewer)
    viewer_response = viewer_client.post(url)
    assert viewer_response.status_code == 403
    assert viewer_response.json() == {"detail": "You cannot analyze this word."}

    editor_client = Client()
    editor_client.force_login(editor)
    get_response = editor_client.get(url)
    assert get_response.status_code == 405
    assert get_response.json() == {"detail": "Method not allowed."}


@pytest.mark.django_db
@REVIEW_SETTINGS
def test_analyze_success_and_failures_do_not_mutate_the_word() -> None:
    reporter = User.objects.create_user(
        "reporter@test.com",
        "reporter@test.com",
        "local-test-password",
    )
    word = _word(flagged_by=reporter, archived_at=timezone.now())
    category = Category.objects.create(name="Food")
    WordCategory.objects.create(word=word, category=category)
    before = _word_state(word)
    admin = _superuser()
    client = Client()
    client.force_login(admin)
    url = _analyze_url(word)
    script_payload = _review_payload(
        suggestions=_null_suggestions(english_basic="<script>alert(1)</script>")
    )

    with patch(
        "api.services.card_review.requests.post",
        return_value=_openrouter_response(content=script_payload),
    ):
        success = client.post(url)

    assert success.status_code == 200
    body = success.json()
    assert body["verdict"] == "issues_found"
    assert body["suggestions"]["english_basic"] == "<script>alert(1)</script>"
    assert _word_state(word) == before

    failure_cases = [
        _openrouter_response(content="not-json"),
        _openrouter_response(status_code=502, raw_json={"error": "down"}),
        _openrouter_response(content=_review_payload(), model="other/model"),
    ]
    for response in failure_cases:
        with patch("api.services.card_review.requests.post", return_value=response):
            failed = client.post(url)
        assert failed.status_code == 502
        assert "detail" in failed.json()
        assert _word_state(word) == before

    with patch("api.services.card_review.requests.post", side_effect=requests.Timeout):
        timed_out = client.post(url)
    assert timed_out.status_code == 502
    assert _word_state(word) == before


@pytest.mark.django_db
@override_settings(CARD_REVIEW_MODEL="", OPENROUTER_API_KEY="test-openrouter-key")
def test_analyze_unconfigured_does_not_call_provider_or_mutate() -> None:
    word = _word()
    before = _word_state(word)
    admin = _superuser()
    client = Client()
    client.force_login(admin)
    with patch("api.services.card_review.requests.post") as post:
        response = client.post(_analyze_url(word))
    assert response.status_code == 503
    assert response.json() == {"detail": "Card review is not configured."}
    post.assert_not_called()
    assert _word_state(word) == before


@pytest.mark.django_db
@override_settings(CARD_REVIEW_MODEL="", OPENROUTER_API_KEY="")
def test_change_form_shows_analyze_panel_only_for_saved_words_with_change_permission() -> None:
    word = _word()
    change_url = reverse("admin:api_word_change", args=[word.pk])
    add_url = reverse("admin:api_word_add")
    analyze_url = _analyze_url(word)

    editor = _staff_with_word_change()
    editor_client = Client()
    editor_client.force_login(editor)
    change = editor_client.get(change_url)

    admin = _superuser()
    add_client = Client()
    add_client.force_login(admin)
    add = add_client.get(add_url)
    change_body = change.content.decode()
    add_body = add.content.decode()

    assert change.status_code == 200
    assert "Analyze card" in change_body
    assert "Results are discarded when you leave or refresh." in change_body
    assert 'data-configured="false"' in change_body
    assert analyze_url in change_body
    assert "admin/js/card_review.js" in change_body
    assert add.status_code == 200
    assert "Analyze card" not in add_body
    assert 'id="card-review"' not in add_body

    viewer = _staff_with_word_view()
    viewer_client = Client()
    viewer_client.force_login(viewer)
    viewer_change = viewer_client.get(change_url).content.decode()
    assert "Analyze card" not in viewer_change
    assert 'id="card-review"' not in viewer_change
