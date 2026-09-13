from __future__ import annotations

from datetime import datetime, timedelta, timezone

from i18n import format_duration
from war_schedule import get_notify_hours, get_war_day_end

# datetime.weekday(): Mon=0 ... Sun=6 (used here).
# JobQueue.run_daily(): Sun=0 ... Sat=6 (jobs.py converts). Do not mix them up.
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)

OFF_DAYS = (TUESDAY, WEDNESDAY)
AUTO_REMINDER_DAYS = (FRIDAY, SATURDAY, SUNDAY, MONDAY)
WEEKLY_BACKUP_DAY = THURSDAY


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def war_day_end_today(now: datetime | None = None) -> datetime:
    moment = _now(now)
    hour, minute = get_war_day_end()
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)


def is_war_active(now: datetime | None = None) -> bool:
    moment = _now(now)
    weekday = moment.weekday()
    if weekday == MONDAY:
        return moment < war_day_end_today(moment)
    return weekday not in OFF_DAYS


def should_send_auto_reminder(now: datetime | None = None) -> bool:
    moment = _now(now)
    return is_war_active(moment) and moment.weekday() in AUTO_REMINDER_DAYS


def _next_day_end(moment: datetime) -> datetime:
    end = war_day_end_today(moment)
    return end + timedelta(days=1) if moment >= end else end


def time_left_text(now: datetime | None = None) -> str:
    moment = _now(now)
    return format_duration(int((_next_day_end(moment) - moment).total_seconds() // 60))


def can_notify_group(now: datetime | None = None) -> bool:
    moment = _now(now)
    return _next_day_end(moment) - moment <= timedelta(hours=get_notify_hours())


def next_weekly_backup_run(now: datetime | None = None) -> datetime:
    moment = _now(now)
    hour, minute = get_war_day_end()
    for offset in range(14):
        day = (moment + timedelta(days=offset)).date()
        if day.weekday() != WEEKLY_BACKUP_DAY:
            continue
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
        if candidate > moment:
            return candidate
    return moment + timedelta(days=7)
