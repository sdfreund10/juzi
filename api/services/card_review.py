from __future__ import annotations

import json
from typing import Any

import requests
from django.conf import settings
from rest_framework import serializers

from api.models import Word
from api.services.openrouter import (
    EXAMPLE_SENTENCE_PROPERTIES,
    OPENROUTER_URL,
    parse_chat_json,
    strict_json_schema,
)

VERDICTS = ("no_clear_issue", "issues_found", "needs_human_review")
PRACTICE_DIRECTIONS = ("pinyin_to_en", "en_to_zh", "zh_to_en")
STRING_FIELDS = (
    "chinese",
    "simplified",
    "pinyin",
    "english_basic",
    *(f"example_sentence_{key}" for key in EXAMPLE_SENTENCE_PROPERTIES),
)
SUGGESTION_FIELDS = (*STRING_FIELDS, "hsk_level")

REVIEW_PROMPT = """
You review vocabulary cards for a household app that practices traditional Chinese.

Each card is used in three directions: pinyin to English, English to Chinese, and
Chinese to English.

Review:
- whether the English meaning is accurate and concise
- whether the pinyin matches the traditional Chinese, including tones
- whether the four example-sentence fields say the same thing
- whether the example is natural
- traditional Chinese and Taiwan usage
- whether difficulty fits the given HSK level
- whether any practice direction is ambiguous

Do not mention learners, reporters, flags, or archive state.
Use null in suggestions to keep the current value. Only suggest a replacement
when you would change that field.
""".strip()


def _nullable_string(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


OUTPUT_SCHEMA = strict_json_schema(
    "card_review",
    {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": list(VERDICTS),
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "aspect": {"type": "string"},
                        "explanation": {"type": "string"},
                        "practice_directions": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(PRACTICE_DIRECTIONS)},
                        },
                    },
                    "required": ["aspect", "explanation", "practice_directions"],
                    "additionalProperties": False,
                },
            },
            "suggestions": {
                "type": "object",
                "properties": {
                    "chinese": _nullable_string("Traditional Chinese."),
                    "simplified": _nullable_string("Simplified Chinese."),
                    "pinyin": _nullable_string("Tone-marked pinyin."),
                    "english_basic": _nullable_string("English gloss."),
                    "hsk_level": {
                        "type": ["integer", "null"],
                        "description": "HSK level, or null to keep the current value.",
                    },
                    **{
                        f"example_sentence_{key}": {**spec, "type": ["string", "null"]}
                        for key, spec in EXAMPLE_SENTENCE_PROPERTIES.items()
                    },
                },
                "required": list(SUGGESTION_FIELDS),
                "additionalProperties": False,
            },
        },
        "required": ["verdict", "findings", "suggestions"],
        "additionalProperties": False,
    },
)


class CardReviewNotConfigured(Exception):
    pass


class CardReviewFailed(Exception):
    pass


class FindingSerializer(serializers.Serializer):
    aspect = serializers.CharField(max_length=255)
    explanation = serializers.CharField(max_length=2000)
    practice_directions = serializers.ListField(
        child=serializers.ChoiceField(choices=PRACTICE_DIRECTIONS),
        allow_empty=True,
    )


class SuggestionsSerializer(serializers.Serializer):
    hsk_level = serializers.IntegerField(allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in STRING_FIELDS:
            self.fields[name] = serializers.CharField(
                max_length=Word._meta.get_field(name).max_length,
                allow_null=True,
                allow_blank=True,
            )


class CardReviewResponseSerializer(serializers.Serializer):
    verdict = serializers.ChoiceField(choices=VERDICTS)
    findings = FindingSerializer(many=True)
    suggestions = SuggestionsSerializer()


def _model_allowed(model: str) -> bool:
    lowered = model.lower()
    return bool(model) and not lowered.startswith("openai/") and "luna" not in lowered


def is_card_review_configured() -> bool:
    return bool(settings.OPENROUTER_API_KEY.strip()) and _model_allowed(
        settings.CARD_REVIEW_MODEL.strip()
    )


def review_input(word: Word) -> dict[str, Any]:
    return {
        **{name: getattr(word, name) for name in SUGGESTION_FIELDS},
        "decks": list(word.categories.order_by("name").values_list("name", flat=True)),
    }


def review_card(word: Word) -> dict[str, Any]:
    """Read-only review of a saved word. Never writes."""
    model = settings.CARD_REVIEW_MODEL.strip()
    api_key = settings.OPENROUTER_API_KEY.strip()
    if not model or not api_key:
        raise CardReviewNotConfigured("Card review is not configured.")
    if not _model_allowed(model):
        raise CardReviewNotConfigured("This review model is not allowed.")

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": REVIEW_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(review_input(word), ensure_ascii=False),
                    },
                ],
                "response_format": OUTPUT_SCHEMA,
                "provider": {"allow_fallbacks": False},
            },
            timeout=(5, 45),
        )
    except requests.Timeout as exc:
        raise CardReviewFailed("The review request timed out.") from exc
    except requests.RequestException as exc:
        raise CardReviewFailed("The review provider returned an error.") from exc

    if response.status_code >= 400:
        raise CardReviewFailed("The review provider returned an error.")

    try:
        payload = response.json()
        parsed = parse_chat_json(payload)
    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise CardReviewFailed("The review response was invalid.") from exc

    if payload.get("model") != model:
        raise CardReviewFailed("The review used a different model than configured.")

    serializer = CardReviewResponseSerializer(data=parsed)
    if not serializer.is_valid():
        raise CardReviewFailed("The review response was invalid.")
    return serializer.validated_data
