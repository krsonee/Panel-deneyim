"""Bio Sayfa — Heylink/Linktree tarzı, kendi barındırdığımız link-in-bio sayfa oluşturucu.

Akış: panel-domain/p/<slug> → sayfa render edilir → buton tıklaması panel-domain/p/<slug>/go/<button_id>
üzerinden tıklama kaydedilip (+ GA4 event) hedef URL'e 302 yönlendirilir.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from urllib.parse import urlparse

from werkzeug.utils import secure_filename

from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    insert_returning_id,
    iso,
    scalar,
    uses_postgres,
    utcnow,
)

from biolink_themes import (
    BRAND_BANNERS,
    BRAND_FAVICONS,
    BRAND_LOGOS,
    DEFAULT_BANNER,
    DEFAULT_BRAND_LOGO,
    DEFAULT_FAVICON,
    DEFAULT_HEADING_STYLE,
    DEFAULT_THEME,
    brand_assets,
    brand_default_favicon,
    brand_default_logo,
    brand_default_theme,
    resolve_theme_key,
    HEADING_STYLE_KEYS,
    HEADING_STYLES,
    THEMES,
    heading_style_list,
    normalize_heading_style,
    theme_list as _theme_list_catalog,
)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
BIOLINK_UPLOAD_DIR = os.path.join(APP_ROOT, "uploads", "biolink")
BIOLINK_UPLOAD_URL_PREFIX = "/uploads/biolink"
LOGO_UPLOAD_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"})
BANNER_UPLOAD_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
FAVICON_UPLOAD_EXTS = frozenset({".ico", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"})
LOGO_UPLOAD_MAX_BYTES = 2 * 1024 * 1024
BANNER_UPLOAD_MAX_BYTES = 6 * 1024 * 1024
FAVICON_UPLOAD_MAX_BYTES = 512 * 1024

RESERVED_SLUGS = frozenset({
    "", "admin", "api", "static", "demo", "r", "p", "site", "health", "favicon.ico",
    "robots.txt", "sitemap.xml", "login", "logout", "mail", "mailing", "go", "new",
})

BUTTON_SHAPES = ("pill", "rounded", "square")

NONE_MARKER = "__none__"
BANNER_LAYOUTS = ("top", "towers", "none")
DEFAULT_BANNER_LAYOUT = "top"
LAYOUT_COLS = ("full", "left", "right")
DEFAULT_LAYOUT_COL = "full"
TEXT_ALIGNS = ("left", "center", "right")
DEFAULT_TEXT_ALIGN = "left"

POPUP_FREQUENCIES = frozenset({"session", "day", "always"})
POPUP_SHAPES = (
    ("rounded", "Yuvarlak"),
    ("square", "Kare"),
    ("soft", "Yumuşak"),
    ("pill", "Hap"),
    ("circle", "Daire"),
    ("diamond", "Elmas"),
    ("hexagon", "Altıgen"),
    ("octagon", "Sekizgen"),
    ("triangle", "Üçgen"),
    ("ticket", "Bilet"),
    ("speech", "Balon"),
    ("arch", "Kemer"),
    ("stamp", "Pul"),
    ("glass", "Cam"),
    ("neon", "Neon"),
    ("wide", "Geniş"),
    ("compact", "Kompakt"),
)
POPUP_SHAPE_KEYS = frozenset(k for k, _ in POPUP_SHAPES)
POPUP_SIZES = frozenset({"sm", "md", "lg"})
POPUP_MEDIA_TYPES = frozenset({"auto", "image", "gif", "video", "embed"})
POPUP_UPLOAD_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
    ".mp4", ".webm", ".mov",
})
POPUP_UPLOAD_MAX_BYTES = 18 * 1024 * 1024
DEFAULT_POPUP = {
    "enabled": False,
    "title": "",
    "body": "",
    "image_url": "",
    "media_url": "",
    "media_type": "auto",
    "shape": "rounded",
    "size": "md",
    "cta_label": "Devam",
    "cta_url": "",
    "delay_ms": 500,
    "frequency": "session",
}

HEADING_TYPE = "heading"
CLICKABLE_TYPE_LIST = ("link", "whatsapp", "telegram", "instagram", "twitter", "tiktok", "youtube", "bonus")
CLICKABLE_TYPES = frozenset(CLICKABLE_TYPE_LIST)
BUTTON_TYPES = CLICKABLE_TYPES | {HEADING_TYPE}

PLATFORM_ICON_TYPES = frozenset({"whatsapp", "telegram", "instagram", "twitter", "tiktok", "youtube"})

BUTTON_TYPE_META = {
    "link": {"label": "Özel Link", "icon": "🔗", "color": "#6366f1", "group": "Genel", "brand_icon": False},
    "whatsapp": {"label": "WhatsApp", "icon": "", "color": "#25D366", "group": "Sosyal", "brand_icon": True},
    "telegram": {"label": "Telegram", "icon": "", "color": "#229ED9", "group": "Sosyal", "brand_icon": True},
    "instagram": {"label": "Instagram", "icon": "", "color": "#E4405F", "group": "Sosyal", "brand_icon": True},
    "twitter": {"label": "X (Twitter)", "icon": "", "color": "#000000", "group": "Sosyal", "brand_icon": True},
    "tiktok": {"label": "TikTok", "icon": "", "color": "#fe2c55", "group": "Sosyal", "brand_icon": True},
    "youtube": {"label": "YouTube", "icon": "", "color": "#FF0000", "group": "Sosyal", "brand_icon": True},
    "bonus": {"label": "Bonus / Promo", "icon": "🎁", "color": "#f5c451", "group": "Promo", "brand_icon": False},
    "heading": {"label": "Bölüm Başlığı", "icon": "📌", "color": "#94a3b8", "group": "Düzen", "brand_icon": False},
}


def theme_list():
    return _theme_list_catalog()


def theme_vars(theme_key, accent_override=""):
    key = resolve_theme_key(theme_key)
    t = THEMES.get(key) or THEMES[brand_default_theme()]
    out = dict(t)
    if (accent_override or "").strip():
        out["accent"] = accent_override.strip()
    out["animated"] = bool(t.get("animated"))
    out["animation"] = t.get("animation") or ""
    out["accent2"] = t.get("accent2") or out["accent"]
    out["style"] = t.get("style") or "classic"
    out["category"] = t.get("category") or ""
    # Tema sabit marka logosu — sayfa "Logo yok" seçiminden bağımsız
    out["brand_logo"] = bool(t.get("brand_logo", True))
    logo_src = _effective_default_logo()
    out["brand_logo_src"] = logo_src if out["brand_logo"] and logo_src else ""
    out["default_banner"] = DEFAULT_BANNER
    return out


def _normalize_media_url(val):
    url = str(val or "").strip()[:500]
    if not url:
        return ""
    if url.startswith("/") or url.startswith("data:"):
        return url
    if "://" not in url:
        url = "https://" + url
    return url


def detect_popup_media_kind(url, media_type="auto"):
    """auto/image/gif/video/embed → image | video | embed."""
    mt = (media_type or "auto").strip().lower()
    if mt in ("image", "gif"):
        return "image"
    if mt == "video":
        return "video"
    if mt == "embed":
        return "embed"
    u = (url or "").strip().lower()
    if not u:
        return "image"
    if any(x in u for x in ("youtube.com/", "youtu.be/", "youtube-nocookie.com/", "vimeo.com/")):
        return "embed"
    path = u.split("?")[0].split("#")[0]
    if path.endswith((".mp4", ".webm", ".mov", ".m4v", ".ogg")):
        return "video"
    return "image"


def popup_embed_src(url):
    """YouTube / Vimeo URL → iframe src."""
    u = (url or "").strip()
    if not u:
        return ""
    try:
        parsed = urlparse(u if "://" in u else "https://" + u)
    except Exception:
        return ""
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = parsed.path or ""
    qs = urllib.parse.parse_qs(parsed.query or "")
    if host in ("youtu.be",):
        vid = path.strip("/").split("/")[0]
        return f"https://www.youtube.com/embed/{vid}?autoplay=1&mute=1&rel=0" if vid else ""
    if "youtube" in host:
        if "/embed/" in path:
            return u if "://" in u else "https://" + u
        if "/shorts/" in path:
            vid = path.split("/shorts/")[-1].split("/")[0]
            return f"https://www.youtube.com/embed/{vid}?autoplay=1&mute=1&rel=0" if vid else ""
        vid = (qs.get("v") or [""])[0]
        if vid:
            return f"https://www.youtube.com/embed/{vid}?autoplay=1&mute=1&rel=0"
    if "vimeo.com" in host:
        parts = [p for p in path.split("/") if p and p.isdigit()]
        if parts:
            return f"https://player.vimeo.com/video/{parts[0]}?autoplay=1&muted=1"
    return ""


def enrich_popup(popup):
    """Render için medya türü / embed src ekle."""
    p = normalize_popup(popup)
    media = p.get("media_url") or p.get("image_url") or ""
    kind = detect_popup_media_kind(media, p.get("media_type") or "auto")
    p["media_kind"] = kind
    p["media_url"] = media
    p["image_url"] = media  # geri uyumluluk
    p["embed_src"] = popup_embed_src(media) if kind == "embed" else ""
    p["has_media"] = bool(media)
    p["has_content"] = bool(p.get("title") or p.get("body") or media)
    return p


def popup_shape_catalog():
    return [{"key": k, "label": lab} for k, lab in POPUP_SHAPES]


def normalize_popup(raw):
    """popup_json / form dict → güvenli popup ayarları."""
    base = dict(DEFAULT_POPUP)
    if raw is None or raw == "":
        return base
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return base
    if not isinstance(data, dict):
        return base
    base["enabled"] = bool(data.get("enabled"))
    base["title"] = str(data.get("title") or "").strip()[:120]
    base["body"] = str(data.get("body") or "").strip()[:600]
    media = _normalize_media_url(data.get("media_url") or data.get("image_url") or "")
    base["media_url"] = media
    base["image_url"] = media
    mt = str(data.get("media_type") or "auto").strip().lower()
    base["media_type"] = mt if mt in POPUP_MEDIA_TYPES else "auto"
    shape = str(data.get("shape") or "rounded").strip().lower()
    base["shape"] = shape if shape in POPUP_SHAPE_KEYS else "rounded"
    size = str(data.get("size") or "md").strip().lower()
    base["size"] = size if size in POPUP_SIZES else "md"
    base["cta_label"] = str(data.get("cta_label") or "").strip()[:60] or "Devam"
    cta = str(data.get("cta_url") or "").strip()[:500]
    if cta and cta != "#" and "://" not in cta and not cta.startswith("/"):
        cta = "https://" + cta
    base["cta_url"] = cta
    try:
        delay = int(data.get("delay_ms") if data.get("delay_ms") is not None else 500)
    except (TypeError, ValueError):
        delay = 500
    base["delay_ms"] = max(0, min(delay, 15000))
    freq = str(data.get("frequency") or "session").strip().lower()
    base["frequency"] = freq if freq in POPUP_FREQUENCIES else "session"
    return base


def popup_to_json(popup):
    return json.dumps(normalize_popup(popup), ensure_ascii=False, separators=(",", ":"))


def uses_brand_icon(button_type):
    return button_type in PLATFORM_ICON_TYPES


def default_icon(button_type):
    if uses_brand_icon(button_type):
        return ""
    try:
        from panel_config import BIOLINK_PACK, PANEL_BRAND
        if PANEL_BRAND == "bizzo" and button_type == "bonus":
            return (BIOLINK_PACK.get("bonus_icon") or "💎")
    except Exception:
        pass
    meta = BUTTON_TYPE_META.get(button_type) or {}
    return meta.get("icon") or "🔗"


def button_type_catalog():
    items = [{"key": k, **dict(v)} for k, v in BUTTON_TYPE_META.items()]
    try:
        from panel_config import BIOLINK_PACK, PANEL_BRAND
        if PANEL_BRAND == "bizzo":
            for item in items:
                if item["key"] == "bonus":
                    item["label"] = BIOLINK_PACK.get("bonus_chip_label") or item["label"]
                    item["icon"] = BIOLINK_PACK.get("bonus_icon") or item["icon"]
                    item["color"] = BIOLINK_PACK.get("bonus_color") or item["color"]
    except Exception:
        pass
    return items


def is_clickable(button_type):
    return button_type in CLICKABLE_TYPES


def resolve_button_url(button_type, url, badge_text=""):
    """Ham alandan tıklanabilir hedef URL üret."""
    button_type = (button_type or "link").strip().lower()
    url = (url or "").strip()
    badge_text = (badge_text or "").strip()

    if button_type == HEADING_TYPE:
        return ""

    if button_type in ("link", "bonus"):
        if _valid_url(url):
            return _normalize_url(url)
        return ""

    if button_type == "whatsapp":
        phone = re.sub(r"\D", "", url)
        if len(phone) < 10:
            return ""
        dest = f"https://wa.me/{phone}"
        if badge_text:
            dest += "?" + urllib.parse.urlencode({"text": badge_text})
        return dest

    if button_type == "telegram":
        user = url.lstrip("@").strip().split("/")[-1]
        if not user:
            return ""
        return f"https://t.me/{user}"

    if button_type == "instagram":
        user = url.lstrip("@").strip().split("/")[-1]
        if not user:
            return ""
        return f"https://instagram.com/{user}"

    if button_type == "twitter":
        user = url.lstrip("@").strip().split("/")[-1]
        if not user:
            return ""
        return f"https://x.com/{user}"

    if button_type == "tiktok":
        user = url.lstrip("@").strip().split("/")[-1]
        if not user:
            return ""
        return f"https://www.tiktok.com/@{user}"

    if button_type == "youtube":
        if _valid_url(url):
            return _normalize_url(url)
        handle = url.lstrip("@").strip()
        if not handle:
            return ""
        if handle.startswith("UC") and len(handle) >= 20:
            return f"https://www.youtube.com/channel/{handle}"
        return f"https://www.youtube.com/@{handle}"

    return ""


def _validate_button(button_type, label, url, badge_text=""):
    button_type = button_type if button_type in BUTTON_TYPES else "link"
    label = (label or "").strip()
    if not label:
        raise ValueError("Başlık / etiket gerekli.")
    if button_type == HEADING_TYPE:
        return button_type, label, "", (badge_text or "").strip()[:80]
    dest = resolve_button_url(button_type, url, badge_text)
    if not dest:
        hints = {
            "whatsapp": "Geçerli telefon numarası girin (ülke kodu ile, örn. 905551234567).",
            "telegram": "Telegram kullanıcı adı girin (örn. makrovip).",
            "instagram": "Instagram kullanıcı adı girin.",
            "twitter": "X kullanıcı adı girin.",
            "tiktok": "TikTok kullanıcı adı girin.",
            "youtube": "YouTube kanal linki veya @kullanıcı adı girin.",
            "bonus": "Promosyon linki girin (https://…).",
            "link": "Geçerli bir URL girin.",
        }
        raise ValueError(hints.get(button_type, "Geçerli bir hedef girin."))
    stored_url = (url or "").strip()[:500]
    return button_type, label[:200], stored_url, (badge_text or "").strip()[:80]


def _slugify(text):
    text = (text or "").strip().lower()
    text = text.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:64] or "sayfa"


def _valid_slug(slug):
    slug = (slug or "").strip().lower()
    if not slug or slug in RESERVED_SLUGS:
        return False
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}[a-z0-9]|[a-z0-9]", slug))


def normalize_custom_domain(raw):
    """example.com veya www.example.com → example.com"""
    d = (raw or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "").strip("/").split("/")[0].split(":")[0]
    if d.startswith("www."):
        d = d[4:]
    return d[:253]


def _valid_custom_domain(domain):
    domain = normalize_custom_domain(domain)
    if not domain or "." not in domain:
        return False
    if domain in ("localhost", "127.0.0.1"):
        return False
    return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+", domain))


def _domain_lookup_hosts(domain):
    domain = normalize_custom_domain(domain)
    if not domain:
        return []
    if domain.startswith("www."):
        return [domain, domain[4:]]
    return [domain, f"www.{domain}"]


def _unique_custom_domain(conn, domain, exclude_id=None):
    domain = normalize_custom_domain(domain)
    if not domain:
        return ""
    row = fetchone(
        conn,
        "SELECT id FROM biolink_pages WHERE custom_domain = ?",
        (domain,),
    )
    if row and (not exclude_id or int(row["id"]) != int(exclude_id)):
        raise ValueError("Bu domain başka bir bio sayfaya bağlı.")
    return domain


def _unique_slug(conn, base_slug, exclude_id=None):
    base_slug = _slugify(base_slug)
    slug = base_slug
    i = 1
    while True:
        row = fetchone(conn, "SELECT id FROM biolink_pages WHERE slug = ?", (slug,))
        if not row or (exclude_id and int(row["id"]) == int(exclude_id)):
            return slug
        i += 1
        slug = f"{base_slug}-{i}"[:64]


def _hash_ip(ip):
    ip = (ip or "").strip()
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


def _valid_url(url):
    url = (url or "").strip()
    if not url:
        return False
    p = urlparse(url if "://" in url else "https://" + url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def _normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return url


def _effective_default_logo():
    """Marka stok logosu; Bizzo'da asla Makrobet logosuna düşme."""
    logo = (brand_default_logo() or "").strip()
    if logo:
        return logo
    try:
        from panel_config import PANEL_BRAND
        if PANEL_BRAND == "bizzo":
            return ""
    except Exception:
        pass
    return DEFAULT_BRAND_LOGO or ""


