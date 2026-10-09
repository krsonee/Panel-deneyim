"""Main menu inline keyboard: shown by /start and after every completed flow."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callback_data import MainMenuCallback
from bot.utils.constants import MediaCategory
from bot.utils.labels import MEDIA_CATEGORY_LABELS


def build_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in MediaCategory:
        builder.button(
            text=MEDIA_CATEGORY_LABELS[category],
            callback_data=MainMenuCallback(action=category.value),
        )
    builder.button(text="📊 Kotam", callback_data=MainMenuCallback(action="quota"))
    builder.button(text="❓ Yardım", callback_data=MainMenuCallback(action="help"))
    builder.adjust(2, 2)
    return builder.as_markup()


def build_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="⬅️ Ana menü",
            callback_data=MainMenuCallback(action="root").pack(),
        )
    )
    return builder.as_markup()
