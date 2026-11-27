"""Live checks for the deck-pick model.

Each case calls ``_select_ids`` and keeps the ids ``_saved_ids`` would store.
Nothing is written to the database. The literal system prompt is not read.

Latency is the wall time of that pick. ``belonging_excluded`` is the share of
cards that belong which the pick left out. ``unrelated_selected`` is the share
of the saved deck whose cards do not belong. An empty deck scores 0 on the
second rate.

One case runs every check before it fails: saved size, every belonging card
included, every unrelated card excluded, and the name when the case has one.
The misses are reported together. A pass still requires both rates at 0, the
required size, and a fitting name when the case checks it.

CI does not run these cases (``pytest -m "not deck_eval"``). Run them locally
with the key in the environment or ``.env``:

    uv run pytest api/tests/test_deck_evals.py -m deck_eval
"""

from __future__ import annotations

import time

import pytest
from django.conf import settings

from api.services.decks import DeckUnavailable, _saved_ids, _select_ids

Row = tuple[str, str, str]


class Card:
    def __init__(
        self,
        *,
        card_id: int,
        chinese: str,
        pinyin: str,
        english: str,
        hsk_level: int,
        belongs: bool,
    ) -> None:
        self.id = card_id
        self.chinese = chinese
        self.pinyin = pinyin
        self.english = english
        self.hsk_level = hsk_level
        self.belongs = belongs


# Short restaurant words, then words that are not about ordering food.
FOOD: tuple[Row, ...] = (
    ("茶", "chá", "tea"),
    ("飯", "fàn", "rice"),
    ("麵", "miàn", "noodles"),
    ("菜", "cài", "vegetable"),
    ("肉", "ròu", "meat"),
    ("魚", "yú", "fish"),
    ("雞", "jī", "chicken"),
    ("湯", "tāng", "soup"),
    ("鹽", "yán", "salt"),
    ("糖", "táng", "sugar"),
    ("油", "yóu", "oil"),
    ("煮", "zhǔ", "to boil"),
    ("炒", "chǎo", "to stir-fry"),
    ("吃", "chī", "to eat"),
    ("喝", "hē", "to drink"),
    ("碗", "wǎn", "bowl"),
    ("筷子", "kuàizi", "chopsticks"),
    ("菜單", "càidān", "menu"),
    ("餓", "è", "hungry"),
    ("味道", "wèidao", "flavor"),
    ("早餐", "zǎocān", "breakfast"),
    ("午餐", "wǔcān", "lunch"),
    ("晚餐", "wǎncān", "dinner"),
    ("水果", "shuǐguǒ", "fruit"),
    ("蘋果", "píngguǒ", "apple"),
    ("水", "shuǐ", "water"),
    ("咖啡", "kāfēi", "coffee"),
    ("甜點", "tiándiǎn", "dessert"),
    ("辣", "là", "spicy"),
    ("新鮮", "xīnxiān", "fresh"),
)

