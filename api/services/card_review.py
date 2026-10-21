from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from rest_framework import serializers

from api.models import Word

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 45

VERDICTS = ("no_clear_issue", "issues_found", "needs_human_review")
PRACTICE_DIRECTIONS = ("pinyin_to_en", "en_to_zh", "zh_to_en")
SUGGESTION_FIELDS = (
    "chinese",
    "simplified",
    "pinyin",
    "english_basic",
    "hsk_level",
    "example_sentence_traditional",
    "example_sentence_simplified",
    "example_sentence_pinyin",
    "example_sentence_english",
)

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


def _string_or_null_schema(*, description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "card_review",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": list(VERDICTS),
                    "description": "Overall review outcome.",
                },
                "findings": {
                    "type": "array",
                    "description": "Explained issues. Empty when there is no clear issue.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "aspect": {
                                "type": "string",
                                "description": "What part of the card the finding is about.",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Why this is a problem for an operator.",
                            },
                            "practice_directions": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": list(PRACTICE_DIRECTIONS),
                                },
                                "description": "Practice directions this finding affects.",
                            },
                        },
                        "required": ["aspect", "explanation", "practice_directions"],
                        "additionalProperties": False,
                    },
                },
                "suggestions": {
                    "type": "object",
                    "description": "Replacement values, or null to keep the current value.",
                    "properties": {
                        "chinese": _string_or_null_schema(description="Traditional Chinese."),
                        "simplified": _string_or_null_schema(description="Simplified Chinese."),
                        "pinyin": _string_or_null_schema(description="Tone-marked pinyin."),
                        "english_basic": _string_or_null_schema(description="English gloss."),
                        "hsk_level": {
                            "type": ["integer", "null"],
                            "description": "HSK level, or null to keep the current value.",
                        },
                        "example_sentence_traditional": _string_or_null_schema(
                            description="Example sentence in traditional Chinese."
                        ),
                        "example_sentence_simplified": _string_or_null_schema(
                            description="Example sentence in simplified Chinese."
                        ),
                        "example_sentence_pinyin": _string_or_null_schema(
                            description="Example sentence in pinyin."
                        ),
                        "example_sentence_english": _string_or_null_schema(
                            description="Example sentence in English."
                        ),
                    },
                    "required": list(SUGGESTION_FIELDS),
                    "additionalProperties": False,
                },
            },
            "required": ["verdict", "findings", "suggestions"],
            "additionalProperties": False,
        },
    },
}


class CardReviewError(Exception):
    """Operator-facing card review failure."""


class CardReviewNotConfigured(CardReviewError):
    pass


class CardReviewFailed(CardReviewError):
    pass


@dataclass(frozen=True)
class CardReviewFinding:
    aspect: str
    explanation: str
    practice_directions: list[str]


@dataclass(frozen=True)
class CardReviewResult:
    verdict: str
    findings: list[CardReviewFinding]
    suggestions: dict[str, str | int | None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "findings": [
                {
                    "aspect": finding.aspect,
                    "explanation": finding.explanation,
                    "practice_directions": finding.practice_directions,
                }
                for finding in self.findings
            ],
            "suggestions": self.suggestions,
        }


def _field_max_length(name: str) -> int:
    max_length = Word._meta.get_field(name).max_length
    if max_length is None:
        raise RuntimeError(f"Word.{name} is missing max_length")
    return max_length


class FindingSerializer(serializers.Serializer):
    aspect = serializers.CharField(max_length=255)
    explanation = serializers.CharField(max_length=2000)
    practice_directions = serializers.ListField(
        child=serializers.ChoiceField(choices=PRACTICE_DIRECTIONS),
        allow_empty=True,
    )


