from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from django.core.management import call_command

from api.models import Category, Word, WordCategory

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_card_data.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("build_card_data", BUILD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load_build_module()


SAMPLE_ENTRIES = [
    {
        "simplified": "百",
        "forms": [
            {
                "traditional": "百",
                "transcriptions": {"pinyin": "Bǎi"},
                "meanings": ["surname Bai"],
            },
            {
                "traditional": "百",
                "transcriptions": {"pinyin": "bǎi"},
                "meanings": ["hundred; numerous"],
            },
        ],
    },
    {
        "simplified": "看",
        "forms": [
            {
                "traditional": "看",
                "transcriptions": {"pinyin": "kān"},
                "meanings": ["to look after"],
            },
            {
                "traditional": "看",
                "transcriptions": {"pinyin": "kàn"},
                "meanings": ["to see; to look at"],
            },
        ],
    },
    {
        "simplified": "那",
        "forms": [
            {
                "traditional": "那",
                "transcriptions": {"pinyin": "nuó"},
                "meanings": ["(archaic) many", "beautiful"],
            },
            {
                "traditional": "那",
                "transcriptions": {"pinyin": "nà"},
                "meanings": ["(specifier) that; the; those"],
            },
        ],
    },
    {
        "simplified": "北京",
        "forms": [
            {
                "traditional": "北京",
                "transcriptions": {"pinyin": "Běi jīng"},
                "meanings": ["Beijing", "capital of People's Republic of China"],
            },
        ],
    },
    {
        "simplified": "姓",
        "forms": [
            {
                "traditional": "姓",
                "transcriptions": {"pinyin": "xìng"},
                "meanings": ["family name", "surname", "to be surnamed"],
            },
        ],
    },
]


def test_choose_english_basic_joins_until_limit() -> None:
    assert build.choose_english_basic(["to see; to look at", "to read"]) == (
        "to see; to look at; to read"
    )
    assert build.choose_english_basic(["family name", "surname", "to be surnamed"]) == (
        "family name; surname; to be surnamed"
    )
    long = "x" * 200
    assert build.choose_english_basic([long, "y" * 100]) == long
    assert len(build.choose_english_basic(["a" * 300])) == 255


def test_useful_meanings_filters_junk_senses() -> None:
    assert build.useful_meanings(["surname Bai"], "Bǎi") == []
    assert build.useful_meanings(["surname", "family name"], "xìng") == [
        "surname",
        "family name",
    ]
    assert build.useful_meanings(["(archaic) many", "beautiful"], "nuó") == ["beautiful"]
    assert build.useful_meanings(["variant of 哪", "that"], "nǎ") == ["that"]


def test_build_cards_drops_surname_and_explodes_polyphones() -> None:
    cards, dropped = build.build_cards_from_entries(SAMPLE_ENTRIES, level=1)
    # surname-only 百/Bǎi + archaic sense stripped from 那/nuó (kept via "beautiful")
    assert dropped == 1
    pinyins = {(c["chinese"], c["pinyin"]) for c in cards}
    assert ("百", "bǎi") in pinyins
    assert ("百", "Bǎi") not in pinyins
    assert ("看", "kān") in pinyins
    assert ("看", "kàn") in pinyins
    assert ("那", "nà") in pinyins
    assert ("那", "nuó") in pinyins  # kept: non-junk sense "beautiful" remains
    assert ("北京", "Běi jīng") in pinyins  # capitalized proper noun, not a surname
    assert ("姓", "xìng") in pinyins  # literal "surname" gloss, lowercase pinyin
    hundred = next(c for c in cards if c["pinyin"] == "bǎi")
    assert hundred["english_basic"] == "hundred; numerous"
    assert hundred["simplified"] == "百"
    nuo = next(c for c in cards if c["pinyin"] == "nuó")
    assert nuo["english_basic"] == "beautiful"
    xing = next(c for c in cards if c["pinyin"] == "xìng")
    assert xing["english_basic"] == "family name; surname; to be surnamed"


def test_build_card_data_cli_writes_cards_json(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "1.json").write_text(json.dumps(SAMPLE_ENTRIES, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cards.json"

    rc = build.main(["--raw-dir", str(raw), "--out", str(out), "--levels", "1"])
    assert rc == 0
    cards = json.loads(out.read_text(encoding="utf-8"))
    assert len(cards) == 7


@pytest.mark.django_db
def test_seed_hsk_from_cards_file(tmp_path: Path) -> None:
    cards = [
        {
            "hsk_level": 1,
            "simplified": "爱",
            "chinese": "愛",
            "pinyin": "ài",
            "english_basic": "to love",
            "example_sentence_traditional": "我愛喝茶。",
            "example_sentence_simplified": "我爱喝茶。",
            "example_sentence_pinyin": "Wǒ ài hē chá.",
            "example_sentence_english": "I like to drink tea.",
        },
        {
            "hsk_level": 2,
            "simplified": "哥哥",
            "chinese": "哥哥",
            "pinyin": "gē ge",
            "english_basic": "older brother",
        },
    ]
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")

    call_command("seed_hsk", "--file", str(path))

    assert Category.objects.filter(name="HSK 1").exists()
    assert Category.objects.filter(name="HSK 2").exists()
    love = Word.objects.get(chinese="愛", pinyin="ài")
    assert love.simplified == "爱"
    assert love.english_basic == "to love"
    assert love.example_sentence_traditional == "我愛喝茶。"
    assert love.example_sentence_simplified == "我爱喝茶。"
    assert love.example_sentence_pinyin == "Wǒ ài hē chá."
    assert love.example_sentence_english == "I like to drink tea."
    assert WordCategory.objects.filter(word=love, category__name="HSK 1").exists()
    brother = Word.objects.get(chinese="哥哥", pinyin="gē ge")
    assert brother.example_sentence_traditional == ""
    assert WordCategory.objects.filter(word=brother, category__name="HSK 2").exists()

    cards[0]["example_sentence_english"] = "I love drinking tea."
    path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    call_command("seed_hsk", "--file", str(path))
    assert Word.objects.count() == 2
    assert WordCategory.objects.count() == 2
    love.refresh_from_db()
    assert love.example_sentence_english == "I love drinking tea."
