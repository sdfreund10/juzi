import math

import requests

from api.models import Word

MODEL_NAME = "openai/text-embedding-3-small"
DIMENSIONS = 1536


def word_embedding_text(word: Word) -> str:
    return f"Chinese: {word.chinese}\nMeaning: {word.english_basic}"


def generate_vectors(
    api_key: str,
    texts: list[str],
    *,
    timeout: tuple[float, float] = (10, 60),
) -> list[list[float]]:
    response = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL_NAME,
            "input": texts,
            "encoding_format": "float",
            "dimensions": DIMENSIONS,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or len(data) != len(texts):
        raise ValueError("OpenRouter returned an unexpected number of embeddings")

    # Match by response index: providers may return entries out of order.
    vectors = {}
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("OpenRouter returned an invalid embedding entry")
        index = entry.get("index")
        vector = entry.get("embedding")
        if type(index) is not int or index not in range(len(texts)) or index in vectors:
            raise ValueError("OpenRouter returned invalid embedding indices")
        if (
            not isinstance(vector, list)
            or len(vector) != DIMENSIONS
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
        ):
            raise ValueError("OpenRouter returned an invalid embedding vector")
        vectors[index] = vector

    return [vectors[index] for index in range(len(texts))]
