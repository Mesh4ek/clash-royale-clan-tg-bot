from __future__ import annotations

from datetime import datetime, timezone

import pytest

import river_race
from river_race import CLAN_DECKS_PER_DAY, ClanScore

OUR_TAG = "#CLAN"


def participant(decks_today=0, decks_used=0, fame=0):
    return {"decksUsedToday": decks_today, "decksUsed": decks_used, "fame": fame}


def race_clan(tag, name, *, fame, period_points, decks_today):
    participants = [participant(decks) for decks in decks_today]
    return {"tag": tag, "name": name, "fame": fame, "periodPoints": period_points, "participants": participants}


def current_race(period_type="warDay"):
    return {
        "periodType": period_type,
        "periodIndex": 5,
        "clans": [
            race_clan("#SLOW", "Slow", fame=1670, period_points=19300, decks_today=[4] * 32),
            race_clan(OUR_TAG, "Ours", fame=2070, period_points=22200, decks_today=[4] * 37 + [1]),
            race_clan("#FAST", "Fast", fame=6870, period_points=30950, decks_today=[4] * 48 + [1]),
        ],
        "periodLogs": [
            {
                "periodIndex": 3,
                "items": [
                    {"clan": {"tag": "#GONE"}, "pointsEarned": 100},
                    {"clan": {"tag": OUR_TAG}, "pointsEarned": 28550},
                    {"clan": {"tag": "#FAST"}, "pointsEarned": 31400},
                ],
            }
        ],
    }


def test_war_day_clans_are_ordered_by_boat():
    race = river_race.parse_current_race(current_race())
    assert [clan.name for clan in race.clans] == ["Fast", "Ours", "Slow"]
    assert race.war_day == 3
    assert not race.is_colosseum
    assert not race.is_training


def test_clan_stats():
    ours = river_race.parse_current_race(current_race()).clans[1]
    assert (ours.decks_used, ours.medals, ours.boat, ours.total_medals) == (149, 22200, 2070, None)
    assert ours.is_ours
    assert ours.average == pytest.approx(22200 / 149)
    assert ours.projected == round(22200 / 149 * CLAN_DECKS_PER_DAY)


def test_no_decks_means_no_average_or_projection():
    score = ClanScore(tag="#X", name="X", medals=0, decks_used=0)
    assert score.average is None
    assert score.projected is None


def test_colosseum_reports_weekly_medals_instead_of_boat():
    race = river_race.parse_current_race(current_race("colosseum"))
    assert race.is_colosseum
    assert all(clan.boat is None for clan in race.clans)
    assert (race.clans[0].name, race.clans[0].total_medals) == ("Fast", 6870)


def test_training_period():
    assert river_race.parse_current_race(current_race("training")).is_training


def test_finished_days_are_ordered_by_medals():
    day = river_race.parse_current_race(current_race()).finished_days[0]
    assert day.war_day == 1
    assert [(clan.name, clan.medals) for clan in day.clans] == [("Fast", 31400), ("Ours", 28550), ("#GONE", 100)]


def standing(rank, tag, fame, participants):
    return {
        "rank": rank,
        "clan": {"tag": tag, "name": tag.strip("#").title(), "fame": fame, "participants": participants},
    }


def test_race_log_keeps_only_our_clan():
    data = {
        "items": [
            {
                "seasonId": 135,
                "sectionIndex": 4,
                "createdDate": "20260907T095004.000Z",
                "standings": [
                    standing(1, "#OTHER", 124550, [participant(decks_used=790, fame=124550)]),
                    standing(
                        2,
                        OUR_TAG,
                        119150,
                        [participant(decks_used=400, fame=60000), participant(decks_used=355, fame=59150)],
                    ),
                ],
            },
            {
                "seasonId": 135,
                "sectionIndex": 3,
                "createdDate": "20260831T095006.000Z",
                "standings": [standing(3, OUR_TAG, 6940, [participant(decks_used=731, fame=113900)])],
            },
        ]
    }

    colosseum, boat_week = river_race.parse_race_log(data)

    assert (colosseum.season_id, colosseum.week, colosseum.place) == (135, 5, 2)
    assert colosseum.ended == datetime(2026, 9, 7, 9, 50, 4, tzinfo=timezone.utc)
    assert (colosseum.clan.medals, colosseum.clan.decks_used, colosseum.clan.boat) == (119150, 755, None)
    assert (boat_week.week, boat_week.clan.medals, boat_week.clan.boat) == (4, 113900, 6940)
