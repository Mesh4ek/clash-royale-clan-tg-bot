from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from access import admin_only
from config import config
from database import (
    Player,
    delete_player_by_tag,
    delete_players_by_tg,
    get_all_players_full,
    get_player_by_tag,
    get_players_by_tg,
    get_telegram_id_by_username,
)
from i18n import format_duration, t
from jobs import reschedule_all
from logs_buffer import get_recent_logs
from reports import format_players_tsv
from tg_utils import safe_answer_callback, send_pre_chunks
from war_schedule import (
    get_notify_hours,
    get_notify_opening,
    get_war_day_end,
    get_war_reminder,
    set_auto_reminder_30min_before_boundary,
    set_boundary_utc,
    set_notify_hours,
    set_reminder_utc,
)
from war_state import next_weekly_backup_run

from .registration import GroupRemoval, remove_from_group

logger = logging.getLogger(__name__)

LOG_LINES = 100
MINUTES_PER_HOUR = 60
MIN_NOTIFY_HOURS = 1
MAX_NOTIFY_HOURS = 24
UNREGISTER_CALLBACK_PREFIX = "unreg:"
UNREGISTER_CALLBACK_PATTERN = r"^unreg:(tag:#\w+|user:\d+|cancel)$"
UNREGISTER_CANCEL = "cancel"
GROUP_REMOVAL_KEYS = {
    GroupRemoval.REMOVED: "unregister.group_removed",
    GroupRemoval.NOT_MEMBER: "unregister.group_not_member",
    GroupRemoval.FAILED: "unregister.group_failed",
}


class _InvalidHoursError(ValueError):
    pass


@admin_only
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parts = [t("admin.panel", time_usage=t("time.usage"))]
    if config.weekly_data_backup:
        parts.append(t("admin.panel_backup"))
    await update.message.reply_text("\n\n".join(parts))


@admin_only
async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = get_recent_logs(lines=LOG_LINES) or t("admin.empty")
    await update.message.reply_text(f"<pre>{html.escape(text)}</pre>", parse_mode="HTML")


@admin_only
async def data_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_pre_chunks(context.bot, update.effective_chat.id, format_players_tsv(get_all_players_full()))


def _find_accounts(query: str) -> list[Player]:
    if query.startswith("#"):
        player = get_player_by_tag(query)
        return get_players_by_tg(player.telegram_id) if player else []
    if query.startswith("@"):
        telegram_id = get_telegram_id_by_username(query[1:])
        return get_players_by_tg(telegram_id) if telegram_id is not None else []
    return get_players_by_tg(int(query)) if query.isdigit() else []


def _account_lines(accounts: list[Player], mark_main: bool) -> str:
    return "\n".join(
        t(
            "unregister.account_main" if mark_main and index == 0 else "unregister.account",
            name=account.clash_name or "",
            tag=account.player_tag,
        )
        for index, account in enumerate(accounts)
    )


def _unregister_keyboard(accounts: list[Player], query: str) -> InlineKeyboardMarkup:
    rows = []
    selected = next((account for account in accounts if account.player_tag.upper() == query.upper()), None)
    if selected is not None and len(accounts) > 1:
        callback = f"{UNREGISTER_CALLBACK_PREFIX}tag:{selected.player_tag}"
        rows.append([InlineKeyboardButton(t("unregister.delete_one", tag=selected.player_tag), callback_data=callback)])
    callback = f"{UNREGISTER_CALLBACK_PREFIX}user:{accounts[0].telegram_id}"
    rows.append([InlineKeyboardButton(t("unregister.delete_all", count=len(accounts)), callback_data=callback)])
    callback = f"{UNREGISTER_CALLBACK_PREFIX}{UNREGISTER_CANCEL}"
    rows.append([InlineKeyboardButton(t("unregister.cancel"), callback_data=callback)])
    return InlineKeyboardMarkup(rows)


@admin_only
async def unregister_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) != 1:
        await update.message.reply_text(t("unregister.usage"))
        return

    query = args[0]
    accounts = _find_accounts(query)
    if not accounts:
        await update.message.reply_text(t("unregister.not_found", query=query))
        return

    owner = accounts[0]
    if owner.telegram_username:
        telegram = t("unregister.telegram_with_username", username=owner.telegram_username, id=owner.telegram_id)
    else:
        telegram = t("unregister.telegram_id_only", id=owner.telegram_id)
    await update.message.reply_text(
        t("unregister.confirm", telegram=telegram, accounts=_account_lines(accounts, mark_main=True)),
        reply_markup=_unregister_keyboard(accounts, query),
    )


