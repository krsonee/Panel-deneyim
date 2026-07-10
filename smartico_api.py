"""Smartico (TheAffiliatePlatform) Reporting API entegrasyonu.

Link Takip modülünün mevcut (kendi tracker.js tabanlı) sistemine ek olarak,
operatörün Smartico affiliate panelindeki linklerin performansını (ziyaret,
kayıt, yatırım, komisyon) göstermek için kullanılır. Bağımsız bir katmandır;
mevcut tracked_links / visitor_sessions sistemini değiştirmez.
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
    get_smartico_setting,
    iso,
    upsert_smartico_setting,
    uses_postgres,
    utcnow,
)

DEFAULT_API_HOST = "https://boapi.smartico.ai"

_SETTING_API_KEY = "api_key"
_SETTING_API_HOST = "api_host"

_HTTP_TIMEOUT = 8

# Kendi tracker.js sistemimizde bir ziyaretçi bu kadar saniye içinde
# heartbeat göndermişse "online" sayılır (app.py ile aynı eşik).
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

# Kısa süreli bellek içi önbellek — panel her 30 sn'de bir yenilediği için
# Smartico tarafına gereksiz yük binmesin.
_report_cache = {}
_aff_cache = {"fetched_at": None, "data": {}}
_CACHE_SECONDS = 45
_AFF_CACHE_SECONDS = 300


def get_config(conn):
    key = (get_smartico_setting(conn, _SETTING_API_KEY, "") or "").strip()
    host = (get_smartico_setting(conn, _SETTING_API_HOST, "") or "").strip() or DEFAULT_API_HOST
    return {"api_key": key, "api_host": host}


def is_configured(conn):
    return bool(get_config(conn)["api_key"])


def mask_key(key):
    key = key or ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "…" + key[-4:]


def save_config(conn, api_key, api_host):
    api_key = (api_key or "").strip()
    api_host = (api_host or "").strip().rstrip("/") or DEFAULT_API_HOST
    upsert_smartico_setting(conn, _SETTING_API_KEY, api_key)
    upsert_smartico_setting(conn, _SETTING_API_HOST, api_host)
    _report_cache.clear()
    _aff_cache["fetched_at"] = None
    _aff_cache["data"] = {}
    return get_config(conn)


def clear_config(conn):
    upsert_smartico_setting(conn, _SETTING_API_KEY, "")
    _report_cache.clear()


class SmarticoError(Exception):
    pass


def _normalize_key(text):
    """Karşılaştırma için: küçük harf, boşluk/tire/alt çizgi vs. temizlenmiş hâli."""
    text = (text or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def get_link_bindings(conn):
    rows = fetchall(conn, "SELECT * FROM smartico_link_bindings ORDER BY created_at DESC")
    return [dict(r) for r in rows]


def get_link_bindings_map(conn):
    """(affiliate_id, link_id) -> (domain, ref_code) eşlemesi."""
    result = {}
    for row in get_link_bindings(conn):
        key = (str(row.get("affiliate_id") or ""), str(row.get("link_id") or ""))
        result[key] = (row.get("domain") or "", row.get("ref_code") or "")
    return result


def save_link_binding(conn, affiliate_id, link_id, domain, ref_code):
    affiliate_id = str(affiliate_id or "").strip()
    link_id = str(link_id or "").strip()
    domain = (domain or "").strip().lower()
    ref_code = (ref_code or "").strip()
    if not domain:
        raise ValueError("Domain gerekli.")
    now = iso(utcnow())
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO smartico_link_bindings (affiliate_id, link_id, domain, ref_code, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (affiliate_id, link_id) DO UPDATE
                SET domain = EXCLUDED.domain, ref_code = EXCLUDED.ref_code
            """,
            (affiliate_id, link_id, domain, ref_code, now),
        )
    else:
        execute(
            conn,
            "DELETE FROM smartico_link_bindings WHERE affiliate_id = ? AND link_id = ?",
            (affiliate_id, link_id),
        )
        execute(
            conn,
            """
            INSERT INTO smartico_link_bindings (affiliate_id, link_id, domain, ref_code, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (affiliate_id, link_id, domain, ref_code, now),
        )
    conn.commit()


def delete_link_binding(conn, affiliate_id, link_id):
    execute(
        conn,
        "DELETE FROM smartico_link_bindings WHERE affiliate_id = ? AND link_id = ?",
        (str(affiliate_id or "").strip(), str(link_id or "").strip()),
    )
    conn.commit()


def _fetch_online_map(conn):
    """Kendi tracker sistemimizden anlık online sayıları çıkar.

    Dönüş:
      by_domain_ref: {(domain, ref_code): online_count}  -> manuel eşleşmeler için
      by_norm_key:   {normalize(ref_code veya label): online_count} -> otomatik ad eşleşmesi için
    """
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

    link_rows = fetchall(conn, "SELECT domain, ref_code, label FROM tracked_links")
    by_label_norm = {}
    for r in link_rows:
        label = (r["label"] or "").strip()
        if not label:
            continue
        domain = (r["domain"] or "").strip().lower()
        ref_code = (r["ref_code"] or "").strip().lower()
        cnt = by_domain_ref.get((domain, ref_code), 0)
        norm = _normalize_key(label)
        if norm:
            by_label_norm[norm] = by_label_norm.get(norm, 0) + cnt

    return {"by_domain_ref": by_domain_ref, "by_ref_norm": by_ref_norm, "by_label_norm": by_label_norm}


def _attach_online_counts(conn, rows):
    bindings = get_link_bindings_map(conn)
    online_map = _fetch_online_map(conn)
    for row in rows:
        key = (str(row.get("affiliate_id") or ""), str(row.get("link_id") or ""))
        binding = bindings.get(key)
        if binding:
            domain, ref_code = binding
            row["bind_domain"] = domain
            row["bind_ref_code"] = ref_code
            # Domain'e gore kesin eslesme aramiyoruz cunku site domaini rotasyonlu
            # (804 -> 805 -> 806 ...). Referans kodu sabit kaldigi surece, hangi
            # rotasyonlu domain'e dustugu onemli degil; tum domainlerdeki toplami aliyoruz.
            norm = _normalize_key(ref_code)
            online = online_map["by_ref_norm"].get(norm)
            if online is None:
                online = online_map["by_domain_ref"].get((domain.lower(), ref_code.lower()), 0)
            row["online_now"] = online
            row["online_source"] = "manual"
            continue
        row["bind_domain"] = None
        row["bind_ref_code"] = None
        # Öncelik: Smartico'nun linki yönlendirirken kullandığı ?affid=<affiliate_id> parametresi
        # (bizim tracker.js artık bunu ref_code olarak kaydediyor) — isim tahmininden çok daha kesin.
        affiliate_id = row.get("affiliate_id")
        candidates = []
        if affiliate_id is not None:
            candidates.append(str(affiliate_id))
        candidates.append(row.get("affiliate_name") or "")
        candidates.append(row.get("link_name") or "")
        online = None
        for cand in candidates:
            norm = _normalize_key(cand)
            if not norm:
                continue
            if norm in online_map["by_ref_norm"]:
                online = online_map["by_ref_norm"][norm]
                break
            if norm in online_map["by_label_norm"]:
                online = online_map["by_label_norm"][norm]
                break
        row["online_now"] = online
        row["online_source"] = "auto" if online is not None else None
    return rows


def _request(host, path, api_key, params=None):
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{host.rstrip('/')}/api/{path}{query}"
    req = urllib.request.Request(url, headers={"authorization": api_key, "User-Agent": "MakroPanel/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        if exc.code in (401, 403):
            raise SmarticoError("API anahtarı geçersiz veya yetkisiz (401/403). Anahtarı kontrol et.") from exc
        raise SmarticoError(f"Smartico API hata verdi ({exc.code}): {detail or exc.reason}") from exc
    except _FETCH_ERRORS as exc:
        raise SmarticoError(f"Smartico API'ye bağlanılamadı: {exc}") from exc
    try:
        return json.loads(body) if body else None
    except json.JSONDecodeError as exc:
        raise SmarticoError("Smartico API beklenmeyen bir cevap döndürdü.") from exc


def date_range_from_period(period):
    """Panelin ortak period parametresiyle aynı sözleşme (today/yesterday/7days/30days/all)."""
    now = datetime.now(timezone.utc)
    today = now.date()
    if period == "today":
        return today, today + timedelta(days=1)
    if period == "yesterday":
        y = today - timedelta(days=1)
        return y, today
    if period == "7days":
        return today - timedelta(days=6), today + timedelta(days=1)
    if period == "30days":
        return today - timedelta(days=29), today + timedelta(days=1)
    if period == "6months":
        return today - timedelta(days=182), today + timedelta(days=1)
    return None, None


def fetch_affiliate_names(conn, force=False):
    """affiliate_id -> affiliate_name eşlemesi. Performans için önbelleklenir."""
    now = datetime.now(timezone.utc)
    if (
        not force
        and _aff_cache["fetched_at"]
        and now - _aff_cache["fetched_at"] < timedelta(seconds=_AFF_CACHE_SECONDS)
    ):
        return _aff_cache["data"]

    cfg = get_config(conn)
    if not cfg["api_key"]:
        return {}
    try:
        data = _request(
            cfg["api_host"], "af2_aff_op", cfg["api_key"],
            {"filter": json.dumps({"without_money": True})},
        )
    except SmarticoError:
        return _aff_cache["data"] or {}
    if not isinstance(data, list):
        return _aff_cache["data"] or {}
    mapping = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        aid = row.get("affiliate_id") or row.get("id")
        if aid is None:
            continue
        name = row.get("affiliate_name") or row.get("username") or f"Affiliate #{aid}"
        mapping[str(aid)] = name
    _aff_cache["fetched_at"] = now
    _aff_cache["data"] = mapping
    return mapping


def fetch_media_report(conn, period="all", force=False):
    """Link/kanal bazlı ziyaret, kayıt, yatırım, komisyon raporu.

    Dönüş: {"rows": [...], "summary": {...}, "error": None|str, "source": "live"|"cache"}
    """
    cfg = get_config(conn)
    if not cfg["api_key"]:
        return {"rows": [], "summary": _empty_summary(), "error": "not_configured", "source": None}

    cache_key = period
    now = datetime.now(timezone.utc)
    cached = _report_cache.get(cache_key)
    if not force and cached and now - cached["fetched_at"] < timedelta(seconds=_CACHE_SECONDS):
        payload = {**cached["payload"]}
        payload["rows"] = _attach_online_counts(conn, [dict(r) for r in payload["rows"]])
        return {**payload, "source": "cache"}

    params = {"group_by": "affiliate_id,link_id"}
    date_from, date_to = date_range_from_period(period)
    if date_from and date_to:
        params["date_from"] = date_from.isoformat()
        params["date_to"] = date_to.isoformat()

    try:
        data = _request(cfg["api_host"], "af2_media_report_op", cfg["api_key"], params)
    except SmarticoError as exc:
        if cached:
            payload = {**cached["payload"]}
            payload["rows"] = _attach_online_counts(conn, [dict(r) for r in payload["rows"]])
            return {**payload, "source": "cache", "error": str(exc)}
        return {"rows": [], "summary": _empty_summary(), "error": str(exc), "source": None}

    if not isinstance(data, dict):
        msg = "Smartico API beklenmeyen bir cevap döndürdü (API anahtarını kontrol et)."
        if isinstance(data, str) and data.strip():
            msg = f"Smartico API hatası: {data.strip()}"
        if cached:
            payload = {**cached["payload"]}
            payload["rows"] = _attach_online_counts(conn, [dict(r) for r in payload["rows"]])
            return {**payload, "source": "cache", "error": msg}
        return {"rows": [], "summary": _empty_summary(), "error": msg, "source": None}

    aff_names = fetch_affiliate_names(conn)
    rows_raw = data.get("data") or []
    if not isinstance(rows_raw, list):
        rows_raw = []
    merged = {}
    for r in rows_raw:
        if not isinstance(r, dict):
            continue
        aff_id = r.get("affiliate_id")
        link_id = r.get("link_id")
        key = (aff_id, link_id)
        if key not in merged:
            merged[key] = {
                "affiliate_id": aff_id,
                "affiliate_name": aff_names.get(str(aff_id)) if aff_id is not None else None,
                "link_id": link_id,
                "link_name": r.get("link_name") or "",
                "brand_name": r.get("brand_name") or "",
                "visit_count": 0,
                "registration_count": 0,
                "ftd_count": 0,
                "ftd_total": 0.0,
                "deposit_count": 0,
                "deposit_total": 0.0,
                "commissions_total": 0.0,
                "balance": 0.0,
            }
        m = merged[key]
        m["visit_count"] += _num(r.get("visit_count"))
        m["registration_count"] += _num(r.get("registration_count"))
        m["ftd_count"] += _num(r.get("ftd_count"))
        m["ftd_total"] += _num(r.get("ftd_total"))
        m["deposit_count"] += _num(r.get("deposit_count"))
        m["deposit_total"] += _num(r.get("deposit_total"))
        m["commissions_total"] += _num(r.get("commissions_total"))
        m["balance"] += _num(r.get("balance"))

    rows = sorted(merged.values(), key=lambda x: x["visit_count"], reverse=True)
    for row in rows:
        for f in ("ftd_total", "deposit_total", "commissions_total", "balance"):
            row[f] = round(row[f], 2)

    summary = _empty_summary()
    for row in rows:
        summary["visit_count"] += row["visit_count"]
        summary["registration_count"] += row["registration_count"]
        summary["ftd_count"] += row["ftd_count"]
        summary["deposit_count"] += row["deposit_count"]
        summary["deposit_total"] += row["deposit_total"]
        summary["commissions_total"] += row["commissions_total"]
    summary["deposit_total"] = round(summary["deposit_total"], 2)
    summary["commissions_total"] = round(summary["commissions_total"], 2)

    meta = (data or {}).get("meta") or {}
    payload = {
        "rows": rows,
        "summary": summary,
        "error": None,
        "currency": meta.get("operator_currency") or "",
    }
    _report_cache[cache_key] = {"fetched_at": now, "payload": payload}
    live_payload = {**payload, "rows": _attach_online_counts(conn, [dict(r) for r in rows])}
    return {**live_payload, "source": "live"}


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _empty_summary():
    return {
        "visit_count": 0,
        "registration_count": 0,
        "ftd_count": 0,
        "deposit_count": 0,
        "deposit_total": 0.0,
        "commissions_total": 0.0,
    }
