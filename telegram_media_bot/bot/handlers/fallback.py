"""Catch-all handler for anything that didn't match a more specific route.

Must be included last in bot/handlers/__init__.py — aiogram tries routers
in registration order and the first matching handler wins, so a
no-filter catch-all has to be the final fallback.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main_menu import build_main_menu

router = Router(name="fallback")


@router.message()
async def handle_unhandled_message(message: Message) -> None:
    await message.answer(
        "🤔 Bunu şu an anlayamadım. Aşağıdaki menüden bir seçim yap ya da /start yaz.",
        reply_markup=build_main_menu(),
    )


@router.callback_query()
async def handle_unhandled_callback(callback: CallbackQuery) -> None:
    await callback.answer(
        "Bu buton artık geçerli değil. /start ile yeniden başlayabilirsin.",
        show_alert=True,
    )
