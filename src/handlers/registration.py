from __future__ import annotations

import asyncio
import logging
from enum import Enum

from telegram import Update
from telegram.ext import ContextTypes

from clash_api import get_player, player_in_clan
from config import SHOWCASE_IMAGE, config
from database import (
    get_player_by_tag,
    get_player_by_tg,
    get_players_by_tg,
    get_registration_info,
    is_tag_registered,
    save_player,
    set_active_by_tg,
)
from i18n import rich, t
from keyboards import menu_keyboard
from tg_utils import api_error_text, create_group_invite_link

from .clan import clan_rank, missing_in_group
from .race import race_cmd
from .war import war_report

logger = logging.getLogger(__name__)

TAG_PREFIX = "#"
CUSTOM_TITLE_MAX_LENGTH = 16
TITLE_ONLY_PERMISSIONS = {
    "can_manage_chat": True,
    "can_change_info": False,
    "can_delete_messages": False,
    "can_invite_users": False,
    "can_restrict_members": False,
    "can_pin_messages": False,
    "can_manage_video_chats": False,
    "can_manage_topics": False,
    "can_promote_members": False,
    "can_post_stories": False,
    "can_edit_stories": False,
    "can_delete_stories": False,
}
NO_ADMIN_RIGHTS = dict.fromkeys(TITLE_ONLY_PERMISSIONS, False)
PROMOTION_SETTLE_SECONDS = 1.5
MEMBER_STATUSES = ("member", "administrator", "creator", "restricted")
LEFT_STATUSES = ("left", "kicked")

# Players removed by /unregister: the removal arrives as a plain "left" update after they are already gone
# from the database, so the farewell message takes the fact and their Clash Royale name from here.
_removed_by_bot: dict[int, str | None] = {}


class GroupRemoval(Enum):
    REMOVED = "removed"
    NOT_MEMBER = "not_member"
    FAILED = "failed"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, entities = rich("registration.welcome")
    keyboard = menu_keyboard()

    if SHOWCASE_IMAGE.is_file():
        try:
            with SHOWCASE_IMAGE.open("rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=text,
                    caption_entities=entities or None,
                    reply_markup=keyboard,
                )
            return
        except Exception as exc:
            logger.exception("start: sending the showcase photo failed: %s", exc)
    else:
        logger.warning("start: showcase image not found at %s", SHOWCASE_IMAGE)

    await update.message.reply_text(text, entities=entities or None, reply_markup=keyboard)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    for label_key, menu_action in MENU_ROUTES.items():
        if text == t(label_key):
            await menu_action(update, context)
            return

    await _register_tag(update, context, text)


async def _register_tag(update: Update, context: ContextTypes.DEFAULT_TYPE, tag: str) -> None:
    if not tag.startswith(TAG_PREFIX):
        await update.message.reply_text(t("registration.bad_tag_format"))
        return

    player, status_code = await get_player(tag)
    if player is None:
        if status_code in (401, 403):
            await update.message.reply_text(api_error_text(status_code))
        else:
            await update.message.reply_text(t("registration.player_not_found"))
        return

    if not player_in_clan(player):
        await update.message.reply_text(t("registration.player_not_in_clan"))
        return

    if is_tag_registered(tag):
        await _handle_known_tag(update, context, tag)
        return

    user_id = update.effective_user.id
    save_player(user_id, update.effective_user.username, tag, player["name"])

    # Someone re-registering (e.g. after an admin /unregister) is already in the group and will never "join" again.
    if await _is_group_member(context, user_id):
        set_active_by_tg(user_id, True)
        if len(get_players_by_tg(user_id)) == 1:
            await _set_clan_title(context, config.group_id, user_id, player["name"])
        text, entities = rich("registration.success_in_group", name=player["name"])
        await update.message.reply_text(text, entities=entities or None)
        return

    link = await create_group_invite_link(context)
    if link is None:
        await update.message.reply_text(t("registration.invite_failed"))
        return

    text, entities = rich("registration.success", name=player["name"], link=link)
    await update.message.reply_text(text, entities=entities or None)