def _effective_default_favicon():
    fav = (brand_default_favicon() or "").strip()
    if fav:
        return fav
    try:
        from panel_config import PANEL_BRAND
        if PANEL_BRAND == "bizzo":
            return ""
    except Exception:
        pass
    return DEFAULT_FAVICON or ""


def _store_avatar_url(val):
    val = (val or "").strip()[:500]
    if val == NONE_MARKER:
        return NONE_MARKER
    # Bizzo'da stok logo yok — boş bırakılabilir
    fallback = _effective_default_logo()
    return val or fallback or NONE_MARKER


def _store_banner_url(val):
    val = (val or "").strip()[:500]
    if val == NONE_MARKER:
        return NONE_MARKER
    # Varsayılan banner yok — boş = bannersız
    if not val or not DEFAULT_BANNER:
        return val or NONE_MARKER
    return val or DEFAULT_BANNER


def _store_favicon_url(val):
    val = (val or "").strip()[:500]
    if val == NONE_MARKER:
        return NONE_MARKER
    return val


def resolve_favicon_url(page):
    """Boş favicon → marka varsayılanı (Bizzo'da stok yoksa boş)."""
    fallback = _effective_default_favicon()
    if not page:
        return fallback
    raw = (page.get("favicon_url") or "").strip()
    if raw and raw != NONE_MARKER:
        return raw
    return fallback


