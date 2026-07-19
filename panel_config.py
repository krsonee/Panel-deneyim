"""Tek kod tabanı — PANEL_BRAND ile Makro / Bizzo ayrımı.

Her panel yalnızca kendi marka metinlerini / varsayılanlarını görür.
"""
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
    "makrolink": True,
    "accounting": True,
    "biolink": True,
    "tracking": True,
}

_BRANDS = {
    "makro": {
        "brand": "makro",
        "service_name": "makropanel",
        "product_name": "MakroPanel",
        "product_html": "Makro<span>Panel</span>",
        "tagline": "Yönetim Merkezi",
        "login_sub": "Link takip, bio sayfa ve muhasebe",
        "casino_name": "Makrobet",
        "shortlink_label": "Kısa Link",
        "shortlink_host_placeholder": "kisalink.com",
        "default_short_host": "",
        "default_aff_base": "",
        "domain_prefix_placeholder": "makrobet",
        "accent": "#6366f1",
        "invoice_vendor": "Pronet",
        "invoice_vendor_upper": "PRONET",
        "biolink_default_theme": "makrobet",
        "biolink_theme_categories_include": None,  # hepsi
        "biolink_theme_categories_exclude": ("Bizzo",),
        "biolink_logo_label": "Makrobet Logo",
        "biolink_favicon_placeholder": "Boş = Makrobet favicon / logo",
        "biolink_title_placeholder": "MAKROVIP DESTEK HATTI",
        "biolink_slug_placeholder": "vipmakro",
        "biolink_domain_placeholder": "vipmakro.com",
        "biolink_promo_placeholder": "https://makrobet804.com/…",
        "default_brand_logo": "/static/biolink/logo/logo-400.png",
        "default_favicon": "/static/biolink/favicons/favicon-makrobet.ico",
        "show_stock_brand_assets": True,
        "totp_issuer": "MakroPanel",
        "tracker_comment": "MakroPanel — ortak takip kodu",
    },
    "bizzo": {
        "brand": "bizzo",
        "service_name": "bizzopanel",
        "product_name": "BizzoPanel",
        "product_html": "Bizzo<span>Panel</span>",
        "tagline": "Bizzo Casino Yönetim",
        "login_sub": "Link takip, bio sayfa ve muhasebe",
        "casino_name": "Bizzo Casino",
        "shortlink_label": "Kısa Link",
        "shortlink_host_placeholder": "kisalink.com",
        "default_short_host": "",
        "default_aff_base": "",
        "domain_prefix_placeholder": "bizzocasino",
        "accent": "#e11d48",
        "invoice_vendor": "Bizzo",
        "invoice_vendor_upper": "BIZZO",
        "biolink_default_theme": "bizzo",
        "biolink_theme_categories_include": None,
        "biolink_theme_categories_exclude": ("Makrobet",),
        "biolink_logo_label": "Bizzo Logo",
        "biolink_favicon_placeholder": "Boş = yüklediğiniz favicon / logo",
        "biolink_title_placeholder": "BIZZO DESTEK HATTI",
        "biolink_slug_placeholder": "bizzo-destek",
        "biolink_domain_placeholder": "ornek-domain.com",
        "biolink_promo_placeholder": "https://ornek-domain.com/…",
        "default_brand_logo": "",
        "default_favicon": "",
        "show_stock_brand_assets": False,
        "totp_issuer": "BizzoPanel",
        "tracker_comment": "BizzoPanel — ortak takip kodu",
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
        "casino_name": BRAND["casino_name"],
        "shortlink_label": BRAND["shortlink_label"],
        "shortlink_host_placeholder": BRAND["shortlink_host_placeholder"],
        "domain_prefix_placeholder": BRAND["domain_prefix_placeholder"],
        "accent": BRAND["accent"],
        "invoice_vendor": BRAND["invoice_vendor"],
        "invoice_vendor_upper": BRAND["invoice_vendor_upper"],
        "biolink_default_theme": BRAND["biolink_default_theme"],
        "biolink_logo_label": BRAND["biolink_logo_label"],
        "biolink_favicon_placeholder": BRAND["biolink_favicon_placeholder"],
        "biolink_title_placeholder": BRAND["biolink_title_placeholder"],
        "biolink_slug_placeholder": BRAND["biolink_slug_placeholder"],
        "biolink_domain_placeholder": BRAND["biolink_domain_placeholder"],
        "biolink_promo_placeholder": BRAND["biolink_promo_placeholder"],
        "enabled_modules": list(ENABLED_MODULES),
        "features": dict(FEATURES),
    }
