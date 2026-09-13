from __future__ import annotations

from telegram import KeyboardButton, ReplyKeyboardMarkup

from i18n import t


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t("menu.war")), KeyboardButton(t("menu.race"))],
            [KeyboardButton(t("menu.rank")), KeyboardButton(t("menu.missing"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
