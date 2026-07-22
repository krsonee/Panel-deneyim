"""Takip edilen domainler — marka varsayılanları + bio özel domain senkronu."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlparse

from database import execute, fetchall, fetchone, get_db, insert_returning_id, integrity_error_type


def _iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_track_domain(domain):
    """URL veya host → www’siz domain."""
    raw = (domain or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw or raw.startswith("//"):
        if not raw.startswith(("http://", "https://", "//")):
            raw = "https://" + raw.lstrip("/")
        parsed = urlparse(raw)
        d = (parsed.hostname or "").strip().lower()
    else:
        d = raw.split("/")[0].split("?")[0].split("#")[0].strip().lower()
    d = d.removeprefix("www.")
    if d == "127.0.0.1":
        return "localhost"
    return d


def upsert_tracked_domain(domain, *, label="", ref_code="", created_by="system"):
    """Domain yoksa tracked_links’e ekler; varsa etiketi boşsa günceller."""
    domain = normalize_track_domain(domain)
    if not domain:
        return None
    ref_code = (ref_code or "").strip()
    label = (label or "").strip()[:120]
    created_by = (created_by or "system").strip()[:64]
    try:
        with closing(get_db()) as conn:
            row = fetchone(
                conn,
                "SELECT id, label FROM tracked_links WHERE domain = ? AND ref_code = ?",
                (domain, ref_code),
            )
            if row:
                existing_label = (row["label"] if "label" in row.keys() else "") or ""
                if label and not str(existing_label).strip():
                    execute(conn, "UPDATE tracked_links SET label = ? WHERE id = ?", (label, row["id"]))
                    conn.commit()
                return int(row["id"])
            link_id = insert_returning_id(
                conn,
                "INSERT INTO tracked_links (domain, ref_code, label, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
                (domain, ref_code, label, _iso_now(), created_by),
            )
            conn.commit()
            return int(link_id)
    except integrity_error_type():
        with closing(get_db()) as conn:
            row = fetchone(
                conn,
                "SELECT id FROM tracked_links WHERE domain = ? AND ref_code = ?",
                (domain, ref_code),
            )
            return int(row["id"]) if row else None


# Operasyondan tamamen çıkarılan domainler — DB + bio bağını temizle (Namecheap’e dokunulmaz)
_RETIRED_TRACK_DOMAINS = frozenset({"girbize.com"})


def purge_retired_domains():
    """Emekli domainleri tracked_links + biolink custom_domain’den siler."""
    targets = sorted(_RETIRED_TRACK_DOMAINS)
    if not targets:
        return
    with closing(get_db()) as conn:
        for domain in targets:
            d = normalize_track_domain(domain)
            if not d:
                continue
            rows = fetchall(conn, "SELECT id FROM tracked_links WHERE domain = ?", (d,))
            for row in rows or []:
                lid = row["id"]
                execute(conn, "DELETE FROM visitor_sessions WHERE tracked_link_id = ?", (lid,))
                execute(conn, "DELETE FROM tracked_links WHERE id = ?", (lid,))
            execute(
                conn,
                """
                UPDATE biolink_pages
                SET custom_domain = ''
                WHERE LOWER(REPLACE(custom_domain, 'www.', '')) = ?
                """,
                (d,),
            )
        conn.commit()


def ensure_brand_tracked_domains():
    """Marka varsayılan domainleri + tüm bio özel domainleri Link Takip’e alır."""
    try:
        from panel_config import BRAND, BIOLINK_PACK
    except Exception:
        return

    try:
        purge_retired_domains()
    except Exception as exc:
        print(f"⚠️  purge_retired_domains: {exc}")

    defaults = list(BRAND.get("default_tracked_domains") or [])
    site = (BIOLINK_PACK.get("site_url") or "").strip()
    if site:
        host = normalize_track_domain(site)
        if host and not any(normalize_track_domain(d.get("domain")) == host for d in defaults):
            defaults.append({"domain": host, "label": f"{BRAND.get('casino_name') or 'Casino'} (ana site)"})

    for item in defaults:
        upsert_tracked_domain(
            item.get("domain") or "",
            label=item.get("label") or "",
            ref_code=item.get("ref_code") or "",
            created_by="brand-seed",
        )

    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            """
            SELECT title, custom_domain FROM biolink_pages
            WHERE custom_domain IS NOT NULL AND TRIM(custom_domain) != ''
            """,
        )
    for row in rows or []:
        domain = normalize_track_domain(row.get("custom_domain") or "")
        if not domain or domain in _RETIRED_TRACK_DOMAINS:
            continue
        title = (row.get("title") or domain).strip()[:80]
        upsert_tracked_domain(domain, label=f"Bio: {title}", created_by="biolink-sync")


def sync_biolink_custom_domain(page):
    """Kaydedilen bio sayfasının özel domainini takip listesine yazar."""
    if not page:
        return
    domain = normalize_track_domain(page.get("custom_domain") or "")
    if not domain or domain in _RETIRED_TRACK_DOMAINS:
        return
    title = (page.get("title") or domain).strip()[:80]
    upsert_tracked_domain(domain, label=f"Bio: {title}", created_by="biolink-sync")
