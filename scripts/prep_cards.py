"""
Take data from data/hsk/cards.json and prep it for use in the app.
Filter out less useful cards, recategorize some cards, and add supporting data.

Usage:
  uv run scripts/prep_cards.py --limit 100
  uv run scripts/prep_cards.py --workers 12
  uv run scripts/prep_cards.py --force
  uv run scripts/prep_cards.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import requests
from dotenv import load_dotenv
from hsk_categories import STUDY_CATEGORIES

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.services.openrouter import (  # noqa: E402
    OPENROUTER_URL,
    example_sentence_schema,
    parse_chat_json,
    strict_json_schema,
)

DEFAULT_IN = ROOT / "data" / "hsk" / "cards.json"
DEFAULT_OUT = ROOT / "data" / "hsk" / "prepped_cards.json"
DEFAULT_LOG_DIR = ROOT / "data" / "hsk" / "logs"


class Card(TypedDict):
    hsk_level: int
    simplified: str
    chinese: str
    pinyin: str
    english_basic: str


ANALYSIS_PROMPT = """
You are a Chinese tutor helping prepare flash cards for a student learning Chinese in Taiwan.
You will be given a Chinese word with basic information from the HSK curriculum.

Your goal is to analyze the word and provide information to help the student learn vocabulary and
understand what matters most for achieving proficiency.

## GUIDELINES
**Meaning**
Meaning should be as concise as possible to convey the meaning of a word.
Favor the provided HSK meaning and only add details if necessary.

**Example Sentence**
The example sentence should use words at the same level or easier than the given word.
Try to use the provided HSK level as a guide for what words to use.
All variants of the example sentence should be equivalent.

**Category**
Choose the single best-fitting topical study category from the allowed enum.
Categories are shared across HSK levels; do not include the HSK level in the category.
Use "Medical Chinese" for vocabulary about symptoms, diagnosis, treatment, and medical care.

