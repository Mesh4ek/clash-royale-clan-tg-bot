from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import war_days
from war_days import DayDecks, DaySnapshot, WarPosition

UTC = timezone.utc
WEEK = date(2026, 9, 7)


def race(period_index, decks, period_type="warDay"):
    participants = [
        {"tag": tag, "name": tag.strip("#").title(), "decksUsed": before + today, "decksUsedToday": today}
        for tag, (before, today) in decks.items()
    ]
    return {"periodType": period_type, "periodIndex": period_index, "clan": {"participants": participants}}


def snapshot(before, today=None, members=None, hour=12):
    return DaySnapshot(
        decks_before=before,
        decks_today=today or {},
        members=members or {},
        updated_at=datetime(2026, 9, 10, hour, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("moment", "period_index", "period_type", "expected"),
    [
        (datetime(2026, 9, 13, 8, 8, tzinfo=UTC), 5, "warDay", WarPosition(WEEK, 3)),
        (datetime(2026, 9, 10, 9, 55, tzinfo=UTC), 3, "warDay", WarPosition(WEEK, 1)),
        (datetime(2026, 9, 14, 9, 40, tzinfo=UTC), 6, "warDay", WarPosition(WEEK, 4)),
        (datetime(2026, 9, 17, 10, 5, tzinfo=UTC), 3, "colosseum", WarPosition(date(2026, 9, 14), 1)),
        (datetime(2026, 9, 15, 12, 0, tzinfo=UTC), 1, "training", None),
    ],
)
def test_war_position(moment, period_index, period_type, expected):
    data = {"periodType": period_type, "periodIndex": period_index}
    assert war_days.war_position(data, moment) == expected


def test_war_day_one_is_thursday():
    assert war_days.war_day_date(WEEK, 1) == date(2026, 9, 10)
    assert war_days.war_day_date(WEEK, 4) == date(2026, 9, 13)


def test_today_decks():
    assert war_days.today_decks(race(5, {"#A": (4, 2)})) == {"#A": 2}


def test_next_day_snapshot_gives_exact_decks():
    week = {
        1: snapshot({}, members={"#A": "A", "#B": "B"}),
        2: snapshot({"#A": 4, "#B": 1}),
        3: snapshot({"#A": 6, "#B": 1}),
    }
    assert war_days.decks_for_day(week, 1) == DayDecks({"#A": 4, "#B": 1}, {"#A": "A", "#B": "B"})
    assert war_days.decks_for_day(week, 2).by_tag == {"#A": 2, "#B": 0}


def test_day_one_needs_only_the_next_snapshot():
    week = {2: snapshot({"#A": 3}, members={"#A": "A"})}
    assert war_days.decks_for_day(week, 1) == DayDecks({"#A": 3}, {"#A": "A"})


def test_last_snapshot_of_the_day_is_used_when_the_next_day_is_missing():
    week = {2: snapshot({"#A": 4}, today={"#A": 1}, members={"#A": "A"}, hour=15)}
    decks = war_days.decks_for_day(week, 2)
    assert decks.by_tag == {"#A": 1}
    assert decks.as_of == datetime(2026, 9, 10, 15, tzinfo=UTC)


def test_day_without_snapshots_has_no_data():
    week = {3: snapshot({"#A": 6})}
    assert war_days.decks_for_day(week, 2) is None
    assert war_days.decks_for_day(week, 4) is None


def test_snapshots_round_trip_with_clan_membership():
    noon = datetime(2026, 9, 10, 12, tzinfo=UTC)
    evening = datetime(2026, 9, 10, 20, tzinfo=UTC)
    next_day = datetime(2026, 9, 11, 15, tzinfo=UTC)
    # Ghost is in the clan at noon but gone by the evening; Left leaves the clan on day 2 but stays a participant.
    war_days.store_snapshot(
        race(3, {"#A": (0, 3), "#LEFT": (0, 1)}), {"#A": "A", "#LEFT": "Left", "#GHOST": "Ghost"}, noon
    )
    war_days.store_snapshot(
        race(3, {"#A": (0, 4), "#LEFT": (0, 1)}), {"#A": "A", "#LEFT": "Left", "#NEW": "New"}, evening
    )
    war_days.store_snapshot(race(4, {"#A": (4, 0), "#LEFT": (1, 0)}), {"#A": "A", "#NEW": "New"}, next_day)

    day_one = war_days.decks_for_day(war_days.load_week(WEEK), 1)

    assert day_one.members == {"#A": "A", "#LEFT": "Left", "#NEW": "New"}
    assert day_one.by_tag == {"#A": 4, "#LEFT": 1, "#NEW": 0}


def test_training_days_are_not_stored():
    assert war_days.store_snapshot(race(1, {"#A": (0, 0)}, "training"), {"#A": "A"}) is None
    assert war_days.load_week(WEEK) == {}
