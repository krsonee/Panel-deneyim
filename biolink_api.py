"""Bio Sayfa — Heylink/Linktree tarzı, kendi barındırdığımız link-in-bio sayfa oluşturucu.

Akış: panel-domain/p/<slug> → sayfa render edilir → buton tıklaması panel-domain/p/<slug>/go/<button_id>
üzerinden tıklama kaydedilip (+ GA4 event) hedef URL'e 302 yönlendirilir.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

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

RESERVED_SLUGS = frozenset({
    "", "admin", "api", "static", "demo", "r", "p", "health", "favicon.ico",
    "robots.txt", "sitemap.xml", "login", "logout", "mail", "mailing", "go", "new",
})

THEMES = {
    "carbon": {
        "name": "Karbon (Siyah)",
        "bg": "linear-gradient(160deg, #05070a 0%, #0d1117 45%, #111827 100%)",
        "text": "#f5f7fa",
        "muted": "#9aa4b2",
        "card_bg": "rgba(255,255,255,0.06)",
        "card_border": "rgba(255,255,255,0.12)",
        "card_hover": "rgba(255,255,255,0.11)",
        "accent": "#22d3a8",
    },
    "midnight": {
        "name": "Gece Mavisi",
        "bg": "linear-gradient(160deg, #060b18 0%, #0b1a3a 50%, #10265c 100%)",
        "text": "#f2f6ff",
        "muted": "#9db3d9",
        "card_bg": "rgba(255,255,255,0.07)",
        "card_border": "rgba(120,170,255,0.25)",
        "card_hover": "rgba(255,255,255,0.13)",
        "accent": "#38bdf8",
    },
    "emerald": {
        "name": "Zümrüt",
        "bg": "linear-gradient(160deg, #04140f 0%, #0b2e22 50%, #114b36 100%)",
        "text": "#f1fbf6",
        "muted": "#9ecbb3",
        "card_bg": "rgba(255,255,255,0.06)",
        "card_border": "rgba(180,255,210,0.2)",
        "card_hover": "rgba(255,255,255,0.12)",
        "accent": "#f5c451",
    },
    "royal": {
        "name": "Kraliyet Moru",
        "bg": "linear-gradient(160deg, #140a24 0%, #2c1250 50%, #451a72 100%)",
        "text": "#f8f3ff",
        "muted": "#c6aee3",
        "card_bg": "rgba(255,255,255,0.08)",
        "card_border": "rgba(230,180,255,0.25)",
        "card_hover": "rgba(255,255,255,0.14)",
        "accent": "#f472b6",
    },
    "sunset": {
        "name": "Gün Batımı",
        "bg": "linear-gradient(160deg, #2b0f1e 0%, #7a1e3d 45%, #d9622f 100%)",
        "text": "#fff8f2",
        "muted": "#f3c7ae",
        "card_bg": "rgba(255,255,255,0.10)",
        "card_border": "rgba(255,230,210,0.28)",
        "card_hover": "rgba(255,255,255,0.16)",
        "accent": "#ffd166",
    },
    "minimal": {
        "name": "Minimal Beyaz",
        "bg": "linear-gradient(160deg, #ffffff 0%, #f3f5f8 100%)",
        "text": "#12151b",
        "muted": "#5b6472",
        "card_bg": "#ffffff",
        "card_border": "rgba(15,20,30,0.10)",
        "card_hover": "#f4f6f9",
        "accent": "#2563eb",
    },
}

DEFAULT_THEME = "carbon"
BUTTON_SHAPES = ("pill", "rounded", "square")


def theme_list():
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk == "name"}} for k, v in THEMES.items()]


def theme_vars(theme_key, accent_override=""):
    t = THEMES.get(theme_key) or THEMES[DEFAULT_THEME]
    out = dict(t)
    if (accent_override or "").strip():
        out["accent"] = accent_override.strip()
    return out


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


def _page_row(row):
    if not row:
        return None
    d = dict(row)
    d["is_active"] = bool(int(d.get("is_active") or 0))
    d["view_count"] = int(d.get("view_count") or 0)
    d["theme"] = d.get("theme") or DEFAULT_THEME
    d["button_shape"] = d.get("button_shape") or "pill"
    d["public_path"] = f"/p/{d['slug']}"
    return d


def _button_row(row):
    if not row:
        return None
    d = dict(row)
    d["is_active"] = bool(int(d.get("is_active") or 0))
    d["highlight"] = bool(int(d.get("highlight") or 0))
    d["click_count"] = int(d.get("click_count") or 0)
    return d


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
        f"FROM biolink_buttons WHERE page_id IN ({placeholders}) AND button_type = 'link' GROUP BY page_id",
        tuple(page_ids),
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


def create_page(conn, *, title="", subtitle="", slug=None, theme=None, accent_color="",
                 avatar_url="", button_shape="pill", ga4_measurement_id="", ga4_api_secret="",
                 created_by=""):
    title = (title or "").strip()[:200] or "Yeni Sayfa"
    subtitle = (subtitle or "").strip()[:400]
    avatar_url = (avatar_url or "").strip()[:500]
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
          (slug, title, subtitle, avatar_url, theme, accent_color, button_shape,
           is_active, view_count, ga4_measurement_id, ga4_api_secret, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?)
        """,
        (final_slug, title, subtitle, avatar_url, theme, accent_color, button_shape,
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
    avatar_url = pick("avatar_url", row["avatar_url"], 500)
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
    execute(
        conn,
        """
        UPDATE biolink_pages
        SET slug = ?, title = ?, subtitle = ?, avatar_url = ?, theme = ?, accent_color = ?,
            button_shape = ?, is_active = ?, ga4_measurement_id = ?, ga4_api_secret = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_slug, title, subtitle, avatar_url, theme, accent_color, button_shape,
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
        avatar_url=src["avatar_url"],
        button_shape=src["button_shape"],
        created_by=created_by,
    )
    for b in src.get("buttons", []):
        add_button(
            conn, new_page["id"],
            button_type=b["button_type"], label=b["label"], url=b["url"], icon=b["icon"],
            highlight=b["highlight"], badge_text=b["badge_text"], is_active=b["is_active"],
        )
    return get_page(conn, new_page["id"])


def add_button(conn, page_id, *, button_type="link", label="", url="", icon="",
                highlight=False, badge_text="", is_active=True):
    button_type = button_type if button_type in ("link", "heading") else "link"
    label = (label or "").strip()[:200]
    url = _normalize_url(url) if button_type == "link" else ""
    if button_type == "link" and not _valid_url(url):
        raise ValueError("Geçerli bir URL girin.")
    icon = (icon or "").strip()[:8]
    badge_text = (badge_text or "").strip()[:32]
    now = iso(utcnow())
    max_order = scalar(conn, "SELECT COALESCE(MAX(sort_order), -1) FROM biolink_buttons WHERE page_id = ?", (int(page_id),))
    sort_order = int(max_order or -1) + 1
    button_id = insert_returning_id(
        conn,
        """
        INSERT INTO biolink_buttons
          (page_id, button_type, label, url, icon, highlight, badge_text, is_active,
           sort_order, click_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (int(page_id), button_type, label, url, icon, int(bool(highlight)), badge_text,
         int(bool(is_active)), sort_order, now, now),
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
    if button_type not in ("link", "heading"):
        button_type = row["button_type"]
    label = (data.get("label", row["label"]) or "").strip()[:200]
    if "url" in data:
        url = _normalize_url(data.get("url")) if button_type == "link" else ""
        if button_type == "link" and not _valid_url(url):
            raise ValueError("Geçerli bir URL girin.")
    else:
        url = row["url"]
    icon = (data.get("icon", row["icon"]) or "").strip()[:8]
    highlight = int(bool(data["highlight"])) if "highlight" in data else int(row["highlight"] or 0)
    badge_text = (data.get("badge_text", row["badge_text"]) or "").strip()[:32]
    is_active = int(bool(data["is_active"])) if "is_active" in data else int(row["is_active"] or 0)
    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE biolink_buttons
        SET button_type = ?, label = ?, url = ?, icon = ?, highlight = ?, badge_text = ?,
            is_active = ?, updated_at = ?
        WHERE id = ?
        """,
        (button_type, label, url, icon, highlight, badge_text, is_active, now, int(button_id)),
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
        "SELECT * FROM biolink_buttons WHERE id = ? AND page_id = ? AND button_type = 'link' AND COALESCE(is_active,1) = 1",
        (int(button_id), int(page_id)),
    )
    if not row:
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
    return row["url"]


def get_stats(conn, page_id):
    page = get_page(conn, page_id, with_buttons=True)
    if not page:
        return None
    buttons = [b for b in page["buttons"] if b["button_type"] == "link"]
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
