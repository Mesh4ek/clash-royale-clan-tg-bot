from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from access import require_clan_access
from clash_api import get_clan_members, get_clan_rank
from database import get_registered_tags, is_tag_registered
from i18n import rich, t
from tg_utils import api_error_text, load_error_text

logger = logging.getLogger(__name__)

REGIONAL_INDICATOR_A = 0x1F1E6
NO_FLAG = "🌍"


def _flag(country_code: str | None) -> str:
    if not country_code or len(country_code) != 2 or not country_code.isascii() or not country_code.isalpha():
        return NO_FLAG
    return "".join(chr(REGIONAL_INDICATOR_A + ord(letter) - ord("A")) for letter in country_code.upper())


@require_clan_access()
async def clan_rank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rank, status_code = await get_clan_rank()
    if status_code != 200:
        await update.message.reply_text(api_error_text(status_code))
        return
    if rank is None:
        await update.message.reply_text(t("clan.no_location"))
        return

    place = {"flag": _flag(rank.country_code), "location": rank.location}
    if rank.position:
        text, entities = rich("clan.rank", rank=rank.position, **place)
    else:
        text, entities = rich("clan.rank_not_in_top", **place)
    await update.message.reply_text(text, entities=entities or None)


@require_clan_access()
async def missing_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    members, status_code = await get_clan_members()
    if members is None:
        await update.message.reply_text(load_error_text(status_code, "clan.load_failed"))
        return

    registered_tags = get_registered_tags()
    present = [name for tag, name in members if is_tag_registered(tag)]
    missing = [name for tag, name in members if tag not in registered_tags]

    text, entities = rich(
        "clan.missing_report",
        present="\n".join(f"- {name}" for name in present),
        missing="\n".join(f"- {name}" for name in missing) if missing else t("clan.nobody"),
    )
    await update.message.reply_text(text, entities=entities or None)