class SuggestionsSerializer(serializers.Serializer):
    chinese = serializers.CharField(
        max_length=_field_max_length("chinese"), allow_null=True, allow_blank=True
    )
    simplified = serializers.CharField(
        max_length=_field_max_length("simplified"), allow_null=True, allow_blank=True
    )
    pinyin = serializers.CharField(
        max_length=_field_max_length("pinyin"), allow_null=True, allow_blank=True
    )
    english_basic = serializers.CharField(
        max_length=_field_max_length("english_basic"), allow_null=True, allow_blank=True
    )
    hsk_level = serializers.IntegerField(allow_null=True)
    example_sentence_traditional = serializers.CharField(
        max_length=_field_max_length("example_sentence_traditional"),
        allow_null=True,
        allow_blank=True,
    )
    example_sentence_simplified = serializers.CharField(
        max_length=_field_max_length("example_sentence_simplified"),
        allow_null=True,
        allow_blank=True,
    )
    example_sentence_pinyin = serializers.CharField(
        max_length=_field_max_length("example_sentence_pinyin"),
        allow_null=True,
        allow_blank=True,
    )
    example_sentence_english = serializers.CharField(
        max_length=_field_max_length("example_sentence_english"),
        allow_null=True,
        allow_blank=True,
    )


class CardReviewResponseSerializer(serializers.Serializer):
    verdict = serializers.ChoiceField(choices=VERDICTS)
    findings = FindingSerializer(many=True)
    suggestions = SuggestionsSerializer()


def _configured_model() -> str:
    return str(getattr(settings, "CARD_REVIEW_MODEL", "") or "").strip()


def _api_key() -> str:
    return str(getattr(settings, "OPENROUTER_API_KEY", "") or "").strip()


def is_model_allowed(model_id: str) -> bool:
    lowered = model_id.lower()
    if not model_id.strip():
        return False
    if lowered.startswith("openai/"):
        return False
    return "luna" not in lowered


def is_card_review_configured() -> bool:
    return bool(_api_key()) and is_model_allowed(_configured_model())


def review_input(word: Word) -> dict[str, Any]:
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
        "decks": list(word.categories.order_by("name").values_list("name", flat=True)),
    }


def _require_configured_model() -> str:
    model = _configured_model()
    if not model or not _api_key():
        raise CardReviewNotConfigured("Card review is not configured.")
    if not is_model_allowed(model):
        raise CardReviewNotConfigured("This review model is not allowed.")
    return model


def _parse_message_content(payload: dict[str, Any]) -> Any:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CardReviewFailed("The review response was invalid.") from exc
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise CardReviewFailed("The review response was invalid.")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise CardReviewFailed("The review response was invalid.") from exc


def _result_from_parsed(parsed: Any) -> CardReviewResult:
    serializer = CardReviewResponseSerializer(data=parsed)
    if not serializer.is_valid():
        raise CardReviewFailed("The review response was invalid.")
    data = serializer.validated_data
    return CardReviewResult(
        verdict=data["verdict"],
        findings=[
            CardReviewFinding(
                aspect=item["aspect"],
                explanation=item["explanation"],
                practice_directions=list(item["practice_directions"]),
            )
            for item in data["findings"]
        ],
        suggestions={field: data["suggestions"][field] for field in SUGGESTION_FIELDS},
    )


def review_card(word: Word) -> CardReviewResult:
    """Read-only review of a saved word. Never writes."""
    model = _require_configured_model()
    body = {
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
    }
    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {_api_key()}"},
            json=body,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
    except requests.Timeout as exc:
        raise CardReviewFailed("The review request timed out.") from exc
    except requests.RequestException as exc:
        raise CardReviewFailed("The review provider returned an error.") from exc

    if response.status_code >= 500:
        raise CardReviewFailed("The review provider returned an error.")
    if response.status_code >= 400:
        raise CardReviewFailed("The review provider returned an error.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise CardReviewFailed("The review response was invalid.") from exc

    if payload.get("model") != model:
        raise CardReviewFailed("The review used a different model than configured.")

    return _result_from_parsed(_parse_message_content(payload))
