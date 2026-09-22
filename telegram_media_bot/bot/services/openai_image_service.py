"""OpenAI DALL-E 3 image generation service.

Wraps the official `openai` async client. The heavy import is done lazily
inside the class so the rest of the bot can start even if the `openai`
package (or its transitive deps) is missing in a given environment.

TODO(production): once a real OPENAI_API_KEY is set in .env, this module
works end-to-end as-is. Nothing else needs to change.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from bot.utils.exceptions import ImageGenerationError, ProviderNotConfiguredError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 2.0


class OpenAIImageService:
    """Async wrapper around OpenAI's `images.generate` (DALL-E 3) endpoint."""

    def __init__(
        self,
        api_key: str | None,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        request_timeout_seconds: int = 60,
    ):
        self._api_key = api_key
        self._model = model
        self._size = size
        self._timeout = request_timeout_seconds
        self._client = None  # lazily created AsyncOpenAI instance

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderNotConfiguredError("OpenAI DALL-E 3", "OPENAI_API_KEY")

        # Lazy import: keeps `openai` off the hot import path for handlers
        # that never touch image generation (e.g. /start, /kota).
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def generate_image(self, prompt: str) -> bytes:
        """Generate a single image for `prompt` and return raw PNG/JPEG bytes.

        Raises:
            ProviderNotConfiguredError: if no API key was supplied.
            ImageGenerationError: on any provider-side failure after retries.
        """
        client = self._ensure_client()

        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 2):
            try:
                logger.info(
                    "DALL-E 3 isteği gönderiliyor (deneme %s/%s): %.80s...",
                    attempt,
                    _MAX_RETRIES + 1,
                    prompt,
                )
                response = await client.images.generate(
                    model=self._model,
                    prompt=prompt,
                    size=self._size,  # type: ignore[arg-type]
                    n=1,
                    response_format="url",
                )
                image_url = response.data[0].url
                if not image_url:
                    raise ImageGenerationError("DALL-E 3 yanıtında görsel URL'si bulunamadı.")
                return await self._download(image_url)
            except ProviderNotConfiguredError:
                raise
            except Exception as exc:  # noqa: BLE001 - provider SDK raises its own hierarchy
                last_error = exc
                logger.warning("DALL-E 3 isteği başarısız (deneme %s): %s", attempt, exc)
                if attempt <= _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)

        raise ImageGenerationError(f"DALL-E 3 görsel üretimi başarısız oldu: {last_error}") from last_error

    async def _download(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=self._timeout)) as resp:
                if resp.status != 200:
                    raise ImageGenerationError(
                        f"Üretilen görsel indirilemedi (HTTP {resp.status})."
                    )
                return await resp.read()
