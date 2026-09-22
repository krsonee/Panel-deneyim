"""Gemini görsel ve Veo video çağrıları. Anahtar sadece ortam değişkeninden okunur."""

import base64
import json
import os
import time
import urllib.error
import urllib.request
from io import BytesIO

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
VIDEO_MODEL = os.environ.get("GEMINI_VIDEO_MODEL", "veo-3.1-lite-generate-preview")

# Kalite ayarları ortam değişkeniyle açılır, koda dokunmadan ayarlanabilir.
# 1'den büyük bir sayı, aynı prompt için birden çok görsel isteyip en netini
# seçer (maliyet aynı oranda artar, bu yüzden varsayılan kapalı: 1).
IMAGE_CANDIDATES = max(1, int(os.environ.get("MEDIA_IMAGE_CANDIDATES", "1") or "1"))

VIDEO_RESOLUTION = os.environ.get("GEMINI_VIDEO_RESOLUTION", "720p")
VIDEO_DURATION_SECONDS = int(os.environ.get("GEMINI_VIDEO_DURATION_SECONDS", "4") or "4")
VIDEO_GENERATE_AUDIO = os.environ.get("GEMINI_VIDEO_AUDIO", "").strip().lower() in ("1", "true", "yes")
VIDEO_NEGATIVE_PROMPT = os.environ.get(
    "GEMINI_VIDEO_NEGATIVE_PROMPT",
    "flicker, jitter, morphing text, warped logo, distorted face, extra limbs, low detail, "
    "washed out colors, choppy motion, watermark",
).strip()


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
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise GeminiError(f"Google bağlantı hatası: {reason}") from exc
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


def extract_images(payload):
    """Dönen JSON'daki tüm görsel adaylarını sırayla listeler.

    Tek adaylık eski davranışla uyumlu kalması için sıralama önceliği aynı:
    output_image, sonra steps, sonra candidates. Best-of-N seçimi bu listeden yapılır.
    """
    images = []
    if not isinstance(payload, dict):
        return images
    interaction_id = payload.get("id") or payload.get("name")
    image = payload.get("output_image") or {}
    parsed = _image_block(image)
    if parsed:
        data, mime = parsed
        images.append({"bytes": data, "mime": mime, "interaction_id": interaction_id})
    for step in payload.get("steps") or []:
        for block in step.get("content") or []:
            parsed = _image_block(block)
            if parsed:
                data, mime = parsed
                images.append({"bytes": data, "mime": mime, "interaction_id": interaction_id})
    for candidate in payload.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            parsed = _image_block(part)
            if parsed:
                data, mime = parsed
                images.append({"bytes": data, "mime": mime, "interaction_id": interaction_id})
    return images


def extract_image(payload):
    """Dönen JSON'dan ilk görselin baytını ve interaction id'sini çıkarır."""
    images = extract_images(payload)
    return images[0] if images else None


def _detail_score(image_bytes):
    """Kaba bir netlik/detay skoru: kenar yoğunluğunun standart sapması.

    Düz, clipart gibi çıkan görseller kenar bakımından zayıf olur; skoru
    yüksek olan aday genelde daha ayrıntılı ve daha keskin dokuya sahiptir.
    """
    try:
        from PIL import Image, ImageFilter
        import statistics

        picture = Image.open(BytesIO(image_bytes)).convert("L")
        picture.thumbnail((256, 256))
        edges = picture.filter(ImageFilter.FIND_EDGES)
        pixels = edges.tobytes()
        if len(pixels) < 2:
            return 0.0
        return statistics.pstdev(pixels)
    except Exception:
        return 0.0


def _pick_best_image(images):
    if len(images) <= 1:
        return images[0] if images else None
    return max(images, key=lambda item: _detail_score(item["bytes"]))


def image_failure_reason(payload):
    if not isinstance(payload, dict):
        return None
    feedback = payload.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        return f"Google bu isteği geri çevirdi ({feedback['blockReason']})"
    for candidate in payload.get("candidates") or []:
        reason = candidate.get("finishReason")
        if reason and reason not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            return f"Google görseli tamamlamadı ({reason})"
    return None


