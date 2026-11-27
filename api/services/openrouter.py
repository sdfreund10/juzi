"""Shared OpenRouter client and chat-schema helpers.

App code posts through ``post_json``. The card-prep scripts import the schema
helpers and send their own requests, because they run without Django.
"""

from __future__ import annotations

import json
from typing import Any

import requests
from django.conf import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(Exception):
    """OpenRouter did not return a JSON body."""


class OpenRouterKeyMissing(OpenRouterError):
    """OPENROUTER_API_KEY is blank."""


class OpenRouterTimeout(OpenRouterError):
    """The request exceeded its timeout."""


class OpenRouterRequestFailed(OpenRouterError):
    """The connection failed or the status was not 200."""


class OpenRouterResponseInvalid(OpenRouterError):
    """The body was not JSON."""


def require_openrouter_key() -> str:
    key = settings.OPENROUTER_API_KEY.strip()
    if not key:
        raise OpenRouterKeyMissing("OPENROUTER_API_KEY is not set.")
    return key


def post_json(url: str, body: dict[str, Any], *, timeout: tuple[float, float]) -> Any:
    """POST a JSON body and return the decoded JSON.

    Raises an OpenRouterError subclass. Callers turn that into their own error.
    """
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {require_openrouter_key()}"},
            json=body,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise OpenRouterTimeout("The OpenRouter request timed out.") from exc
    except requests.RequestException as exc:
        raise OpenRouterRequestFailed("The OpenRouter request failed.") from exc

    if response.status_code != 200:
        raise OpenRouterRequestFailed("The OpenRouter request failed.")

    try:
        return response.json()
    except ValueError as exc:
        raise OpenRouterResponseInvalid("The OpenRouter response was not JSON.") from exc


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
