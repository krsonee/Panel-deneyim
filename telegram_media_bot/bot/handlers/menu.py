"""Main-menu callback routing: category pick, quota view, help, back-to-root."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.handlers.quota import render_quota_text
from bot.handlers.start import HELP_TEXT, WELCOME_TEXT
from bot.keyboards.callback_data import MainMenuCallback
from bot.keyboards.main_menu import build_main_menu
from bot.keyboards.theme_menus import build_casino_theme_menu, build_sports_theme_menu
from bot.services.quota_service import QuotaService
from bot.states.generation_states import GenerationStates
from bot.utils.constants import MediaCategory

logger = logging.getLogger(__name__)

router = Router(name="menu")


@router.callback_query(MainMenuCallback.filter(F.action == MediaCategory.CASINO.value))
async def handle_pick_casino(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GenerationStates.choosing_theme)
    await state.update_data(category=MediaCategory.CASINO.value)
    await callback.message.edit_text("🎰 Casino teması seç:", reply_markup=build_casino_theme_menu())
    await callback.answer()


@router.callback_query(MainMenuCallback.filter(F.action == MediaCategory.SPORTS.value))
async def handle_pick_sports(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GenerationStates.choosing_theme)
    await state.update_data(category=MediaCategory.SPORTS.value)
    await callback.message.edit_text("⚽ Spor bahis teması seç:", reply_markup=build_sports_theme_menu())
    await callback.answer()


@router.callback_query(MainMenuCallback.filter(F.action == "quota"))
async def handle_show_quota(callback: CallbackQuery, quota_service: QuotaService) -> None:
    text = await render_quota_text(quota_service, callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(MainMenuCallback.filter(F.action == "help"))
async def handle_show_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(HELP_TEXT, reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(MainMenuCallback.filter(F.action == "root"))
async def handle_back_to_root(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=build_main_menu())
    await callback.answer()
