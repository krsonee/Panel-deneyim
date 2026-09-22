"""Daily quota lookup: the /kota command and its shared text-rendering helper.

The rendering helper is also reused by bot/handlers/menu.py so the
"📊 Kotam" inline button and the /kota command always stay in sync.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.main_menu import build_main_menu
from bot.services.quota_service import QuotaService

router = Router(name="quota")

_KIND_LABELS = {"image": "🖼️ Görsel", "video": "🎬 Video", "sticker": "✨ Sticker"}


async def render_quota_text(quota_service: QuotaService, user_id: int) -> str:
    statuses = await quota_service.get_all_status(user_id)
    lines = ["📊 <b>Günlük Kotan</b>\n"]
    for status in statuses:
        label = _KIND_LABELS.get(status.kind, status.kind)
        lines.append(f"{label}: {status.used}/{status.limit} kullanıldı ({status.remaining} kaldı)")
    lines.append("\nKota her gün UTC 00:00'da sıfırlanır.")
    return "\n".join(lines)


@router.message(Command("kota"))
async def handle_quota_command(message: Message, quota_service: QuotaService) -> None:
    text = await render_quota_text(quota_service, message.from_user.id)
    await message.answer(text, reply_markup=build_main_menu())