def _page_row(row):
    if not row:
        return None
    d = dict(row)
    d["is_active"] = bool(int(d.get("is_active") or 0))
    d["view_count"] = int(d.get("view_count") or 0)
    d["theme"] = resolve_theme_key(d.get("theme") or brand_default_theme())
    d["button_shape"] = d.get("button_shape") or "pill"

    raw_avatar = (d.get("avatar_url") or "").strip()
    raw_banner = (d.get("banner_url") or "").strip()
    layout = (d.get("banner_layout") or DEFAULT_BANNER_LAYOUT).strip()
    if layout not in BANNER_LAYOUTS:
        layout = DEFAULT_BANNER_LAYOUT

    d["hide_logo"] = raw_avatar == NONE_MARKER
    d["avatar_url"] = raw_avatar
    d["logo_url"] = "" if d["hide_logo"] else (raw_avatar or _effective_default_logo())

    d["hide_banner"] = raw_banner == NONE_MARKER or layout == "none" or not (raw_banner or DEFAULT_BANNER)
    if d["hide_banner"]:
        d["banner_url"] = ""
        d["banner_layout"] = "none"
    else:
        d["banner_url"] = raw_banner or DEFAULT_BANNER
        d["banner_layout"] = layout

    raw_favicon = (d.get("favicon_url") or "").strip()
    d["favicon_url"] = raw_favicon
    d["resolved_favicon"] = resolve_favicon_url(d)

    d["popup"] = enrich_popup(d.get("popup_json") or "")
    d.pop("popup_json", None)

    d["custom_domain"] = normalize_custom_domain(d.get("custom_domain") or "")
    d["public_path"] = f"/p/{d['slug']}"
    d["site_path"] = f"/site/{d['slug']}"
    d["public_url"] = f"https://{d['custom_domain']}/" if d["custom_domain"] else d["site_path"]
    return d


