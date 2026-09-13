from __future__ import annotations

import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from access import require_clan_access
from clash_api import DECKS_PER_DAY, get_clan_members, get_current_river_race, get_war_status_for_tags
from config import config
from database import Player, get_all_players
from i18n import t
from markup import RichText
from reports import build_day_report, build_manual_reminder, build_today_report, build_unique_mentions
from river_race import WAR_DAYS
from tg_utils import load_error_text, safe_answer_callback
from war_days import WarPosition, decks_for_day, load_week, today_decks, war_day_date, war_position
from war_schedule import get_notify_hours, get_notify_opening
from war_state import can_notify_group, is_war_active, time_left_text

logger = logging.getLogger(__name__)

REMIND_ALL_CALLBACK = "remind_all"
DAY_CALLBACK_PREFIX = "war_day:"
DAY_CALLBACK_PATTERN = rf"^{DAY_CALLBACK_PREFIX}\d{{4}}-\d{{2}}-\d{{2}}:\d$"


def _day_tabs(week_start: date, today: int | None, viewed_day: int | None) -> list[InlineKeyboardButton]:
    buttons = []
    for day in range(1, (today or WAR_DAYS) + 1):
        label = t("war.tab_today") if day == today else t("war.tab_day", day=day)
        if day == viewed_day:
            label = t("common.active_tab", label=label)
        buttons.append(
            InlineKeyboardButton(label, callback_data=f"{DAY_CALLBACK_PREFIX}{week_start.isoformat()}:{day}")
        )
    return buttons


def _keyboard(
    week_start: date | None,
    today: int | None,
    viewed_day: int | None,
    can_remind: bool,
) -> InlineKeyboardMarkup | None:
    rows = []
    if week_start is not None and (today or WAR_DAYS) > 1:
        rows.append(_day_tabs(week_start, today, viewed_day))
    if can_remind:
        rows.append([InlineKeyboardButton(t("war.remind_all_button"), callback_data=REMIND_ALL_CALLBACK)])
    return InlineKeyboardMarkup(rows) if rows else None


def _api_args(players: list[Player]) -> list[tuple[str, str | None, str | None]]:
    return [(p.player_tag, p.clash_name, p.telegram_username) for p in players]


async def _current_position() -> WarPosition | None:
    data, _ = await get_current_river_race()
    return war_position(data) if data else None


async def _live_report(players: list[Player]) -> tuple[RichText, bool] | str:
    race_data, status_code = await get_current_river_race()
    if race_data is None:
        return load_error_text(status_code, "war.load_failed")
    members, status_code = await get_clan_members()
    if members is None:
        logger.warning("war report: clan members unavailable (status %s), showing registered players only", status_code)

    decks = today_decks(race_data)
    can_remind = any(decks.get(player.player_tag, 0) < DECKS_PER_DAY for player in players)
    return build_today_report(players, dict(members or []), decks), can_remind


async def _notify_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception as exc:
        logger.warning("could not DM tg_id=%s: %s", user_id, exc)


async def _trigger_label(context: ContextTypes.DEFAULT_TYPE, user: User) -> str:
    try:
        member = await context.bot.get_chat_member(chat_id=config.group_id, user_id=user.id)
        if getattr(member, "custom_title", None):
            return member.custom_title
    except Exception as exc:
        logger.debug("custom_title lookup failed for tg_id=%s: %s", user.id, exc)
    if user.username:
        return f"@{user.username}"
    return user.first_name or t("war.someone")


@require_clan_access()
async def war_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_war_active():
        await update.message.reply_text(t("war.no_active_war"))
        return

    report = await _live_report(get_all_players())
    if isinstance(report, str):
        await update.message.reply_text(report)
        return

    (text, entities), can_remind = report
    position = await _current_position()
    week_start, today = (position.week_start, position.day) if position else (None, None)
    keyboard = _keyboard(week_start, today, today, can_remind)
    try:
        await update.message.reply_text(
            text,
            entities=entities or None,
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
    except BadRequest as exc:
        logger.warning("war_report: retrying without entities: %s", exc)
        await update.message.reply_text(text, reply_markup=keyboard)


@require_clan_access(is_callback=True)
async def war_day_tab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    week_text, day_text = query.data.removeprefix(DAY_CALLBACK_PREFIX).rsplit(":", 1)
    week_start, day = date.fromisoformat(week_text), int(day_text)
    players = get_all_players()

    position = await _current_position()
    today = position.day if position and position.week_start == week_start else None

    if day == today:
        report = await _live_report(players)
        if isinstance(report, str):
            await safe_answer_callback(query, text=report, show_alert=True)
            return
        (text, entities), can_remind = report
    else:
        decks = decks_for_day(load_week(week_start), day)
        if decks is None:
            await safe_answer_callback(query, text=t("war.day_no_data_alert", day=day), show_alert=True)
            return
        text, entities = build_day_report(decks, day, war_day_date(week_start, day))
        can_remind = False

    await safe_answer_callback(query)
    try:
        await query.edit_message_text(
            text,
            entities=entities or None,
            disable_web_page_preview=True,
            reply_markup=_keyboard(week_start, today, day, can_remind),
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("war_day_tab: day %s unchanged", day)


@require_clan_access(is_callback=True)
async def remind_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    if not is_war_active():
        await safe_answer_callback(query, text=t("war.no_active_war_alert"), show_alert=True)
        return

    if not can_notify_group():
        hour, minute = get_notify_opening()
        alert = t("war.remind_too_early_alert", hours=get_notify_hours(), time=f"{hour:02d}:{minute:02d}")
        await safe_answer_callback(query, text=alert, show_alert=True)
        return

    players = get_all_players()
    if not players:
        await safe_answer_callback(query, text=t("war.no_players_in_db"), show_alert=True)
        return

    await safe_answer_callback(query)

    war_rows, status_code = await get_war_status_for_tags(_api_args(players))
    if war_rows is None:
        await _notify_user(context, update.effective_user.id, load_error_text(status_code, "war.load_failed"))
        return

    mentions = build_unique_mentions(players, war_rows)
    if not mentions:
        await _notify_user(context, update.effective_user.id, t("war.nobody_to_remind"))
        return

    label = await _trigger_label(context, update.effective_user)
    text, entities = build_manual_reminder(mentions, time_left_text(), label)
    try:
        await context.bot.send_message(
            chat_id=config.group_id,
            text=text,
            entities=entities or None,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.exception("remind_all: send to group failed: %s", exc)
        await _notify_user(context, update.effective_user.id, t("war.group_send_failed"))


# Not dead code: per-user buttons in older messages still send war_dm:<id> callbacks.
@require_clan_access(is_callback=True)
async def war_dm_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_answer_callback(update.callback_query, text=t("war.no_username_alert"), show_alert=True)
