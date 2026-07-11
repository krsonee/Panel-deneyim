"""MakroLink — kısa link (çoklu domain) → Smartico go.aff.

Akış: sada.com/xxx | makrovip.com/xxx → go.aff.makroaffi.com/slug
GA4: tek property, Measurement Protocol (tüm short host'lar).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import string
import threading
import urllib.error
import urllib.parse
import urllib.request
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


def _clean_host(host):
    host = (host or "").strip().lower()
    host = host.replace("https://", "").replace("http://", "").strip("/").split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _parse_host_list(raw, fallback=DEFAULT_PUBLIC_HOST):
    if not raw:
        return [fallback]
    hosts = []
    seen = set()
    for part in re.split(r"[\s,;]+", str(raw)):
        h = _clean_host(part)
        if not h or "." not in h or h in seen:
            continue
        seen.add(h)
        hosts.append(h)
    return hosts or [fallback]


def get_config(conn, include_secrets=False):
    default_host = _clean_host(get_setting(conn, "public_host", DEFAULT_PUBLIC_HOST) or DEFAULT_PUBLIC_HOST)
    hosts = _parse_host_list(get_setting(conn, "short_hosts", ""), default_host or DEFAULT_PUBLIC_HOST)
    if default_host and default_host not in hosts:
        hosts.insert(0, default_host)
    if not default_host:
        default_host = hosts[0]

    scheme = (get_setting(conn, "public_scheme", "https") or "https").strip().lower()
    if scheme not in ("https", "http"):
        scheme = "https"
    aff_base = (get_setting(conn, "aff_base", DEFAULT_AFF_BASE) or DEFAULT_AFF_BASE).strip().rstrip("/")
    if not aff_base.startswith("http"):
        aff_base = "https://" + aff_base

    mid = (get_setting(conn, "ga4_measurement_id", "") or "").strip()
    secret = (get_setting(conn, "ga4_api_secret", "") or "").strip()

    cfg = {
        "public_host": default_host,
        "short_hosts": hosts,
        "public_scheme": scheme,
        "aff_base": aff_base or DEFAULT_AFF_BASE,
        "ga4_measurement_id": mid,
        "ga4_configured": bool(mid and secret),
    }
    if include_secrets:
        cfg["ga4_api_secret"] = secret
    else:
        cfg["ga4_api_secret_set"] = bool(secret)
    return cfg


def save_config(
    conn,
    public_host=None,
    short_hosts=None,
    public_scheme=None,
    aff_base=None,
    ga4_measurement_id=None,
    ga4_api_secret=None,
):
    if short_hosts is not None:
        if isinstance(short_hosts, list):
            raw = "\n".join(str(x) for x in short_hosts)
        else:
            raw = str(short_hosts)
        hosts = _parse_host_list(raw, DEFAULT_PUBLIC_HOST)
        upsert_setting(conn, "short_hosts", "\n".join(hosts))
        # public_host listede yoksa ilkini varsayılan yap
        current_default = _clean_host(get_setting(conn, "public_host", "") or "")
        if not current_default or current_default not in hosts:
            upsert_setting(conn, "public_host", hosts[0])

    if public_host is not None:
        host = _clean_host(public_host) or DEFAULT_PUBLIC_HOST
        upsert_setting(conn, "public_host", host)
        # Varsayılanı listeye ekle
        hosts = _parse_host_list(get_setting(conn, "short_hosts", ""), host)
        if host not in hosts:
            hosts.insert(0, host)
            upsert_setting(conn, "short_hosts", "\n".join(hosts))

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
        mid = (ga4_measurement_id or "").strip().upper()
        if mid and not re.fullmatch(r"G-[A-Z0-9]+", mid):
            raise ValueError("GA4 Measurement ID G-XXXXXXXX formatında olmalı.")
        upsert_setting(conn, "ga4_measurement_id", mid)

    if ga4_api_secret is not None:
        # Boş string = silme; dolu = kaydet. None = dokunma — caller boş bırakırsa silmesin
        secret = (ga4_api_secret or "").strip()
        if secret:
            upsert_setting(conn, "ga4_api_secret", secret)
        elif ga4_api_secret == "":
            upsert_setting(conn, "ga4_api_secret", "")

    return get_config(conn, include_secrets=False)


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
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Smartico go.aff linki gerekli.")
    base = get_config(conn)["aff_base"].rstrip("/")

    if re.fullmatch(r"[A-Za-z0-9_-]{4,64}", raw) and "://" not in raw and "/" not in raw:
        return f"{base}/{raw}"

    if not raw.startswith("http"):
        raw = "https://" + raw.lstrip("/")

    p = urlparse(raw)
    if not p.netloc:
        raise ValueError("Geçerli Smartico go.aff URL gerekli.")

    slug = (p.path or "").strip("/")
    if not slug:
        raise ValueError("go.aff linkinde path/slug yok (örn. …/46ix1iwv).")
    out = f"{base}/{slug.split('/')[0]}"
    if p.query:
        out += "?" + p.query
    if p.fragment:
        out += "#" + p.fragment
    return out


def short_url(conn, code, host=None):
    cfg = get_config(conn)
    h = _clean_host(host) if host else cfg["public_host"]
    if h not in cfg["short_hosts"]:
        h = cfg["public_host"]
    return f"{cfg['public_scheme']}://{h}/{code}"


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
    destination_url = normalize_smartico_aff_url(conn, destination_url)
    if not _valid_url(destination_url):
        raise ValueError("Geçerli Smartico go.aff URL gerekli.")

    label = (label or "").strip()[:200]
    affiliate_id = (affiliate_id or "").strip()[:64]
    smartico_link_id = (smartico_link_id or "").strip()[:64]
    ref_code = (ref_code or "").strip()[:128]
    created_by = (created_by or "").strip()[:64]
    now = iso(utcnow())

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


def send_ga4_click(cfg, *, link_code, aff_slug, short_host, destination_url, client_id):
    """Measurement Protocol — redirect'i bloklamaz (thread)."""
    mid = (cfg.get("ga4_measurement_id") or "").strip()
    secret = (cfg.get("ga4_api_secret") or "").strip()
    if not mid or not secret:
        return

    payload = {
        "client_id": client_id or secrets.token_hex(8),
        "events": [
            {
                "name": "makrolink_click",
                "params": {
                    "link_code": (link_code or "")[:100],
                    "aff_slug": (aff_slug or "")[:100],
                    "short_host": (short_host or "")[:100],
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
        headers={"Content-Type": "application/json", "User-Agent": "MakroLink/1.0"},
        method="POST",
    )

    def _run():
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                resp.read()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def record_click_and_resolve(conn, code, ip="", user_agent="", referer="", short_host=""):
    link = get_link_by_code(conn, code, active_only=True)
    if not link:
        return None
    now = iso(utcnow())
    ip_hash = _hash_ip(ip)
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
            ip_hash,
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

    cfg = get_config(conn, include_secrets=True)
    host = _clean_host(short_host) or cfg["public_host"]
    slug = link.get("smartico_link_id") or urlparse(link["destination_url"]).path.strip("/").split("/")[0]
    client_id = ip_hash or secrets.token_hex(8)
    # UUID-ish for GA: insert dashes into hex
    if len(client_id) >= 16:
        cid = f"{client_id[:8]}-{client_id[8:12]}-{client_id[12:16]}-{client_id[16:20] if len(client_id) > 16 else '0000'}-{client_id[20:32] if len(client_id) >= 32 else client_id[:12].ljust(12, '0')}"
    else:
        cid = client_id
    send_ga4_click(
        cfg,
        link_code=link["code"],
        aff_slug=slug,
        short_host=host,
        destination_url=link["destination_url"],
        client_id=cid,
    )
    return link["destination_url"]


def is_makrolink_host(host, conn=None):
    host = _clean_host((host or "").split(":")[0])
    if not host:
        return False
    if conn is None:
        return host == DEFAULT_PUBLIC_HOST
    cfg = get_config(conn)
    return host in cfg["short_hosts"] or host == cfg["public_host"]
