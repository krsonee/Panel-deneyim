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
from urllib.parse import urlparse

from werkzeug.utils import secure_filename

from database import (
    execute,
    fetchall,
    fetchone,
    insert_returning_id,
    iso,
    scalar,
    uses_postgres,
    utcnow,
)

from biolink_themes import (
    BRAND_BANNERS,
    BRAND_LOGOS,
    DEFAULT_BANNER,
    DEFAULT_BRAND_LOGO,
    DEFAULT_HEADING_STYLE,
    DEFAULT_THEME,
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
LOGO_UPLOAD_MAX_BYTES = 2 * 1024 * 1024
BANNER_UPLOAD_MAX_BYTES = 6 * 1024 * 1024

RESERVED_SLUGS = frozenset({
    "", "admin", "api", "static", "demo", "r", "p", "health", "favicon.ico",
    "robots.txt", "sitemap.xml", "login", "logout", "mail", "mailing", "go", "new",
})

BUTTON_SHAPES = ("pill", "rounded", "square")

NONE_MARKER = "__none__"
BANNER_LAYOUTS = ("top", "towers", "none")
DEFAULT_BANNER_LAYOUT = "top"
LAYOUT_COLS = ("full", "left", "right")
DEFAULT_LAYOUT_COL = "full"

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
    t = THEMES.get(theme_key) or THEMES[DEFAULT_THEME]
    out = dict(t)
    if (accent_override or "").strip():
        out["accent"] = accent_override.strip()
    out["animated"] = bool(t.get("animated"))
    out["animation"] = t.get("animation") or ""
    out["accent2"] = t.get("accent2") or out["accent"]
    out["style"] = t.get("style") or "classic"
    out["category"] = t.get("category") or ""
    # Tüm temalarda Makrobet marka logosu
    out["brand_logo"] = True
    out["brand_logo_src"] = DEFAULT_BRAND_LOGO
    out["default_banner"] = DEFAULT_BANNER
    return out


def uses_brand_icon(button_type):
    return button_type in PLATFORM_ICON_TYPES


def default_icon(button_type):
    if uses_brand_icon(button_type):
        return ""
    meta = BUTTON_TYPE_META.get(button_type) or {}
    return meta.get("icon") or "🔗"


def button_type_catalog():
    return [
        {"key": k, **v}
        for k, v in BUTTON_TYPE_META.items()
    ]


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
        return button_type, label, "", (badge_text or "").strip()[:32]
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
    return button_type, label[:200], stored_url, (badge_text or "").strip()[:32]


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


def _store_avatar_url(val):
    val = (val or "").strip()[:500]
    if val == NONE_MARKER:
        return NONE_MARKER
    return val or DEFAULT_BRAND_LOGO


def _store_banner_url(val):
    val = (val or "").strip()[:500]
    if val == NONE_MARKER:
        return NONE_MARKER
    return val or DEFAULT_BANNER


def _page_row(row):
    if not row:
        return None
    d = dict(row)
    d["is_active"] = bool(int(d.get("is_active") or 0))
    d["view_count"] = int(d.get("view_count") or 0)
    d["theme"] = d.get("theme") or DEFAULT_THEME
    d["button_shape"] = d.get("button_shape") or "pill"

    raw_avatar = (d.get("avatar_url") or "").strip()
    raw_banner = (d.get("banner_url") or "").strip()
    layout = (d.get("banner_layout") or DEFAULT_BANNER_LAYOUT).strip()
    if layout not in BANNER_LAYOUTS:
        layout = DEFAULT_BANNER_LAYOUT

    d["hide_logo"] = raw_avatar == NONE_MARKER
    d["avatar_url"] = raw_avatar
    d["logo_url"] = "" if d["hide_logo"] else (raw_avatar or DEFAULT_BRAND_LOGO)

    d["hide_banner"] = raw_banner == NONE_MARKER or layout == "none"
    if d["hide_banner"]:
        d["banner_url"] = ""
        d["banner_layout"] = "none"
    else:
        d["banner_url"] = raw_banner or DEFAULT_BANNER
        d["banner_layout"] = layout

    d["public_path"] = f"/p/{d['slug']}"
    return d


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
            page["avatar_url"] = av or DEFAULT_BRAND_LOGO
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
    return page


def create_page(conn, *, title="", subtitle="", slug=None, theme=None, accent_color="",
                 avatar_url="", banner_url="", banner_layout=None, button_shape="pill",
                 ga4_measurement_id="", ga4_api_secret="", created_by=""):
    title = (title or "").strip()[:200] or "Yeni Sayfa"
    subtitle = (subtitle or "").strip()[:400]
    avatar_url = _store_avatar_url(avatar_url)
    banner_url = _store_banner_url(banner_url)
    banner_layout = (banner_layout or DEFAULT_BANNER_LAYOUT).strip()
    if banner_layout not in BANNER_LAYOUTS:
        banner_layout = DEFAULT_BANNER_LAYOUT
    if banner_url == NONE_MARKER:
        banner_layout = "none"
    theme = theme if theme in THEMES else DEFAULT_THEME
    accent_color = (accent_color or "").strip()[:32]
    button_shape = button_shape if button_shape in BUTTON_SHAPES else "pill"
    ga4_measurement_id = (ga4_measurement_id or "").strip()[:64]
    ga4_api_secret = (ga4_api_secret or "").strip()[:128]
    created_by = (created_by or "").strip()[:64]
    now = iso(utcnow())

    base = slug.strip() if (slug or "").strip() else title
    final_slug = _unique_slug(conn, _slugify(base))

    page_id = insert_returning_id(
        conn,
        """
        INSERT INTO biolink_pages
          (slug, title, subtitle, avatar_url, banner_url, banner_layout, theme, accent_color, button_shape,
           is_active, view_count, ga4_measurement_id, ga4_api_secret, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?)
        """,
        (final_slug, title, subtitle, avatar_url, banner_url, banner_layout, theme, accent_color, button_shape,
         ga4_measurement_id, ga4_api_secret, created_by, now, now),
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
    banner_layout = pick("banner_layout", row.get("banner_layout") or DEFAULT_BANNER_LAYOUT, choices=set(BANNER_LAYOUTS))
    theme = pick("theme", row["theme"], choices=set(THEMES.keys()))
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

    now = iso(utcnow())
    stored_avatar = _store_avatar_url(avatar_url)
    stored_banner = _store_banner_url(banner_url)
    stored_layout = "none" if stored_banner == NONE_MARKER else banner_layout
    execute(
        conn,
        """
        UPDATE biolink_pages
        SET slug = ?, title = ?, subtitle = ?, avatar_url = ?, banner_url = ?, banner_layout = ?,
            theme = ?, accent_color = ?, button_shape = ?, is_active = ?,
            ga4_measurement_id = ?, ga4_api_secret = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_slug, title, subtitle, stored_avatar, stored_banner, stored_layout,
         theme, accent_color, button_shape,
         is_active, ga4_measurement_id, ga4_api_secret, now, int(page_id)),
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
        avatar_url=src.get("avatar_url") or DEFAULT_BRAND_LOGO,
        banner_url=src.get("banner_url") or DEFAULT_BANNER,
        banner_layout=src.get("banner_layout") or DEFAULT_BANNER_LAYOUT,
        button_shape=src["button_shape"],
        created_by=created_by,
    )
    for b in src.get("buttons", []):
        add_button(
            conn, new_page["id"],
            button_type=b["button_type"], label=b["label"], url=b["url"], icon=b["icon"],
            highlight=b["highlight"], badge_text=b["badge_text"], is_active=b["is_active"],
            heading_style=b.get("heading_style") or "",
            layout_col=b.get("layout_col") or DEFAULT_LAYOUT_COL,
        )
    return get_page(conn, new_page["id"])


def add_button(conn, page_id, *, button_type="link", label="", url="", icon="",
                highlight=False, badge_text="", is_active=True, heading_style="",
                layout_col=DEFAULT_LAYOUT_COL):
    button_type, label, url, badge_text = _validate_button(button_type, label, url, badge_text)
    if button_type == "bonus" and not highlight:
        highlight = True
    if uses_brand_icon(button_type):
        icon = ""
    else:
        icon = (icon or default_icon(button_type)).strip()[:8]
    hs = normalize_heading_style(heading_style) if button_type == HEADING_TYPE else DEFAULT_HEADING_STYLE
    lc = (layout_col or DEFAULT_LAYOUT_COL).strip()
    if button_type == HEADING_TYPE:
        lc = "full"
    elif lc not in LAYOUT_COLS:
        lc = DEFAULT_LAYOUT_COL
    now = iso(utcnow())
    max_order = scalar(conn, "SELECT COALESCE(MAX(sort_order), -1) FROM biolink_buttons WHERE page_id = ?", (int(page_id),))
    sort_order = int(max_order or -1) + 1
    button_id = insert_returning_id(
        conn,
        """
        INSERT INTO biolink_buttons
          (page_id, button_type, label, url, icon, highlight, badge_text, is_active,
           sort_order, click_count, heading_style, layout_col, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (int(page_id), button_type, label, url, icon, int(bool(highlight)), badge_text,
         int(bool(is_active)), sort_order, hs, lc, now, now),
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
        badge_text = (badge_text or "").strip()[:32]
    if uses_brand_icon(button_type):
        icon = ""
    elif "icon" in data:
        icon = (data.get("icon") or default_icon(button_type)).strip()[:8]
    else:
        icon = (row["icon"] or default_icon(button_type)).strip()[:8]
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
    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE biolink_buttons
        SET button_type = ?, label = ?, url = ?, icon = ?, highlight = ?, badge_text = ?,
            is_active = ?, heading_style = ?, layout_col = ?, updated_at = ?
        WHERE id = ?
        """,
        (button_type, label, url, icon, highlight, badge_text, is_active, hs, lc, now, int(button_id)),
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
    if kind in ("logo", "banner"):
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
    logos = list(BRAND_LOGOS) + [a for a in custom if a["kind"] == "logo"]
    banners = list(BRAND_BANNERS) + [a for a in custom if a["kind"] == "banner"]
    return {
        "logos": logos,
        "banners": banners,
        "default_logo": DEFAULT_BRAND_LOGO,
        "default_banner": DEFAULT_BANNER,
    }


def upload_asset(conn, kind, file_storage, *, label="", created_by=""):
    kind = (kind or "").strip().lower()
    if kind not in ("logo", "banner"):
        raise ValueError("Tür logo veya banner olmalı.")
    if not file_storage or not (file_storage.filename or "").strip():
        raise ValueError("Dosya seçilmedi.")

    orig = secure_filename(file_storage.filename.strip())
    if not orig:
        raise ValueError("Geçersiz dosya adı.")
    ext = os.path.splitext(orig)[1].lower()
    allowed = LOGO_UPLOAD_EXTS if kind == "logo" else BANNER_UPLOAD_EXTS
    if ext not in allowed:
        raise ValueError("Desteklenmeyen format: " + ", ".join(sorted(allowed)))

    file_storage.stream.seek(0, os.SEEK_END)
    size = int(file_storage.stream.tell() or 0)
    file_storage.stream.seek(0)
    max_size = LOGO_UPLOAD_MAX_BYTES if kind == "logo" else BANNER_UPLOAD_MAX_BYTES
    if size <= 0:
        raise ValueError("Boş dosya yüklenemez.")
    if size > max_size:
        raise ValueError(f"Dosya çok büyük (max {max_size // (1024 * 1024)} MB).")

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