@admin_only
async def unregister_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action = query.data.removeprefix(UNREGISTER_CALLBACK_PREFIX)
    await safe_answer_callback(query)
    if action == UNREGISTER_CANCEL:
        await query.edit_message_text(t("unregister.cancelled"))
        return

    kind, value = action.split(":", 1)
    if kind == "tag":
        player = get_player_by_tag(value)
        deleted = [player] if player else []
        delete_player_by_tag(value)
    else:
        deleted = get_players_by_tg(int(value))
        delete_players_by_tg(int(value))

    if not deleted:
        await query.edit_message_text(t("unregister.nothing_deleted"))
        return
    logger.info(
        "unregister: %s deleted by tg_id=%s", ", ".join(p.player_tag for p in deleted), update.effective_user.id
    )

    owner_id = deleted[0].telegram_id
    parts = [t("unregister.done", accounts=_account_lines(deleted, mark_main=False))]
    if get_players_by_tg(owner_id):
        parts.append(t("unregister.accounts_left"))
    else:
        removal = await remove_from_group(context, owner_id, deleted[0].clash_name)
        parts.append(t(GROUP_REMOVAL_KEYS[removal]))
    await query.edit_message_text("\n\n".join(parts))


def _clock(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _reminder_note() -> str:
    end_hour, end_minute = get_war_day_end()
    reminder_hour, reminder_minute = get_war_reminder()
    lead = (end_hour - reminder_hour) * MINUTES_PER_HOUR + end_minute - reminder_minute
    if lead <= 0:
        return t("time.reminder_not_before_end")
    return t("time.reminder_lead", lead=format_duration(lead))


def _backup_text() -> str:
    if not config.weekly_data_backup:
        return t("time.backup_off")
    run = next_weekly_backup_run()
    return t("time.backup_next", date=run.strftime("%d.%m"), time=run.strftime("%H:%M"))


def _schedule_text() -> str:
    now = datetime.now(timezone.utc)
    return t(
        "time.schedule",
        now=_clock(now.hour, now.minute),
        end=_clock(*get_war_day_end()),
        reminder=_clock(*get_war_reminder()),
        reminder_note=_reminder_note(),
        notify_from=_clock(*get_notify_opening()),
        notify_hours=get_notify_hours(),
        backup=_backup_text(),
    )


def _parse_clock(args: list[str]) -> tuple[int, int]:
    if len(args) != 2:
        raise ValueError("expected HOUR MINUTE")
    hour, minute = int(args[0]), int(args[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("clock out of range")
    return hour, minute


def _parse_hours(args: list[str]) -> int:
    try:
        hours = int(args[0]) if len(args) == 1 else None
    except ValueError:
        hours = None
    if hours is None or not MIN_NOTIFY_HOURS <= hours <= MAX_NOTIFY_HOURS:
        raise _InvalidHoursError("expected HOURS")
    return hours


def _apply_time_change(args: list[str]) -> str:
    command, rest = args[0].lower(), args[1:]
    if command == "notify":
        set_notify_hours(_parse_hours(rest))
        return t("time.set_notify", notify_from=_clock(*get_notify_opening()), notify_hours=get_notify_hours())
    if command == "boundary":
        set_boundary_utc(*_parse_clock(rest))
        return t("time.set_end", end=_clock(*get_war_day_end()))
    if command == "reminder":
        set_reminder_utc(*_parse_clock(rest))
        return t("time.set_reminder", reminder=_clock(*get_war_reminder()))
    if command == "auto" and not rest:
        set_auto_reminder_30min_before_boundary()
        return t("time.set_reminder", reminder=_clock(*get_war_reminder()))
    if command == "auto":
        set_boundary_utc(*_parse_clock(rest))
        set_auto_reminder_30min_before_boundary()
        return t("time.set_both", end=_clock(*get_war_day_end()), reminder=_clock(*get_war_reminder()))
    raise KeyError(command)


@admin_only
async def time_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []

    if not args:
        parts = [_schedule_text(), t("time.usage")]
    else:
        try:
            headline = _apply_time_change(args)
        except _InvalidHoursError:
            await update.message.reply_text(t("time.invalid_hours"))
            return
        except ValueError:
            await update.message.reply_text(t("time.invalid_value"))
            return
        except KeyError:
            await update.message.reply_text(t("time.unknown_command", usage=t("time.usage")))
            return
        reschedule_all(context.application)
        logger.info("time: %r by tg_id=%s", " ".join(args), update.effective_user.id)
        parts = [headline, _schedule_text()]

    if context.application.job_queue is None:
        parts.append(t("time.no_job_queue"))
    await update.message.reply_text("\n\n".join(parts))
