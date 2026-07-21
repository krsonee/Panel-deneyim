"""Tek kod tabanı — PANEL_BRAND ile Makro / Bizzo ayrımı.

Her panel yalnızca kendi marka metinlerini / varsayılanlarını görür.
Bio sayfa materyalleri (bonus kartı, CTA, placeholder, font) markaya özeldir —
iki panel dışarıdan kopya görünmesin diye bilinçli olarak farklı tutulur.
"""
from __future__ import annotations

import os

_RAW = (os.environ.get("PANEL_BRAND") or "makro").strip().lower()
PANEL_BRAND = "bizzo" if _RAW in ("bizzo", "bizzocasino", "bizzo-casino") else "makro"

# Mailing yalnızca Makro panel + allowlist kullanıcılar (varsayılan: tolgakt)
_MAILING_USERS_RAW = (os.environ.get("MAILING_ALLOWED_USERS") or "tolgakt").strip().lower()
MAILING_ALLOWED_USERS = frozenset(
    u.strip() for u in _MAILING_USERS_RAW.split(",") if u.strip()
)

# Mikromail ayrıldı: panelde mailing varsayılan kapalı (SERVICE_MODE=panel).
# Embedded mailing yalnızca MAILING_EMBEDDED=1 ile açılır (geçiş dönemi).
_SERVICE_MODE = (os.environ.get("SERVICE_MODE") or "panel").strip().lower()
_MAILING_EMBEDDED = (os.environ.get("MAILING_EMBEDDED") or "").strip().lower() in (
    "1", "true", "yes", "on",
)
_MAILING_ON_PANEL = PANEL_BRAND == "makro" and (
    _SERVICE_MODE == "mailing" or _MAILING_EMBEDDED
)

# Makro'da mailing (embedded) opsiyonel; Bizzo'da kapalı
_BASE_MODULES = ("tracking", "accounting", "biolink")
ENABLED_MODULES = _BASE_MODULES + (("mailing",) if _MAILING_ON_PANEL else ())

FEATURES = {
    # Makro: Smartico TAP rapor + üye taşıma (int-api). Bizzo: kapalı.
    "smartico": PANEL_BRAND == "makro",
    "blink": False,
    "mailing": _MAILING_ON_PANEL,
    "marketing": False,
    "makrolink": True,
    "accounting": True,
    "biolink": True,
    "tracking": True,
}
MAILING_STANDALONE = _SERVICE_MODE == "mailing"