**should_exclude**
Some words are given an alternative definition by the HSK curriculum that are not
actually useful for a learner trying to achieve proficiency. Slang or archaic uses
of a word should be excluded from the deck.
Consider the provided HSK level and decide if the word is actually useful for a
learner at that stage.
They may still be included in other categories.
"""

OUTPUT_SCHEMA = strict_json_schema(
    "card_data",
    {
        "type": "object",
        "properties": {
            "meaning": {
                "type": "string",
                "description": "Meaning of the word or phrase in English",
            },
            "example_sentence": example_sentence_schema(),
            "category": {
                "type": "string",
                "description": "The primary study category for this card.",
                "enum": STUDY_CATEGORIES,
            },
            "exclude": {
                "type": "boolean",
                "description": (
                    "Whether the word should be excluded or recategorized from the "
                    "provided HSK category."
                ),
            },
        },
        "required": ["meaning", "example_sentence", "category", "exclude"],
        "additionalProperties": False,
    },
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "openai/gpt-6-luna"


def analyze_card(card: Card) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (analysis, metrics) for one card."""
    int(card["hsk_level"])

    formatted_word = f"""
        Simplified: {card["simplified"]}
        Traditional: {card["chinese"]}
        Pinyin: {card["pinyin"]}
        English: {card["english_basic"]}
        HSK Level: {card["hsk_level"]}
    """
    started = time.perf_counter()
    response = requests.post(
        url=OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": ANALYSIS_PROMPT},
                {"role": "user", "content": formatted_word},
            ],
            "response_format": OUTPUT_SCHEMA,
            "reasoning": {
                "effort": "low",
                "exclude": True,
            },
            "usage": {"include": True},
        },
        timeout=(10, 120),
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    response.raise_for_status()
    payload = response.json()
    try:
        analysis = parse_chat_json(payload)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter response: {payload}") from exc

    usage = payload.get("usage") or {}
    metrics = {
        "ts": datetime.now(UTC).isoformat(),
        "hsk_level": card["hsk_level"],
        "simplified": card["simplified"],
        "chinese": card["chinese"],
        "pinyin": card["pinyin"],
        "model": payload.get("model") or MODEL,
        "generation_id": payload.get("id"),
        "latency_ms": latency_ms,
        "cost": usage.get("cost"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    if analysis.get("category") not in STUDY_CATEGORIES:
        raise ValueError(f"Model returned an invalid category: {analysis.get('category')!r}")
    return analysis, metrics


def append_log(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def prep_row(card: Card, analysis: dict[str, Any]) -> dict[str, Any]:
    """Merge source card + LLM analysis into a ready-to-import row.

    Import hints:
    - exclude: skip linking this word to its HSK level category (may still use categories)
    - categories: extra semantic decks to attach beyond HSK level
    """
    example = analysis["example_sentence"]
    return {
        "hsk_level": card["hsk_level"],
        "simplified": card["simplified"],
        "chinese": card["chinese"],
        "pinyin": card["pinyin"],
        "english_basic": str(analysis["meaning"]).strip()[:255],
        "example_sentence_traditional": example["traditional"],
        "example_sentence_simplified": example["simplified"],
        "example_sentence_pinyin": example["pinyin"],
        "example_sentence_english": example["english"],
        "categories": analysis["category"],
        "exclude": bool(analysis["exclude"]),
    }


def card_key(row: dict[str, Any]) -> tuple[int, str, str, str]:
    """Identity used to resume without re-calling the LLM."""
    return (
        int(row["hsk_level"]),
        str(row["simplified"]),
        str(row["chinese"]),
        str(row["pinyin"]),
    )


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Output file must be a JSON array: {path}")
    return data


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomically write the current card data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def process_pending_cards(
    pending: list[Card],
    rows: list[dict[str, Any]],
    out_path: Path,
    log_path: Path,
    workers: int,
) -> tuple[float, float]:
    """Analyze pending cards concurrently and checkpoint each successful result."""
    total_cost = 0.0
    total_latency_ms = 0.0
    failed_card: Card | None = None
    failure: Exception | None = None
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(analyze_card, card): card for card in pending}
        for future in as_completed(futures):
            card = futures[future]
            if future.cancelled():
                continue

            try:
                analysis, metrics = future.result()
            except Exception as exc:
                if failure is None:
                    failed_card = card
                    failure = exc
                    for other in futures:
                        if other is not future:
                            other.cancel()
                continue

            rows.append(prep_row(card, analysis))
            # Keep completed cards resumable if the run is interrupted or fails.
            write_rows(out_path, rows)
            append_log(log_path, metrics)

            cost = metrics.get("cost")
            if isinstance(cost, (int, float)):
                total_cost += float(cost)
            total_latency_ms += float(metrics["latency_ms"])
            completed += 1
            print(
                f"[{completed}/{len(pending)}] {card['simplified']} ({card['pinyin']}) "
                f"{metrics['latency_ms']}ms cost={cost}"
            )

    if failure is not None and failed_card is not None:
        raise SystemExit(
            f"Failed to analyze {failed_card['simplified']} ({failed_card['pinyin']}, "
            f"HSK {failed_card['hsk_level']}): {failure}. "
            "Successful in-flight cards were saved; rerun to retry unfinished cards."
        )

    return total_cost, total_latency_ms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="in_path",
        type=Path,
        default=DEFAULT_IN,
        help=f"Input cards.json (default: {DEFAULT_IN})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output prepped JSON (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N unprocessed cards (useful for smoke tests)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Number of cards to analyze concurrently (default: 12)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help=f"Directory for per-run JSONL logs (default: {DEFAULT_LOG_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-analyze cards even if already in the output file (replaces matching rows)",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")

    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")

    if not OPENROUTER_API_KEY:
        raise SystemExit("OPENROUTER_API_KEY is not set")

    in_path = args.in_path.expanduser().resolve()
    out_path = args.out.expanduser().resolve()
    log_dir = args.log_dir.expanduser().resolve()
    if not in_path.is_file():
        raise SystemExit(f"Input not found: {in_path}")

    rows = load_rows(out_path)
    done = {card_key(row) for row in rows} if not args.force else set()
    if done:
        print(f"resuming with {len(done)} cards already in {out_path}")

    cards: list[Card] = json.loads(in_path.read_text(encoding="utf-8"))
    if args.limit is not None:
        limited = []
        for card in cards:
            if card_key(card) not in done:
                limited.append(card)
                if len(limited) >= args.limit:
                    break
        cards = limited

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"prep_cards_{run_id}.jsonl"
    pending = [card for card in cards if card_key(card) not in done]

    # --force re-analyzes pending keys: drop existing matches first so appends stay unique.
    if args.force and pending:
        pending_keys = {card_key(card) for card in pending}
        before = len(rows)
        rows = [row for row in rows if card_key(row) not in pending_keys]
        removed = before - len(rows)
        if removed:
            print(f"force: removed {removed} existing row(s) for {len(pending_keys)} card(s)")
            write_rows(out_path, rows)

    total_cost, total_latency_ms = process_pending_cards(
        pending, rows, out_path, log_path, args.workers
    )

    print(
        f"wrote {len(rows)} cards to {out_path} ({len(pending)} newly analyzed); "
        f"run spend=${total_cost:.6f} avg_latency={total_latency_ms / max(len(pending), 1):.1f}ms; "
        f"log={log_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
