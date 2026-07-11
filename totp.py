"""Basit TOTP (RFC 6238) — Google Authenticator uyumlu, ek bağımlılık yok."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

ISSUER = "MakroPanel"


def generate_secret():
    """32 karakterlik Base32 secret (Authenticator uygulamalarıyla uyumlu)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").rstrip("=")


def _hotp(secret_b32, counter, digits=6):
    key = base64.b32decode(_pad_b32(secret_b32), casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code_int).zfill(digits)


def _pad_b32(secret_b32):
    secret_b32 = (secret_b32 or "").strip().upper().replace(" ", "")
    pad = (-len(secret_b32)) % 8
    return secret_b32 + ("=" * pad)


def current_code(secret_b32, digits=6, period=30, at_time=None):
    counter = int((at_time if at_time is not None else time.time()) // period)
    return _hotp(secret_b32, counter, digits)


def verify_code(secret_b32, code, digits=6, period=30, window=1, at_time=None):
    """window=1 → önceki/şu anki/sonraki 30 sn dilimine tolerans (saat kayması)."""
    code = (code or "").strip().replace(" ", "")
    if not code or not code.isdigit():
        return False
    now = at_time if at_time is not None else time.time()
    counter = int(now // period)
    for offset in range(-window, window + 1):
        if _hotp(secret_b32, counter + offset, digits) == code:
            return True
    return False


def build_otpauth_uri(secret_b32, account_name, issuer=ISSUER):
    label = urllib.parse.quote(f"{issuer}:{account_name}")
    query = urllib.parse.urlencode({
        "secret": secret_b32,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    })
    return f"otpauth://totp/{label}?{query}"


def qr_svg_data_uri(uri):
    """QR'ı tamamen sunucuda (üçüncü taraf yok) üretir; qrcode paketi kurulu değilse None döner."""
    try:
        import io

        import qrcode
        import qrcode.image.svg

        img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        svg_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/svg+xml;base64,{svg_b64}"
    except Exception:
        return None
