from __future__ import annotations

import logging
from datetime import time, timezone

from telegram.ext import Application, ContextTypes

from clash_api import get_clan_members, get_current_river_race, get_war_status_for_tags
from config import config
from database import get_all_players, get_all_players_full
from i18n import t
from reports import build_auto_reminder, build_unique_mentions, format_players_tsv
from tg_utils import send_pre_chunks
from war_days import store_snapshot
from war_schedule import get_war_day_end, get_war_reminder
from war_state import AUTO_REMINDER_DAYS, WEEKLY_BACKUP_DAY, should_send_auto_reminder, time_left_text

logger = logging.getLogger(__name__)

WAR_REMINDER_JOB = "war_reminder"
WEEKLY_BACKUP_JOB = "weekly_data_backup"
WAR_DECKS_SNAPSHOT_JOB = "war_decks_snapshot"
WAR_DECKS_SNAPSHOT_INTERVAL_SECONDS = 30 * 60
WAR_DECKS_SNAPSHOT_FIRST_SECONDS = 30
MISFIRE_GRACE_SECONDS = 300


def _to_job_days(weekdays: tuple[int, ...]) -> tuple[int, ...]:
    # datetime.weekday() (Mon=0) -> JobQueue.run_daily() days (Sun=0).
    return tuple(sorted((day + 1) % 7 for day in weekdays))


def _clear_job(application: Application, name: str) -> None:
    if application.job_queue:
        for job in application.job_queue.get_jobs_by_name(name):
            job.schedule_removal()


def schedule_war_reminder(application: Application) -> None:
    if not application.job_queue:
        return
    _clear_job(application, WAR_REMINDER_JOB)
    hour, minute = get_war_reminder()
    application.job_queue.run_daily(
        war_reminder_job,
        time=time(hour, minute, tzinfo=timezone.utc),
        days=_to_job_days(AUTO_REMINDER_DAYS),
        name=WAR_REMINDER_JOB,
        job_kwargs={"misfire_grace_time": MISFIRE_GRACE_SECONDS},
    )
    logger.info("%s: scheduled daily at %02d:%02d UTC (Fri–Mon)", WAR_REMINDER_JOB, hour, minute)


def schedule_weekly_backup(application: Application) -> None:
    if not application.job_queue:
        return
    _clear_job(application, WEEKLY_BACKUP_JOB)
    if not config.weekly_data_backup or config.primary_admin_id is None:
        logger.info("%s: disabled (WEEKLY_DATA_BACKUP=0 or no LOGS_ALLOWED_TG_IDS)", WEEKLY_BACKUP_JOB)
        return
    hour, minute = get_war_day_end()
    application.job_queue.run_daily(
        weekly_backup_job,
        time=time(hour, minute, tzinfo=timezone.utc),
        days=_to_job_days((WEEKLY_BACKUP_DAY,)),
        name=WEEKLY_BACKUP_JOB,
        job_kwargs={"misfire_grace_time": MISFIRE_GRACE_SECONDS},
    )
    logger.info(
        "%s: scheduled Thursdays %02d:%02d UTC -> tg_id=%s",
        WEEKLY_BACKUP_JOB,
        hour,
        minute,
        config.primary_admin_id,
    )


def schedule_war_decks_snapshot(application: Application) -> None:
    if not application.job_queue:
        return
    _clear_job(application, WAR_DECKS_SNAPSHOT_JOB)
    application.job_queue.run_repeating(
        war_decks_snapshot_job,
        interval=WAR_DECKS_SNAPSHOT_INTERVAL_SECONDS,
        first=WAR_DECKS_SNAPSHOT_FIRST_SECONDS,
        name=WAR_DECKS_SNAPSHOT_JOB,
    )
    logger.info("%s: every %s min", WAR_DECKS_SNAPSHOT_JOB, WAR_DECKS_SNAPSHOT_INTERVAL_SECONDS // 60)


def reschedule_all(application: Application) -> None:
    schedule_war_reminder(application)
    schedule_weekly_backup(application)
    schedule_war_decks_snapshot(application)


async def war_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not should_send_auto_reminder():
        return False
    players = get_all_players()
    if not players:
        return False

    war_rows, _ = await get_war_status_for_tags(
        [(p.player_tag, p.clash_name, p.telegram_username) for p in players]
    )
    if war_rows is None:
        return False

    mentions = build_unique_mentions(players, war_rows)
    if not mentions:
        return False

    text, entities = build_auto_reminder(mentions, time_left_text())
    try:
        await context.bot.send_message(
            chat_id=config.group_id,
            text=text,
            entities=entities or None,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.exception("%s: failed to send to group: %s", WAR_REMINDER_JOB, exc)
        return False
    logger.info("%s: auto reminder sent to group", WAR_REMINDER_JOB)
    return True


async def weekly_backup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.weekly_data_backup or config.primary_admin_id is None:
        return
    try:
        sent = await send_pre_chunks(
            context.bot,
            config.primary_admin_id,
            format_players_tsv(get_all_players_full()),
            title=t("admin.backup_header"),
        )
        logger.info("%s: sent %s message(s) to tg_id=%s", WEEKLY_BACKUP_JOB, sent, config.primary_admin_id)
    except Exception as exc:
        logger.exception("%s: failed: %s", WEEKLY_BACKUP_JOB, exc)


async def war_decks_snapshot_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data, race_status = await get_current_river_race()
    members, clan_status = await get_clan_members()
    if data is None or members is None:
        logger.warning("%s: API unavailable (race %s, clan %s)", WAR_DECKS_SNAPSHOT_JOB, race_status, clan_status)
        return
    position = store_snapshot(data, dict(members))
    if position is not None:
        logger.debug("%s: saved week %s day %s", WAR_DECKS_SNAPSHOT_JOB, position.week_start, position.day)