def group_layout_rows(buttons):
    """Blokları satırlara ayır.

    - Sol + Sağ ardışık → yan yana çift
    - Tek kalan Sol/Sağ → tam genişlik (sağa/sola kaymış tek buton olmasın)
    - Tam / başlık → tam satır
    """
    items = list(buttons or [])
    rows = []
    i = 0
    n = len(items)
    while i < n:
        b = items[i]
        bt = (b.get("button_type") or "link").strip().lower()
        col = (b.get("layout_col") or "full").strip().lower()
        if bt == HEADING_TYPE or col not in ("left", "right"):
            rows.append({"kind": "full", "blocks": [b]})
            i += 1
            continue
        nxt = items[i + 1] if i + 1 < n else None
        nxt_col = ((nxt or {}).get("layout_col") or "full").strip().lower()
        nxt_bt = ((nxt or {}).get("button_type") or "link").strip().lower()
        if (
            col == "left"
            and nxt
            and nxt_bt != HEADING_TYPE
            and nxt_col == "right"
        ):
            rows.append({"kind": "pair", "blocks": [b, nxt]})
            i += 2
            continue
        # Yetim yarım → tam genişlik göster
        rows.append({"kind": "full", "blocks": [b]})
        i += 1
    return rows


def _button_row(row):
    if not row:
        return None
    d = dict(row)
    d["is_active"] = bool(int(d.get("is_active") or 0))
    d["highlight"] = bool(int(d.get("highlight") or 0))
    d["click_count"] = int(d.get("click_count") or 0)
    bt = d.get("button_type") or "link"
    d["resolved_url"] = resolve_button_url(bt, d.get("url") or "", d.get("badge_text") or "")
    if not (d.get("icon") or "").strip():
        d["display_icon"] = default_icon(bt)
    else:
        d["display_icon"] = d["icon"]
    if bt == HEADING_TYPE:
        d["heading_style"] = normalize_heading_style(d.get("heading_style"))
        d["layout_col"] = "full"
    else:
        d["heading_style"] = d.get("heading_style") or DEFAULT_HEADING_STYLE
        lc = (d.get("layout_col") or DEFAULT_LAYOUT_COL).strip()
        d["layout_col"] = lc if lc in LAYOUT_COLS else DEFAULT_LAYOUT_COL
    ta = (d.get("text_align") or DEFAULT_TEXT_ALIGN).strip()
    d["text_align"] = ta if ta in TEXT_ALIGNS else DEFAULT_TEXT_ALIGN
    return d


def _clickable_types_sql():
    return ",".join(["?"] * len(CLICKABLE_TYPE_LIST))


def list_pages(conn):
    rows = fetchall(conn, "SELECT * FROM biolink_pages ORDER BY created_at DESC")
    pages = [_page_row(r) for r in rows]
    if not pages:
        return pages
    page_ids = [p["id"] for p in pages]
    placeholders = ",".join(["?"] * len(page_ids))
    btn_rows = fetchall(
        conn,
        f"SELECT page_id, COUNT(*) AS cnt, COALESCE(SUM(click_count),0) AS clicks "
        f"FROM biolink_buttons WHERE page_id IN ({placeholders}) "
        f"AND button_type IN ({_clickable_types_sql()}) GROUP BY page_id",
        tuple(page_ids) + tuple(CLICKABLE_TYPE_LIST),
    )
    stats = {int(r["page_id"]): r for r in btn_rows}
    for p in pages:
        s = stats.get(p["id"])
        p["button_count"] = int(s["cnt"]) if s else 0
        p["total_clicks"] = int(s["clicks"]) if s else 0
    return pages


def get_page(conn, page_id, with_buttons=True):
    row = fetchone(conn, "SELECT * FROM biolink_pages WHERE id = ?", (int(page_id),))
    if not row:
        return None
    page = _page_row(row)
    if with_buttons:
        page["buttons"] = list_buttons(conn, page_id, active_only=False)
    return page


def list_buttons(conn, page_id, active_only=False):
    if active_only:
        rows = fetchall(
            conn,
            "SELECT * FROM biolink_buttons WHERE page_id = ? AND COALESCE(is_active,1) = 1 ORDER BY sort_order ASC, id ASC",
            (int(page_id),),
        )
    else:
        rows = fetchall(
            conn,
            "SELECT * FROM biolink_buttons WHERE page_id = ? ORDER BY sort_order ASC, id ASC",
            (int(page_id),),
        )
    return [_button_row(r) for r in rows]


def get_public_page_by_domain(conn, host):
    domain = normalize_custom_domain((host or "").split(":")[0])
    if not domain:
        return None
    row = fetchone(
        conn,
        "SELECT * FROM biolink_pages WHERE custom_domain = ? AND COALESCE(is_active,1) = 1",
        (domain,),
    )
    if not row:
        return None
    page = _page_row(row)
    page["buttons"] = list_buttons(conn, page["id"], active_only=True)
    return page


def get_public_page(conn, slug):
    slug = (slug or "").strip().lower()
    row = fetchone(conn, "SELECT * FROM biolink_pages WHERE slug = ? AND COALESCE(is_active,1) = 1", (slug,))
    if not row:
        return None
    page = _page_row(row)
    page["buttons"] = list_buttons(conn, page["id"], active_only=True)
    return page


def get_page_by_slug(conn, slug, *, active_only=False, buttons_active_only=False):
    slug = (slug or "").strip().lower()
    if active_only:
        row = fetchone(
            conn,
            "SELECT * FROM biolink_pages WHERE slug = ? AND COALESCE(is_active,1) = 1",
            (slug,),
        )
    else:
        row = fetchone(conn, "SELECT * FROM biolink_pages WHERE slug = ?", (slug,))
    if not row:
        return None
    page = _page_row(row)
    page["buttons"] = list_buttons(conn, page["id"], active_only=buttons_active_only)
    return page


