"""Tek kod tabanı — PANEL_BRAND ile Makro / Bizzo ayrımı."""
from __future__ import annotations

import os

_RAW = (os.environ.get("PANEL_BRAND") or "makro").strip().lower()
PANEL_BRAND = "bizzo" if _RAW in ("bizzo", "bizzocasino", "bizzo-casino") else "makro"

# Her iki panelde aynı sade modül seti
ENABLED_MODULES = ("tracking", "accounting", "biolink")

FEATURES = {
    "smartico": False,
    "blink": False,
    "mailing": False,
    "marketing": False,
    "makrolink": True,  # Kısa link (domain hedefi; Smartico yok)
    "accounting": True,
    "biolink": True,
    "tracking": True,
}

_BRANDS = {
    "makro": {
        "brand": "makro",
        "service_name": "makropanel",
        "product_name": "MakroPanel",
        "product_html": 'Makro<span>Panel</span>',
        "tagline": "Yönetim Merkezi",
        "login_sub": "Link takip, bio sayfa ve muhasebe",
        "shortlink_label": "Kısa Link",
        "shortlink_host_placeholder": "kisalink.com",
        "default_short_host": "",
        "default_aff_base": "",
        "accent": "#6366f1",
        # Muhasebe fatura alanı görünen adı (API/tablo adı pronet kalabilir)
        "invoice_vendor": "Pronet",
        "invoice_vendor_upper": "PRONET",
    },
    "bizzo": {
        "brand": "bizzo",
        "service_name": "bizzopanel",
        "product_name": "BizzoPanel",
        "product_html": 'Bizzo<span>Panel</span>',
        "tagline": "Bizzo Casino Yönetim",
        "login_sub": "Link takip, bio sayfa ve muhasebe",
        "shortlink_label": "Kısa Link",
        "shortlink_host_placeholder": "kisalink.com",
        "default_short_host": "",
        "default_aff_base": "",
        "accent": "#e11d48",
        "invoice_vendor": "Bizzo",
        "invoice_vendor_upper": "BIZZO",
    },
}

BRAND = _BRANDS[PANEL_BRAND]


def feature_enabled(name: str) -> bool:
    return bool(FEATURES.get(name, False))


def panel_context() -> dict:
    """Jinja /api/me için panel bağlamı."""
    return {
        "brand": BRAND["brand"],
        "service_name": BRAND["service_name"],
        "product_name": BRAND["product_name"],
        "product_html": BRAND["product_html"],
        "tagline": BRAND["tagline"],
        "login_sub": BRAND["login_sub"],
        "shortlink_label": BRAND["shortlink_label"],
        "shortlink_host_placeholder": BRAND["shortlink_host_placeholder"],
        "accent": BRAND["accent"],
        "invoice_vendor": BRAND["invoice_vendor"],
        "invoice_vendor_upper": BRAND["invoice_vendor_upper"],
        "enabled_modules": list(ENABLED_MODULES),
        "features": dict(FEATURES),
    }
