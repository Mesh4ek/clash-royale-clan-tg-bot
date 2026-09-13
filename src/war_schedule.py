from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import config

logger = logging.getLogger(__name__)

AUTO_REMINDER_OFFSET = timedelta(minutes=30)
DEFAULT_NOTIFY_HOURS = 12

_KEYS = ("war_day_end_utc", "war_day_end_minute", "war_reminder_utc", "war_reminder_minute", "notify_hours")

_state: dict[str, int] | None = None


def schedule_path() -> Path:
    return config.data_dir / "war_schedule.json"


def _defaults() -> dict[str, int]:
    end_hour, end_minute = config.war_day_end_default
    reminder_hour, reminder_minute = config.war_reminder_default
    return {
        "war_day_end_utc": end_hour,
        "war_day_end_minute": end_minute,
        "war_reminder_utc": reminder_hour,
        "war_reminder_minute": reminder_minute,
        "notify_hours": DEFAULT_NOTIFY_HOURS,
    }


def init_war_schedule() -> dict[str, int]:
    global _state
    state = _defaults()
    path = schedule_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Files saved by older versions lack newer keys; those keep their defaults.
            state.update({key: int(data[key]) for key in _KEYS if key in data})
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("war_schedule: %s unreadable (%s), using .env defaults", path, exc)
    _state = state
    return _state


def _current() -> dict[str, int]:
    return _state if _state is not None else init_war_schedule()


def _persist() -> None:
    schedule_path().write_text(json.dumps(_current(), indent=2, ensure_ascii=False), encoding="utf-8")


def get_war_day_end() -> tuple[int, int]:
    state = _current()
    return state["war_day_end_utc"], state["war_day_end_minute"]


def get_war_reminder() -> tuple[int, int]:
    state = _current()
    return state["war_reminder_utc"], state["war_reminder_minute"]


def get_notify_hours() -> int:
    return _current()["notify_hours"]


def get_notify_opening() -> tuple[int, int]:
    hour, minute = get_war_day_end()
    opening = datetime(2000, 1, 1, hour, minute, tzinfo=timezone.utc) - timedelta(hours=get_notify_hours())
    return opening.hour, opening.minute


def set_boundary_utc(hour: int, minute: int) -> None:
    state = _current()
    state["war_day_end_utc"] = hour
    state["war_day_end_minute"] = minute
    _persist()


def set_reminder_utc(hour: int, minute: int) -> None:
    state = _current()
    state["war_reminder_utc"] = hour
    state["war_reminder_minute"] = minute
    _persist()


def set_notify_hours(hours: int) -> None:
    _current()["notify_hours"] = hours
    _persist()


def set_auto_reminder_30min_before_boundary() -> None:
    hour, minute = get_war_day_end()
    shifted = datetime(2000, 1, 1, hour, minute, tzinfo=timezone.utc) - AUTO_REMINDER_OFFSET
    set_reminder_utc(shifted.hour, shifted.minute)
