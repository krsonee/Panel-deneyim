"""Sports-betting theme selection: user picked "⚽ Spor Bahis" from the main menu."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.callback_data import SportsThemeCallback
from bot.states.generation_states import GenerationStates
from bot.utils.constants import MediaCategory, SportsTheme
from bot.utils.labels import SPORTS_THEME_DESCRIPTIONS, SPORTS_THEME_LABELS

logger = logging.getLogger(__name__)

router = Router(name="sports")


@router.callback_query(GenerationStates.choosing_theme, SportsThemeCallback.filter())
async def handle_sports_theme_chosen(
    callback: CallbackQuery, callback_data: SportsThemeCallback, state: FSMContext
) -> None:
    theme = SportsTheme(callback_data.theme)
    await state.update_data(category=MediaCategory.SPORTS.value, theme=theme.value)
    await state.set_state(GenerationStates.entering_subject)

    label = SPORTS_THEME_LABELS[theme]
    description = SPORTS_THEME_DESCRIPTIONS[theme]
    await callback.message.edit_text(
        f"{label}\n<i>{description}</i>\n\n"
        "🎯 Hangi maç/takım/sporcu için üretelim? Örnek: <b>Galatasaray - Fenerbahçe derbisi</b> "
        "ya da spesifik bir maçın yoksa <b>'jenerik futbol derbisi'</b> gibi yaz."
    )
    await callback.answer()
