from __future__ import annotations

from datetime import date
from typing import Iterable, Iterator

from clash_api import DECKS_PER_DAY
from database import Player
from i18n import rich, t
from markup import Link, RichText, join
from war_days import DayDecks

WarRow = tuple[str | None, int, str | None]

MENTION_SEPARATOR = " "
DATE_FORMAT = "%d.%m"
SNAPSHOT_TIME_FORMAT = "%d.%m %H:%M"


def _pending(players: Iterable[Player], war_rows: Iterable[WarRow]) -> Iterator[tuple[Player, WarRow]]:
    for player, row in zip(players, war_rows):
        if row[1] > 0:
            yield player, row


def _profile_url(player: Player) -> str:
    username = (player.telegram_username or "").strip()
    return f"https://t.me/{username}" if username else f"tg://user?id={player.telegram_id}"


def build_unique_mentions(players: list[Player], war_rows: list[WarRow]) -> list[Link]:
    by_user: dict[int, dict] = {}
    for player, (clash_name, _, telegram_username) in _pending(players, war_rows):
        entry = by_user.setdefault(player.telegram_id, {"username": None, "name": clash_name, "count": 0})
        username = (telegram_username or "").strip()
        if username:
            entry["username"] = username
        if not entry["name"] and clash_name:
            entry["name"] = clash_name
        entry["count"] += 1

    mentions = []
    for telegram_id, entry in by_user.items():
        suffix = f" (+{entry['count'] - 1})" if entry["count"] > 1 else ""
        if entry["username"]:
            mentions.append(Link(f"@{entry['username']}{suffix}"))
        else:
            label = f"{entry['name'] or t('war.unknown_player')}{suffix}".strip()
            mentions.append(Link(label, f"tg://user?id={telegram_id}"))
    return mentions


def _decks_left(decks: dict[str, int], tag: str) -> int:
    return DECKS_PER_DAY - max(0, min(decks.get(tag, 0), DECKS_PER_DAY))


def _missing_lines(members: dict[str, str], decks: dict[str, int]) -> list[str]:
    missing = []
    for tag, name in members.items():
        decks_left = _decks_left(decks, tag)
        if decks_left:
            missing.append((decks_left, name))
    missing.sort(key=lambda item: (-item[0], item[1].lower()))
    return [f"{name} ({decks_left}/{DECKS_PER_DAY})" for decks_left, name in missing]


def build_today_report(players: list[Player], members: dict[str, str], decks: dict[str, int]) -> RichText:
    registered = []
    for player in players:
        decks_left = _decks_left(decks, player.player_tag)
        if decks_left:
            registered.append([Link(player.clash_name or "", _profile_url(player)), f" ({decks_left}/{DECKS_PER_DAY})"])
    registered_tags = {player.player_tag for player in players}
    others = _missing_lines({tag: name for tag, name in members.items() if tag not in registered_tags}, decks)

    blocks = []
    if registered:
        blocks.append(join(registered, "\n"))
    if others:
        blocks.append(rich("war.not_in_telegram", players="\n".join(others)))
    return rich("war.report", players=join(blocks, "\n\n") if blocks else t("war.all_decks_used"))


def build_day_report(decks: DayDecks, war_day: int, day_date: date) -> RichText:
    lines = _missing_lines(decks.members, decks.by_tag)
    params = {
        "day": war_day,
        "date": day_date.strftime(DATE_FORMAT),
        "players": "\n".join(lines) if lines else t("war.day_all_used"),
    }
    if decks.as_of is None:
        return rich("war.day_report", **params)
    return rich("war.day_report_approx", time=decks.as_of.strftime(SNAPSHOT_TIME_FORMAT), **params)


def build_auto_reminder(mentions: list[Link], time_left: str) -> RichText:
    return rich("war.auto_reminder", time_left=time_left, mentions=join(mentions, MENTION_SEPARATOR))


def build_manual_reminder(mentions: list[Link], time_left: str, triggered_by: str) -> RichText:
    return rich(
        "war.manual_reminder",
        time_left=time_left,
        mentions=join(mentions, MENTION_SEPARATOR),
        label=triggered_by,
    )


def format_players_tsv(players: list[Player]) -> str:
    header = "telegram_id\ttelegram_username\tplayer_tag\tclash_name\tactive"
    rows = [
        f"{p.telegram_id}\t{p.telegram_username or ''}\t{p.player_tag}\t{p.clash_name or ''}\t{p.active}"
        for p in players
    ]
    return "\n".join([header, *rows])
