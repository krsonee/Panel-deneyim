"""bl.ink (app.bl.ink) kısa link servisi entegrasyonu.

Smartico entegrasyonuna paralel, bağımsız bir katman: bl.ink hesabındaki
tüm kısa linkleri (ve gerçek yönlendirme adreslerini) çekip, kendi
tracker.js tabanlı anlık ziyaretçi verimizle eşleştirerek "şu an online"
sayısını gösterir. bl.ink API'si canlı oturum bilgisi vermez — sadece
tıklama/yönlendirme verisi tutar; online bilgisi tamamen bizim kendi
visitor_sessions tablomuzdan gelir.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.client import RemoteDisconnected

from database import (
    execute,
    fetchall,
    get_blink_setting,
    iso,
    upsert_blink_setting,
    uses_postgres,
    utcnow,
)

API_BASE = "https://app.bl.ink/api/v4"

_SETTING_EMAIL = "email"
_SETTING_PASSWORD = "password"

_HTTP_TIMEOUT = 8
_ONLINE_THRESHOLD_SECONDS = 90

_FETCH_ERRORS = (
    urllib.error.URLError,
    urllib.error.HTTPError,
    RemoteDisconnected,
    ConnectionError,
    TimeoutError,
    ValueError,
    TypeError,
    json.JSONDecodeError,
)

# access_token 24 saat geçerli; biz güvenli tarafta kalıp 20 saatte bir tazeliyoruz.
_TOKEN_TTL_SECONDS = 20 * 3600
_token_cache = {"token": None, "fetched_at": None}

_links_cache = {"fetched_at": None, "rows": []}
_CACHE_SECONDS = 60


class BlinkError(Exception):
    pass


def get_config(conn):
    email = (get_blink_setting(conn, _SETTING_EMAIL, "") or "").strip()
    password = (get_blink_setting(conn, _SETTING_PASSWORD, "") or "").strip()
    return {"email": email, "password": password}


def is_configured(conn):
    cfg = get_config(conn)
    return bool(cfg["email"] and cfg["password"])


def mask_email(email):
    email = email or ""
    if "@" not in email:
        return "•" * len(email)
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        masked_name = name[:1] + "•"
    else:
        masked_name = name[:2] + "•" * (len(name) - 2)
    return f"{masked_name}@{domain}"


def save_config(conn, email, password):
    email = (email or "").strip()
    password = (password or "").strip()
    upsert_blink_setting(conn, _SETTING_EMAIL, email)
    upsert_blink_setting(conn, _SETTING_PASSWORD, password)
    _token_cache["token"] = None
    _token_cache["fetched_at"] = None
    _links_cache["fetched_at"] = None
    _links_cache["rows"] = []
    return get_config(conn)


def clear_config(conn):
    upsert_blink_setting(conn, _SETTING_EMAIL, "")
    upsert_blink_setting(conn, _SETTING_PASSWORD, "")
    _token_cache["token"] = None
    _token_cache["fetched_at"] = None
    _links_cache["fetched_at"] = None
    _links_cache["rows"] = []


def _http(method, path, token=None, params=None, body=None):
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{API_BASE}{path}{query}"
    headers = {"Content-Type": "application/json", "User-Agent": "MakroPanel/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        if exc.code == 401:
            raise BlinkError("bl.ink giriş bilgileri geçersiz (401). Email/şifreyi kontrol et.") from exc
        raise BlinkError(f"bl.ink API hata verdi ({exc.code}): {detail or exc.reason}") from exc
    except _FETCH_ERRORS as exc:
        raise BlinkError(f"bl.ink API'ye bağlanılamadı: {exc}") from exc
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        raise BlinkError("bl.ink API beklenmeyen bir cevap döndürdü.") from exc


def _get_access_token(conn, force=False):
    now = datetime.now(timezone.utc)
    if (
        not force
        and _token_cache["token"]
        and _token_cache["fetched_at"]
        and now - _token_cache["fetched_at"] < timedelta(seconds=_TOKEN_TTL_SECONDS)
    ):
        return _token_cache["token"]

    cfg = get_config(conn)
    if not cfg["email"] or not cfg["password"]:
        raise BlinkError("bl.ink email/şifre tanımlı değil.")

    data = _http("POST", "/access_token", body={"email": cfg["email"], "password": cfg["password"]})
    if not isinstance(data, dict) or not data.get("access_token"):
        raise BlinkError("bl.ink giriş başarısız — email/şifreyi kontrol et.")

    token = data["access_token"]
    _token_cache["token"] = token
    _token_cache["fetched_at"] = now
    return token


def _authed_get(conn, path, params=None, retried=False):
    token = _get_access_token(conn)
    try:
        return _http("GET", path, token=token, params=params)
    except BlinkError:
        if not retried:
            _token_cache["token"] = None
            return _authed_get(conn, path, params=params, retried=True)
        raise


def fetch_domains(conn):
    data = _authed_get(conn, "/domains")
    objs = (data or {}).get("objects") if isinstance(data, dict) else None
    if not isinstance(objs, list):
        return []
    return [{"id": d.get("id"), "domain": d.get("domain") or ""} for d in objs if isinstance(d, dict)]


_REF_PARAM_NAMES = ("ref", "referral", "ref_code", "affid", "aff_id")


def _extract_ref_code(url):
    """Yönlendirme URL'sinden bizim tracker'ımızın okuduğu ?ref= parametresini çıkar."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
    except Exception:
        return ""
    for key, values in query.items():
        if key.lower() in _REF_PARAM_NAMES and values:
            return (values[0] or "").strip()
    return ""


