"""OpenAI DALL-E 3 image generation service.

Wraps the official `openai` async client. The heavy import is done lazily
inside the class so the rest of the bot can start even if the `openai`
package (or its transitive deps) is missing in a given environment.

TODO(production): once a real OPENAI_API_KEY is set in .env, this module
works end-to-end as-is. Nothing else needs to change.

Model compatibility note
-------------------------
OpenAI's Images API has two model families with different response
contracts:

- ``dall-e-2`` / ``dall-e-3``: accept an explicit ``response_format``
  ("url" or "b64_json").
- ``gpt-image-1`` (and successors, e.g. ``gpt-image-1.5``): do **not**
  accept ``response_format`` at all — sending it raises
  ``400 Unknown parameter: 'response_format'``. These models always
  return base64-encoded images in ``data[0].b64_json``.

`generate_image()` below only sends `response_format` for models that
support it, and reads whichever field the response actually populated
(`b64_json` first, falling back to downloading `url`), so switching
`OPENAI_IMAGE_MODEL` between families in `.env` does not require any code
changes.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import aiohttp

from bot.utils.exceptions import ImageGenerationError, ProviderNotConfiguredError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 2.0

# Model families that reject the `response_format` parameter outright and
# always return base64-encoded images (see module docstring above).
_MODELS_WITHOUT_RESPONSE_FORMAT_PREFIXES = ("gpt-image",)


def _supports_response_format(model: str) -> bool:
    normalized = model.strip().lower()
    return not normalized.startswith(_MODELS_WITHOUT_RESPONSE_FORMAT_PREFIXES)


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

        request_kwargs: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "size": self._size,
            "n": 1,
        }
        if _supports_response_format(self._model):
            # Ask for base64 directly rather than "url": it avoids a second
            # HTTP round-trip and sidesteps the fact that OpenAI's hosted
            # image URLs expire after 60 minutes. GPT image models always
            # return base64 and reject this parameter entirely, so it is
            # only added for dall-e-2/dall-e-3.
            request_kwargs["response_format"] = "b64_json"

        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 2):
            try:
                logger.info(
                    "DALL-E 3 isteği gönderiliyor (deneme %s/%s, model=%s): %.80s...",
                    attempt,
                    _MAX_RETRIES + 1,
                    self._model,
                    prompt,
                )
                response = await client.images.generate(**request_kwargs)
                return await self._extract_image_bytes(response.data[0])
            except ProviderNotConfiguredError:
                raise
            except Exception as exc:  # noqa: BLE001 - provider SDK raises its own hierarchy
                last_error = exc
                logger.warning("DALL-E 3 isteği başarısız (deneme %s): %s", attempt, exc)
                if attempt <= _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)

        raise ImageGenerationError(f"DALL-E 3 görsel üretimi başarısız oldu: {last_error}") from last_error

    async def _extract_image_bytes(self, image_entry: object) -> bytes:
        """Pull raw image bytes out of a single `images.generate()` result item.

        Handles both possible response shapes: `b64_json` (GPT image
        models always, dall-e-2/3 when requested) and `url` (dall-e-2/3
        default / fallback).
        """
        b64_json = getattr(image_entry, "b64_json", None)
        if b64_json:
            return base64.b64decode(b64_json)

        image_url = getattr(image_entry, "url", None)
        if image_url:
            return await self._download(image_url)

        raise ImageGenerationError(
            "DALL-E 3 yanıtında ne b64_json ne de url alanı bulundu; API yanıt formatı beklenenden farklı."
        )

    async def _download(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=self._timeout)) as resp:
                if resp.status != 200:
                    raise ImageGenerationError(
                        f"Üretilen görsel indirilemedi (HTTP {resp.status})."
                    )
                return await resp.read()
