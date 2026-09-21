"""Gemini görsel ve Veo video çağrıları. Anahtar sadece ortam değişkeninden okunur."""

import base64
import json
import os
import time
import urllib.error
import urllib.request

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
VIDEO_MODEL = os.environ.get("GEMINI_VIDEO_MODEL", "veo-3.1-lite-generate-preview")


class GeminiError(RuntimeError):
    pass


def _api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiError("GEMINI_API_KEY yok")
    return key


def _request(url, payload=None, timeout=120):
    data = None
    headers = {"x-goog-api-key": _api_key()}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise GeminiError(_short_error(body) or f"Google {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise GeminiError(f"Google bağlantı hatası: {exc.reason}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _short_error(body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:300]
    err = payload.get("error") or {}
    return err.get("message") or body[:300]


def extract_image(payload):
    """Dönen JSON'dan son görselin baytını ve interaction id'sini çıkarır."""
    if not isinstance(payload, dict):
        return None
    interaction_id = payload.get("id") or payload.get("name")
    image = payload.get("output_image") or {}
    parsed = _image_block(image)
    if parsed:
        data, mime = parsed
        return {"bytes": data, "mime": mime, "interaction_id": interaction_id}
    for step in payload.get("steps") or []:
        for block in step.get("content") or []:
            parsed = _image_block(block)
            if parsed:
                data, mime = parsed
                return {"bytes": data, "mime": mime, "interaction_id": interaction_id}
    return None


def _image_block(block):
    if not isinstance(block, dict):
        return None
    data = block.get("data")
    if not data and isinstance(block.get("inline_data"), dict):
        data = block["inline_data"].get("data")
    if not data:
        return None
    mime = block.get("mime_type") or block.get("mimeType") or "image/png"
    try:
        return base64.b64decode(data), mime
    except (ValueError, TypeError):
        return None


def generate_image(prompt, aspect_ratio, previous_interaction_id=None, reference=None):
    """reference = {'bytes': b, 'mime': 'image/png'} önceki görseli düzenlemek için."""
    if reference:
        user_input = [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "data": base64.b64encode(reference["bytes"]).decode("ascii"),
                "mime_type": reference.get("mime") or "image/png",
            },
        ]
    else:
        user_input = prompt
    body = {
        "model": IMAGE_MODEL,
        "input": user_input,
        "response_format": {
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": aspect_ratio,
            "image_size": "1K",
        },
    }
    if previous_interaction_id:
        body["previous_interaction_id"] = previous_interaction_id
    payload = _request(f"{API_BASE}/interactions", body, timeout=180)
    image = extract_image(payload)
    if not image:
        raise GeminiError("Model görsel döndürmedi. Metni kısaltıp tekrar dene.")
    return image


def generate_video(prompt, image_bytes, mime, aspect_ratio):
    """4 saniyelik 720p video. Veo kare (1:1) kabul etmez."""
    body = {
        "instances": [
            {
                "prompt": prompt,
                "image": {
                    "inlineData": {
                        "mimeType": mime or "image/png",
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                    }
                },
            }
        ],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "durationSeconds": "4",
            "resolution": "720p",
        },
    }
    started = _request(
        f"{API_BASE}/models/{VIDEO_MODEL}:predictLongRunning",
        body,
        timeout=60,
    )
    name = started.get("name")
    if not name:
        raise GeminiError("Video işi başlamadı")
    deadline = time.time() + 300
    while time.time() < deadline:
        status = _request(f"{API_BASE}/{name}", timeout=60)
        if status.get("done"):
            if status.get("error"):
                raise GeminiError(status["error"].get("message") or "Video hatası")
            uri = _video_uri(status)
            if not uri:
                raise GeminiError("Video hazır görünüyor ama indirme linki yok")
            return _download(uri)
        time.sleep(8)
    raise GeminiError("Video 5 dakikada bitmedi. Tekrar dene.")


def _video_uri(status):
    response = status.get("response") or {}
    samples = (
        (response.get("generateVideoResponse") or {}).get("generatedSamples")
        or response.get("generatedSamples")
        or []
    )
    if not samples:
        videos = response.get("generatedVideos") or []
        if videos:
            video = videos[0].get("video") or {}
            return video.get("uri")
        return None
    video = (samples[0] or {}).get("video") or {}
    return video.get("uri")


def _download(uri):
    req = urllib.request.Request(uri, headers={"x-goog-api-key": _api_key()})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise GeminiError(f"Video indirilemedi ({exc.code})") from exc
    if not data:
        raise GeminiError("Video dosyası boş")
    return data