def _extract_domain(url):
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        return (parsed.netloc or "").split(":")[0].strip().lower()
    except Exception:
        return ""


def fetch_links(conn, force=False):
    """Tüm domainlerdeki bl.ink kısa linklerini (redirect_url + ref_code dahil) döner."""
    now = datetime.now(timezone.utc)
    if not force and _links_cache["fetched_at"] and now - _links_cache["fetched_at"] < timedelta(seconds=_CACHE_SECONDS):
        return _links_cache["rows"], "cache"

    domains = fetch_domains(conn)
    rows = []
    for d in domains:
        domain_id = d.get("id")
        if domain_id is None:
            continue
        page = 1
        while True:
            data = _authed_get(conn, f"/{domain_id}/links", params={"page": page})
            if not isinstance(data, dict):
                break
            objs = data.get("objects") or []
            for link in objs:
                if not isinstance(link, dict):
                    continue
                redirect_url = link.get("redirect_url") or link.get("url") or ""
                ref_code = _extract_ref_code(redirect_url)
                dest_domain = _extract_domain(redirect_url)
                rows.append({
                    "link_id": str(link.get("id")),
                    "alias": link.get("alias") or "",
                    "short_link": link.get("short_link") or "",
                    "redirect_url": redirect_url,
                    "dest_domain": dest_domain,
                    "ref_code": ref_code,
                    "click_count": int(link.get("click_count") or 0),
                    "status": link.get("status") or "",
                    "notes": link.get("notes") or "",
                    "bl_domain": d.get("domain") or "",
                })
            meta = data.get("meta") or {}
            next_page = meta.get("next_page")
            if not next_page or next_page == page:
                break
            page = next_page

    rows.sort(key=lambda r: r["click_count"], reverse=True)
    _links_cache["fetched_at"] = now
    _links_cache["rows"] = rows
    return rows, "live"