POOR: tuple[Row, ...] = (
    ("飛機", "fēijī", "airplane"),
    ("機場", "jīchǎng", "airport"),
    ("護照", "hùzhào", "passport"),
    ("火車", "huǒchē", "train"),
    ("車票", "chēpiào", "train ticket"),
    ("數學", "shùxué", "mathematics"),
    ("物理", "wùlǐ", "physics"),
    ("化學", "huàxué", "chemistry"),
    ("電腦", "diànnǎo", "computer"),
    ("鍵盤", "jiànpán", "keyboard"),
    ("滑鼠", "huáshǔ", "computer mouse"),
    ("律師", "lǜshī", "lawyer"),
    ("法院", "fǎyuàn", "court"),
    ("法官", "fǎguān", "judge"),
    ("股票", "gǔpiào", "stock share"),
    ("銀行", "yínháng", "bank"),
    ("利息", "lìxī", "interest"),
    ("醫院", "yīyuàn", "hospital"),
    ("手術", "shǒushù", "surgery"),
    ("藥", "yào", "medicine"),
    ("醫生", "yīshēng", "doctor"),
    ("護士", "hùshi", "nurse"),
    ("足球", "zúqiú", "soccer"),
    ("籃球", "lánqiú", "basketball"),
    ("鋼琴", "gāngqín", "piano"),
    ("小提琴", "xiǎotíqín", "violin"),
    ("山", "shān", "mountain"),
    ("海", "hǎi", "ocean"),
    ("天氣", "tiānqì", "weather"),
    ("雲", "yún", "cloud"),
    ("雨", "yǔ", "rain"),
    ("雪", "xuě", "snow"),
    ("電", "diàn", "electricity"),
    ("電池", "diànchí", "battery"),
    ("引擎", "yǐnqíng", "engine"),
    ("輪胎", "lúntāi", "tire"),
    ("橋", "qiáo", "bridge"),
    ("高速公路", "gāosùgōnglù", "highway"),
    ("博物館", "bówùguǎn", "museum"),
    ("畫", "huà", "painting"),
    ("小說", "xiǎoshuō", "novel"),
    ("詩", "shī", "poem"),
    ("選舉", "xuǎnjǔ", "election"),
    ("總統", "zǒngtǒng", "president"),
    ("士兵", "shìbīng", "soldier"),
    ("武器", "wǔqì", "weapon"),
    ("行星", "xíngxīng", "planet"),
    ("望遠鏡", "wàngyuǎnjìng", "telescope"),
    ("軟體", "ruǎntǐ", "software"),
    ("電子郵件", "diànzǐyóujiàn", "email"),
)

WEDDING: tuple[Row, ...] = (
    ("父母", "fùmǔ", "parents"),
    ("結婚", "jiéhūn", "wedding"),
    ("春天", "chūntiān", "spring"),
    ("台北", "Táiběi", "Taipei"),
    ("家庭", "jiātíng", "family"),
)

RESTAURANT = "ordering food at a restaurant"
WEDDING_PROMPT = "I need words for talking to my parents about a wedding next spring in Taipei"


def _live(reason: str):
    missing = not settings.OPENROUTER_API_KEY.strip()
    return pytest.mark.skipif(missing, reason=reason)


live = _live("Set OPENROUTER_API_KEY, then: uv run pytest api/tests/test_deck_evals.py")


def cards_from(*groups: tuple[tuple[Row, ...], bool]) -> list[Card]:
    rows: list[tuple[Row, bool]] = []
    for group, belongs in groups:
        rows.extend((row, belongs) for row in group)
    return [
        Card(
            card_id=index + 1,
            chinese=chinese,
            pinyin=pinyin,
            english=english,
            hsk_level=(index % 6) + 1,
            belongs=belongs,
        )
        for index, ((chinese, pinyin, english), belongs) in enumerate(rows)
    ]


def restaurant(belonging: int, poor: int) -> list[Card]:
    return cards_from((FOOD[:belonging], True), (POOR[:poor], False))


def score_pick(
    belonging: set[int], outsiders: set[int], selected: list[int]
) -> tuple[float, float]:
    """Return (belonging_excluded, unrelated_selected)."""
    chosen = set(selected)
    belonging_excluded = len(belonging - chosen) / len(belonging)
    unrelated_selected = len(chosen & outsiders) / len(chosen) if chosen else 0.0
    return belonging_excluded, unrelated_selected


def name_fits(name: str, prompt: str, hints: tuple[str, ...]) -> bool:
    """A short title that is not the prompt and mentions the situation."""
    title = " ".join(name.split()).casefold()
    source = " ".join(prompt.split()).casefold()
    if not title or title == source or len(title) > 60:
        return False
    return any(hint.casefold() in title for hint in hints)


def _candidate(card: Card) -> dict[str, object]:
    return {
        "id": card.id,
        "chinese": card.chinese,
        "pinyin": card.pinyin,
        "english_basic": card.english,
        "hsk_level": card.hsk_level,
        "topic": "",
    }


