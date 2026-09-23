"""Casino theme selection: user picked "🎰 Casino" from the main menu."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.callback_data import CasinoThemeCallback
from bot.states.generation_states import GenerationStates
from bot.utils.constants import CasinoTheme, MediaCategory
from bot.utils.labels import CASINO_THEME_DESCRIPTIONS, CASINO_THEME_LABELS

logger = logging.getLogger(__name__)

router = Router(name="casino")


@router.callback_query(GenerationStates.choosing_theme, CasinoThemeCallback.filter())
async def handle_casino_theme_chosen(
    callback: CallbackQuery, callback_data: CasinoThemeCallback, state: FSMContext
) -> None:
    theme = CasinoTheme(callback_data.theme)
    await state.update_data(category=MediaCategory.CASINO.value, theme=theme.value)
    await state.set_state(GenerationStates.entering_subject)

    label = CASINO_THEME_LABELS[theme]
    description = CASINO_THEME_DESCRIPTIONS[theme]
    await callback.message.edit_text(
        f"{label}\n<i>{description}</i>\n\n"
        "🎯 Hangi oyun/marka için üretelim? Örnek: <b>Aztec Gold Deluxe</b> ya da "
        "spesifik bir oyunun yoksa <b>'jenerik kaplan temalı slot'</b> gibi yaz."
    )
    await callback.answer()
