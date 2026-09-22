"""Local media post-processing: background removal (rembg) + ffmpeg encoding.

Everything here runs on this machine — no external API calls. This is
what turns a raw DALL-E 3 / Luma / Runway output into a Telegram-ready
transparent sticker (.webm for animated, .png for static).

`rembg` is imported lazily (inside `remove_background`) because it pulls
in onnxruntime/opencv, which are heavy and only needed for the sticker
flow — the rest of the bot should start instantly without them.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from PIL import Image

import ffmpeg  # ffmpeg-python: used to build filter graphs, executed via asyncio subprocess

from bot.utils.constants import TELEGRAM_STICKER_SIZE_PX
from bot.utils.exceptions import MediaProcessingError

logger = logging.getLogger(__name__)


class MediaProcessingService:
    def __init__(self, ffmpeg_binary: str, tmp_dir: Path):
        self._ffmpeg_binary = ffmpeg_binary
        self._tmp_dir = tmp_dir
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    def _tmp_path(self, suffix: str) -> Path:
        return self._tmp_dir / f"{uuid.uuid4().hex}{suffix}"

    # --- Background removal --------------------------------------------------

    async def remove_background(self, image_bytes: bytes) -> bytes:
        """Cut the subject out onto a transparent background using rembg.

        rembg's `remove()` is CPU-bound and synchronous, so it is offloaded
        to a worker thread via `asyncio.to_thread` to avoid blocking the
        event loop (and therefore the whole bot) while it runs.
        """
        try:
            from rembg import remove  # lazy import, see module docstring
        except ImportError as exc:  # pragma: no cover - depends on optional heavy deps
            raise MediaProcessingError(
                "rembg paketi kurulu değil. `pip install -r requirements.txt` komutunu "
                "çalıştırdığınızdan emin olun."
            ) from exc

        try:
            return await asyncio.to_thread(remove, image_bytes)
        except Exception as exc:  # noqa: BLE001 - rembg/onnxruntime raise assorted errors
            raise MediaProcessingError(f"Arka plan kaldırma başarısız: {exc}") from exc

    # --- Static sticker (PNG, transparent, Telegram-sized) -------------------

    async def to_static_sticker_png(self, image_bytes: bytes) -> bytes:
        """Resize/pad a (already background-removed) image to a Telegram sticker.

        Telegram requires one side to be exactly 512px, the other <= 512px,
        static stickers are PNG/WEBP with a transparent background.
        """
        return await asyncio.to_thread(self._resize_to_sticker_canvas_sync, image_bytes)

    def _resize_to_sticker_canvas_sync(self, image_bytes: bytes) -> bytes:
        import io

        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert("RGBA")
            scale = TELEGRAM_STICKER_SIZE_PX / max(image.width, image.height)
            new_size = (max(round(image.width * scale), 1), max(round(image.height * scale), 1))
            resized = image.resize(new_size, Image.LANCZOS)

            canvas = Image.new("RGBA", (TELEGRAM_STICKER_SIZE_PX, TELEGRAM_STICKER_SIZE_PX), (0, 0, 0, 0))
            offset = (
                (TELEGRAM_STICKER_SIZE_PX - resized.width) // 2,
                (TELEGRAM_STICKER_SIZE_PX - resized.height) // 2,
            )
            canvas.paste(resized, offset, resized)

            out = io.BytesIO()
            canvas.save(out, format="PNG")
            return out.getvalue()

    # --- ffmpeg: image -> looping animated .webm sticker ----------------------

    async def image_to_webm_sticker(self, image_bytes: bytes, duration_seconds: float = 2.5) -> bytes:
        """Turn a still (transparent) image into a short looping .webm sticker.

        Produces a subtle slow zoom-in loop, which reads as "alive" without
        needing a real video-generation call. Useful as a cheap animated
        sticker path, or as a fallback when the video provider is not yet
        configured.
        """
        input_path = self._tmp_path(".png")
        output_path = self._tmp_path(".webm")
        input_path.write_bytes(image_bytes)
        try:
            args = self._build_zoom_webm_args(input_path, output_path, duration_seconds)
            await self._run_ffmpeg(args)
            return output_path.read_bytes()
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def _build_zoom_webm_args(self, input_path: Path, output_path: Path, duration: float) -> list[str]:
        fps = 30
        frame_count = max(int(duration * fps), 1)
        # NOTE: `-loop 1` alone makes the single input frame available
        # indefinitely; zoompan's `d=` is "output frames per input frame",
        # so with exactly one (looped) input frame, d=frame_count directly
        # controls total output length. Do NOT also pass `t=` on the
        # input — combined with looping it multiplies out to a much longer
        # clip than intended (zoompan holds *each* looped input frame for
        # `d` output frames). The output-side `t=duration` below is a
        # safety cap in case of any rounding drift.
        stream = ffmpeg.input(str(input_path), loop=1)
        stream = stream.filter(
            "scale", TELEGRAM_STICKER_SIZE_PX, TELEGRAM_STICKER_SIZE_PX, force_original_aspect_ratio="increase"
        )
        stream = stream.filter("crop", TELEGRAM_STICKER_SIZE_PX, TELEGRAM_STICKER_SIZE_PX)
        stream = stream.filter(
            "zoompan",
            z="min(zoom+0.0015,1.1)",
            d=frame_count,
            s=f"{TELEGRAM_STICKER_SIZE_PX}x{TELEGRAM_STICKER_SIZE_PX}",
            fps=fps,
        )
        stream = ffmpeg.output(
            stream,
            str(output_path),
            t=duration,
            vcodec="libvpx-vp9",
            pix_fmt="yuva420p",
            **{"b:v": "150k", "crf": 35, "speed": 4, "an": None},
        )
        return ffmpeg.compile(stream, cmd=self._ffmpeg_binary, overwrite_output=True)

    # --- ffmpeg: provider video -> Telegram-ready .webm sticker ---------------

    async def video_to_webm_sticker(self, video_bytes: bytes, max_duration_seconds: float = 3.0) -> bytes:
        """Trim/resize/strip-audio a generated video into a Telegram video sticker.

        Enforces the Telegram video sticker constraints: 512x512, <= 3s,
        no audio track, VP9-in-WebM.
        """
        input_path = self._tmp_path(".mp4")
        output_path = self._tmp_path(".webm")
        input_path.write_bytes(video_bytes)
        try:
            args = self._build_video_to_sticker_args(input_path, output_path, max_duration_seconds)
            await self._run_ffmpeg(args)
            return output_path.read_bytes()
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def _build_video_to_sticker_args(
        self, input_path: Path, output_path: Path, max_duration: float
    ) -> list[str]:
        stream = ffmpeg.input(str(input_path))
        stream = stream.trim(start=0, end=max_duration).filter("setpts", "PTS-STARTPTS")
        stream = stream.filter(
            "scale", TELEGRAM_STICKER_SIZE_PX, TELEGRAM_STICKER_SIZE_PX, force_original_aspect_ratio="increase"
        )
        stream = stream.filter("crop", TELEGRAM_STICKER_SIZE_PX, TELEGRAM_STICKER_SIZE_PX)
        # Telegram's 256KB video-sticker cap is tight for VP9+alpha; the
        # bitrate/crf pair below is a reasonable starting point but real
        # footage (motion complexity varies a lot) may still need manual
        # tuning per source. Verify actual output size before shipping to
        # production and adjust `b:v`/`crf` if a specific clip overshoots.
        stream = ffmpeg.output(
            stream,
            str(output_path),
            vcodec="libvpx-vp9",
            an=None,
            r=30,
            **{"b:v": "150k", "crf": 35, "speed": 4},
        )
        return ffmpeg.compile(stream, cmd=self._ffmpeg_binary, overwrite_output=True)

    # --- subprocess runner -----------------------------------------------------

    async def _run_ffmpeg(self, args: list[str]) -> None:
        logger.debug("ffmpeg çalıştırılıyor: %s", " ".join(args))
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise MediaProcessingError(
                f"ffmpeg başarısız oldu (çıkış kodu {process.returncode}): "
                f"{stderr.decode(errors='ignore')[-800:]}"
            )
