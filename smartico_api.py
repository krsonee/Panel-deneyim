"""Smartico (TheAffiliatePlatform) Reporting API entegrasyonu.

Link Takip modülünün mevcut (kendi tracker.js tabanlı) sistemine ek olarak,
operatörün Smartico affiliate panelindeki linklerin performansını (ziyaret,
kayıt, yatırım, komisyon) göstermek için kullanılır. Bağımsız bir katmandır;
mevcut tracked_links / visitor_sessions sistemini değiştirmez.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.client import RemoteDisconnected

from database import get_smartico_setting, upsert_smartico_setting

DEFAULT_API_HOST = "https://boapi.smartico.ai"

_SETTING_API_KEY = "api_key"
_SETTING_API_HOST = "api_host"

_HTTP_TIMEOUT = 8

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
        return {**cached["payload"], "source": "cache"}

    params = {"group_by": "affiliate_id,link_id"}
    date_from, date_to = date_range_from_period(period)
    if date_from and date_to:
        params["date_from"] = date_from.isoformat()
        params["date_to"] = date_to.isoformat()

    try:
        data = _request(cfg["api_host"], "af2_media_report_op", cfg["api_key"], params)
    except SmarticoError as exc:
        if cached:
            return {**cached["payload"], "source": "cache", "error": str(exc)}
        return {"rows": [], "summary": _empty_summary(), "error": str(exc), "source": None}

    if not isinstance(data, dict):
        msg = "Smartico API beklenmeyen bir cevap döndürdü (API anahtarını kontrol et)."
        if isinstance(data, str) and data.strip():
            msg = f"Smartico API hatası: {data.strip()}"
        if cached:
            return {**cached["payload"], "source": "cache", "error": msg}
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
    return {**payload, "source": "live"}


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
