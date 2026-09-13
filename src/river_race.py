from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from clash_api import DECKS_PER_DAY
from config import config

MAX_CLAN_MEMBERS = 50
CLAN_DECKS_PER_DAY = MAX_CLAN_MEMBERS * DECKS_PER_DAY
PERIODS_PER_WEEK = 7
TRAINING_DAYS = 3
WAR_DAYS = PERIODS_PER_WEEK - TRAINING_DAYS

WAR_DAY = "warDay"
COLOSSEUM = "colosseum"
API_TIME_FORMAT = "%Y%m%dT%H%M%S.%fZ"


@dataclass(frozen=True)
class ClanScore:
    tag: str
    name: str
    medals: int
    decks_used: int | None = None
    boat: int | None = None
    total_medals: int | None = None

    @property
    def is_ours(self) -> bool:
        return self.tag == config.clan_tag

    @property
    def average(self) -> float | None:
        return self.medals / self.decks_used if self.decks_used else None

    @property
    def projected(self) -> int | None:
        return round(self.average * CLAN_DECKS_PER_DAY) if self.average is not None else None


@dataclass(frozen=True)
class DayStandings:
    war_day: int
    clans: list[ClanScore] = field(default_factory=list)


@dataclass(frozen=True)
class CurrentRace:
    period_type: str
    war_day: int
    clans: list[ClanScore]
    finished_days: list[DayStandings]

    @property
    def is_colosseum(self) -> bool:
        return self.period_type == COLOSSEUM

    @property
    def is_training(self) -> bool:
        return self.period_type not in (WAR_DAY, COLOSSEUM)


@dataclass(frozen=True)
class PastRace:
    season_id: int
    week: int
    ended: datetime
    place: int
    clan: ClanScore


def _participants_total(clan: dict, key: str) -> int:
    return sum(participant.get(key, 0) for participant in clan.get("participants", []))


def war_day_number(period_index: int) -> int:
    return period_index % PERIODS_PER_WEEK - TRAINING_DAYS + 1


def parse_current_race(data: dict) -> CurrentRace:
    period_type = data.get("periodType", "")
    colosseum = period_type == COLOSSEUM
    raw_clans = data.get("clans", [])

    clans = [
        ClanScore(
            tag=clan.get("tag", ""),
            name=clan.get("name", ""),
            medals=clan.get("periodPoints", 0),
            decks_used=_participants_total(clan, "decksUsedToday"),
            # In a colosseum week "fame" is the weekly medal total; otherwise it is boat progress.
            boat=None if colosseum else clan.get("fame", 0),
            total_medals=clan.get("fame", 0) if colosseum else None,
        )
        for clan in raw_clans
    ]
    clans.sort(key=lambda clan: (clan.total_medals if colosseum else clan.boat, clan.medals), reverse=True)

    names = {clan.get("tag"): clan.get("name", "") for clan in raw_clans}
    finished_days = [
        DayStandings(
            war_day=war_day_number(log.get("periodIndex", 0)),
            clans=sorted(
                (
                    ClanScore(
                        tag=item["clan"]["tag"],
                        name=names.get(item["clan"]["tag"], item["clan"]["tag"]),
                        medals=item.get("pointsEarned", 0),
                    )
                    for item in log.get("items", [])
                ),
                key=lambda clan: clan.medals,
                reverse=True,
            ),
        )
        for log in data.get("periodLogs", [])
    ]

    return CurrentRace(
        period_type=period_type,
        war_day=war_day_number(data.get("periodIndex", 0)),
        clans=clans,
        finished_days=finished_days,
    )


def parse_race_log(data: dict) -> list[PastRace]:
    races = []
    for item in data.get("items", []):
        for standing in item.get("standings", []):
            clan = standing.get("clan", {})
            if clan.get("tag") != config.clan_tag:
                continue
            medals = _participants_total(clan, "fame")
            fame = clan.get("fame", 0)
            races.append(
                PastRace(
                    season_id=item.get("seasonId", 0),
                    week=item.get("sectionIndex", 0) + 1,
                    ended=datetime.strptime(item["createdDate"], API_TIME_FORMAT).replace(tzinfo=timezone.utc),
                    place=standing.get("rank", 0),
                    clan=ClanScore(
                        tag=clan["tag"],
                        name=clan.get("name", ""),
                        medals=medals,
                        decks_used=_participants_total(clan, "decksUsed"),
                        # Colosseum weeks report the medal total as "fame", so there is no boat to show.
                        boat=None if fame == medals else fame,
                    ),
                )
            )
    return races
