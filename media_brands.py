"""Telegram medya botundaki markalar.

Yeni marka eklemek için BRANDS sözlüğüne bir kayıt koy.
Anahtar kısa ve harf/rakam olmalı (buton kodunda kullanılır).
"""

BRANDS = {
    "makrobet": {
        "name": "Makrobet",
        "domain": "makrobet.com",
        "colors": "koyu lacivert arka plan (#08142c), altın sarısı vurgu (#ffcc00), beyaz yazı",
        "wordmark": "MAKROBET",
    },
    "betced": {
        "name": "Betced",
        "domain": "betced.com",
        "colors": "siyah arka plan, zümrüt yeşili vurgu, beyaz yazı",
        "wordmark": "BETCED",
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
