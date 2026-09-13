from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from database import WarDecksRow, get_war_decks, save_war_decks
from river_race import COLOSSEUM, PERIODS_PER_WEEK, TRAINING_DAYS, WAR_DAY, war_day_number

DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class WarPosition:
    week_start: date
    day: int


@dataclass(frozen=True)
class DaySnapshot:
    decks_before: dict[str, int]
    decks_today: dict[str, int]
    members: dict[str, str]
    updated_at: datetime


@dataclass(frozen=True)
class DayDecks:
    by_tag: dict[str, int]
    members: dict[str, str]
    as_of: datetime | None = None


def war_position(data: dict, now: datetime | None = None) -> WarPosition | None:
    if data.get("periodType") not in (WAR_DAY, COLOSSEUM):
        return None
    period_index = data.get("periodIndex", 0)
    moment = now or datetime.now(timezone.utc)
    estimate = (moment - timedelta(days=period_index % PERIODS_PER_WEEK)).date()
    # A race week starts on Monday; the daily reset (~10:00 UTC) can put the estimate a day off either way.
    offset = (estimate.weekday() + 3) % DAYS_PER_WEEK - 3
    return WarPosition(week_start=estimate - timedelta(days=offset), day=war_day_number(period_index))


def war_day_date(week_start: date, day: int) -> date:
    return week_start + timedelta(days=TRAINING_DAYS + day - 1)


def _participants(data: dict) -> dict[str, dict]:
    return {participant.get("tag", ""): participant for participant in data.get("clan", {}).get("participants", [])}


def today_decks(data: dict) -> dict[str, int]:
    return {tag: participant.get("decksUsedToday", 0) for tag, participant in _participants(data).items()}


def store_snapshot(data: dict, members: dict[str, str], now: datetime | None = None) -> WarPosition | None:
    moment = now or datetime.now(timezone.utc)
    position = war_position(data, moment)
    if position is None:
        return None

    # Participants also include players who already left the clan, so membership comes from the member list.
    participants = _participants(data)
    rows = []
    for tag in participants.keys() | members.keys():
        participant = participants.get(tag, {})
        decks_today = participant.get("decksUsedToday", 0)
        rows.append(
            (
                tag,
                members.get(tag) or participant.get("name"),
                participant.get("decksUsed", 0) - decks_today,
                decks_today,
                tag in members,
            )
        )
    save_war_decks(position.week_start.isoformat(), position.day, rows, moment.isoformat(timespec="seconds"))
    return position


def _day_snapshot(rows: list[WarDecksRow]) -> DaySnapshot:
    latest = max(row.updated_at for row in rows)
    return DaySnapshot(
        decks_before={row.player_tag: row.decks_before for row in rows},
        decks_today={row.player_tag: row.decks_today for row in rows},
        # Rows left out of the day's latest snapshot are stale, so only that snapshot says who was in the clan.
        members={
            row.player_tag: row.player_name or row.player_tag
            for row in rows
            if row.in_clan and row.updated_at == latest
        },
        updated_at=datetime.fromisoformat(latest),
    )


def load_week(week_start: date) -> dict[int, DaySnapshot]:
    rows_by_day: dict[int, list[WarDecksRow]] = {}
    for row in get_war_decks(week_start.isoformat()):
        rows_by_day.setdefault(row.war_day, []).append(row)
    return {day: _day_snapshot(rows) for day, rows in rows_by_day.items()}


def decks_for_day(week: dict[int, DaySnapshot], day: int) -> DayDecks | None:
    current, following = week.get(day), week.get(day + 1)
    # decksUsed - decksUsedToday is exact for all earlier days, so any snapshot of the next day settles this one.
    if following is not None and (current is not None or day == 1):
        start = current.decks_before if current else {}
        members = current.members if current else following.members
        return DayDecks({tag: total - start.get(tag, 0) for tag, total in following.decks_before.items()}, members)
    if current is not None:
        return DayDecks(dict(current.decks_today), current.members, as_of=current.updated_at)
    return None
