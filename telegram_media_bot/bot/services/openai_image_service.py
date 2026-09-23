"""OpenAI DALL-E 3 image generation service.

Wraps the official `openai` async client. The heavy import is done lazily
inside the class so the rest of the bot can start even if the `openai`
package (or its transitive deps) is missing in a given environment.

TODO(production): once a real OPENAI_API_KEY is set in .env, this module
works end-to-end as-is. Nothing else needs to change.

Model compatibility note
-------------------------
We do **not** send the `response_format` parameter at all, on purpose.

`response_format` used to be required to request base64 output from
`dall-e-2`/`dall-e-3`, and OpenAI's newer GPT image models (`gpt-image-1`
and successors) never supported it in the first place — both raise
``400 Unknown parameter: 'response_format'`` once an account/API version
stops accepting it. Rather than trying to special-case every model
family (which broke in practice: an earlier version of this file gated
the parameter on the model name, but real-world `dall-e-3` accounts
started rejecting it too), we simply never ask for a specific format.
`_extract_image_bytes()` below reads whichever field the response
actually populated (`b64_json` or `url`), which works unconditionally
across every model/account variant we've observed.

As an extra safety net, `_call_with_unknown_parameter_fallback()` detects
*any* "unknown_parameter" 400 error from the API, drops that specific
parameter from the request, and retries once. This means if some other
parameter we send (`size`, `n`, ...) is ever rejected by a future API
change, the request self-heals instead of hard-failing.
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
_UNKNOWN_PARAMETER_ERROR_CODE = "unknown_parameter"


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

        # Deliberately no `response_format` — see module docstring.
        request_kwargs: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "size": self._size,
            "n": 1,
        }

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
                response = await self._call_with_unknown_parameter_fallback(client, request_kwargs)
                return await self._extract_image_bytes(response.data[0])
            except ProviderNotConfiguredError:
                raise
            except Exception as exc:  # noqa: BLE001 - provider SDK raises its own hierarchy
                last_error = exc
                logger.warning("DALL-E 3 isteği başarısız (deneme %s): %s", attempt, exc)
                if attempt <= _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)

        raise ImageGenerationError(f"DALL-E 3 görsel üretimi başarısız oldu: {last_error}") from last_error

    async def _call_with_unknown_parameter_fallback(self, client, request_kwargs: dict[str, object]):
        """Call `images.generate()`; if the API rejects one of our own
        parameters as unknown, drop it and retry once immediately.

        This is a defensive net against API/account drift — e.g. some
        accounts started rejecting `response_format` even on `dall-e-3`,
        after previously requiring it. We no longer send that parameter by
        default, but this fallback protects against the *next* parameter
        that might get deprecated without a corresponding code change here.
        """
        try:
            return await client.images.generate(**request_kwargs)
        except Exception as exc:  # noqa: BLE001 - inspecting provider SDK error shape
            offending_param = getattr(exc, "param", None)
            error_code = getattr(exc, "code", None)
            if error_code == _UNKNOWN_PARAMETER_ERROR_CODE and offending_param in request_kwargs:
                logger.warning(
                    "OpenAI '%s' parametresini reddetti (unknown_parameter); "
                    "bu parametre olmadan tekrar deneniyor.",
                    offending_param,
                )
                retry_kwargs = {k: v for k, v in request_kwargs.items() if k != offending_param}
                return await client.images.generate(**retry_kwargs)
            raise

    async def _extract_image_bytes(self, image_entry: object) -> bytes:
        """Pull raw image bytes out of a single `images.generate()` result item.

        Handles both possible response shapes: `b64_json` (the default for
        GPT image models, and what dall-e-2/3 return when no
        `response_format` is given depends on API version) and `url`.
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
