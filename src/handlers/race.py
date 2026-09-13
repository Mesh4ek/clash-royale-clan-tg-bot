from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from access import require_clan_access
from clash_api import get_current_river_race, get_river_race_log
from i18n import t
from markup import RichText
from race_reports import build_race_days, build_race_history, build_race_today
from river_race import parse_current_race, parse_race_log
from tg_utils import load_error_text, safe_answer_callback

logger = logging.getLogger(__name__)

TODAY, DAYS, HISTORY = "today", "days", "history"
VIEWS = (TODAY, DAYS, HISTORY)
TAB_KEYS = {TODAY: "race.tab_today", DAYS: "race.tab_days", HISTORY: "race.tab_history"}
CALLBACK_PREFIX = "race:"
CALLBACK_PATTERN = rf"^{CALLBACK_PREFIX}({'|'.join(VIEWS)})$"


def _keyboard(active_view: str) -> InlineKeyboardMarkup:
    buttons = []
    for view in VIEWS:
        label = t(TAB_KEYS[view])
        if view == active_view:
            label = t("common.active_tab", label=label)
        buttons.append(InlineKeyboardButton(label, callback_data=f"{CALLBACK_PREFIX}{view}"))
    return InlineKeyboardMarkup([buttons])


async def _render(view: str) -> RichText | str:
    if view == HISTORY:
        data, status_code = await get_river_race_log()
        if data is None:
            return load_error_text(status_code, "race.load_failed")
        return build_race_history(parse_race_log(data))

    data, status_code = await get_current_river_race()
    if data is None:
        return load_error_text(status_code, "race.load_failed")
    race = parse_current_race(data)
    return build_race_days(race) if view == DAYS else build_race_today(race)


@require_clan_access()
async def race_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = await _render(TODAY)
    if isinstance(result, str):
        await update.message.reply_text(result)
        return
    await update.message.reply_text(result.text, entities=result.entities or None, reply_markup=_keyboard(TODAY))


@require_clan_access(is_callback=True)
async def race_tab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    view = query.data.removeprefix(CALLBACK_PREFIX)

    result = await _render(view)
    if isinstance(result, str):
        await safe_answer_callback(query, text=result, show_alert=True)
        return

    await safe_answer_callback(query)
    try:
        await query.edit_message_text(result.text, entities=result.entities or None, reply_markup=_keyboard(view))
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("race_tab: %s view unchanged", view)
