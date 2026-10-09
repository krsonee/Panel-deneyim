"""Typed callback_data factories (aiogram 3.x CallbackData) for all inline buttons.

Using CallbackData factories instead of hand-built strings gives us
compile-time-checked field names and automatic, collision-free packing
into Telegram's 1-64 byte callback_data limit.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MainMenuCallback(CallbackData, prefix="menu"):
    action: str  # "casino" | "sports" | "quota" | "help"


class CasinoThemeCallback(CallbackData, prefix="casino_theme"):
    theme: str  # bot.utils.constants.CasinoTheme value


class SportsThemeCallback(CallbackData, prefix="sports_theme"):
    theme: str  # bot.utils.constants.SportsTheme value


class SkipDetailsCallback(CallbackData, prefix="skip_details"):
    skip: bool = True


class OutputTypeCallback(CallbackData, prefix="output_type"):
    output_type: str  # bot.utils.constants.OutputType value


class ConfirmCallback(CallbackData, prefix="confirm"):
    action: str  # "confirm" | "cancel" | "restart"
