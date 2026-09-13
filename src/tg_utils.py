from __future__ import annotations

import html
import logging

from telegram import Bot
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import config
from i18n import t

logger = logging.getLogger(__name__)

MAX_PRE_CONTENT = 4000

_EXPIRED_QUERY_MARKERS = ("too old", "invalid", "query id")


def api_error_text(status_code: int) -> str:
    if status_code in (401, 403):
        return t("api.token_error")
    if status_code == 429:
        return t("api.rate_limited")
    return t("api.generic_error")


def load_error_text(status_code: int, fallback_key: str) -> str:
    return api_error_text(status_code) if status_code != 200 else t(fallback_key)


async def safe_answer_callback(query, **kwargs) -> None:
    try:
        await query.answer(**kwargs)
    except BadRequest as exc:
        if any(marker in str(exc).lower() for marker in _EXPIRED_QUERY_MARKERS):
            logger.warning("callback answer skipped (expired): %s", exc)
        else:
            raise


def split_for_pre(text: str, max_content: int = MAX_PRE_CONTENT) -> list[str]:
    if not text:
        return [t("admin.empty")]
    if len(text) <= max_content:
        return [text]

    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_content:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", 0, max_content)
        if cut <= 0:
            cut = max_content
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks


async def send_pre_chunks(bot: Bot, chat_id: int, text: str, *, title: str | None = None) -> int:
    chunks = split_for_pre(text)
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        body = chunk if total == 1 else f"{t('admin.part', index=index, total=total)}\n{chunk}"
        heading = f"{html.escape(title)}\n\n" if title and index == 1 else ""
        await bot.send_message(
            chat_id=chat_id,
            text=f"{heading}<pre>{html.escape(body)}</pre>",
            parse_mode="HTML",
        )
    return total


async def create_group_invite_link(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=config.group_id,
            creates_join_request=True,
        )
    except Exception as exc:
        logger.warning("invite link creation failed: %s", exc)
        return None
    return invite.invite_link
