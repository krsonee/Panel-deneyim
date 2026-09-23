"""/start and /help commands: entry points and general guidance."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.main_menu import build_main_menu

logger = logging.getLogger(__name__)

router = Router(name="start")

WELCOME_TEXT = (
    "👋 <b>Casino &amp; Spor Bahis Medya Botu</b>na hoş geldin!\n\n"
    "Bu bot, Pragmatic Play tarzı premium casino görselleri ve spor bahis "
    "medyaları üretmene yardımcı olur.\n\n"
    "Aşağıdan bir kategori seç ve adım adım ilerle 👇"
)

HELP_TEXT = (
    "ℹ️ <b>Nasıl çalışır?</b>\n\n"
    "1️⃣ Kategori seç: Casino ya da Spor Bahis\n"
    "2️⃣ Görsel temasını seç (slot ana görseli, freespin yağmuru, maskot, ...)\n"
    "3️⃣ Konuyu yaz (oyun adı, maç/takım adı)\n"
    "4️⃣ İstersen ek sanat detayı ekle\n"
    "5️⃣ Çıktı türünü seç: Görsel / Video / Şeffaf Sticker\n"
    "6️⃣ Üretilen prompt'u onayla, botun üretmesini izle\n\n"
    "📊 <code>/kota</code> — günlük kullanım hakkını gösterir\n"
    "🔁 <code>/start</code> — akışı sıfırdan başlatır"
)


@router.message(Command("start"))
async def handle_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=build_main_menu())


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
