"""Output-type selection keyboard (image / video / sticker) and skip-details button."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callback_data import OutputTypeCallback, SkipDetailsCallback
from bot.utils.constants import OutputType
from bot.utils.labels import OUTPUT_TYPE_LABELS


def build_output_type_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for output_type in OutputType:
        builder.button(
            text=OUTPUT_TYPE_LABELS[output_type],
            callback_data=OutputTypeCallback(output_type=output_type.value),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_skip_details_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Detaysız geç", callback_data=SkipDetailsCallback())
    return builder.as_markup()
