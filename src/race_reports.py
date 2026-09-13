from __future__ import annotations

from i18n import format_number, rich, t
from markup import Bold, RichText, join
from river_race import CLAN_DECKS_PER_DAY, WAR_DAYS, ClanScore, CurrentRace, PastRace
from war_state import time_left_text

BLOCK_SEPARATOR = "\n\n"
LINE_SEPARATOR = "\n"
NO_VALUE = "—"
DATE_FORMAT = "%d.%m"


def _number(value: float | None, decimals: int = 0) -> str:
    return NO_VALUE if value is None else format_number(value, decimals)


def _name(clan: ClanScore) -> str | Bold:
    return Bold(clan.name) if clan.is_ours else clan.name


def build_race_today(race: CurrentRace) -> RichText:
    if race.is_training:
        return rich("race.training")

    clan_key = "race.clan_colosseum" if race.is_colosseum else "race.clan"
    blocks = [
        rich(
            clan_key,
            place=place,
            name=_name(clan),
            decks=clan.decks_used,
            max_decks=CLAN_DECKS_PER_DAY,
            medals=_number(clan.medals),
            average=_number(clan.average, decimals=1),
            projected=_number(clan.projected),
            boat=_number(clan.boat),
            total=_number(clan.total_medals),
        )
        for place, clan in enumerate(race.clans, start=1)
    ]
    title_key = "race.title_colosseum" if race.is_colosseum else "race.title_war"
    legend_key = "race.legend_colosseum" if race.is_colosseum else "race.legend_war"
    return rich(
        "race.today",
        title=t(title_key, day=race.war_day, days=WAR_DAYS),
        time_left=time_left_text(),
        clans=join(blocks, BLOCK_SEPARATOR),
        legend=t(legend_key),
    )


def build_race_days(race: CurrentRace) -> RichText:
    if not race.finished_days:
        return rich("race.no_finished_days")

    days = [
        rich(
            "race.day",
            day=day.war_day,
            clans=join(
                [
                    rich("race.day_clan", place=place, name=_name(clan), medals=_number(clan.medals))
                    for place, clan in enumerate(day.clans, start=1)
                ],
                LINE_SEPARATOR,
            ),
        )
        for day in race.finished_days
    ]
    return rich("race.days", days=join(days, BLOCK_SEPARATOR))


def build_race_history(races: list[PastRace]) -> RichText:
    if not races:
        return rich("race.no_history")

    weeks = [
        rich(
            "race.history_week" if past.clan.boat is None else "race.history_week_boat",
            season=past.season_id,
            week=past.week,
            date=past.ended.strftime(DATE_FORMAT),
            place=past.place,
            medals=_number(past.clan.medals),
            decks=_number(past.clan.decks_used),
            average=_number(past.clan.average, decimals=1),
            boat=_number(past.clan.boat),
        )
        for past in races
    ]
    return rich("race.history", weeks=join(weeks, BLOCK_SEPARATOR))
