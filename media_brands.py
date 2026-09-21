"""Telegram medya botundaki markalar.

Yeni marka eklemek için BRANDS sözlüğüne bir kayıt koy.
Anahtar kısa ve harf/rakam olmalı (buton kodunda kullanılır).
logo: bu dosyadaki gerçek logo. Bot harfleri yeniden çizmez, bu dosyayı basar.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent

BRANDS = {
    "makrobet": {
        "name": "Makrobet",
        "domain": "makrobet818.com",
        "colors": "koyu lacivert zemin (#08142c), altın sarısı ve beyaz logo",
        "wordmark": "MAKROBET",
        "logo": "static/mailing/makrobet-logo.png",
    },
    "betced": {
        "name": "Betced",
        "domain": "betced368.com",
        "colors": "koyu lacivert zemin (#0D1824), turuncu fiş logosu (#FD6A02), beyaz yazı",
        "wordmark": "BETCED",
        "logo": "static/media/betced-logo.png",
    },
}

FORMATS = {
    "1x1": ("1:1", "1:1 Kare"),
    "9x16": ("9:16", "9:16 Dikey"),
    "16x9": ("16:9", "16:9 Yatay"),
}

CATEGORIES = {
    "casino": "Casino Promo",
    "sport": "Spor Bahisi",
    "slot": "Slot",
}


def brand_list():
    return [(key, BRANDS[key]) for key in BRANDS]


def logo_reference(brand_key):
    rel = (BRANDS.get(brand_key) or {}).get("logo")
    if not rel:
        return None
    path = ROOT / rel
    if not path.is_file():
        return None
    return {"bytes": path.read_bytes(), "mime": "image/png"}