def run_case(label: str, prompt: str, size: int, deck: list[Card]):
    started = time.perf_counter()
    try:
        returned, name = _select_ids(prompt, size, [_candidate(card) for card in deck])
        selected = _saved_ids(returned, {card.id for card in deck}, size)
    except DeckUnavailable as exc:
        elapsed = time.perf_counter() - started
        raise AssertionError(f"deck eval case={label} failed after {elapsed:.3f}s") from exc
    elapsed = time.perf_counter() - started
    belonging = {card.id for card in deck if card.belongs}
    outsiders = {card.id for card in deck if not card.belongs}
    excluded, unrelated = score_pick(belonging, outsiders, selected)
    chosen = set(selected)
    print(
        "deck eval "
        f"case={label} "
        f"latency_s={elapsed:.3f} "
        f"belonging_excluded={excluded:.3f} "
        f"({len(belonging - chosen)}/{len(belonging)}) "
        f"unrelated_selected={unrelated:.3f} "
        f"({len(chosen & outsiders)}/{len(selected)}) "
        f"selected={len(selected)} "
        f"name={name}"
    )
    return selected, name, outsiders


def test_case_sizes_match_the_requests() -> None:
    thirty = restaurant(20, 10)
    assert len(thirty) == 30
    assert sum(card.belongs for card in thirty) == 20
    wide = restaurant(30, 50)
    assert len(wide) == 80
    assert sum(not card.belongs for card in wide) > 40


def test_score_counts_missed_belonging_cards_and_selected_outsiders() -> None:
    excluded, unrelated = score_pick({1, 2, 3, 4}, {5, 6}, [1, 5])
    assert excluded == 0.75
    assert unrelated == 0.5
    excluded, unrelated = score_pick({1, 2}, {3}, [])
    assert excluded == 1.0
    assert unrelated == 0.0


def test_name_check_accepts_a_short_hint_and_rejects_the_prompt() -> None:
    prompt = RESTAURANT
    assert name_fits("Restaurant food", prompt, ("food", "restaurant"))
    assert not name_fits(prompt, prompt, ("food", "restaurant"))
    assert not name_fits("Airport words", prompt, ("food", "restaurant"))


def require_perfect(
    label: str,
    *,
    prompt: str,
    deck: list[Card],
    selected: list[int],
    name: str,
    outsiders: set[int],
    required_size: int,
    hints: tuple[str, ...] | None = None,
) -> None:
    """Run every check for one case, then report every miss together."""
    belonging = {card.id for card in deck if card.belongs}
    chosen = set(selected)
    excluded, unrelated = score_pick(belonging, outsiders, selected)
    problems: list[str] = []
    if len(selected) != required_size:
        problems.append(f"saved={len(selected)} required_size={required_size}")
    if excluded != 0:
        left_out = len(belonging - chosen)
        problems.append(f"belonging_excluded={excluded:.3f} ({left_out}/{len(belonging)})")
    if unrelated != 0:
        kept = len(chosen & outsiders)
        problems.append(f"unrelated_selected={unrelated:.3f} ({kept}/{len(selected)})")
    if hints is not None and not name_fits(name, prompt, hints):
        problems.append(f"name={name!r}")
    if not problems:
        return
    message = f"deck eval case={label} imperfect " + "; ".join(problems)
    print(message)
    raise AssertionError(message)


def test_a_perfect_pick_passes() -> None:
    deck = restaurant(2, 2)
    outsiders = {card.id for card in deck if not card.belongs}
    require_perfect(
        "perfect",
        prompt=RESTAURANT,
        deck=deck,
        selected=[1, 2],
        name="Restaurant food",
        outsiders=outsiders,
        required_size=2,
        hints=("food", "restaurant"),
    )


