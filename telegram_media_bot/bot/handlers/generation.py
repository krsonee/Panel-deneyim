"""Core generation flow: subject -> details -> output type -> confirm -> generate.

This module owns the heaviest logic in the bot: turning FSM-collected user
choices into a finished prompt (via bot.utils.prompt_builder), calling the
appropriate AI provider, post-processing with ffmpeg/rembg when a sticker
was requested, and delivering the result back to the user — all while
respecting the per-user daily quota tracked in bot.services.quota_service.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.keyboards.callback_data import ConfirmCallback, OutputTypeCallback, SkipDetailsCallback
from bot.keyboards.confirm_menu import build_confirm_menu
from bot.keyboards.main_menu import build_main_menu
from bot.keyboards.output_menu import build_output_type_menu, build_skip_details_keyboard
from bot.keyboards.theme_menus import build_casino_theme_menu, build_sports_theme_menu
from bot.services.media_processing_service import MediaProcessingService
from bot.services.openai_image_service import OpenAIImageService
from bot.services.quota_service import QuotaService
from bot.services.video_generation_service import BaseVideoGenerationService
from bot.states.generation_states import GenerationStates
from bot.utils.constants import (
    QUOTA_KIND_IMAGE,
    QUOTA_KIND_STICKER,
    QUOTA_KIND_VIDEO,
    CasinoTheme,
    MediaCategory,
    OutputType,
    SportsTheme,
)
from bot.utils.exceptions import (
    ImageGenerationError,
    MediaProcessingError,
    ProviderNotConfiguredError,
    QuotaExceededError,
    VideoGenerationError,
)
from bot.utils.labels import OUTPUT_TYPE_LABELS
from bot.utils.prompt_builder import PromptResult, build_prompt_for_casino, build_prompt_for_sports

logger = logging.getLogger(__name__)

router = Router(name="generation")

_QUOTA_KIND_BY_OUTPUT = {
    OutputType.IMAGE: QUOTA_KIND_IMAGE,
    OutputType.VIDEO: QUOTA_KIND_VIDEO,
    OutputType.STICKER: QUOTA_KIND_STICKER,
}


def _theme_from_data(data: dict[str, Any]) -> CasinoTheme | SportsTheme:
    category = MediaCategory(data["category"])
    if category is MediaCategory.CASINO:
        return CasinoTheme(data["theme"])
    return SportsTheme(data["theme"])


def _build_prompt(data: dict[str, Any], output_type: OutputType) -> PromptResult:
    category = MediaCategory(data["category"])
    theme = _theme_from_data(data)
    subject = data.get("subject", "") or ""
    custom_details = data.get("custom_details")
    if category is MediaCategory.CASINO:
        return build_prompt_for_casino(theme, subject, output_type, custom_details)
    return build_prompt_for_sports(theme, subject, output_type, custom_details)


@router.message(GenerationStates.entering_subject, F.text)
async def handle_subject_entered(message: Message, state: FSMContext) -> None:
    subject = (message.text or "").strip()
    if not subject:
        await message.answer("Lütfen boş olmayan bir metin gir.")
        return
    await state.update_data(subject=subject)
    await state.set_state(GenerationStates.entering_custom_details)
    await message.answer(
        "✏️ İstersen ek sanat yönü ekle (renk, sahne detayı, maskot türü, vb.). "
        "Eklemek istemiyorsan aşağıdaki butona bas.",
        reply_markup=build_skip_details_keyboard(),
    )


@router.message(GenerationStates.entering_custom_details, F.text)
async def handle_details_entered(message: Message, state: FSMContext) -> None:
    await state.update_data(custom_details=(message.text or "").strip())
    await state.set_state(GenerationStates.choosing_output_type)
    await message.answer("🎛️ Çıktı türünü seç:", reply_markup=build_output_type_menu())


@router.callback_query(GenerationStates.entering_custom_details, SkipDetailsCallback.filter())
async def handle_details_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(custom_details=None)
    await state.set_state(GenerationStates.choosing_output_type)
    await callback.message.edit_text("🎛️ Çıktı türünü seç:", reply_markup=build_output_type_menu())
    await callback.answer()


@router.callback_query(GenerationStates.choosing_output_type, OutputTypeCallback.filter())
async def handle_output_type_chosen(
    callback: CallbackQuery, callback_data: OutputTypeCallback, state: FSMContext
) -> None:
    output_type = OutputType(callback_data.output_type)
    await state.update_data(output_type=output_type.value)
    await state.set_state(GenerationStates.confirming)

    data = await state.get_data()
    prompt_result = _build_prompt(data, output_type)
    await state.update_data(built_prompt=prompt_result.positive_prompt)

    preview = (
        "🧾 <b>Önizleme</b>\n"
        f"Çıktı türü: {OUTPUT_TYPE_LABELS[output_type]}\n\n"
        f"<i>Üretim için gönderilecek prompt:</i>\n<code>{prompt_result.positive_prompt}</code>\n\n"
        "Bu prompt ile üretime geçelim mi?"
    )
    await callback.message.edit_text(preview, reply_markup=build_confirm_menu())
    await callback.answer()


@router.callback_query(GenerationStates.confirming, ConfirmCallback.filter(F.action == "restart"))
async def handle_restart(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    category = MediaCategory(data.get("category", MediaCategory.CASINO.value))
    await state.set_state(GenerationStates.choosing_theme)
    await state.update_data(subject=None, custom_details=None, output_type=None, built_prompt=None)

    if category is MediaCategory.CASINO:
        await callback.message.edit_text("🎰 Casino teması seç:", reply_markup=build_casino_theme_menu())
    else:
        await callback.message.edit_text("⚽ Spor bahis teması seç:", reply_markup=build_sports_theme_menu())
    await callback.answer()


@router.callback_query(GenerationStates.confirming, ConfirmCallback.filter(F.action == "cancel"))
async def handle_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ İşlem iptal edildi.", reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(GenerationStates.confirming, ConfirmCallback.filter(F.action == "confirm"))
async def handle_confirm_generate(
    callback: CallbackQuery,
    state: FSMContext,
    quota_service: QuotaService,
    image_service: OpenAIImageService,
    video_service: BaseVideoGenerationService,
    media_service: MediaProcessingService,
) -> None:
    data = await state.get_data()
    output_type = OutputType(data["output_type"])
    prompt = data["built_prompt"]
    category = data["category"]
    theme = data["theme"]
    user_id = callback.from_user.id
    quota_kind = _QUOTA_KIND_BY_OUTPUT[output_type]

    await state.set_state(GenerationStates.generating)
    await callback.answer("Üretim başlıyor...")
    status_message = callback.message
    await status_message.edit_text("⏳ Üretiliyor, bu biraz zaman alabilir...")

    try:
        await quota_service.check_and_increment(user_id, quota_kind)
    except QuotaExceededError as exc:
        await status_message.edit_text(
            f"🚫 Günlük {OUTPUT_TYPE_LABELS[output_type]} kotan doldu "
            f"({exc.used}/{exc.limit}). Yarın tekrar dene.",
            reply_markup=build_main_menu(),
        )
        await state.clear()
        return

    try:
        result_bytes, caption, send_as = await _run_generation_pipeline(
            output_type, prompt, image_service, video_service, media_service
        )
        await quota_service.log_generation(user_id, category, theme, output_type.value, prompt, "ok")
    except ProviderNotConfiguredError as exc:
        logger.info("Provider not configured, showing placeholder message: %s", exc)
        await quota_service.log_generation(
            user_id, category, theme, output_type.value, prompt, "error", str(exc)
        )
        await status_message.edit_text(
            "⚠️ <b>Bu servis henüz yapılandırılmadı.</b>\n"
            f"{exc.provider_name} için <code>{exc.env_var}</code> .env dosyasında tanımlı değil.\n\n"
            "Bu, gerçek bir API key eklenene kadar beklenen bir durumdur (TODO yer tutucusu). "
            "Key eklendiğinde bu adım otomatik olarak çalışacaktır.\n\n"
            f"<i>Üretilecek prompt (referans için):</i>\n<code>{prompt}</code>",
            reply_markup=build_main_menu(),
        )
        await state.clear()
        return
    except (ImageGenerationError, VideoGenerationError, MediaProcessingError) as exc:
        logger.exception("Media generation failed for user_id=%s: %s", user_id, exc)
        await quota_service.log_generation(
            user_id, category, theme, output_type.value, prompt, "error", str(exc)
        )
        await status_message.edit_text(
            f"❌ Üretim sırasında bir hata oluştu:\n<code>{exc}</code>",
            reply_markup=build_main_menu(),
        )
        await state.clear()
        return

    await status_message.delete()
    file = BufferedInputFile(result_bytes, filename=f"generated.{send_as}")
    if send_as == "png":
        await callback.message.answer_photo(file, caption=caption)
    elif send_as == "mp4":
        await callback.message.answer_video(file, caption=caption)
    else:  # webm video-sticker
        await callback.message.answer_sticker(file)
        await callback.message.answer(caption)

    await callback.message.answer("Yeni bir üretim için ana menü 👇", reply_markup=build_main_menu())
    await state.clear()


async def _run_generation_pipeline(
    output_type: OutputType,
    prompt: str,
    image_service: OpenAIImageService,
    video_service: BaseVideoGenerationService,
    media_service: MediaProcessingService,
) -> tuple[bytes, str, str]:
    """Run the provider call(s) for one output type.

    Returns:
        (raw_bytes, user_facing_caption, file_extension) where
        file_extension is one of "png", "mp4", "webm".
    """
    if output_type is OutputType.IMAGE:
        image_bytes = await image_service.generate_image(prompt)
        return image_bytes, "🖼️ Görsel hazır!", "png"

    if output_type is OutputType.VIDEO:
        video_bytes = await video_service.generate_video(prompt)
        return video_bytes, "🎬 Video hazır!", "mp4"

    # STICKER: generate a base image, cut the subject out, encode as a
    # short looping transparent .webm ready for Telegram's sticker API.
    image_bytes = await image_service.generate_image(prompt)
    cutout_bytes = await media_service.remove_background(image_bytes)
    sticker_bytes = await media_service.image_to_webm_sticker(cutout_bytes)
    return sticker_bytes, "✨ Şeffaf sticker hazır!", "webm"