def apply_preview_overrides(page, args):
    """Admin iframe önizlemesi — kaydedilmemiş form değerlerini query ile uygula."""
    if not page or not args:
        return page
    theme = (args.get("theme") or "").strip()
    if theme in THEMES:
        page["theme"] = theme
    shape = (args.get("button_shape") or "").strip()
    if shape in BUTTON_SHAPES:
        page["button_shape"] = shape
    if "title" in args:
        page["title"] = (args.get("title") or "").strip()[:200] or page.get("title") or ""
    if "subtitle" in args:
        page["subtitle"] = (args.get("subtitle") or "").strip()[:400]
    if "avatar_url" in args:
        av = (args.get("avatar_url") or "").strip()[:500]
        if av == NONE_MARKER:
            page["avatar_url"] = NONE_MARKER
            page["logo_url"] = ""
            page["hide_logo"] = True
        else:
            page["hide_logo"] = False
            page["avatar_url"] = av or _effective_default_logo()
            page["logo_url"] = page["avatar_url"]
    if "banner_url" in args:
        ban = (args.get("banner_url") or "").strip()[:500]
        if ban == NONE_MARKER:
            page["banner_url"] = ""
            page["hide_banner"] = True
            page["banner_layout"] = "none"
        else:
            page["hide_banner"] = False
            page["banner_url"] = ban or DEFAULT_BANNER
    if "banner_layout" in args:
        bl = (args.get("banner_layout") or "").strip()
        if bl in BANNER_LAYOUTS:
            if bl == "none":
                page["hide_banner"] = True
                page["banner_url"] = ""
                page["banner_layout"] = "none"
            elif not page.get("hide_banner"):
                page["banner_layout"] = bl
    if "accent_color" in args:
        page["accent_color"] = (args.get("accent_color") or "").strip()[:32]
    if "favicon_url" in args:
        fav = (args.get("favicon_url") or "").strip()[:500]
        if fav == NONE_MARKER:
            page["favicon_url"] = NONE_MARKER
        else:
            page["favicon_url"] = fav
        page["resolved_favicon"] = resolve_favicon_url(page)
    if "popup" in args or any(k.startswith("popup_") for k in args.keys()):
        cur = dict(page.get("popup") or DEFAULT_POPUP)
        if "popup" in args:
            try:
                raw = args.get("popup")
                if isinstance(raw, str):
                    raw = json.loads(raw) if raw.strip() else {}
                if isinstance(raw, dict):
                    cur.update(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        for key in ("enabled", "title", "body", "image_url", "cta_label", "cta_url", "delay_ms", "frequency"):
            arg_key = "popup_" + key
            if arg_key in args:
                val = args.get(arg_key)
                if key == "enabled":
                    cur[key] = str(val).lower() in ("1", "true", "yes", "on")
                else:
                    cur[key] = val
        page["popup"] = enrich_popup(cur)
    return page


def create_page(conn, *, title="", subtitle="", slug=None, theme=None, accent_color="",
                 avatar_url="", banner_url="", banner_layout=None, button_shape="pill",
                 ga4_measurement_id="", ga4_api_secret="", custom_domain="", favicon_url="",
                 popup=None, created_by=""):
    title = (title or "").strip()[:200] or "Yeni Sayfa"
    subtitle = (subtitle or "").strip()[:400]
    avatar_url = _store_avatar_url(avatar_url)
    banner_url = _store_banner_url(banner_url)
    favicon_url = _store_favicon_url(favicon_url)
    stored_popup = popup_to_json(popup)
    banner_layout = (banner_layout or DEFAULT_BANNER_LAYOUT).strip()
    if banner_layout not in BANNER_LAYOUTS:
        banner_layout = DEFAULT_BANNER_LAYOUT
    if banner_url == NONE_MARKER:
        banner_layout = "none"
    theme = resolve_theme_key(theme)
    accent_color = (accent_color or "").strip()[:32]
    button_shape = button_shape if button_shape in BUTTON_SHAPES else "pill"
    ga4_measurement_id = (ga4_measurement_id or "").strip()[:64]
    ga4_api_secret = (ga4_api_secret or "").strip()[:128]
    created_by = (created_by or "").strip()[:64]
    stored_domain = _unique_custom_domain(conn, custom_domain)
    if stored_domain and not _valid_custom_domain(stored_domain):
        raise ValueError("Geçersiz özel domain (örn. ornek.com).")
    now = iso(utcnow())

    base = slug.strip() if (slug or "").strip() else title
    final_slug = _unique_slug(conn, _slugify(base))

    page_id = insert_returning_id(
        conn,
        """
        INSERT INTO biolink_pages
          (slug, title, subtitle, avatar_url, banner_url, banner_layout, theme, accent_color, button_shape,
           is_active, view_count, ga4_measurement_id, ga4_api_secret, custom_domain, favicon_url, popup_json,
           created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (final_slug, title, subtitle, avatar_url, banner_url, banner_layout, theme, accent_color, button_shape,
         ga4_measurement_id, ga4_api_secret, stored_domain, favicon_url, stored_popup, created_by, now, now),
    )
    conn.commit()
    return get_page(conn, page_id)


def update_page(conn, page_id, data):
    row = fetchone(conn, "SELECT * FROM biolink_pages WHERE id = ?", (int(page_id),))
    if not row:
        raise ValueError("Sayfa bulunamadı.")
    row = dict(row)

    def pick(key, cur, maxlen=None, choices=None):
        if key not in data:
            return cur
        val = data.get(key)
        if isinstance(val, str):
            val = val.strip()
            if maxlen:
                val = val[:maxlen]
        if choices and val not in choices:
            return cur
        return val

    title = pick("title", row["title"], 200) or "Sayfa"
    subtitle = pick("subtitle", row["subtitle"], 400)
    avatar_url = pick("avatar_url", row.get("avatar_url") or "", 500)
    banner_url = pick("banner_url", row.get("banner_url") or "", 500)
    favicon_url = pick("favicon_url", row.get("favicon_url") or "", 500)
    banner_layout = pick("banner_layout", row.get("banner_layout") or DEFAULT_BANNER_LAYOUT, choices=set(BANNER_LAYOUTS))
    theme = resolve_theme_key(data["theme"] if "theme" in data else row["theme"])
    accent_color = pick("accent_color", row["accent_color"], 32)
    button_shape = pick("button_shape", row["button_shape"], choices=set(BUTTON_SHAPES))
    ga4_measurement_id = pick("ga4_measurement_id", row["ga4_measurement_id"], 64)
    ga4_api_secret = pick("ga4_api_secret", row["ga4_api_secret"], 128)
    is_active = int(bool(data["is_active"])) if "is_active" in data else int(row["is_active"] or 0)

    new_slug = row["slug"]
    if "slug" in data and (data.get("slug") or "").strip():
        candidate = _slugify(data["slug"])
        if not _valid_slug(candidate):
            raise ValueError("Geçersiz slug (harf/rakam/-, en az 1 karakter).")
        existing = fetchone(conn, "SELECT id FROM biolink_pages WHERE slug = ?", (candidate,))
        if existing and int(existing["id"]) != int(page_id):
            raise ValueError("Bu slug zaten kullanılıyor.")
        new_slug = candidate

    new_domain = row.get("custom_domain") or ""
    if "custom_domain" in data:
        raw_domain = (data.get("custom_domain") or "").strip()
        if raw_domain:
            candidate_domain = normalize_custom_domain(raw_domain)
            if not _valid_custom_domain(candidate_domain):
                raise ValueError("Geçersiz özel domain (örn. vippmakro.com).")
            new_domain = _unique_custom_domain(conn, candidate_domain, exclude_id=page_id)
        else:
            new_domain = ""

    now = iso(utcnow())
    stored_avatar = _store_avatar_url(avatar_url)
    stored_banner = _store_banner_url(banner_url)
    stored_favicon = _store_favicon_url(favicon_url)
    stored_layout = "none" if stored_banner == NONE_MARKER else banner_layout
    if "popup" in data:
        stored_popup = popup_to_json(data.get("popup"))
    else:
        stored_popup = popup_to_json(normalize_popup(row.get("popup_json") or ""))
    execute(
        conn,
        """
        UPDATE biolink_pages
        SET slug = ?, title = ?, subtitle = ?, avatar_url = ?, banner_url = ?, banner_layout = ?,
            theme = ?, accent_color = ?, button_shape = ?, is_active = ?,
            ga4_measurement_id = ?, ga4_api_secret = ?, custom_domain = ?, favicon_url = ?,
            popup_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_slug, title, subtitle, stored_avatar, stored_banner, stored_layout,
         theme, accent_color, button_shape,
         is_active, ga4_measurement_id, ga4_api_secret, new_domain, stored_favicon,
         stored_popup, now, int(page_id)),
    )
    conn.commit()
    return get_page(conn, page_id)


