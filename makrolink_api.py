"""MakroLink — kendi kısa link servisi (makrovip.com).

Akış: makrovip.com/xxx → https://go.aff.makroaffi.com/46ix1iwv (Smartico)
804/805 rotasyonunu Smartico go.aff halleder; biz sadece kısaltıp tıklama sayarız.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import string
from urllib.parse import urlparse

from database import (
    execute,
    fetchall,
    fetchone,
    iso,
    scalar,
    uses_postgres,
    utcnow,
)

DEFAULT_PUBLIC_HOST = "makrovip.com"
DEFAULT_AFF_BASE = "https://go.aff.makroaffi.com"
CODE_ALPHABET = string.ascii_letters + string.digits
CODE_LEN = 7

RESERVED_PATHS = frozenset({
    "", "admin", "api", "static", "demo", "r", "health", "favicon.ico",
    "robots.txt", "sitemap.xml", "login", "logout", "mail", "mailing",
})


def get_setting(conn, key, default=None):
    val = scalar(conn, "SELECT value FROM makrolink_settings WHERE key = ?", (key,))
    return val if val is not None else default


def upsert_setting(conn, key, value):
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO makrolink_settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, str(value)),
        )
    else:
        execute(
            conn,
            "INSERT OR REPLACE INTO makrolink_settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
    conn.commit()


def get_config(conn):
    host = (get_setting(conn, "public_host", DEFAULT_PUBLIC_HOST) or DEFAULT_PUBLIC_HOST).strip().lower()
    host = host.replace("https://", "").replace("http://", "").strip("/").split("/")[0]
    scheme = (get_setting(conn, "public_scheme", "https") or "https").strip().lower()
    if scheme not in ("https", "http"):
        scheme = "https"
    aff_base = (get_setting(conn, "aff_base", DEFAULT_AFF_BASE) or DEFAULT_AFF_BASE).strip()
    aff_base = aff_base.rstrip("/")
    if not aff_base.startswith("http"):
        aff_base = "https://" + aff_base
    return {
        "public_host": host or DEFAULT_PUBLIC_HOST,
        "public_scheme": scheme,
        "aff_base": aff_base or DEFAULT_AFF_BASE,
        "ga4_measurement_id": (get_setting(conn, "ga4_measurement_id", "") or "").strip(),
    }


def save_config(conn, public_host=None, public_scheme=None, aff_base=None, ga4_measurement_id=None):
    if public_host is not None:
        host = (public_host or "").strip().lower()
        host = host.replace("https://", "").replace("http://", "").strip("/").split("/")[0]
        upsert_setting(conn, "public_host", host or DEFAULT_PUBLIC_HOST)
    if public_scheme is not None:
        scheme = (public_scheme or "https").strip().lower()
        upsert_setting(conn, "public_scheme", scheme if scheme in ("https", "http") else "https")
    if aff_base is not None:
        base = (aff_base or "").strip().rstrip("/")
        if base and not base.startswith("http"):
            base = "https://" + base
        if not base or not _valid_url(base + "/x"):
            raise ValueError("Geçerli Smartico aff base gerekli (örn. https://go.aff.makroaffi.com).")
        upsert_setting(conn, "aff_base", base)
    if ga4_measurement_id is not None:
        upsert_setting(conn, "ga4_measurement_id", (ga4_measurement_id or "").strip())
    return get_config(conn)


def _gen_code(n=CODE_LEN):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


def _valid_code(code):
    code = (code or "").strip()
    if not code or len(code) > 32:
        return False
    if code.lower() in RESERVED_PATHS:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", code))


def _valid_url(url):
    url = (url or "").strip()
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def normalize_smartico_aff_url(conn, raw):
    """Tam go.aff URL veya sadece slug (46ix1iwv) → https://go.aff.makroaffi.com/46ix1iwv"""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Smartico go.aff linki gerekli.")
    base = get_config(conn)["aff_base"].rstrip("/")

    # Sadece slug: 46ix1iwv
    if re.fullmatch(r"[A-Za-z0-9_-]{4,64}", raw) and "://" not in raw and "/" not in raw:
        return f"{base}/{raw}"

    if not raw.startswith("http"):
        raw = "https://" + raw.lstrip("/")

    p = urlparse(raw)
    if not p.netloc:
        raise ValueError("Geçerli Smartico go.aff URL gerekli.")

    # Path'ten slug al; host ne olursa olsun aff_base'e oturt (yanlış host yapıştırılırsa)
    slug = (p.path or "").strip("/")
    if not slug:
        raise ValueError("go.aff linkinde path/slug yok (örn. …/46ix1iwv).")
    # query/fragment Smartico'da nadir; koru
    out = f"{base}/{slug.split('/')[0]}"
    if p.query:
        out += "?" + p.query
    if p.fragment:
        out += "#" + p.fragment
    return out


def short_url(conn, code):
    cfg = get_config(conn)
    return f"{cfg['public_scheme']}://{cfg['public_host']}/{code}"


def _row_to_dict(conn, row):
    if not row:
        return None
    d = dict(row)
    d["short_url"] = short_url(conn, d["code"])
    d["clicks"] = int(d.get("click_count") or 0)
    return d


