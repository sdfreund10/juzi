from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from api.models import Learner, LearnerScore

DAILY_DECAY = Decimal("5")
BASE_POINTS = Decimal("10")
EXTRA_BAND_BONUS = Decimal("0.25")
DEFAULT_SERIES_DAYS = 14
MAX_SERIES_DAYS = 90

BAND_WEIGHT: dict[str, Decimal] = {
    Learner.ProficiencyLevel.NOVICE: Decimal("1"),
    Learner.ProficiencyLevel.INTERMEDIATE: Decimal("1.25"),
    Learner.ProficiencyLevel.ADVANCED: Decimal("1.5"),
    Learner.ProficiencyLevel.EXPERT: Decimal("2"),
}


@dataclass(frozen=True)
class LearnerScorePoint:
    date: date
    score: Decimal


@dataclass(frozen=True)
class LearnerScoreSnapshot:
    score: Decimal
    days: list[LearnerScorePoint]


@dataclass(frozen=True)
class CompletionResult:
    row: LearnerScore
    points: Decimal
    client_id: str


def points_for_difficulties(difficulties: list[str]) -> Decimal:
    """Points for one finished session from its difficulty bands."""
    weights = [BAND_WEIGHT[band] for band in difficulties]
    highest = max(weights)
    extras = len(weights) - 1
    return BASE_POINTS * (highest + EXTRA_BAND_BONUS * extras)


def decayed_score(score: Decimal, *, from_date: date, to_date: date) -> Decimal:
    """Apply flat daily decay from ``from_date`` to ``to_date``, floored at 0."""
    days_between = (to_date - from_date).days
    if days_between <= 0:
        return score
    return max(Decimal("0"), score - DAILY_DECAY * days_between)


def _starting_score_for(user: AbstractBaseUser, on_date: date) -> Decimal:
    previous = LearnerScore.objects.filter(user=user, date__lt=on_date).order_by("-date").first()
    if previous is None:
        return Decimal("0")
    return decayed_score(previous.score, from_date=previous.date, to_date=on_date)


def _points_for_client_id(completions: list, client_id: str) -> Decimal | None:
    for entry in completions:
        if entry.get("client_id") == client_id:
            return Decimal(str(entry["points"]))
    return None


@transaction.atomic
def record_completion(
    *,
    user: AbstractBaseUser,
    difficulties: list[str],
    client_id: str,
) -> CompletionResult:
    """Create or bump today's LearnerScore for a finished deck.

    ``client_id`` makes the write idempotent: a repeated id does not add points again.
    """
    today = timezone.localdate()
    points = points_for_difficulties(difficulties)

    row = LearnerScore.objects.select_for_update().filter(user=user, date=today).first()
    if row is None:
        starting = _starting_score_for(user, today)
        row = LearnerScore.objects.create(
            user=user,
            date=today,
            starting_score=starting,
            score=starting + points,
            completions=[{"client_id": client_id, "points": float(points)}],
        )
        return CompletionResult(row=row, points=points, client_id=client_id)

    existing_points = _points_for_client_id(row.completions, client_id)
    if existing_points is not None:
        return CompletionResult(row=row, points=existing_points, client_id=client_id)

    row.score += points
    row.completions = [
        *row.completions,
        {"client_id": client_id, "points": float(points)},
    ]
    row.save(update_fields=["score", "completions"])
    return CompletionResult(row=row, points=points, client_id=client_id)


def get_learner_score(
    *,
    user: AbstractBaseUser,
    days: int = DEFAULT_SERIES_DAYS,
) -> LearnerScoreSnapshot:
    """Return today's score and a calendar series without writing rows."""
    today = timezone.localdate()
    window = max(1, min(days, MAX_SERIES_DAYS))
    start = today - timedelta(days=window - 1)

    by_date = {
        row.date: row
        for row in LearnerScore.objects.filter(user=user, date__gte=start, date__lte=today)
    }
    # Quiet days at the start of the window still decay from the latest earlier row.
    anchor = LearnerScore.objects.filter(user=user, date__lt=start).order_by("-date").first()

    series: list[LearnerScorePoint] = []
    day = start
    while day <= today:
        if day in by_date:
            anchor = by_date[day]
            series.append(LearnerScorePoint(date=day, score=anchor.score))
        elif anchor is None:
            series.append(LearnerScorePoint(date=day, score=Decimal("0")))
        else:
            series.append(
                LearnerScorePoint(
                    date=day,
                    score=decayed_score(anchor.score, from_date=anchor.date, to_date=day),
                )
            )
        day += timedelta(days=1)

    current = series[-1].score if series else Decimal("0")
    return LearnerScoreSnapshot(score=current, days=series)