@pytest.mark.parametrize(
    ("selected", "required_size", "name", "hints", "match"),
    [
        ([1], 2, "Restaurant food", ("food", "restaurant"), "belonging_excluded=0.500"),
        ([1, 2, 3], 2, "Restaurant food", ("food", "restaurant"), "unrelated_selected=0.333"),
        ([1, 2], 3, "Restaurant food", ("food", "restaurant"), "required_size=3"),
        ([1, 2], 2, RESTAURANT, ("food", "restaurant"), "name="),
    ],
)
def test_an_imperfect_pick_fails_and_logs_the_miss(
    selected: list[int],
    required_size: int,
    name: str,
    hints: tuple[str, ...] | None,
    match: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deck = restaurant(2, 2)
    outsiders = {card.id for card in deck if not card.belongs}
    with pytest.raises(AssertionError, match=match):
        require_perfect(
            "sample",
            prompt=RESTAURANT,
            deck=deck,
            selected=selected,
            name=name,
            outsiders=outsiders,
            required_size=required_size,
            hints=hints,
        )
    assert match in capsys.readouterr().out


def test_an_imperfect_pick_logs_every_miss_together(capsys: pytest.CaptureFixture[str]) -> None:
    deck = restaurant(2, 2)
    outsiders = {card.id for card in deck if not card.belongs}
    with pytest.raises(AssertionError) as failure:
        require_perfect(
            "sample",
            prompt=RESTAURANT,
            deck=deck,
            selected=[1, 3],
            name=RESTAURANT,
            outsiders=outsiders,
            required_size=3,
            hints=("food",),
        )
    message = str(failure.value)
    assert "saved=2 required_size=3" in message
    assert "belonging_excluded=0.500" in message
    assert "unrelated_selected=0.500" in message
    assert "name=" in message
    assert message in capsys.readouterr().out


@live
@pytest.mark.deck_eval
def test_twenty_card_request_saves_the_twenty_food_cards() -> None:
    deck = restaurant(20, 10)
    selected, name, outsiders = run_case("size-20", RESTAURANT, 20, deck)
    require_perfect(
        "size-20",
        prompt=RESTAURANT,
        deck=deck,
        selected=selected,
        name=name,
        outsiders=outsiders,
        required_size=20,
    )


@live
@pytest.mark.deck_eval
def test_forty_card_request_saves_the_twenty_food_cards() -> None:
    deck = restaurant(20, 10)
    selected, name, outsiders = run_case("size-40", RESTAURANT, 40, deck)
    require_perfect(
        "size-40",
        prompt=RESTAURANT,
        deck=deck,
        selected=selected,
        name=name,
        outsiders=outsiders,
        required_size=20,
    )


@live
@pytest.mark.deck_eval
def test_sixty_card_request_saves_the_thirty_food_cards() -> None:
    deck = restaurant(30, 50)
    selected, name, outsiders = run_case("size-60", RESTAURANT, 60, deck)
    require_perfect(
        "size-60",
        prompt=RESTAURANT,
        deck=deck,
        selected=selected,
        name=name,
        outsiders=outsiders,
        required_size=30,
    )


@live
@pytest.mark.deck_eval
@pytest.mark.parametrize(
    ("label", "prompt", "hints", "deck"),
    [
        (
            "name-wedding",
            WEDDING_PROMPT,
            ("parent", "wedding", "family", "spring", "taipei"),
            cards_from((WEDDING, True), (POOR[:2], False)),
        ),
        (
            "name-restaurant",
            RESTAURANT,
            ("food", "restaurant", "dining", "meal", "order"),
            cards_from((FOOD[:6], True), (POOR[:2], False)),
        ),
    ],
)
def test_the_deck_name_condenses_the_prompt(label, prompt, hints, deck) -> None:
    selected, name, outsiders = run_case(label, prompt, 20, deck)
    require_perfect(
        label,
        prompt=prompt,
        deck=deck,
        selected=selected,
        name=name,
        outsiders=outsiders,
        required_size=sum(card.belongs for card in deck),
        hints=hints,
    )
