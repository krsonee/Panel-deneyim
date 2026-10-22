"""Final confirmation keyboard: confirm the built prompt or cancel/restart."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callback_data import ConfirmCallback


def build_confirm_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Üret", callback_data=ConfirmCallback(action="confirm"))
    builder.button(text="🔄 Baştan başla", callback_data=ConfirmCallback(action="restart"))
    builder.button(text="❌ Vazgeç", callback_data=ConfirmCallback(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()