# Bio studio + public sayfa materyalleri (markaya özel — kopya görünümü engelle)
_BIOLINK_PACKS = {
    "makro": {
        "handle": "makrovip",
        "site_url": "https://makrogir.com",
        "youtube_url": "https://youtube.com/@makrovip",
        "font": "Plus Jakarta Sans",
        "font_url": "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap",
        "bonus_chip_label": "Bonus / Promo",
        "bonus_color": "#f5c451",
        "bonus_icon": "🎁",
        "bonus_skin": "classic",
        "bonus_kicker": "",
        "bonus_default_label": "3.000 TL Deneme Bonusu",
        "bonus_default_badge": "YENİ",
        "bonus_title_field": "Promo başlığı",
        "bonus_badge_field": "Etiket / tutar",
        "bonus_title_placeholder": "500.000 TL Slot Turnuvası",
        "bonus_badge_placeholder": "3.000 TL",
        "bonus_cta_strong": "Katıl →",
        "bonus_cta_rest": "Promosyonu görüntüle",
        "bonus_composer_hint": "Promo kartı — etiket + link",
        "heading_default": "🏆 Aktif Etkinlikler",
        "link_default_label": "Siteye Git",
        "link_label_placeholder": "Resmi Site",
        "link_color": "#6366f1",
        "wa_default": "WhatsApp Destek",
        "tg_default": "Telegram VIP Grubu",
        "new_page_title": "Yeni Sayfa",
    },
    "bizzo": {
        "handle": "bizzocasino",
        "site_url": "https://www.bizzocasino168.com",
        "youtube_url": "https://youtube.com/@bizzocasino",
        "font": "Outfit",
        "font_url": "https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap",
        "bonus_chip_label": "Kampanya Kartı",
        "bonus_color": "#b2ff4f",
        "bonus_icon": "💎",
        "bonus_skin": "table",
        "bonus_kicker": "BIZZO KAMPANYA",
        "bonus_default_label": "%100 Slot Hoş Geldin",
        "bonus_default_badge": "SINIRSIZ",
        "bonus_title_field": "Kampanya adı",
        "bonus_badge_field": "Vurgu metni",
        "bonus_title_placeholder": "%100 Slot Hoş Geldin Bonusu",
        "bonus_badge_placeholder": "Çekim Yapana kadar SINIRSIZ",
        "bonus_cta_strong": "Bonusu Al →",
        "bonus_cta_rest": "Hemen oyna",
        "bonus_composer_hint": "Kampanya bileti — vurgu + link",
        "heading_default": "🎰 Canlı Promosyonlar",
        "link_default_label": "Bizzo'ya Git",
        "link_label_placeholder": "Güncel Giriş",
        "link_color": "#b2ff4f",
        "wa_default": "Bizzo WhatsApp Destek",
        "tg_default": "Bizzo Telegram",
        "new_page_title": "Bizzo Bio",
    },
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
        "biolink_pack": _BIOLINK_PACKS["makro"],
        "default_tracked_domains": [],
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
        "accent": "#b2ff4f",
        "invoice_vendor": "Bizzo",
        "invoice_vendor_upper": "BIZZO",
        "biolink_default_theme": "bizzo",
        "biolink_theme_categories_include": None,
        "biolink_theme_categories_exclude": ("Makrobet",),
        "biolink_logo_label": "Bizzo Logo",
        "biolink_favicon_placeholder": "Boş = Bizzo favicon / logo",
        "biolink_title_placeholder": "BIZZO DESTEK HATTI",
        "biolink_slug_placeholder": "bizzo-destek",
        "biolink_domain_placeholder": "bizzocasino168.com",
        "biolink_promo_placeholder": "https://www.bizzocasino168.com/…",
        "default_brand_logo": "/static/biolink/logo/bizzo/logo-main.svg",
        "default_favicon": "/static/biolink/favicons/favicon-bizzo.png",
        "show_stock_brand_assets": True,
        "totp_issuer": "BizzoPanel",
        "tracker_comment": "BizzoPanel — ortak takip kodu",
        "biolink_pack": _BIOLINK_PACKS["bizzo"],
        # Link Takip’e otomatik eklenen domainler (online sayacı; www normalize edilir)
        "default_tracked_domains": [
            {"domain": "bizzocasino168.com", "label": "Bizzo Casino (ana site)"},
        ],
    },
}

BRAND = _BRANDS[PANEL_BRAND]
BIOLINK_PACK = BRAND["biolink_pack"]


def feature_enabled(name: str) -> bool:
    return bool(FEATURES.get(name, False))


def can_access_mailing(username: str | None) -> bool:
    """Mailing UI + API: yalnızca Makro markası ve allowlist kullanıcılar."""
    if PANEL_BRAND != "makro" or not feature_enabled("mailing"):
        return False
    user = (username or "").strip().lower()
    return bool(user) and user in MAILING_ALLOWED_USERS


def panel_context(username: str | None = None) -> dict:
    """Jinja /api/me için panel bağlamı.

    username verilirse mailing özelliği kullanıcı allowlist'ine göre maskelenir
    (diğer admin hesapları menüde Mailing görmez).
    """
    pack = dict(BRAND.get("biolink_pack") or {})
    features = dict(FEATURES)
    if features.get("mailing") and username is not None and not can_access_mailing(username):
        features["mailing"] = False
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
        "default_brand_logo": BRAND.get("default_brand_logo") or "",
        "default_favicon": BRAND.get("default_favicon") or "",
        "biolink_pack": pack,
        "enabled_modules": list(ENABLED_MODULES),
        "features": features,
        "mikromail_url": (
            os.environ.get("MIKROMAIL_URL")
            or os.environ.get("MAKROMAIL_URL")
            or "https://mikromail.onrender.com"
        ).rstrip("/"),
        # Geriye uyumluluk
        "makromail_url": (
            os.environ.get("MIKROMAIL_URL")
            or os.environ.get("MAKROMAIL_URL")
            or "https://mikromail.onrender.com"
        ).rstrip("/"),
        "mailing_standalone": MAILING_STANDALONE,
    }