def list_links(conn, q_text=None, limit=200):
    rows = fetchall(
        conn,
        """
        SELECT * FROM makrolink_links
        WHERE COALESCE(is_active, 1) = 1
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    items = [_row_to_dict(conn, r) for r in rows]
    q_text = (q_text or "").strip().lower()
    if q_text:
        items = [
            x for x in items
            if q_text in (x.get("code") or "").lower()
            or q_text in (x.get("label") or "").lower()
            or q_text in (x.get("destination_url") or "").lower()
            or q_text in (x.get("affiliate_id") or "").lower()
            or q_text in (x.get("ref_code") or "").lower()
        ]
    return items


def get_link_by_code(conn, code, active_only=True):
    code = (code or "").strip()
    if not _valid_code(code):
        return None
    if active_only:
        row = fetchone(
            conn,
            "SELECT * FROM makrolink_links WHERE code = ? AND COALESCE(is_active, 1) = 1",
            (code,),
        )
    else:
        row = fetchone(conn, "SELECT * FROM makrolink_links WHERE code = ?", (code,))
    return _row_to_dict(conn, row) if row else None


def create_link(
    conn,
    destination_url,
    label="",
    code=None,
    affiliate_id="",
    smartico_link_id="",
    ref_code="",
    created_by="",
):
    try:
        destination_url = normalize_smartico_aff_url(conn, destination_url)
    except ValueError:
        raise
    if not _valid_url(destination_url):
        raise ValueError("Geçerli Smartico go.aff URL gerekli.")

    label = (label or "").strip()[:200]
    affiliate_id = (affiliate_id or "").strip()[:64]
    smartico_link_id = (smartico_link_id or "").strip()[:64]
    ref_code = (ref_code or "").strip()[:128]
    created_by = (created_by or "").strip()[:64]
    now = iso(utcnow())

    # Slug'ı smartico_link_id olarak sakla (boşsa)
    slug = urlparse(destination_url).path.strip("/").split("/")[0]
    if not smartico_link_id and slug:
        smartico_link_id = slug[:64]

    if code:
        code = code.strip()
        if not _valid_code(code):
            raise ValueError("Kod geçersiz (harf/rakam/_/- , reserved değil).")
        exists = fetchone(conn, "SELECT id FROM makrolink_links WHERE code = ?", (code,))
        if exists:
            raise ValueError("Bu kısa kod zaten kullanılıyor.")
    else:
        for _ in range(12):
            code = _gen_code()
            if not fetchone(conn, "SELECT id FROM makrolink_links WHERE code = ?", (code,)):
                break
        else:
            raise ValueError("Kısa kod üretilemedi, tekrar dene.")

    if uses_postgres():
        cur = execute(
            conn,
            """
            INSERT INTO makrolink_links
              (code, destination_url, label, affiliate_id, smartico_link_id, ref_code,
               click_count, is_active, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)
            RETURNING id
            """,
            (code, destination_url, label, affiliate_id, smartico_link_id, ref_code, created_by, now, now),
        )
        link_id = cur.fetchone()["id"]
    else:
        cur = execute(
            conn,
            """
            INSERT INTO makrolink_links
              (code, destination_url, label, affiliate_id, smartico_link_id, ref_code,
               click_count, is_active, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)
            """,
            (code, destination_url, label, affiliate_id, smartico_link_id, ref_code, created_by, now, now),
        )
        link_id = cur.lastrowid
    conn.commit()
    row = fetchone(conn, "SELECT * FROM makrolink_links WHERE id = ?", (link_id,))
    return _row_to_dict(conn, row)


def deactivate_link(conn, link_id):
    now = iso(utcnow())
    cur = execute(
        conn,
        "UPDATE makrolink_links SET is_active = 0, updated_at = ? WHERE id = ?",
        (now, int(link_id)),
    )
    conn.commit()
    return cur.rowcount > 0


def update_link(conn, link_id, destination_url=None, label=None, ref_code=None):
    row = fetchone(conn, "SELECT * FROM makrolink_links WHERE id = ?", (int(link_id),))
    if not row:
        raise ValueError("Link bulunamadı.")
    if destination_url is not None:
        dest = normalize_smartico_aff_url(conn, destination_url)
    else:
        dest = row["destination_url"]
    if not _valid_url(dest):
        raise ValueError("Geçerli hedef URL gerekli.")
    lab = label if label is not None else row["label"]
    ref = ref_code if ref_code is not None else row["ref_code"]
    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE makrolink_links
        SET destination_url = ?, label = ?, ref_code = ?, updated_at = ?
        WHERE id = ?
        """,
        (dest, (lab or "").strip()[:200], (ref or "").strip()[:128], now, int(link_id)),
    )
    conn.commit()
    return _row_to_dict(conn, fetchone(conn, "SELECT * FROM makrolink_links WHERE id = ?", (int(link_id),)))


def _hash_ip(ip):
    ip = (ip or "").strip()
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


def record_click_and_resolve(conn, code, ip="", user_agent="", referer=""):
    """302 hedefi: saklanan go.aff URL — UTM ekleme (Smartico kırılmasın)."""
    link = get_link_by_code(conn, code, active_only=True)
    if not link:
        return None
    now = iso(utcnow())
    execute(
        conn,
        """
        INSERT INTO makrolink_clicks
          (link_id, code, clicked_at, ip_hash, user_agent, referer)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            link["id"],
            link["code"],
            now,
            _hash_ip(ip),
            (user_agent or "")[:500],
            (referer or "")[:500],
        ),
    )
    execute(
        conn,
        "UPDATE makrolink_links SET click_count = COALESCE(click_count, 0) + 1, updated_at = ? WHERE id = ?",
        (now, link["id"]),
    )
    conn.commit()
    return link["destination_url"]


def is_makrolink_host(host, conn=None):
    host = (host or "").split(":")[0].strip().lower()
    if not host:
        return False
    if conn is not None:
        cfg_host = get_config(conn)["public_host"]
    else:
        cfg_host = DEFAULT_PUBLIC_HOST
    return host == cfg_host or host == f"www.{cfg_host}"
