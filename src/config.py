from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
SHOWCASE_IMAGE = ASSETS_DIR / "showcase.png"
LOCALES_DIR = PROJECT_ROOT / "locales"

DEFAULT_LANGUAGE = "en"
_FALSY = ("0", "false", "no", "")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSY


def _optional_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else None


def _int_list_env(name: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in os.environ.get(name, "").split(",") if part.strip())


def _normalize_clan_tag(raw: str) -> str:
    tag = raw.strip().upper()
    return tag if tag.startswith("#") else f"#{tag}"


@dataclass(frozen=True)
class Config:
    telegram_token: str
    group_id: int
    admin_ids: tuple[int, ...]
    clash_api_token: str
    clan_tag: str
    language: str
    weekly_data_backup: bool
    poll_interval: float
    telegram_proxy: str | None
    database_path: str | None
    war_day_end_default: tuple[int, int]
    war_reminder_default: tuple[int, int]
    log_level: str
    clash_request_timeout: float
    clash_location_id: int | None
    decks_per_day: int

    @property
    def primary_admin_id(self) -> int | None:
        return self.admin_ids[0] if self.admin_ids else None

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids

    @property
    def database_file(self) -> Path:
        if self.database_path:
            return Path(self.database_path)
        return PROJECT_ROOT / "database" / "database.db"

    @property
    def data_dir(self) -> Path:
        directory = self.database_file.parent
        directory.mkdir(parents=True, exist_ok=True)
        return directory


def load_config() -> Config:
    return Config(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        group_id=int(os.environ["TELEGRAM_GROUP_ID"]),
        admin_ids=_int_list_env("LOGS_ALLOWED_TG_IDS"),
        clash_api_token=os.environ["CLASH_API_TOKEN"],
        clan_tag=_normalize_clan_tag(os.environ["CLAN_TAG"]),
        language=(os.environ.get("BOT_LANGUAGE") or DEFAULT_LANGUAGE).strip().lower(),
        weekly_data_backup=_bool_env("WEEKLY_DATA_BACKUP", True),
        poll_interval=float(os.environ.get("POLL_INTERVAL", "0")),
        telegram_proxy=os.environ.get("TELEGRAM_PROXY") or os.environ.get("HTTPS_PROXY") or None,
        database_path=os.environ.get("DATABASE_PATH") or None,
        war_day_end_default=(
            int(os.environ.get("WAR_DAY_END_UTC", 9)),
            int(os.environ.get("WAR_DAY_END_MINUTE", 30)),
        ),
        war_reminder_default=(
            int(os.environ.get("WAR_REMINDER_UTC", 9)),
            int(os.environ.get("WAR_REMINDER_MINUTE", 0)),
        ),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        clash_request_timeout=float(os.environ.get("REQUEST_TIMEOUT_SECONDS", 15)),
        clash_location_id=_optional_int_env("CLASH_LOCATION_ID"),
        decks_per_day=int(os.environ.get("RIVER_RACE_DECKS_PER_DAY", 4)),
    )


config = load_config()
