from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

import clash_api
import jobs
from config import config
from database import init_db
from handlers import admin, clan, race, registration, war
from i18n import init_i18n, t
from war_schedule import init_war_schedule

logger = logging.getLogger(__name__)

TELEGRAM_TIMEOUT_SECONDS = 60.0

PRIVATE = filters.ChatType.PRIVATE
MENU_COMMANDS = ("start", "war", "race", "rank", "missing")


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands([BotCommand(name, t(f"commands.{name}")) for name in MENU_COMMANDS])
    if application.job_queue:
        jobs.reschedule_all(application)
    else:
        logger.warning("job queue unavailable — install python-telegram-bot[job-queue] for scheduled pings")


async def _post_shutdown(application: Application) -> None:
    await clash_api.aclose()


def _register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", registration.start, filters=PRIVATE))
    application.add_handler(CommandHandler("war", war.war_report, filters=PRIVATE))
    application.add_handler(CommandHandler("race", race.race_cmd, filters=PRIVATE))
    application.add_handler(CommandHandler("rank", clan.clan_rank, filters=PRIVATE))
    application.add_handler(CommandHandler("missing", clan.missing_in_group, filters=PRIVATE))

    application.add_handler(CommandHandler("admin", admin.admin_cmd, filters=PRIVATE))
    application.add_handler(CommandHandler("logs", admin.logs_cmd, filters=PRIVATE))
    application.add_handler(CommandHandler("data", admin.data_cmd, filters=PRIVATE))
    application.add_handler(CommandHandler("time", admin.time_cmd, filters=PRIVATE))
    application.add_handler(CommandHandler("unregister", admin.unregister_cmd, filters=PRIVATE))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & PRIVATE, registration.handle_text)
    )

    application.add_handler(
        CallbackQueryHandler(war.remind_all, pattern=f"^{war.REMIND_ALL_CALLBACK}$")
    )
    application.add_handler(CallbackQueryHandler(war.war_dm_legacy, pattern=r"^war_dm:\d+$"))
    application.add_handler(CallbackQueryHandler(race.race_tab, pattern=race.CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(war.war_day_tab, pattern=war.DAY_CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(admin.unregister_confirm, pattern=admin.UNREGISTER_CALLBACK_PATTERN))

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, registration.new_member))
    application.add_handler(
        ChatMemberHandler(
            registration.member_left,
            chat_member_types=ChatMemberHandler.CHAT_MEMBER,
            chat_id=config.group_id,
        )
    )
    application.add_handler(
        ChatJoinRequestHandler(registration.handle_join_request, chat_id=config.group_id)
    )


def build_application() -> Application:
    init_i18n()
    init_war_schedule()
    init_db()

    request = HTTPXRequest(
        connect_timeout=TELEGRAM_TIMEOUT_SECONDS,
        read_timeout=TELEGRAM_TIMEOUT_SECONDS,
        write_timeout=TELEGRAM_TIMEOUT_SECONDS,
        proxy=config.telegram_proxy,
    )
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .request(request)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    _register_handlers(application)
    return application
