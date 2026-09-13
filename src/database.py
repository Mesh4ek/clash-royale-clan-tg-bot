from __future__ import annotations

import logging
import sqlite3
from typing import NamedTuple

from config import config

logger = logging.getLogger(__name__)

_connection: sqlite3.Connection | None = None


class Player(NamedTuple):
    telegram_id: int
    telegram_username: str | None
    player_tag: str
    clash_name: str | None
    active: int = 1


class WarDecksRow(NamedTuple):
    war_day: int
    player_tag: str
    player_name: str | None
    decks_before: int
    decks_today: int
    in_clan: int
    updated_at: str


def _conn() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        path = config.database_file
        path.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(path, check_same_thread=False)
        logger.info("database: using %s", path)
        _create_schema(_connection)
    return _connection


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS players(
            telegram_id INTEGER,
            telegram_username TEXT,
            player_tag TEXT,
            clash_name TEXT,
            active INTEGER DEFAULT 1
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(players)")}
    if "active" not in columns:
        conn.execute("ALTER TABLE players ADD COLUMN active INTEGER DEFAULT 1")
        logger.info("database: added missing 'active' column")
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_tag ON players(player_tag)")
    except sqlite3.IntegrityError:
        logger.warning("database: duplicate player_tag rows present, unique index not created")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_players_telegram_id ON players(telegram_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS war_decks(
            week_start TEXT NOT NULL,
            war_day INTEGER NOT NULL,
            player_tag TEXT NOT NULL,
            player_name TEXT,
            decks_before INTEGER NOT NULL,
            decks_today INTEGER NOT NULL,
            in_clan INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (week_start, war_day, player_tag)
        )
        """
    )
    war_decks_columns = {row[1] for row in conn.execute("PRAGMA table_info(war_decks)")}
    if "in_clan" not in war_decks_columns:
        conn.execute("ALTER TABLE war_decks ADD COLUMN in_clan INTEGER NOT NULL DEFAULT 0")
        logger.info("database: added missing 'in_clan' column to war_decks")
    conn.commit()


def init_db() -> None:
    _conn()


def save_player(telegram_id: int, username: str | None, tag: str, clash_name: str | None) -> None:
    conn = _conn()
    exists = conn.execute("SELECT 1 FROM players WHERE player_tag = ?", (tag,)).fetchone()
    if exists:
        conn.execute(
            "UPDATE players SET telegram_id = ?, telegram_username = ?, clash_name = ? WHERE player_tag = ?",
            (telegram_id, username, clash_name, tag),
        )
    else:
        is_first = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
        conn.execute(
            "INSERT INTO players (telegram_id, telegram_username, player_tag, clash_name, active) "
            "VALUES (?, ?, ?, ?, ?)",
            (telegram_id, username, tag, clash_name, 1 if is_first else 0),
        )
    conn.commit()


def set_active_by_tg(telegram_id: int, active: bool) -> None:
    conn = _conn()
    conn.execute("UPDATE players SET active = ? WHERE telegram_id = ?", (1 if active else 0, telegram_id))
    conn.commit()


def is_tag_registered(tag: str) -> bool:
    return _conn().execute("SELECT 1 FROM players WHERE player_tag = ?", (tag,)).fetchone() is not None


def get_registration_info(tag: str) -> tuple[int, int] | None:
    return _conn().execute("SELECT telegram_id, active FROM players WHERE player_tag = ?", (tag,)).fetchone()


def get_player_by_tg(telegram_id: int, active_only: bool = True) -> str | None:
    query = "SELECT clash_name FROM players WHERE telegram_id = ?"
    if active_only:
        query += " AND active = 1"
    row = _conn().execute(query, (telegram_id,)).fetchone()
    return row[0] if row else None


def get_player_by_tag(tag: str) -> Player | None:
    row = (
        _conn()
        .execute(
            "SELECT telegram_id, telegram_username, player_tag, clash_name, active FROM players "
            "WHERE UPPER(player_tag) = UPPER(?)",
            (tag,),
        )
        .fetchone()
    )
    return Player(*row) if row else None


def get_players_by_tg(telegram_id: int) -> list[Player]:
    rows = _conn().execute(
        "SELECT telegram_id, telegram_username, player_tag, clash_name, active FROM players "
        "WHERE telegram_id = ? ORDER BY rowid",
        (telegram_id,),
    )
    return [Player(*row) for row in rows]


def get_telegram_id_by_username(username: str) -> int | None:
    row = (
        _conn()
        .execute("SELECT telegram_id FROM players WHERE LOWER(telegram_username) = LOWER(?)", (username,))
        .fetchone()
    )
    return row[0] if row else None


def delete_player_by_tag(tag: str) -> None:
    conn = _conn()
    conn.execute("DELETE FROM players WHERE UPPER(player_tag) = UPPER(?)", (tag,))
    conn.commit()


def delete_players_by_tg(telegram_id: int) -> None:
    conn = _conn()
    conn.execute("DELETE FROM players WHERE telegram_id = ?", (telegram_id,))
    conn.commit()


def get_all_players() -> list[Player]:
    rows = _conn().execute(
        "SELECT telegram_id, telegram_username, player_tag, clash_name FROM players WHERE active = 1"
    )
    return [Player(*row) for row in rows]


def get_all_players_full() -> list[Player]:
    rows = _conn().execute(
        "SELECT telegram_id, telegram_username, player_tag, clash_name, active FROM players ORDER BY player_tag"
    )
    return [Player(*row) for row in rows]


def get_registered_tags() -> set[str]:
    return {row[0] for row in _conn().execute("SELECT player_tag FROM players WHERE active = 1")}


def save_war_decks(
    week_start: str,
    war_day: int,
    rows: list[tuple[str, str | None, int, int, bool]],
    updated_at: str,
) -> None:
    conn = _conn()
    conn.executemany(
        "INSERT INTO war_decks "
        "(week_start, war_day, player_tag, player_name, decks_before, decks_today, in_clan, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (week_start, war_day, player_tag) DO UPDATE SET "
        "player_name = excluded.player_name, decks_before = excluded.decks_before, "
        "decks_today = excluded.decks_today, in_clan = excluded.in_clan, updated_at = excluded.updated_at",
        [
            (week_start, war_day, tag, name, before, today, int(in_clan), updated_at)
            for tag, name, before, today, in_clan in rows
        ],
    )
    conn.commit()


def get_war_decks(week_start: str) -> list[WarDecksRow]:
    rows = _conn().execute(
        "SELECT war_day, player_tag, player_name, decks_before, decks_today, in_clan, updated_at "
        "FROM war_decks WHERE week_start = ?",
        (week_start,),
    )
    return [WarDecksRow(*row) for row in rows]
