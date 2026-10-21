"""Shared OpenRouter helpers for card prep and Word admin review."""

from __future__ import annotations

import json
from typing import Any

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

EXAMPLE_SENTENCE_PROPERTIES = {
    "traditional": {
        "type": "string",
        "description": "The example sentence in traditional Chinese.",
    },
    "simplified": {
        "type": "string",
        "description": "The example sentence in simplified Chinese.",
    },
    "pinyin": {
        "type": "string",
        "description": "The example sentence in pinyin.",
    },
    "english": {
        "type": "string",
        "description": "The translation of the example sentence in English.",
    },
}


def strict_json_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


def example_sentence_schema(*, nullable: bool = False) -> dict[str, Any]:
    properties = {}
    for key, spec in EXAMPLE_SENTENCE_PROPERTIES.items():
        if nullable:
            properties[key] = {**spec, "type": ["string", "null"]}
        else:
            properties[key] = spec
    return {
        "type": "object",
        "description": "An example sentence using the word",
        "properties": properties,
        "additionalProperties": False,
        "required": list(EXAMPLE_SENTENCE_PROPERTIES),
    }


def parse_chat_json(payload: dict[str, Any]) -> Any:
    return json.loads(payload["choices"][0]["message"]["content"])