def _image_block(block):
    if not isinstance(block, dict):
        return None
    data = block.get("data")
    inline = block.get("inline_data") or block.get("inlineData") or {}
    if not data and isinstance(inline, dict):
        data = inline.get("data")
    if not data:
        return None
    mime = (
        block.get("mime_type")
        or block.get("mimeType")
        or (inline.get("mime_type") if isinstance(inline, dict) else None)
        or (inline.get("mimeType") if isinstance(inline, dict) else None)
        or "image/png"
    )
    try:
        return base64.b64decode(data), mime
    except (ValueError, TypeError):
        return None


def _reference_list(reference):
    if not reference:
        return []
    if isinstance(reference, dict):
        return [reference] if reference.get("bytes") else []
    return [item for item in reference if item and item.get("bytes")]


def image_parts(prompt, reference=None, image_first=False):
    """Maskot düzeninde fotoğraf metinden önce gider, model yeni karakter uydurmasın."""
    text = {"text": prompt}
    images = []
    for item in _reference_list(reference):
        images.append({
            "inlineData": {
                "mimeType": item.get("mime") or "image/png",
                "data": base64.b64encode(item["bytes"]).decode("ascii"),
            }
        })
    if image_first and images:
        return images + [text]
    return [text] + images


def generate_image(prompt, aspect_ratio, previous_interaction_id=None, reference=None, image_first=False, candidates=None):
    """reference bir logo ya da önceki görsel olabilir. Liste de kabul edilir.

    candidates > 1 olursa aynı prompt için birden çok görsel istenir ve
    en detaylı/net görünen aday otomatik seçilir (bkz. _detail_score).
    """
    parts = image_parts(prompt, reference, image_first=image_first)
    if previous_interaction_id and len(parts) == 1:
        parts[0]["text"] = prompt + " Keep the previous poster and apply only the requested change."
    candidate_count = candidates if candidates is not None else IMAGE_CANDIDATES
    generation_config = {
        "responseModalities": ["IMAGE", "TEXT"],
        "imageConfig": {"aspectRatio": aspect_ratio},
    }
    if candidate_count > 1:
        generation_config["candidateCount"] = candidate_count
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
    }
    payload = _request(
        f"{API_BASE}/models/{IMAGE_MODEL}:generateContent",
        body,
        timeout=70,
    )
    images = extract_images(payload)
    best = _pick_best_image(images)
    if not best:
        raise GeminiError(image_failure_reason(payload) or "Model görsel döndürmedi. Metni kısaltıp tekrar dene.")
    return best


def video_request_body(prompt, image_bytes, mime, aspect_ratio):
    """Veo, Gemini'deki inlineData alanını kabul etmez."""
    image_bytes, mime = _shrink_for_video(image_bytes, mime)
    parameters = {
        "aspectRatio": aspect_ratio,
        "durationSeconds": VIDEO_DURATION_SECONDS,
        "resolution": VIDEO_RESOLUTION,
        "sampleCount": 1,
    }
    if VIDEO_NEGATIVE_PROMPT:
        parameters["negativePrompt"] = VIDEO_NEGATIVE_PROMPT
    if VIDEO_GENERATE_AUDIO:
        parameters["generateAudio"] = True
    return {
        "instances": [
            {
                "prompt": prompt,
                "image": {
                    "mimeType": mime or "image/jpeg",
                    "bytesBase64Encoded": base64.b64encode(image_bytes).decode("ascii"),
                },
            }
        ],
        "parameters": parameters,
    }


def _shrink_for_video(image_bytes, mime):
    try:
        from PIL import Image
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image.thumbnail((1280, 1280))
        out = BytesIO()
        image.save(out, format="JPEG", quality=85)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, mime or "image/png"


def generate_video(prompt, image_bytes, mime, aspect_ratio):
    """4 saniyelik 720p video. Veo kare (1:1) kabul etmez."""
    body = video_request_body(prompt, image_bytes, mime, aspect_ratio)
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
