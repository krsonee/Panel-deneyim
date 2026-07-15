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
    insert_returning_id,
    integrity_error_type,
    iso,
    scalar,
    uses_postgres,
    utcnow,
)

IntegrityError = integrity_error_type()

DEFAULT_PUBLIC_HOST = "makrovip.com"
DEFAULT_AFF_BASE = "https://go.aff.makroaffi.com"
CODE_ALPHABET = string.ascii_letters + string.digits
CODE_LEN = 7

# MakroLink kategori listesi (oluşturma + manuel atama)
LINK_CATEGORIES = (
    "Marketing",
    "Call Center",
    "Sosyal Medya",
    "Mailing",
    "Sms",
    "Seo&Meta",
    "Twitter",
    "Instagram",
    "IVR",
)
_LINK_CATEGORY_MAP = {c.lower(): c for c in LINK_CATEGORIES}


def normalize_category(value, *, allow_empty=True):
    raw = (value or "").strip()
    if not raw:
        if allow_empty:
            return ""
        raise ValueError("Kategori gerekli.")
    canon = _LINK_CATEGORY_MAP.get(raw.lower())
    if not canon:
        # Yaygın yazım hataları
        aliases = {
            "twiter": "Twitter",
            "seo & meta": "Seo&Meta",
            "seo and meta": "Seo&Meta",
            "callcenter": "Call Center",
            "call-center": "Call Center",
            "sosyalmedya": "Sosyal Medya",
        }
        canon = aliases.get(raw.lower())
    if not canon:
        raise ValueError(
            "Geçersiz kategori. Seçenekler: " + ", ".join(LINK_CATEGORIES)
        )
    return canon


def list_categories():
    return list(LINK_CATEGORIES)

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


