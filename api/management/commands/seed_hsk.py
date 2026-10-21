from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from api.models import Category, Word, WordCategory

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CARDS = ROOT / "data" / "hsk" / "prepped_cards.json"
REMOTE_CARDS_URL = "https://juzi-data.sfo3.digitaloceanspaces.com/prepped_cards.json"
BATCH_SIZE = 100


def category_name_for_level(level: int) -> str:
    if level == 7:
        return "HSK 7+"
    return f"HSK {level}"


def parse_cards(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise CommandError("Cards data must be a JSON array")

    parsed: list[dict[str, Any]] = []
    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise CommandError(f"cards[{index}] must be an object")

        try:
            level = row["hsk_level"]
            chinese = row["chinese"]
            simplified = row["simplified"]
            pinyin = row["pinyin"]
            english_basic = row["english_basic"]
        except KeyError as exc:
            raise CommandError(f"cards[{index}] missing/invalid fields: {exc}") from exc

        if type(level) is not int or level not in range(1, 8):
            raise CommandError(f"cards[{index}].hsk_level must be an integer from 1 to 7")
        text_fields = (chinese, simplified, pinyin, english_basic)
        if any(not isinstance(value, str) for value in text_fields):
            raise CommandError(f"cards[{index}] text fields must be strings")
        chinese, simplified, pinyin, english_basic = (value.strip() for value in text_fields)
        english_basic = english_basic[:255]
        if not chinese or not simplified or not pinyin or not english_basic:
            raise CommandError(f"cards[{index}] has an empty or invalid required field")

        raw_categories = row.get("categories", [])
        if isinstance(raw_categories, str):
            raw_categories = [raw_categories]
        if not isinstance(raw_categories, list):
            raise CommandError(f"cards[{index}].categories must be a string or array of strings")

        categories: list[str] = []
        for name in raw_categories:
            if not isinstance(name, str) or not name.strip():
                raise CommandError(f"cards[{index}].categories contains an invalid category")
            normalized_name = name.strip()
            if len(normalized_name) > 100:
                raise CommandError(f"cards[{index}] category name exceeds 100 characters")
            if normalized_name not in categories:
                categories.append(normalized_name)

        excluded = row.get("exclude", False)
        if not isinstance(excluded, bool):
            raise CommandError(f"cards[{index}].exclude must be a boolean")

        example_fields = (
            "example_sentence_traditional",
            "example_sentence_simplified",
            "example_sentence_pinyin",
            "example_sentence_english",
        )
        examples: dict[str, str] = {}
        for field in example_fields:
            raw = row.get(field, "")
            if raw is None:
                raw = ""
            if not isinstance(raw, str):
                raise CommandError(f"cards[{index}].{field} must be a string")
            value = raw.strip()
            if len(value) > 255:
                raise CommandError(f"cards[{index}].{field} exceeds 255 characters")
            examples[field] = value

        parsed.append(
            {
                "hsk_level": level,
                "chinese": chinese,
                "simplified": simplified,
                "pinyin": pinyin,
                "english_basic": english_basic,
                "categories": categories,
                "exclude": excluded,
                **examples,
            }
        )
    return parsed


def load_cards(path: Path, url: str | None) -> tuple[list[dict[str, Any]], str]:
    """Prefer the local data file, falling back to the configured remote URL."""
    if path.is_file():
        source = str(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {path}: {exc}") from exc
        return parse_cards(data), source

    if not url:
        raise CommandError(
            f"Cards file not found: {path}. "
            "Set HSK_PREPPED_CARDS_URL or pass --url to use a remote file."
        )

    try:
        response = requests.get(url, timeout=(10, 60))
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise CommandError(f"Remote cards file from {url} is not valid JSON: {exc}") from exc
    except requests.RequestException as exc:
        raise CommandError(f"Could not download cards from {url}: {exc}") from exc

    return parse_cards(data), url


def batches(items: list[Any], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def seed_word_batch(
    cards: list[dict[str, Any]], categories: dict[str, Category]
) -> tuple[int, int, int]:
    """Bulk upsert words and add their category links for one batch of cards.

    Matches existing rows by (chinese, pinyin). Content updates never clear
    archived_at, so imports do not reactivate archived words. Editing a word's
    Chinese or pinyin identity can leave the archived row unmatched and create a
    separate word on the next seed.
    """
    cards_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    category_names_by_key: dict[tuple[str, str], set[str]] = {}
    for row in cards:
        key = (row["chinese"], row["pinyin"])
        cards_by_key[key] = row
        names = category_names_by_key.setdefault(key, set())
        if not row["exclude"]:
            names.add(category_name_for_level(row["hsk_level"]))
        names.update(row["categories"])

    query = Q()
    for chinese, pinyin in cards_by_key:
        query |= Q(chinese=chinese, pinyin=pinyin)
    words_by_key: dict[tuple[str, str], Word] = {}
    # Keep the first matching existing row, as get_or_create() would.
    for word in Word.objects.filter(query).order_by("id"):
        words_by_key.setdefault((word.chinese, word.pinyin), word)

    new_words = [
        Word(
            chinese=key[0],
            pinyin=key[1],
            simplified=row["simplified"],
            english_basic=row["english_basic"],
            hsk_level=row["hsk_level"],
            example_sentence_traditional=row["example_sentence_traditional"],
            example_sentence_simplified=row["example_sentence_simplified"],
            example_sentence_pinyin=row["example_sentence_pinyin"],
            example_sentence_english=row["example_sentence_english"],
        )
        for key, row in cards_by_key.items()
        if key not in words_by_key
    ]
    if new_words:
        Word.objects.bulk_create(new_words, batch_size=BATCH_SIZE)

    # Re-fetch so this works consistently on database backends that don't return
    # primary keys from bulk_create().
    if new_words:
        for word in Word.objects.filter(query).order_by("id"):
            words_by_key.setdefault((word.chinese, word.pinyin), word)

    # New words were added to words_by_key during the re-fetch above.
    new_keys = {(word.chinese, word.pinyin) for word in new_words}
    update_fields = [
        "simplified",
        "english_basic",
        "hsk_level",
        "example_sentence_traditional",
        "example_sentence_simplified",
        "example_sentence_pinyin",
        "example_sentence_english",
    ]
    updated: list[Word] = []
    updated_count = 0
    for key, row in cards_by_key.items():
        word = words_by_key[key]
        if key not in new_keys:
            changed = False
            for field in update_fields:
                if getattr(word, field) != row[field]:
                    setattr(word, field, row[field])
                    changed = True
            if changed:
                updated_count += 1
                updated.append(word)
    if updated:
        Word.objects.bulk_update(updated, update_fields, batch_size=BATCH_SIZE)

    word_ids = {key: words_by_key[key].id for key in cards_by_key}
    links_to_add = {
        (word_ids[key], categories[name].id)
        for key, names in category_names_by_key.items()
        for name in names
    }
    existing_links = set(
        WordCategory.objects.filter(
            word_id__in={word_id for word_id, _ in links_to_add},
            category_id__in={category_id for _, category_id in links_to_add},
        ).values_list("word_id", "category_id")
    )
    missing_links = links_to_add - existing_links
    if missing_links:
        WordCategory.objects.bulk_create(
            [
                WordCategory(word_id=word_id, category_id=category_id)
                for word_id, category_id in missing_links
            ],
            batch_size=BATCH_SIZE,
            ignore_conflicts=True,
        )

    return len(new_words), updated_count, len(missing_links)


class Command(BaseCommand):
    help = "Seed words and HSK/study categories from prepped HSK card data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=Path,
            default=DEFAULT_CARDS,
            help=f"Local prepped cards JSON (default: {DEFAULT_CARDS})",
        )
        parser.add_argument(
            "--url",
            default=None,
            help=f"Remote JSON URL fallback (default: ${REMOTE_CARDS_URL})",
        )

    def handle(self, *args, **options):
        path: Path = options["file"].expanduser().resolve()
        url = options["url"] or os.getenv("HSK_PREPPED_CARDS_URL", REMOTE_CARDS_URL)
        cards, source = load_cards(path, url)

        created_words = 0
        updated_words = 0
        created_links = 0
        used_category_names = {name for row in cards for name in row["categories"]}
        used_category_names.update(
            category_name_for_level(row["hsk_level"]) for row in cards if not row["exclude"]
        )

        with transaction.atomic():
            Category.objects.bulk_create(
                [Category(name=name) for name in used_category_names],
                batch_size=BATCH_SIZE,
                ignore_conflicts=True,
            )
            categories = {
                category.name: category
                for category in Category.objects.filter(name__in=used_category_names)
            }

            for card_batch in batches(cards, BATCH_SIZE):
                new_count, update_count, link_count = seed_word_batch(card_batch, categories)
                created_words += new_count
                updated_words += update_count
                created_links += link_count

        self.stdout.write(
            f"Seeded {len(cards)} cards from {source} across "
            f"{len(used_category_names)} categories: "
            f"created {created_words} words, updated {updated_words}, "
            f"linked {created_links}."
        )
        self.stdout.write(self.style.SUCCESS("Done."))