def delete_page(conn, page_id):
    page_id = int(page_id)
    execute(conn, "DELETE FROM biolink_clicks WHERE page_id = ?", (page_id,))
    execute(conn, "DELETE FROM biolink_buttons WHERE page_id = ?", (page_id,))
    cur = execute(conn, "DELETE FROM biolink_pages WHERE id = ?", (page_id,))
    conn.commit()
    return cur.rowcount > 0


def duplicate_page(conn, page_id, created_by=""):
    src = get_page(conn, page_id)
    if not src:
        raise ValueError("Sayfa bulunamadı.")
    new_page = create_page(
        conn,
        title=src["title"] + " (Kopya)",
        subtitle=src["subtitle"],
        theme=src["theme"],
        accent_color=src["accent_color"],
        avatar_url=src.get("avatar_url") or _effective_default_logo(),
        banner_url=src.get("banner_url") or DEFAULT_BANNER,
        banner_layout=src.get("banner_layout") or DEFAULT_BANNER_LAYOUT,
        button_shape=src["button_shape"],
        popup=src.get("popup"),
        created_by=created_by,
    )
    for b in src.get("buttons", []):
        add_button(
            conn, new_page["id"],
            button_type=b["button_type"], label=b["label"], url=b["url"], icon=b["icon"],
            highlight=b["highlight"], badge_text=b["badge_text"], is_active=b["is_active"],
            heading_style=b.get("heading_style") or "",
            layout_col=b.get("layout_col") or DEFAULT_LAYOUT_COL,
            text_align=b.get("text_align") or DEFAULT_TEXT_ALIGN,
        )
    return get_page(conn, new_page["id"])


def add_button(conn, page_id, *, button_type="link", label="", url="", icon="",
                highlight=False, badge_text="", is_active=True, heading_style="",
                layout_col=DEFAULT_LAYOUT_COL, text_align=DEFAULT_TEXT_ALIGN):
    button_type, label, url, badge_text = _validate_button(button_type, label, url, badge_text)
    if button_type == "bonus" and not highlight:
        highlight = True
    if uses_brand_icon(button_type):
        icon = ""
    else:
        icon = (icon or default_icon(button_type)).strip()[:16]
    hs = normalize_heading_style(heading_style) if button_type == HEADING_TYPE else DEFAULT_HEADING_STYLE
    lc = (layout_col or DEFAULT_LAYOUT_COL).strip()
    if button_type == HEADING_TYPE:
        lc = "full"
    elif lc not in LAYOUT_COLS:
        lc = DEFAULT_LAYOUT_COL
    ta = (text_align or DEFAULT_TEXT_ALIGN).strip()
    ta = ta if ta in TEXT_ALIGNS else DEFAULT_TEXT_ALIGN
    now = iso(utcnow())
    max_order = scalar(conn, "SELECT COALESCE(MAX(sort_order), -1) FROM biolink_buttons WHERE page_id = ?", (int(page_id),))
    sort_order = int(max_order or -1) + 1
    button_id = insert_returning_id(
        conn,
        """
        INSERT INTO biolink_buttons
          (page_id, button_type, label, url, icon, highlight, badge_text, is_active,
           sort_order, click_count, heading_style, layout_col, text_align, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
        """,
        (int(page_id), button_type, label, url, icon, int(bool(highlight)), badge_text,
         int(bool(is_active)), sort_order, hs, lc, ta, now, now),
    )
    execute(conn, "UPDATE biolink_pages SET updated_at = ? WHERE id = ?", (now, int(page_id)))
    conn.commit()
    return _button_row(fetchone(conn, "SELECT * FROM biolink_buttons WHERE id = ?", (button_id,)))


