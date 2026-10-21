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

REVIEW_MODEL = "anthropic/claude-sonnet-4.5"
VERDICTS = ("no_clear_issue", "issues_found", "remove", "needs_human_review")
DICTIONARY_FIELDS = ("chinese", "simplified", "pinyin")
SUGGESTION_FIELDS = (
    "english_basic",
    *(f"example_sentence_{key}" for key in EXAMPLE_SENTENCE_PROPERTIES),
)

REVIEW_PROMPT = """
You review vocabulary cards for an app to practice traditional Chinese as used in Taiwan.

Each card has a word or phrase from the HSK dictionary in traditional Chinese,
simplified Chinese, and pinyin. These dictionary fields are fixed: never suggest
changes to them.
Each card also has an English meaning and an example sentence in traditional
Chinese, simplified Chinese, pinyin, and English. These fields can be changed.

Review:
- whether the English meaning is accurate and concise
- whether the four example-sentence fields say the same thing
- whether the example is natural traditional Chinese as used in Taiwan
- whether any practice direction is ambiguous

Use the "remove" verdict when the word or phrase itself is uncommon in Taiwan at the given HSK level
Explain why in the findings and eave every suggestion null.

Value brevity in your analysis.
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
                    },
                    "required": ["aspect", "explanation"],
                    "additionalProperties": False,
                },
            },
            "suggestions": {
                "type": "object",
                "properties": {
                    "english_basic": _nullable_string("English gloss."),
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


class CardReviewFailed(Exception):
    pass


class FindingSerializer(serializers.Serializer):
    aspect = serializers.CharField(max_length=255)
    explanation = serializers.CharField(max_length=2000)


class SuggestionsSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in SUGGESTION_FIELDS:
            self.fields[name] = serializers.CharField(
                max_length=Word._meta.get_field(name).max_length,
                allow_null=True,
                allow_blank=True,
            )


class CardReviewResponseSerializer(serializers.Serializer):
    verdict = serializers.ChoiceField(choices=VERDICTS)
    findings = FindingSerializer(many=True)
    suggestions = SuggestionsSerializer()


def review_input(word: Word) -> dict[str, Any]:
    return {
        **{name: getattr(word, name) for name in (*DICTIONARY_FIELDS, *SUGGESTION_FIELDS)},
        "hsk_level": word.hsk_level,
        "decks": list(word.categories.order_by("name").values_list("name", flat=True)),
    }


def review_card(word: Word) -> dict[str, Any]:
    """Read-only review of a saved word. Never writes."""
    api_key = settings.OPENROUTER_API_KEY.strip()
    if not api_key:
        raise CardReviewFailed("Card review is not configured.")

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": REVIEW_MODEL,
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

    if payload.get("model") != REVIEW_MODEL:
        raise CardReviewFailed("The review used a different model than configured.")

    serializer = CardReviewResponseSerializer(data=parsed)
    if not serializer.is_valid():
        raise CardReviewFailed("The review response was invalid.")
    return serializer.validated_data
