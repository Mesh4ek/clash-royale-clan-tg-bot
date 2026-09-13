from __future__ import annotations

import functools
import logging
from enum import Enum
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from config import config
from database import get_player_by_tg
from i18n import t
from tg_utils import create_group_invite_link, safe_answer_callback

logger = logging.getLogger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


class Access(Enum):
    OK = "ok"
    NOT_IN_GROUP = "not_in_group"
    NOT_REGISTERED = "not_registered"


def check_clan_access(telegram_id: int) -> Access:
    if get_player_by_tg(telegram_id, active_only=True):
        return Access.OK
    if get_player_by_tg(telegram_id, active_only=False):
        return Access.NOT_IN_GROUP
    return Access.NOT_REGISTERED


async def reply_access_denied(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    is_callback: bool = False,
) -> None:
    status = check_clan_access(update.effective_user.id)
    if status is Access.NOT_REGISTERED:
        message = t("access.not_registered")
    elif is_callback:
        message = t("access.join_group_hint")
    else:
        link = await create_group_invite_link(context)
        message = t("access.join_group_with_link", link=link) if link else t("access.join_group_no_link")

    if is_callback:
        await safe_answer_callback(update.callback_query, text=message, show_alert=True)
    else:
        await update.message.reply_text(message)


def require_clan_access(*, is_callback: bool = False) -> Callable[[Handler], Handler]:
    def decorator(handler: Handler) -> Handler:
        @functools.wraps(handler)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            status = check_clan_access(update.effective_user.id)
            if status is not Access.OK:
                logger.info("%s: access denied (%s)", handler.__name__, status.value)
                await reply_access_denied(update, context, is_callback=is_callback)
                return
            await handler(update, context)

        return wrapper

    return decorator


def admin_only(handler: Handler) -> Handler:
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not config.admin_ids:
            message = t("access.no_admins_configured")
        elif not config.is_admin(update.effective_user.id):
            message = t("access.not_allowed")
        else:
            await handler(update, context)
            return

        if update.callback_query:
            await safe_answer_callback(update.callback_query, text=message, show_alert=True)
        else:
            await update.message.reply_text(message)

    return wrapper