def update_button(conn, button_id, data):
    row = fetchone(conn, "SELECT * FROM biolink_buttons WHERE id = ?", (int(button_id),))
    if not row:
        raise ValueError("Buton bulunamadı.")
    row = dict(row)

    button_type = data.get("button_type", row["button_type"])
    if button_type not in BUTTON_TYPES:
        button_type = row["button_type"]
    label = (data.get("label", row["label"]) or "").strip()
    url = data.get("url", row["url"]) if "url" in data else row["url"]
    badge_text = data.get("badge_text", row["badge_text"]) if "badge_text" in data else row["badge_text"]
    if "url" in data or "label" in data or "badge_text" in data or "button_type" in data:
        button_type, label, url, badge_text = _validate_button(button_type, label, url, badge_text)
    else:
        label = label[:200]
        badge_text = (badge_text or "").strip()[:80]
    if uses_brand_icon(button_type):
        icon = ""
    elif "icon" in data:
        icon = (data.get("icon") or default_icon(button_type)).strip()[:16]
    else:
        icon = (row["icon"] or default_icon(button_type)).strip()[:16]
    highlight = int(bool(data["highlight"])) if "highlight" in data else int(row["highlight"] or 0)
    is_active = int(bool(data["is_active"])) if "is_active" in data else int(row["is_active"] or 0)
    if button_type == HEADING_TYPE:
        if "heading_style" in data:
            hs = normalize_heading_style(data.get("heading_style"))
        else:
            hs = normalize_heading_style(row.get("heading_style"))
    else:
        hs = DEFAULT_HEADING_STYLE
    if button_type == HEADING_TYPE:
        lc = "full"
    elif "layout_col" in data:
        lc = (data.get("layout_col") or DEFAULT_LAYOUT_COL).strip()
        lc = lc if lc in LAYOUT_COLS else DEFAULT_LAYOUT_COL
    else:
        lc = (row.get("layout_col") or DEFAULT_LAYOUT_COL).strip()
        lc = lc if lc in LAYOUT_COLS else DEFAULT_LAYOUT_COL
    if "text_align" in data:
        ta = (data.get("text_align") or DEFAULT_TEXT_ALIGN).strip()
        ta = ta if ta in TEXT_ALIGNS else DEFAULT_TEXT_ALIGN
    else:
        ta = (row.get("text_align") or DEFAULT_TEXT_ALIGN).strip()
        ta = ta if ta in TEXT_ALIGNS else DEFAULT_TEXT_ALIGN
    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE biolink_buttons
        SET button_type = ?, label = ?, url = ?, icon = ?, highlight = ?, badge_text = ?,
            is_active = ?, heading_style = ?, layout_col = ?, text_align = ?, updated_at = ?
        WHERE id = ?
        """,
        (button_type, label, url, icon, highlight, badge_text, is_active, hs, lc, ta, now, int(button_id)),
    )
    execute(conn, "UPDATE biolink_pages SET updated_at = ? WHERE id = ?", (now, int(row["page_id"])))
    conn.commit()
    return _button_row(fetchone(conn, "SELECT * FROM biolink_buttons WHERE id = ?", (int(button_id),)))


def delete_button(conn, button_id):
    execute(conn, "DELETE FROM biolink_clicks WHERE button_id = ?", (int(button_id),))
    cur = execute(conn, "DELETE FROM biolink_buttons WHERE id = ?", (int(button_id),))
    conn.commit()
    return cur.rowcount > 0


def reorder_buttons(conn, page_id, ordered_ids):
    now = iso(utcnow())
    for idx, bid in enumerate(ordered_ids):
        execute(
            conn,
            "UPDATE biolink_buttons SET sort_order = ?, updated_at = ? WHERE id = ? AND page_id = ?",
            (idx, now, int(bid), int(page_id)),
        )
    conn.commit()


def record_view(conn, slug):
    execute(conn, "UPDATE biolink_pages SET view_count = COALESCE(view_count,0) + 1 WHERE slug = ?", (slug,))
    conn.commit()


def record_click_and_resolve(conn, page_id, button_id, *, ip="", user_agent="", referer=""):
    row = fetchone(
        conn,
        f"SELECT * FROM biolink_buttons WHERE id = ? AND page_id = ? "
        f"AND button_type IN ({_clickable_types_sql()}) AND COALESCE(is_active,1) = 1",
        (int(button_id), int(page_id), *CLICKABLE_TYPE_LIST),
    )
    if not row:
        return None
    dest = resolve_button_url(row["button_type"], row["url"], row.get("badge_text") or "")
    if not dest:
        return None
    now = iso(utcnow())
    execute(
        conn,
        """
        INSERT INTO biolink_clicks (button_id, page_id, clicked_at, ip_hash, user_agent, referer)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (int(button_id), int(page_id), now, _hash_ip(ip), (user_agent or "")[:500], (referer or "")[:500]),
    )
    execute(conn, "UPDATE biolink_buttons SET click_count = COALESCE(click_count,0) + 1, updated_at = ? WHERE id = ?", (now, int(button_id)))
    conn.commit()
    return dest


def get_stats(conn, page_id):
    page = get_page(conn, page_id, with_buttons=True)
    if not page:
        return None
    buttons = [b for b in page["buttons"] if is_clickable(b["button_type"])]
    buttons.sort(key=lambda b: -b["click_count"])
    total_clicks = sum(b["click_count"] for b in buttons)
    return {
        "view_count": page["view_count"],
        "total_clicks": total_clicks,
        "buttons": [
            {"id": b["id"], "label": b["label"], "url": b["url"], "click_count": b["click_count"]}
            for b in buttons
        ],
    }


def send_ga4_event(page, *, event_name, button_label="", destination_url="", client_id=None):
    mid = (page.get("ga4_measurement_id") or "").strip()
    secret = (page.get("ga4_api_secret") or "").strip()
    if not mid or not secret:
        return
    payload = {
        "client_id": client_id or secrets.token_hex(8),
        "events": [
            {
                "name": event_name,
                "params": {
                    "page_slug": (page.get("slug") or "")[:100],
                    "button_label": (button_label or "")[:100],
                    "destination": (destination_url or "")[:300],
                    "engagement_time_msec": 1,
                },
            }
        ],
    }
    url = (
        "https://www.google-analytics.com/mp/collect"
        f"?measurement_id={urllib.parse.quote(mid)}"
        f"&api_secret={urllib.parse.quote(secret)}"
    )
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "BioLink/1.0"},
        method="POST",
    )

    def _run():
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                resp.read()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def _ensure_biolink_upload_dir():
    os.makedirs(BIOLINK_UPLOAD_DIR, exist_ok=True)


def _custom_asset_row(row):
    if not row:
        return None
    d = dict(row)
    return {
        "key": f"custom-{d['id']}",
        "id": int(d["id"]),
        "label": d.get("label") or "Yüklediğim",
        "url": d.get("public_url") or "",
        "w": 0,
        "h": 0,
        "custom": True,
        "kind": d.get("kind") or "",
    }


def list_custom_assets(conn, kind=None):
    kind = (kind or "").strip().lower()
    if kind in ("logo", "banner", "favicon", "popup"):
        rows = fetchall(
            conn,
            "SELECT * FROM biolink_assets WHERE kind = ? ORDER BY created_at DESC, id DESC",
            (kind,),
        )
    else:
        rows = fetchall(conn, "SELECT * FROM biolink_assets ORDER BY created_at DESC, id DESC")
    return [_custom_asset_row(r) for r in rows]


def list_brand_assets(conn):
    custom = list_custom_assets(conn)
    hidden = {
        (r["asset_key"] or "").strip()
        for r in (fetchall(conn, "SELECT asset_key FROM biolink_hidden_assets") or [])
        if (r["asset_key"] or "").strip()
    }
    stock = brand_assets()
    logos = [
        a for a in list(stock.get("logos") or [])
        if a.get("key") not in hidden
    ] + [a for a in custom if a["kind"] == "logo"]
    banners = [
        a for a in list(stock.get("banners") or [])
        if a.get("key") not in hidden
    ] + [a for a in custom if a["kind"] == "banner"]
    favicons = [
        a for a in list(stock.get("favicons") or [])
        if a.get("key") not in hidden
    ] + [a for a in custom if a["kind"] == "favicon"]
    popups = [a for a in custom if a["kind"] == "popup"]
    return {
        "logos": logos,
        "banners": banners,
        "favicons": favicons,
        "popups": popups,
        "default_logo": stock.get("default_logo") or "",
        "default_banner": stock.get("default_banner") or DEFAULT_BANNER,
        "default_favicon": stock.get("default_favicon") or "",
        "default_theme": brand_default_theme(),
        "casino_name": stock.get("casino_name") or "",
        "hidden_count": len(hidden),
        "popup_shapes": popup_shape_catalog(),
    }