def _normalize_key(text):
    text = (text or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def get_link_bindings(conn):
    rows = fetchall(conn, "SELECT * FROM blink_link_bindings ORDER BY created_at DESC")
    return [dict(r) for r in rows]


def get_link_bindings_map(conn):
    return {str(r["link_id"]): (r["domain"] or "", r["ref_code"] or "") for r in get_link_bindings(conn)}


def save_link_binding(conn, link_id, domain, ref_code):
    link_id = str(link_id or "").strip()
    domain = (domain or "").strip().lower()
    ref_code = (ref_code or "").strip()
    if not link_id:
        raise ValueError("link_id gerekli.")
    if not domain:
        raise ValueError("Domain gerekli.")
    now = iso(utcnow())
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO blink_link_bindings (link_id, domain, ref_code, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (link_id) DO UPDATE SET domain = EXCLUDED.domain, ref_code = EXCLUDED.ref_code
            """,
            (link_id, domain, ref_code, now),
        )
    else:
        execute(conn, "DELETE FROM blink_link_bindings WHERE link_id = ?", (link_id,))
        execute(
            conn,
            "INSERT INTO blink_link_bindings (link_id, domain, ref_code, created_at) VALUES (?, ?, ?, ?)",
            (link_id, domain, ref_code, now),
        )
    conn.commit()


def delete_link_binding(conn, link_id):
    execute(conn, "DELETE FROM blink_link_bindings WHERE link_id = ?", (str(link_id or "").strip(),))
    conn.commit()


def _fetch_online_map(conn):
    cutoff = iso(utcnow() - timedelta(seconds=_ONLINE_THRESHOLD_SECONDS))
    session_rows = fetchall(
        conn,
        "SELECT domain, ref_code, COUNT(*) AS cnt FROM visitor_sessions "
        "WHERE last_seen_at >= ? GROUP BY domain, ref_code",
        (cutoff,),
    )
    by_domain_ref = {}
    by_ref_norm = {}
    for r in session_rows:
        domain = (r["domain"] or "").strip().lower()
        ref_code = (r["ref_code"] or "").strip().lower()
        cnt = int(r["cnt"] or 0)
        by_domain_ref[(domain, ref_code)] = by_domain_ref.get((domain, ref_code), 0) + cnt
        norm = _normalize_key(ref_code)
        if norm:
            by_ref_norm[norm] = by_ref_norm.get(norm, 0) + cnt
    return {"by_domain_ref": by_domain_ref, "by_ref_norm": by_ref_norm}


def _attach_online_counts(conn, rows):
    bindings = get_link_bindings_map(conn)
    online_map = _fetch_online_map(conn)
    for row in rows:
        binding = bindings.get(str(row.get("link_id")))
        if binding:
            domain, ref_code = binding
            row["bind_domain"] = domain
            row["bind_ref_code"] = ref_code
            # Domain rotasyonlu oldugu icin (804 -> 805 -> 806 ...) once ref koduna
            # gore tum domainlerdeki toplami ariyoruz, sadece bulunamazsa domain'e
            # kilitli eski davranisa dusuyoruz.
            norm = _normalize_key(ref_code)
            online = online_map["by_ref_norm"].get(norm)
            if online is None:
                online = online_map["by_domain_ref"].get((domain.lower(), ref_code.lower()), 0)
            row["online_now"] = online
            row["online_source"] = "manual"
            continue
        row["bind_domain"] = None
        row["bind_ref_code"] = None
        ref_code = (row.get("ref_code") or "").strip().lower()
        dest_domain = (row.get("dest_domain") or "").strip().lower()
        if ref_code:
            online = online_map["by_domain_ref"].get((dest_domain, ref_code))
            if online is None:
                norm = _normalize_key(ref_code)
                online = online_map["by_ref_norm"].get(norm)
            row["online_now"] = online if online is not None else 0
            row["online_source"] = "url"
        else:
            row["online_now"] = None
            row["online_source"] = None
    return rows


def fetch_links_with_online(conn, force=False):
    cfg = get_config(conn)
    if not cfg["email"] or not cfg["password"]:
        return {"rows": [], "error": "not_configured", "source": None}
    try:
        rows, source = fetch_links(conn, force=force)
    except BlinkError as exc:
        cached = _links_cache["rows"]
        if cached:
            rows = _attach_online_counts(conn, [dict(r) for r in cached])
            return {"rows": rows, "error": str(exc), "source": "cache"}
        return {"rows": [], "error": str(exc), "source": None}
    rows = _attach_online_counts(conn, [dict(r) for r in rows])
    return {"rows": rows, "error": None, "source": source}
