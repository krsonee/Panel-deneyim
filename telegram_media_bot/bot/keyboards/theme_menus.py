"""Theme-selection keyboards for the casino and sports-betting categories."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callback_data import CasinoThemeCallback, SportsThemeCallback
from bot.utils.constants import CasinoTheme, SportsTheme
from bot.utils.labels import CASINO_THEME_LABELS, SPORTS_THEME_LABELS


def build_casino_theme_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for theme in CasinoTheme:
        builder.button(
            text=CASINO_THEME_LABELS[theme],
            callback_data=CasinoThemeCallback(theme=theme.value),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_sports_theme_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for theme in SportsTheme:
        builder.button(
            text=SPORTS_THEME_LABELS[theme],
            callback_data=SportsThemeCallback(theme=theme.value),
        )
    builder.adjust(1)
    return builder.as_markup()