def hide_brand_asset(conn, asset_key, kind=""):
    """Marka (hazır) logo/banner/favicon'u seçiciden gizle — dosya silinmez."""
    key = (asset_key or "").strip()
    if not key:
        raise ValueError("Varlık anahtarı gerekli.")
    stock = brand_assets()
    stock_items = list(stock.get("logos") or []) + list(stock.get("banners") or []) + list(stock.get("favicons") or [])
    known = {a.get("key") for a in stock_items}
    if key not in known:
        raise ValueError("Bu hazır varlık bulunamadı.")
    # Varsayılanları koru
    protected = set()
    defaults = {stock.get("default_logo"), stock.get("default_favicon"), DEFAULT_BANNER}
    for a in stock_items:
        if a.get("url") in defaults:
            protected.add(a.get("key"))
    if key in protected:
        raise ValueError("Varsayılan logo/banner/favicon gizlenemez.")
    kind = (kind or "").strip()[:32]
    now = iso(utcnow())
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO biolink_hidden_assets (asset_key, kind, hidden_at) VALUES (?, ?, ?)
            ON CONFLICT (asset_key) DO UPDATE SET kind = EXCLUDED.kind, hidden_at = EXCLUDED.hidden_at
            """,
            (key, kind, now),
        )
    else:
        execute(
            conn,
            "INSERT OR REPLACE INTO biolink_hidden_assets (asset_key, kind, hidden_at) VALUES (?, ?, ?)",
            (key, kind, now),
        )
    conn.commit()
    return True


def unhide_all_brand_assets(conn):
    execute(conn, "DELETE FROM biolink_hidden_assets")
    conn.commit()
    return True


def clear_all_page_banners_once():
    """Deploy'da bir kez: tüm bio sayfalarından banner'ı kaldır + yüklenen banner asset'lerini sil."""
    from database import get_mail_setting, upsert_mail_setting

    flag = "biolink_banners_cleared_v20260713a"
    try:
        with closing(get_db()) as conn:
            # mail_settings tablosu her ortamda var; ortak one-shot flag için kullan
            if (get_mail_setting(conn, flag, "") or "").strip() == "1":
                return 0
            execute(
                conn,
                "UPDATE biolink_pages SET banner_url = ?, banner_layout = 'none'",
                (NONE_MARKER,),
            )
            # Yüklenen custom banner dosyalarını sil
            rows = fetchall(conn, "SELECT id, stored_name FROM biolink_assets WHERE kind = 'banner'") or []
            for row in rows:
                d = dict(row)
                stored = os.path.basename(d.get("stored_name") or "")
                if stored:
                    path = os.path.join(BIOLINK_UPLOAD_DIR, stored)
                    if os.path.isfile(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
            execute(conn, "DELETE FROM biolink_assets WHERE kind = 'banner'")
            upsert_mail_setting(conn, flag, "1")
            conn.commit()
            print(f"🧹 biolink banners cleared ({len(rows)} uploaded + all page refs)")
            return len(rows)
    except Exception as exc:
        print(f"⚠️  biolink banner clear failed: {exc}")
        return -1


def upload_asset(conn, kind, file_storage, *, label="", created_by=""):
    kind = (kind or "").strip().lower()
    if kind not in ("logo", "banner", "favicon", "popup"):
        raise ValueError("Tür logo, banner, favicon veya popup olmalı.")
    if not file_storage or not (file_storage.filename or "").strip():
        raise ValueError("Dosya seçilmedi.")

    orig = secure_filename(file_storage.filename.strip())
    if not orig:
        raise ValueError("Geçersiz dosya adı.")
    ext = os.path.splitext(orig)[1].lower()
    if kind == "favicon":
        allowed = FAVICON_UPLOAD_EXTS
        max_size = FAVICON_UPLOAD_MAX_BYTES
    elif kind == "logo":
        allowed = LOGO_UPLOAD_EXTS
        max_size = LOGO_UPLOAD_MAX_BYTES
    elif kind == "popup":
        allowed = POPUP_UPLOAD_EXTS
        max_size = POPUP_UPLOAD_MAX_BYTES
    else:
        allowed = BANNER_UPLOAD_EXTS
        max_size = BANNER_UPLOAD_MAX_BYTES
    if ext not in allowed:
        raise ValueError("Desteklenmeyen format: " + ", ".join(sorted(allowed)))

    file_storage.stream.seek(0, os.SEEK_END)
    size = int(file_storage.stream.tell() or 0)
    file_storage.stream.seek(0)
    if size <= 0:
        raise ValueError("Boş dosya yüklenemez.")
    if size > max_size:
        raise ValueError(f"Dosya çok büyük (max {max_size // (1024 * 1024) or 1} MB).")

    _ensure_biolink_upload_dir()
    stored = f"{kind}_{utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}{ext}"
    path = os.path.join(BIOLINK_UPLOAD_DIR, stored)
    file_storage.save(path)

    public_url = f"{BIOLINK_UPLOAD_URL_PREFIX}/{stored}"
    label = (label or os.path.splitext(orig)[0] or "Yüklediğim").strip()[:120]
    now = iso(utcnow())
    asset_id = insert_returning_id(
        conn,
        """
        INSERT INTO biolink_assets
          (kind, label, stored_name, public_url, mime_type, file_size, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kind,
            label,
            stored,
            public_url,
            (file_storage.mimetype or "")[:120],
            size,
            (created_by or "")[:64],
            now,
        ),
    )
    conn.commit()
    return _custom_asset_row(fetchone(conn, "SELECT * FROM biolink_assets WHERE id = ?", (asset_id,)))


def delete_asset(conn, asset_id):
    row = fetchone(conn, "SELECT * FROM biolink_assets WHERE id = ?", (int(asset_id),))
    if not row:
        return False
    stored = os.path.basename(dict(row).get("stored_name") or "")
    if stored:
        path = os.path.join(BIOLINK_UPLOAD_DIR, stored)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    execute(conn, "DELETE FROM biolink_assets WHERE id = ?", (int(asset_id),))
    conn.commit()
    return True


def biolink_upload_path(filename):
    safe = os.path.basename(filename or "")
    if not safe or safe != filename:
        return None
    path = os.path.join(BIOLINK_UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        return None
    return path