async def _handle_known_tag(update: Update, context: ContextTypes.DEFAULT_TYPE, tag: str) -> None:
    info = get_registration_info(tag)
    owner_id, active = info if info else (None, None)
    if owner_id != update.effective_user.id or active != 0:
        await update.message.reply_text(t("registration.tag_already_taken"))
        return

    if await _is_group_member(context, owner_id):
        set_active_by_tg(owner_id, True)
        player = get_player_by_tag(tag)
        text, entities = rich("registration.success_in_group", name=player.clash_name if player else tag)
        await update.message.reply_text(text, entities=entities or None)
        return

    link = await create_group_invite_link(context)
    if link is None:
        await update.message.reply_text(t("registration.already_registered_no_invite"))
        return

    text, entities = rich("registration.already_registered", link=link)
    await update.message.reply_text(text, entities=entities or None)


async def _is_group_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=config.group_id, user_id=user_id)
    except Exception as exc:
        logger.warning("membership check failed for tg_id=%s: %s", user_id, exc)
        return False
    return member.status in MEMBER_STATUSES


async def remove_from_group(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    clash_name: str | None,
) -> GroupRemoval:
    try:
        member = await context.bot.get_chat_member(chat_id=config.group_id, user_id=user_id)
    except Exception as exc:
        logger.warning("remove_from_group: lookup failed for tg_id=%s: %s", user_id, exc)
        return GroupRemoval.FAILED
    if member.status not in MEMBER_STATUSES:
        return GroupRemoval.NOT_MEMBER
    if member.status == "creator":
        return GroupRemoval.FAILED

    _removed_by_bot[user_id] = clash_name
    try:
        # Administrators can't be removed, and members get a title-only admin role on join.
        if member.status == "administrator":
            await context.bot.promote_chat_member(chat_id=config.group_id, user_id=user_id, **NO_ADMIN_RIGHTS)
        # Unbanning a current member removes them without a ban, so they can come back through an invite link.
        await context.bot.unban_chat_member(chat_id=config.group_id, user_id=user_id)
    except Exception as exc:
        _removed_by_bot.pop(user_id, None)
        logger.warning("remove_from_group: tg_id=%s: %s", user_id, exc)
        return GroupRemoval.FAILED
    logger.info("remove_from_group: tg_id=%s removed", user_id)
    return GroupRemoval.REMOVED


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join_request = update.chat_join_request
    if get_player_by_tg(join_request.from_user.id, active_only=False):
        await join_request.approve()
    else:
        await join_request.decline()


async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        clash_name = get_player_by_tg(member.id, active_only=False)
        if not clash_name:
            continue

        set_active_by_tg(member.id, True)
        chat_id = update.effective_chat.id

        try:
            text, entities = rich("registration.member_joined", name=clash_name)
            await context.bot.send_message(chat_id=chat_id, text=text, entities=entities or None)
        except Exception as exc:
            logger.warning("new_member: welcome message failed: %s", exc)

        await _set_clan_title(context, chat_id, member.id, clash_name)


async def _set_clan_title(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    clash_name: str,
) -> None:
    try:
        await context.bot.promote_chat_member(chat_id=chat_id, user_id=user_id, **TITLE_ONLY_PERMISSIONS)
        await asyncio.sleep(PROMOTION_SETTLE_SECONDS)

        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status not in ("administrator", "creator"):
            logger.warning("title: tg_id=%s is still %s after promote", user_id, member.status)
            return

        title = clash_name[:CUSTOM_TITLE_MAX_LENGTH]
        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title=title,
        )
        logger.info("title: set %r for tg_id=%s", title, user_id)
    except Exception as exc:
        logger.warning("title: promote/set failed for tg_id=%s: %s", user_id, exc)


async def member_left(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_member = update.chat_member
    if not chat_member:
        return
    new_status = chat_member.new_chat_member.status
    if new_status not in LEFT_STATUSES:
        return

    user = chat_member.new_chat_member.user
    set_active_by_tg(user.id, False)
    # A removal arrives as member -> kicked -> left; only the first step is a real departure.
    if chat_member.old_chat_member.status not in MEMBER_STATUSES:
        return

    removed_by_bot = user.id in _removed_by_bot
    removed_name = _removed_by_bot.pop(user.id, None)
    label = get_player_by_tg(user.id, active_only=False) or removed_name or user.full_name
    if user.username:
        label = f"{label} (@{user.username})"
    key = "registration.member_removed" if new_status == "kicked" or removed_by_bot else "registration.member_left"
    try:
        await context.bot.send_message(chat_id=chat_member.chat.id, text=t(key, name=label))
    except Exception as exc:
        logger.warning("member_left: farewell message failed: %s", exc)


MENU_ROUTES = {
    "menu.war": war_report,
    "menu.race": race_cmd,
    "menu.rank": clan_rank,
    "menu.missing": missing_in_group,
}