def _normalize_domain(domain):
    """app.py'deki normalize_domain ile aynı mantık (tracked_links ile uyumlu kalması için)."""
    raw = (domain or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw or raw.startswith("//"):
        if not raw.startswith(("http://", "https://", "//")):
            raw = "https://" + raw.lstrip("/")
        d = (urlparse(raw).hostname or "").strip().lower()
    else:
        d = raw.split("/")[0].split("?")[0].split("#")[0].strip().lower()
    d = d.removeprefix("www.")
    if d == "127.0.0.1":
        return "localhost"
    return d


def _sync_tracked_link(conn, domain, ref_code, label):
    """MakroLink'in hedef domaini + kısa kodunu tracked_links'e UPSERT eder,
    böylece bu linkten gelen ziyaretçiler takip listesinde MakroLink etiketiyle görünür."""
    domain = _normalize_domain(domain)
    ref_code = (ref_code or "").strip()
    label = (label or "").strip()[:200]
    if not domain or not ref_code:
        return
    now = iso(utcnow())
    existing = fetchone(
        conn,
        "SELECT id FROM tracked_links WHERE domain = ? AND ref_code = ?",
        (domain, ref_code),
    )
    if existing:
        execute(
            conn,
            "UPDATE tracked_links SET label = ? WHERE id = ?",
            (label, existing["id"]),
        )
        return
    try:
        insert_returning_id(
            conn,
            "INSERT INTO tracked_links (domain, ref_code, label, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
            (domain, ref_code, label, now, "makrolink"),
        )
    except IntegrityError:
        # Yarış durumu — muhtemelen aynı anda oluştu, etiketi güncelle.
        execute(
            conn,
            "UPDATE tracked_links SET label = ? WHERE domain = ? AND ref_code = ?",
            (label, domain, ref_code),
        )


def _sync_makrolink_tracking(conn, *, target_domain, code, label, affiliate_id=""):
    """Online takip için hedef domain'e hem kısa kodu hem Smartico affid'i kaydet.

    Casino sitede tracker.js varsa:
    - ?ref=makrolink-kodu  → kısa kod eşleşir
    - ?affid=12345         → Affiliate ID notu eşleşir (Smartico genelde bunu taşır)
    """
    if not target_domain:
        return
    _sync_tracked_link(conn, target_domain, code, label)
    aff = (affiliate_id or "").strip()
    if aff and aff.lower() != (code or "").strip().lower():
        _sync_tracked_link(conn, target_domain, aff, f"{label} (affid)")


MAX_ONLINE_GROUP = 150


def expand_online_domain_group(raw):
    """Canlı casino domain grubu: 'makrobet804-820' veya satır/virgül ile tek domainler.

    Aralık sözdizimi app.expand_domain_line ile aynı: prefix + start-end → prefixN.com
    """
    if isinstance(raw, list):
        lines = raw
    else:
        lines = str(raw or "").replace(",", "\n").split("\n")

    domains = []
    seen = set()
    for line in lines:
        line = (line or "").strip()
        if not line or line.startswith("#"):
            continue
        compact = re.sub(r"\s+", "", line)
        range_match = re.match(r"^([a-zA-Z][a-zA-Z0-9]*?)(\d+)-(\d+)$", compact, re.I)
        if range_match:
            prefix = range_match.group(1).lower()
            start = int(range_match.group(2))
            end = int(range_match.group(3))
            if start > end:
                start, end = end, start
            count = end - start + 1
            if count > MAX_ONLINE_GROUP:
                raise ValueError(
                    f"Online domain grubu en fazla {MAX_ONLINE_GROUP} domain olabilir "
                    f"({count} istendi). Dar bir canlı pencere kullan: örn. makrobet804-820"
                )
            for num in range(start, end + 1):
                d = f"{prefix}{num}.com"
                if d not in seen:
                    seen.add(d)
                    domains.append(d)
            continue
        d = _normalize_domain(line)
        if d and d not in seen:
            seen.add(d)
            domains.append(d)

    if len(domains) > MAX_ONLINE_GROUP:
        raise ValueError(
            f"Online domain grubu en fazla {MAX_ONLINE_GROUP} domain olabilir ({len(domains)})."
        )
    return domains


def get_online_domain_group_raw(conn):
    return (get_setting(conn, "online_domain_group", "") or "").strip()


def get_online_domains(conn):
    """Ayarlardaki canlı gruptan domain listesi (boş = online sync yok)."""
    try:
        return expand_online_domain_group(get_online_domain_group_raw(conn))
    except ValueError:
        return []


def _sync_makrolink_to_online_group(conn, *, code, label, affiliate_id=""):
    """Link'in kod + Affid'ini canlı domain grubundaki TÜM domainlere yazar."""
    domains = get_online_domains(conn)
    if not domains:
        return 0
    for domain in domains:
        _sync_makrolink_tracking(
            conn,
            target_domain=domain,
            code=code,
            label=label,
            affiliate_id=affiliate_id,
        )
    return len(domains)


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
    group_raw = get_online_domain_group_raw(conn)
    try:
        online_domains = expand_online_domain_group(group_raw) if group_raw else []
        online_group_error = ""
    except ValueError as exc:
        online_domains = []
        online_group_error = str(exc)

    cfg = {
        "public_host": default_host,
        "short_hosts": hosts,
        "public_scheme": scheme,
        "aff_base": aff_base or DEFAULT_AFF_BASE,
        "online_domain_group": group_raw,
        "online_domains": online_domains,
        "online_domain_count": len(online_domains),
        "online_group_error": online_group_error,
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
    online_domain_group=None,
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

    if online_domain_group is not None:
        raw_group = str(online_domain_group or "").strip()
        # Validate (boş serbest)
        if raw_group:
            expand_online_domain_group(raw_group)
        upsert_setting(conn, "online_domain_group", raw_group)

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
            or q_text in (x.get("category") or "").lower()
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
    target_domain=None,
    category="",
):
    destination_url = normalize_smartico_aff_url(conn, destination_url)
    if not _valid_url(destination_url):
        raise ValueError("Geçerli Smartico go.aff URL gerekli.")

    label = (label or "").strip()[:200]
    if not label:
        raise ValueError("Etiket gerekli.")
    code = (code or "").strip()
    if not code:
        raise ValueError("Özel kod gerekli.")
    if not _valid_code(code):
        raise ValueError("Kod geçersiz (harf/rakam/_/- , reserved değil).")
    affiliate_id = (affiliate_id or "").strip()[:64]
    smartico_link_id = (smartico_link_id or "").strip()[:64]
    ref_code = (ref_code or "").strip()[:128]
    created_by = (created_by or "").strip()[:64]
    target_domain = _normalize_domain(target_domain) if target_domain else ""
    # Per-link domain yerine canlı grup kullanılır; kayıtta grup özetini sakla (geriye dönük alan)
    if not target_domain:
        group_raw = get_online_domain_group_raw(conn)
        if group_raw:
            target_domain = ("group:" + group_raw)[:200]
    category = normalize_category(category, allow_empty=False)
    now = iso(utcnow())

    slug = urlparse(destination_url).path.strip("/").split("/")[0]
    if not smartico_link_id and slug:
        smartico_link_id = slug[:64]

    revive_id = None
    existing = fetchone(conn, "SELECT id, is_active FROM makrolink_links WHERE code = ?", (code,))
    if existing:
        if int(existing["is_active"] or 0) == 1:
            raise ValueError("Bu kısa kod zaten kullanılıyor.")
        # Pasif (silinmiş) linkin kodu — yeniden canlandır, yeni verilerle güncelle.
        revive_id = existing["id"]

    if revive_id is not None:
        execute(
            conn,
            """
            UPDATE makrolink_links
            SET destination_url = ?, label = ?, affiliate_id = ?, smartico_link_id = ?,
                ref_code = ?, click_count = 0, is_active = 1, created_by = ?,
                created_at = ?, updated_at = ?, target_domain = ?, category = ?
            WHERE id = ?
            """,
            (
                destination_url, label, affiliate_id, smartico_link_id, ref_code,
                created_by, now, now, target_domain, category, revive_id,
            ),
        )
        link_id = revive_id
    elif uses_postgres():
        cur = execute(
            conn,
            """
            INSERT INTO makrolink_links
              (code, destination_url, label, affiliate_id, smartico_link_id, ref_code,
               click_count, is_active, created_by, created_at, updated_at, target_domain, category)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                code, destination_url, label, affiliate_id, smartico_link_id, ref_code,
                created_by, now, now, target_domain, category,
            ),
        )
        link_id = cur.fetchone()["id"]
    else:
        cur = execute(
            conn,
            """
            INSERT INTO makrolink_links
              (code, destination_url, label, affiliate_id, smartico_link_id, ref_code,
               click_count, is_active, created_by, created_at, updated_at, target_domain, category)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?, ?)
            """,
            (
                code, destination_url, label, affiliate_id, smartico_link_id, ref_code,
                created_by, now, now, target_domain, category,
            ),
        )
        link_id = cur.lastrowid

    # Online: canlı domain grubundaki tüm casino domainlerine Affid + kod yaz
    _sync_makrolink_to_online_group(
        conn,
        code=code,
        label=label,
        affiliate_id=affiliate_id,
    )

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


def update_link(
    conn,
    link_id,
    destination_url=None,
    label=None,
    code=None,
    affiliate_id=None,
    ref_code=None,
    target_domain=None,
    category=None,
):
    row = fetchone(conn, "SELECT * FROM makrolink_links WHERE id = ?", (int(link_id),))
    if not row:
        raise ValueError("Link bulunamadı.")
    row = dict(row)
    if int(row.get("is_active") or 0) != 1:
        raise ValueError("Pasif link düzenlenemez.")

    if destination_url is not None:
        dest = normalize_smartico_aff_url(conn, destination_url)
    else:
        dest = row["destination_url"]
    if not _valid_url(dest):
        raise ValueError("Geçerli hedef URL gerekli.")

    if label is not None:
        lab = (label or "").strip()[:200]
        if not lab:
            raise ValueError("Etiket gerekli.")
    else:
        lab = row.get("label") or ""

    if code is not None:
        new_code = (code or "").strip()
        if not new_code:
            raise ValueError("Özel kod gerekli.")
        if not _valid_code(new_code):
            raise ValueError("Kod geçersiz (harf/rakam/_/- , reserved değil).")
        if new_code != row.get("code"):
            other = fetchone(
                conn,
                """
                SELECT id FROM makrolink_links
                WHERE code = ? AND id != ? AND COALESCE(is_active, 1) = 1
                """,
                (new_code, int(link_id)),
            )
            if other:
                raise ValueError("Bu kısa kod zaten kullanılıyor.")
    else:
        new_code = row.get("code") or ""

    if affiliate_id is not None:
        aff = (affiliate_id or "").strip()[:64]
    else:
        aff = row.get("affiliate_id") or ""

    ref = ref_code if ref_code is not None else row.get("ref_code")
    ref = (ref or "").strip()[:128]

    if target_domain is not None and str(target_domain).strip() and not str(target_domain).strip().startswith("group:"):
        new_target_domain = _normalize_domain(target_domain)
    else:
        group_raw = get_online_domain_group_raw(conn)
        new_target_domain = (("group:" + group_raw)[:200] if group_raw else (row.get("target_domain") or ""))

    if category is not None:
        new_category = normalize_category(category, allow_empty=True)
    else:
        new_category = row.get("category") or ""

    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE makrolink_links
        SET destination_url = ?, label = ?, code = ?, affiliate_id = ?, ref_code = ?,
            target_domain = ?, category = ?, updated_at = ?
        WHERE id = ?
        """,
        (dest, lab, new_code, aff, ref, new_target_domain, new_category, now, int(link_id)),
    )
    _sync_makrolink_to_online_group(
        conn,
        code=new_code,
        label=lab,
        affiliate_id=aff,
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


def test_ga4(conn):
    """GA4 Measurement Protocol doğrulama (debug endpoint, senkron)."""
    cfg = get_config(conn, include_secrets=True)
    mid = (cfg.get("ga4_measurement_id") or "").strip()
    secret = (cfg.get("ga4_api_secret") or "").strip()
    if not mid:
        return {"ok": False, "error": "GA4 Measurement ID eksik (G-…)."}
    if not secret:
        return {"ok": False, "error": "GA4 API Secret eksik. Ayarlara kaydet."}

    payload = {
        "client_id": f"makrolink-test.{secrets.token_hex(4)}",
        "events": [
            {
                "name": "makrolink_ga4_test",
                "params": {
                    "debug_mode": 1,
                    "engagement_time_msec": 1,
                    "short_host": (cfg.get("public_host") or "")[:100],
                },
            }
        ],
    }
    debug_url = (
        "https://www.google-analytics.com/debug/mp/collect"
        f"?measurement_id={urllib.parse.quote(mid)}"
        f"&api_secret={urllib.parse.quote(secret)}"
    )
    live_url = (
        "https://www.google-analytics.com/mp/collect"
        f"?measurement_id={urllib.parse.quote(mid)}"
        f"&api_secret={urllib.parse.quote(secret)}"
    )
    body = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            debug_url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "MakroLink/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw[:500]}
        messages = parsed.get("validationMessages") or []
        if messages:
            return {
                "ok": False,
                "error": "; ".join(
                    (m.get("description") or m.get("validationCode") or str(m)) for m in messages
                )[:400],
                "debug": parsed,
            }
        # Debug OK → gerçek bir test eventi de gönder (Realtime'da görünsün)
        try:
            live_req = urllib.request.Request(
                live_url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "MakroLink/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(live_req, timeout=6) as live_resp:
                live_resp.read()
        except Exception:
            pass
        return {
            "ok": True,
            "message": "GA4 kabul etti. Realtime’da ‘makrolink_ga4_test’ olayını kontrol et (1–2 dk).",
            "measurement_id": mid,
        }
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {exc.code}: {detail or exc.reason}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def resync_all_tracking(conn):
    """Aktif MakroLink'lerin Affid+kodunu canlı domain grubundaki tüm domainlere yazar."""
    domains = get_online_domains(conn)
    if not domains:
        return {
            "ok": False,
            "error": "Önce Ayarlar’da canlı casino domain grubunu yaz (örn. makrobet804-820).",
            "synced": 0,
            "domains": 0,
        }
    rows = fetchall(
        conn,
        """
        SELECT code, label, affiliate_id
        FROM makrolink_links
        WHERE COALESCE(is_active, 1) = 1
        """,
    )
    synced = 0
    for row in rows:
        r = dict(row)
        _sync_makrolink_to_online_group(
            conn,
            code=r.get("code") or "",
            label=r.get("label") or "",
            affiliate_id=r.get("affiliate_id") or "",
        )
        synced += 1
    # Link kayıtlarında grup işaretini güncelle
    group_raw = get_online_domain_group_raw(conn)
    marker = ("group:" + group_raw)[:200] if group_raw else ""
    if marker:
        execute(
            conn,
            """
            UPDATE makrolink_links
            SET target_domain = ?, updated_at = ?
            WHERE COALESCE(is_active, 1) = 1
            """,
            (marker, iso(utcnow())),
        )
    conn.commit()
    return {"ok": True, "synced": synced, "domains": len(domains)}


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
