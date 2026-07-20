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
DEFAULT_INT_API_BASE = "https://go.aff.makroaffi.com"
# Eski yanlış default (DNS yok) → otomatik düzelt
_LEGACY_INT_API_BASES = frozenset({
    "https://api.aff.makroaffi.com",
    "http://api.aff.makroaffi.com",
    "api.aff.makroaffi.com",
})

_SETTING_API_KEY = "api_key"
_SETTING_API_HOST = "api_host"
_SETTING_INT_API_BASE = "int_api_base"
_SETTING_INT_AUTH_TOKEN = "int_authorization_token"
_SETTING_LABEL_ID = "label_id"
_SETTING_BRAND_ID = "brand_id"
_SETTING_DEFAULT_AFFILIATE_ID = "default_affiliate_id"

_HTTP_TIMEOUT = 8
_INT_HTTP_TIMEOUT = 20
_MOVE_AFFILIATE_CID = 30062
_MOVE_AFFILIATE_RESP_CID = 30063

# int-api JWT bellek önbelleği (process ömrü)
_int_jwt = {"token": None, "expires_at": None, "label_id": None}

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
_player_cache = {}
_aff_cache = {"fetched_at": None, "data": {}}
_CACHE_SECONDS = 45
_PLAYER_CACHE_SECONDS = 90
_AFF_CACHE_SECONDS = 300
_PLAYER_HTTP_TIMEOUT = 45


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
    _player_cache.clear()
    _aff_cache["fetched_at"] = None
    _aff_cache["data"] = {}
    return get_config(conn)


def clear_config(conn):
    upsert_smartico_setting(conn, _SETTING_API_KEY, "")
    _report_cache.clear()
    _player_cache.clear()


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
      by_ref_norm:   {normalize(ref_code): online_count} -> şu an gerçekten online olanlar
      by_label_norm: {normalize(label): online_count}    -> tracked_links etiketi eşleşmesi
      known_ref_norm: {normalize(ref_code), ...}          -> şu an online olmasa da HİÇ görülmüş kodlar
                       (bu olmadan, kanaldan şu an kimse yoksa "eşleşmedi" ile "hiç görülmedi"
                       ayırt edilemiyor, tüm sessiz kanallar yanlışlıkla "Eşleştir" gösteriyordu)
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

    known_rows = fetchall(
        conn,
        "SELECT DISTINCT ref_code FROM visitor_sessions WHERE ref_code IS NOT NULL AND ref_code != ''",
    )
    known_ref_norm = set()
    for r in known_rows:
        norm = _normalize_key(r["ref_code"] or "")
        if norm:
            known_ref_norm.add(norm)

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

    return {
        "by_domain_ref": by_domain_ref,
        "by_ref_norm": by_ref_norm,
        "by_label_norm": by_label_norm,
        "known_ref_norm": known_ref_norm,
    }


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
            if norm in online_map["known_ref_norm"]:
                # Bu koddan biri var ama şu an (son 90sn) online değil -> 0, "Eşleştir" değil.
                online = 0
                break
        row["online_now"] = online
        row["online_source"] = "auto" if online is not None else None
    return rows


def _request(host, path, api_key, params=None, timeout=None):
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{host.rstrip('/')}/api/{path}{query}"
    req = urllib.request.Request(url, headers={"authorization": api_key, "User-Agent": "MakroPanel/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout or _HTTP_TIMEOUT) as resp:
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


_CUSTOM_PERIOD_RE = re.compile(r"^custom:(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$")


def date_range_from_period(period):
    """Panelin ortak period parametresiyle aynı sözleşme (today/yesterday/7days/30days/all/custom:.../...)."""
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
    match = _CUSTOM_PERIOD_RE.match(period or "")
    if match:
        try:
            start = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            end = datetime.strptime(match.group(2), "%Y-%m-%d").date()
        except ValueError:
            return None, None
        if start > end:
            start, end = end, start
        return start, min(end + timedelta(days=1), today + timedelta(days=1))
    return None, None


# TAP AffiliateStatus: Pending=1 Approved=2 Declined=3 Suspended=4 ViewOnly=5 Blocked=6/7
AFF_STATUS_APPROVED = 2
AFF_STATUS_SUSPENDED = 4


def fetch_affiliates_raw(conn, status_ids=None, force=False):
    """Ham affiliate listesi. status_ids örn. [2] = Approved (Suspended hariç için [2] kullan)."""
    cfg = get_config(conn)
    if not cfg["api_key"]:
        return []
    filt = {"without_money": True}
    if status_ids:
        filt["aff_status_id"] = list(status_ids)
    cache_key = json.dumps(filt, sort_keys=True)
    now = datetime.now(timezone.utc)
    cached = _aff_cache.get("raw", {}).get(cache_key)
    if (
        not force
        and cached
        and now - cached["fetched_at"] < timedelta(seconds=_AFF_CACHE_SECONDS)
    ):
        return cached["data"]
    try:
        data = _request(
            cfg["api_host"], "af2_aff_op", cfg["api_key"],
            {"filter": json.dumps(filt)},
        )
    except SmarticoError:
        return (cached or {}).get("data") or []
    if not isinstance(data, list):
        return (cached or {}).get("data") or []
    rows = [row for row in data if isinstance(row, dict)]
    _aff_cache.setdefault("raw", {})[cache_key] = {"fetched_at": now, "data": rows}
    return rows


def fetch_affiliate_names(conn, force=False):
    """affiliate_id -> affiliate_name eşlemesi. Performans için önbelleklenir."""
    now = datetime.now(timezone.utc)
    if (
        not force
        and _aff_cache["fetched_at"]
        and now - _aff_cache["fetched_at"] < timedelta(seconds=_AFF_CACHE_SECONDS)
        and _aff_cache.get("data")
    ):
        return _aff_cache["data"]

    rows = fetch_affiliates_raw(conn, status_ids=None, force=force)
    mapping = {}
    for row in rows:
        aid = row.get("affiliate_id") or row.get("id")
        if aid is None:
            continue
        name = row.get("affiliate_name") or row.get("username") or f"Affiliate #{aid}"
        mapping[str(aid)] = name
    _aff_cache["fetched_at"] = now
    _aff_cache["data"] = mapping
    return mapping


def fetch_affiliate_home_deal_id(conn, affiliate_id):
    """Affiliate'in home/default deal_id'sini getir (af2_deals_op).

    TAP move sadece affiliate_id ile çoğu zaman ConstraintViolation verir;
    home deal_id ile taşınması gerekir.
    """
    cfg = get_config(conn)
    if not cfg["api_key"]:
        return None
    try:
        aid = int(affiliate_id)
    except (TypeError, ValueError):
        return None
    try:
        data = _request(
            cfg["api_host"],
            "af2_deals_op",
            cfg["api_key"],
            {"affiliate_id": str(aid)},
            timeout=15,
        )
    except SmarticoError:
        return None
    rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)
    if not isinstance(rows, list) or not rows:
        return None
    default_row = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_default") is True or row.get("is_default") == 1:
            default_row = row
            break
    pick = default_row or (rows[0] if isinstance(rows[0], dict) else None)
    if not pick:
        return None
    deal = pick.get("deal_id") or pick.get("id")
    try:
        return int(deal) if deal is not None else None
    except (TypeError, ValueError):
        return None

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
                "withdrawal_count": 0,
                "withdrawal_total": 0.0,
                "commissions_total": 0.0,
                "bonus_total": 0.0,
                "balance": 0.0,
            }
        m = merged[key]
        m["visit_count"] += _num(r.get("visit_count"))
        m["registration_count"] += _num(r.get("registration_count"))
        m["ftd_count"] += _num(r.get("ftd_count"))
        m["ftd_total"] += _num(r.get("ftd_total"))
        m["deposit_count"] += _num(r.get("deposit_count"))
        m["deposit_total"] += _num(r.get("deposit_total"))
        m["withdrawal_count"] += _num(r.get("withdrawal_count"))
        m["withdrawal_total"] += _num(r.get("withdrawal_total"))
        m["commissions_total"] += _num(r.get("commissions_total"))
        # bonus_amount = oyunculara/uyelere verilen bonus tutari (adjustments alani
        # affiliate komisyon duzeltmesidir, bonusla ilgisi yok - onceki hatali versiyon onu kullaniyordu)
        m["bonus_total"] += _num(r.get("bonus_amount"))
        m["balance"] += _num(r.get("balance"))

    rows = sorted(merged.values(), key=lambda x: x["visit_count"], reverse=True)
    for row in rows:
        for f in ("ftd_total", "deposit_total", "withdrawal_total", "commissions_total", "bonus_total", "balance"):
            row[f] = round(row[f], 2)

    summary = _empty_summary()
    for row in rows:
        summary["visit_count"] += row["visit_count"]
        summary["registration_count"] += row["registration_count"]
        summary["ftd_count"] += row["ftd_count"]
        summary["deposit_count"] += row["deposit_count"]
        summary["deposit_total"] += row["deposit_total"]
        summary["withdrawal_count"] += row["withdrawal_count"]
        summary["withdrawal_total"] += row["withdrawal_total"]
        summary["commissions_total"] += row["commissions_total"]
        summary["bonus_total"] += row["bonus_total"]
    summary["deposit_total"] = round(summary["deposit_total"], 2)
    summary["withdrawal_total"] = round(summary["withdrawal_total"], 2)
    summary["commissions_total"] = round(summary["commissions_total"], 2)
    summary["bonus_total"] = round(summary["bonus_total"], 2)

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


def fetch_subid_conversions(conn, affiliate_id, subid_param, force=False):
    """Belirli bir affiliate hesabının linkinde, sub-id (afp1..afp9) bazında
    kayıt/FTD/yatırım rakamlarını döner — her satır tek bir sub-id değerine
    (bizde: mail contact_id) karşılık gelir.

    Dönüş: {"rows": [{"subid": "123", "registration_count", "ftd_count",
             "deposit_count", "deposit_total", ...}], "error": None|str}
    """
    cfg = get_config(conn)
    if not cfg["api_key"]:
        return {"rows": [], "error": "not_configured"}
    affiliate_id = str(affiliate_id or "").strip()
    subid_param = (subid_param or "afp1").strip() or "afp1"
    if not affiliate_id:
        return {"rows": [], "error": "affiliate_id_missing"}

    params = {"group_by": subid_param, "affiliate_id": affiliate_id}
    try:
        data = _request(cfg["api_host"], "af2_media_report_op", cfg["api_key"], params)
    except SmarticoError as exc:
        return {"rows": [], "error": str(exc)}

    if not isinstance(data, dict):
        msg = "Smartico API beklenmeyen bir cevap döndürdü."
        if isinstance(data, str) and data.strip():
            msg = f"Smartico API hatası: {data.strip()}"
        return {"rows": [], "error": msg}

    rows_raw = data.get("data") or []
    if not isinstance(rows_raw, list):
        rows_raw = []
    merged = {}
    for r in rows_raw:
        if not isinstance(r, dict):
            continue
        subid = str(r.get(subid_param) or "").strip()
        if not subid:
            continue
        if subid not in merged:
            merged[subid] = {
                "subid": subid,
                "visit_count": 0,
                "registration_count": 0,
                "ftd_count": 0,
                "ftd_total": 0.0,
                "deposit_count": 0,
                "deposit_total": 0.0,
                "withdrawal_count": 0,
                "withdrawal_total": 0.0,
                "bonus_total": 0.0,
            }
        m = merged[subid]
        m["visit_count"] += _num(r.get("visit_count"))
        m["registration_count"] += _num(r.get("registration_count"))
        m["ftd_count"] += _num(r.get("ftd_count"))
        m["ftd_total"] += _num(r.get("ftd_total"))
        m["deposit_count"] += _num(r.get("deposit_count"))
        m["deposit_total"] += _num(r.get("deposit_total"))
        m["withdrawal_count"] += _num(r.get("withdrawal_count"))
        m["withdrawal_total"] += _num(r.get("withdrawal_total"))
        m["bonus_total"] += _num(r.get("bonus_amount"))

    rows = sorted(merged.values(), key=lambda x: x["subid"])
    for row in rows:
        for f in ("ftd_total", "deposit_total", "withdrawal_total", "bonus_total"):
            row[f] = round(row[f], 2)
    return {"rows": rows, "error": None}


def _empty_player_row(subid_param, r=None):
    r = r or {}
    subid = str(r.get(subid_param) or "").strip()
    return {
        "subid": subid,
        "username": str(r.get("username") or "").strip(),
        "registration_id": str(r.get("registration_id") or "").strip(),
        "ext_customer_id": str(r.get("ext_customer_id") or "").strip(),
        "visit_count": 0,
        "registration_count": 0,
        "ftd_count": 0,
        "ftd_total": 0.0,
        "deposit_count": 0,
        "deposit_total": 0.0,
        "withdrawal_count": 0,
        "withdrawal_total": 0.0,
        "bonus_total": 0.0,
        "commissions_total": 0.0,
        "net_deposit_total": 0.0,
    }


def _merge_player_metrics(target, src):
    target["visit_count"] += _num(src.get("visit_count"))
    target["registration_count"] += _num(src.get("registration_count"))
    target["ftd_count"] += _num(src.get("ftd_count"))
    target["ftd_total"] += _num(src.get("ftd_total"))
    target["deposit_count"] += _num(src.get("deposit_count"))
    target["deposit_total"] += _num(src.get("deposit_total"))
    target["withdrawal_count"] += _num(src.get("withdrawal_count"))
    target["withdrawal_total"] += _num(src.get("withdrawal_total"))
    target["bonus_total"] += _num(src.get("bonus_amount"))
    target["commissions_total"] += _num(src.get("commissions_total"))
    target["net_deposit_total"] += _num(src.get("net_deposit_total") or src.get("net_deposits"))
    if not target.get("username") and src.get("username"):
        target["username"] = str(src.get("username") or "").strip()
    if not target.get("registration_id") and src.get("registration_id"):
        target["registration_id"] = str(src.get("registration_id") or "").strip()
    if not target.get("ext_customer_id") and src.get("ext_customer_id"):
        target["ext_customer_id"] = str(src.get("ext_customer_id") or "").strip()


def fetch_mailing_players(conn, affiliate_id, subid_param="afp1", period="30days", force=False):
    """Mailing aff linkinden gelen oyuncu bazlı kayıt/yatırım/çekim/bonus raporu.

    group_by: username + registration_id + ext_customer_id + sub-id (afp1).
    Registrations report yetkisi yoksa kademeli düşer (username+subid → sadece subid).

    Dönüş: {rows, summary, currency, error, source, group_by}
    """
    cfg = get_config(conn)
    if not cfg["api_key"]:
        return {
            "rows": [], "summary": _empty_player_summary(), "currency": "",
            "error": "not_configured", "source": None, "group_by": None,
        }
    affiliate_id = str(affiliate_id or "").strip()
    subid_param = (subid_param or "afp1").strip() or "afp1"
    if not affiliate_id:
        return {
            "rows": [], "summary": _empty_player_summary(), "currency": "",
            "error": "affiliate_id_missing", "source": None, "group_by": None,
        }

    cache_key = f"{affiliate_id}|{subid_param}|{period or 'all'}"
    now = datetime.now(timezone.utc)
    cached = _player_cache.get(cache_key)
    if not force and cached and now - cached["fetched_at"] < timedelta(seconds=_PLAYER_CACHE_SECONDS):
        payload = {**cached["payload"], "rows": [dict(r) for r in cached["payload"]["rows"]]}
        return {**payload, "source": "cache"}

    group_attempts = [
        f"username,registration_id,ext_customer_id,{subid_param}",
        f"username,{subid_param}",
        subid_param,
    ]
    date_from, date_to = date_range_from_period(period)
    last_error = None
    data = None
    used_group = None

    for group_by in group_attempts:
        params = {"group_by": group_by, "affiliate_id": affiliate_id}
        if date_from and date_to:
            params["date_from"] = date_from.isoformat()
            params["date_to"] = date_to.isoformat()
        try:
            data = _request(
                cfg["api_host"], "af2_media_report_op", cfg["api_key"], params,
                timeout=_PLAYER_HTTP_TIMEOUT,
            )
        except SmarticoError as exc:
            last_error = str(exc)
            data = None
            continue
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            used_group = group_by
            break
        if isinstance(data, str) and data.strip():
            last_error = f"Smartico API hatası: {data.strip()}"
        else:
            last_error = "Smartico API beklenmeyen bir cevap döndürdü."
        data = None

    if data is None:
        if cached:
            payload = {**cached["payload"], "rows": [dict(r) for r in cached["payload"]["rows"]]}
            return {**payload, "source": "cache", "error": last_error}
        return {
            "rows": [], "summary": _empty_player_summary(), "currency": "",
            "error": last_error or "Smartico oyuncu raporu alınamadı",
            "source": None, "group_by": None,
        }

    rows_raw = data.get("data") or []
    if not isinstance(rows_raw, list):
        rows_raw = []
    merged = {}
    for r in rows_raw:
        if not isinstance(r, dict):
            continue
        subid = str(r.get(subid_param) or "").strip()
        username = str(r.get("username") or "").strip()
        reg_id = str(r.get("registration_id") or "").strip()
        ext_id = str(r.get("ext_customer_id") or "").strip()
        # Sadece ziyaret (kayıt yok) ve subid boş satırları atla — gürültü
        if not subid and not username and not reg_id and not ext_id:
            continue
        if (
            _num(r.get("registration_count")) <= 0
            and _num(r.get("ftd_count")) <= 0
            and _num(r.get("deposit_count")) <= 0
            and _num(r.get("withdrawal_count")) <= 0
            and not username
        ):
            continue
        key = "|".join([
            username or "",
            reg_id or "",
            ext_id or "",
            subid or "",
        ])
        if not any(key.split("|")):
            continue
        if key not in merged:
            merged[key] = _empty_player_row(subid_param, r)
        _merge_player_metrics(merged[key], r)

    rows = list(merged.values())
    for row in rows:
        for f in ("ftd_total", "deposit_total", "withdrawal_total", "bonus_total",
                  "commissions_total", "net_deposit_total"):
            row[f] = round(row[f], 2)
    rows.sort(key=lambda x: (x.get("deposit_total") or 0, x.get("ftd_total") or 0), reverse=True)

    summary = _empty_player_summary()
    for row in rows:
        summary["players"] += 1
        if row.get("registration_count", 0) > 0 or row.get("username") or row.get("registration_id"):
            summary["registered"] += 1
        summary["ftd_count"] += int(row.get("ftd_count") or 0)
        summary["deposit_total"] += row.get("deposit_total") or 0
        summary["withdrawal_total"] += row.get("withdrawal_total") or 0
        summary["bonus_total"] += row.get("bonus_total") or 0
        summary["ftd_total"] += row.get("ftd_total") or 0
    for f in ("deposit_total", "withdrawal_total", "bonus_total", "ftd_total"):
        summary[f] = round(summary[f], 2)

    meta = (data or {}).get("meta") or {}
    payload = {
        "rows": rows,
        "summary": summary,
        "currency": meta.get("operator_currency") or "",
        "error": None,
        "group_by": used_group,
    }
    _player_cache[cache_key] = {"fetched_at": now, "payload": payload}
    return {**payload, "rows": [dict(r) for r in rows], "source": "live"}


def _empty_player_summary():
    return {
        "players": 0,
        "registered": 0,
        "ftd_count": 0,
        "ftd_total": 0.0,
        "deposit_total": 0.0,
        "withdrawal_total": 0.0,
        "bonus_total": 0.0,
    }


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
        "withdrawal_count": 0,
        "withdrawal_total": 0.0,
        "commissions_total": 0.0,
        "bonus_total": 0.0,
    }


# ---------------------------------------------------------------------------
# TAP int-api — AFF_MOVE_AFFILIATE (cid 30062)
# Raporlama (boapi) anahtarından ayrı: authorization_token + label_id + JWT
# ---------------------------------------------------------------------------


def _normalize_int_api_base(base):
    base = (base or "").strip().rstrip("/")
    if not base or base in _LEGACY_INT_API_BASES:
        return DEFAULT_INT_API_BASE
    return base


def get_int_config(conn):
    base = _normalize_int_api_base(get_smartico_setting(conn, _SETTING_INT_API_BASE, ""))
    token = (get_smartico_setting(conn, _SETTING_INT_AUTH_TOKEN, "") or "").strip()
    label_raw = (get_smartico_setting(conn, _SETTING_LABEL_ID, "") or "").strip()
    brand_raw = (get_smartico_setting(conn, _SETTING_BRAND_ID, "") or "").strip()
    default_aff_raw = (get_smartico_setting(conn, _SETTING_DEFAULT_AFFILIATE_ID, "") or "").strip()
    try:
        label_id = int(label_raw) if label_raw else None
    except (TypeError, ValueError):
        label_id = None
    try:
        brand_id = int(brand_raw) if brand_raw else None
    except (TypeError, ValueError):
        brand_id = None
    try:
        default_affiliate_id = int(default_aff_raw) if default_aff_raw else None
    except (TypeError, ValueError):
        default_affiliate_id = None
    return {
        "int_api_base": base,
        "authorization_token": token,
        "label_id": label_id,
        "brand_id": brand_id,
        "default_affiliate_id": default_affiliate_id,
    }


def is_int_configured(conn):
    cfg = get_int_config(conn)
    return bool(cfg["authorization_token"] and cfg["label_id"] and cfg["brand_id"])


def save_int_config(
    conn,
    authorization_token,
    label_id,
    brand_id,
    int_api_base=None,
    default_affiliate_id=None,
):
    token = (authorization_token or "").strip()
    base = _normalize_int_api_base(int_api_base)
    try:
        lid = int(label_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("label_id sayı olmalı.") from exc
    try:
        bid = int(brand_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("brand_id sayı olmalı.") from exc
    if not token:
        raise ValueError("authorization_token boş olamaz.")
    default_aff = None
    if default_affiliate_id is not None and str(default_affiliate_id).strip() != "":
        try:
            default_aff = int(default_affiliate_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("default_affiliate_id sayı olmalı.") from exc
    upsert_smartico_setting(conn, _SETTING_INT_AUTH_TOKEN, token)
    upsert_smartico_setting(conn, _SETTING_LABEL_ID, str(lid))
    upsert_smartico_setting(conn, _SETTING_BRAND_ID, str(bid))
    upsert_smartico_setting(conn, _SETTING_INT_API_BASE, base)
    upsert_smartico_setting(
        conn, _SETTING_DEFAULT_AFFILIATE_ID, str(default_aff) if default_aff is not None else ""
    )
    _int_jwt["token"] = None
    _int_jwt["expires_at"] = None
    _int_jwt["label_id"] = None
    return get_int_config(conn)


def clear_int_config(conn):
    upsert_smartico_setting(conn, _SETTING_INT_AUTH_TOKEN, "")
    upsert_smartico_setting(conn, _SETTING_LABEL_ID, "")
    upsert_smartico_setting(conn, _SETTING_BRAND_ID, "")
    upsert_smartico_setting(conn, _SETTING_DEFAULT_AFFILIATE_ID, "")
    _int_jwt["token"] = None
    _int_jwt["expires_at"] = None
    _int_jwt["label_id"] = None


def _int_json_request(method, url, *, headers=None, body=None, timeout=None):
    data = None
    req_headers = {"User-Agent": "MakroPanel/1.0", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or _INT_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw or str(exc)}
        raise SmarticoError(
            payload.get("error") or payload.get("message") or f"HTTP {exc.code}"
        ) from exc
    except _FETCH_ERRORS as exc:
        raise SmarticoError(f"int-api bağlantı hatası: {exc}") from exc
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise SmarticoError("int-api geçersiz JSON yanıtı.") from exc
    if status and int(status) >= 400:
        raise SmarticoError(payload.get("error") or payload.get("message") or f"HTTP {status}")
    return payload


def obtain_int_token(conn, force=False):
    """POST /int-api/auth/v1 → jwt_token (yaklaşık 24 saat)."""
    cfg = get_int_config(conn)
    if not cfg["authorization_token"] or not cfg["label_id"]:
        raise SmarticoError("int-api ayarları eksik (authorization_token + label_id).")

    now = utcnow()
    cached = _int_jwt.get("token")
    exp = _int_jwt.get("expires_at")
    if (
        not force
        and cached
        and exp
        and _int_jwt.get("label_id") == cfg["label_id"]
        and exp > now + timedelta(minutes=5)
    ):
        return cached

    url = f"{cfg['int_api_base']}/int-api/auth/v1"
    payload = _int_json_request(
        "POST",
        url,
        body={
            "authorization_token": cfg["authorization_token"],
            "label_id": cfg["label_id"],
        },
    )
    jwt = (payload.get("jwt_token") or "").strip()
    if not jwt:
        raise SmarticoError("int-api token alınamadı (jwt_token yok).")
    _int_jwt["token"] = jwt
    _int_jwt["label_id"] = cfg["label_id"]
    # Dokümanda 24 saat; güvenli tarafta 23 saat tut
    _int_jwt["expires_at"] = now + timedelta(hours=23)
    return jwt


def _int_api_post(conn, body):
    """Bearer JWT ile POST /int-api/ — 401'de bir kez token yenile."""
    cfg = get_int_config(conn)
    url = f"{cfg['int_api_base']}/int-api/"
    jwt = obtain_int_token(conn)
    try:
        return _int_json_request(
            "POST",
            url,
            headers={"Authorization": f"Bearer {jwt}"},
            body=body,
        )
    except SmarticoError as exc:
        msg = str(exc).lower()
        if "401" in msg or "token" in msg or "unauthorized" in msg or "expired" in msg:
            jwt = obtain_int_token(conn, force=True)
            return _int_json_request(
                "POST",
                url,
                headers={"Authorization": f"Bearer {jwt}"},
                body=body,
            )
        raise


def _lookup_row_matches(row, needle):
    """needle: ext_customer_id, registration_id veya username (case-insensitive)."""
    if not isinstance(row, dict) or not needle:
        return False, None
    n = needle.lower()
    ext = str(row.get("ext_customer_id") or "").strip()
    reg = str(row.get("registration_id") or "").strip()
    user = str(row.get("username") or "").strip()
    if ext and ext.lower() == n:
        return True, "ext_customer_id"
    if reg and reg.lower() == n:
        return True, "registration_id"
    if user and user.lower() == n:
        return True, "username"
    return False, None


def _lookup_date_windows():
    """Küçük pencereden büyüğe — lifetime tüm oyuncu dump'ı timeout eder."""
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=1)
    windows = [
        (today - timedelta(days=6), end, "7days"),
        (today - timedelta(days=29), end, "30days"),
        (today - timedelta(days=89), end, "90days"),
        (today - timedelta(days=179), end, "180days"),
    ]
    # Daha eski: ay ay geriye (max ~18 ay)
    cursor = today - timedelta(days=180)
    for _ in range(18):
        chunk_end = cursor
        chunk_start = cursor - timedelta(days=30)
        windows.append((chunk_start, chunk_end, f"{chunk_start.isoformat()}:{chunk_end.isoformat()}"))
        cursor = chunk_start
    return windows


def lookup_player_by_ext_id(conn, ext_customer_id):
    """Oyuncunun mevcut affiliate/kanal kayıtlarını getir.

    Aranan değer: ext_customer_id, registration_id veya username.
    TAP media report'u oyuncu bazında filtrelemez; kısa tarih pencerelerinde
    aranır (lifetime dump timeout / 100k satır limiti yüzünden).
    """
    cfg = get_config(conn)
    if not cfg["api_key"]:
        raise SmarticoError(
            "Smartico rapor API anahtarı yok (Link Takip → Smartico Ayarlar). "
            "Oyuncu sorgusu için Media reports key gerekli."
        )
    query = (ext_customer_id or "").strip()
    if not query:
        raise ValueError("Oyuncu ID / registration ID / username gerekli.")

    group_attempts = [
        "affiliate_id,link_id,ext_customer_id,username,registration_id",
        "affiliate_id,ext_customer_id,username,registration_id",
    ]
    last_error = None
    used_group = None
    used_period = None
    currency = ""
    matched_field = None
    rows = []
    aff_names = None  # lazy

    for date_from, date_to, period_label in _lookup_date_windows():
        data = None
        for group_by in group_attempts:
            params = {
                "group_by": group_by,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            }
            try:
                data = _request(
                    cfg["api_host"], "af2_media_report_op", cfg["api_key"], params,
                    timeout=25,
                )
            except SmarticoError as exc:
                last_error = str(exc)
                data = None
                continue
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                used_group = group_by
                break
            if isinstance(data, str) and data.strip():
                last_error = f"Smartico API hatası: {data.strip()}"
            else:
                last_error = "Smartico API beklenmeyen cevap."
            data = None

        if data is None:
            continue

        currency = (data.get("meta") or {}).get("operator_currency") or currency
        hits = []
        for r in data.get("data") or []:
            ok, field = _lookup_row_matches(r, query)
            if not ok:
                continue
            if (
                _num(r.get("registration_count")) <= 0
                and not str(r.get("registration_id") or "").strip()
                and not str(r.get("username") or "").strip()
            ):
                continue
            if matched_field is None:
                matched_field = field
            aff_id = r.get("affiliate_id")
            if aff_id is not None and str(aff_id).strip() == "":
                aff_id = None
            name_from_row = str(r.get("affiliate_name") or "").strip()
            if not name_from_row and aff_id is not None:
                if aff_names is None:
                    aff_names = fetch_affiliate_names(conn)
                name_from_row = aff_names.get(str(aff_id)) or f"Affiliate #{aff_id}"
            hits.append({
                "ext_customer_id": str(r.get("ext_customer_id") or "").strip(),
                "username": str(r.get("username") or "").strip(),
                "registration_id": str(r.get("registration_id") or "").strip(),
                "affiliate_id": aff_id,
                "affiliate_name": name_from_row or ("—" if aff_id is None else f"Affiliate #{aff_id}"),
                "link_id": r.get("link_id") if r.get("link_id") not in ("", None) else None,
                "link_name": str(r.get("link_name") or "").strip(),
                "brand_id": r.get("brand_id"),
                "brand_name": str(r.get("brand_name") or "").strip(),
                "registration_count": int(_num(r.get("registration_count"))),
                "ftd_count": int(_num(r.get("ftd_count"))),
                "deposit_total": round(_num(r.get("deposit_total")), 2),
                "matched_by": field,
            })

        if hits:
            rows = hits
            used_period = period_label
            break

        # 100k satır tavanı: oyuncu kesilmiş olabilir → haftalık alt pencere
        raw_n = len(data.get("data") or [])
        if raw_n >= 100000 and (date_to - date_from).days > 7:
            cursor = date_from
            while cursor < date_to and not rows:
                week_end = min(cursor + timedelta(days=7), date_to)
                for group_by in group_attempts:
                    params = {
                        "group_by": group_by,
                        "date_from": cursor.isoformat(),
                        "date_to": week_end.isoformat(),
                    }
                    try:
                        sub = _request(
                            cfg["api_host"], "af2_media_report_op", cfg["api_key"], params,
                            timeout=25,
                        )
                    except SmarticoError as exc:
                        last_error = str(exc)
                        continue
                    if not (isinstance(sub, dict) and isinstance(sub.get("data"), list)):
                        continue
                    used_group = group_by
                    for r in sub.get("data") or []:
                        ok, field = _lookup_row_matches(r, query)
                        if not ok:
                            continue
                        if matched_field is None:
                            matched_field = field
                        aff_id = r.get("affiliate_id")
                        if aff_id is not None and str(aff_id).strip() == "":
                            aff_id = None
                        name_from_row = str(r.get("affiliate_name") or "").strip()
                        if not name_from_row and aff_id is not None:
                            if aff_names is None:
                                aff_names = fetch_affiliate_names(conn)
                            name_from_row = aff_names.get(str(aff_id)) or f"Affiliate #{aff_id}"
                        rows.append({
                            "ext_customer_id": str(r.get("ext_customer_id") or "").strip(),
                            "username": str(r.get("username") or "").strip(),
                            "registration_id": str(r.get("registration_id") or "").strip(),
                            "affiliate_id": aff_id,
                            "affiliate_name": name_from_row or ("—" if aff_id is None else f"Affiliate #{aff_id}"),
                            "link_id": r.get("link_id") if r.get("link_id") not in ("", None) else None,
                            "link_name": str(r.get("link_name") or "").strip(),
                            "brand_id": r.get("brand_id"),
                            "brand_name": str(r.get("brand_name") or "").strip(),
                            "registration_count": int(_num(r.get("registration_count"))),
                            "ftd_count": int(_num(r.get("ftd_count"))),
                            "deposit_total": round(_num(r.get("deposit_total")), 2),
                            "matched_by": field,
                        })
                    if rows:
                        used_period = f"{cursor.isoformat()}:{week_end.isoformat()}"
                        break
                cursor = week_end
            if rows:
                break

    if not rows and last_error and used_group is None:
        raise SmarticoError(last_error)

    rows.sort(
        key=lambda x: (
            -(x.get("registration_count") or 0),
            -(x.get("ftd_count") or 0),
            str(x.get("affiliate_name") or ""),
        )
    )
    # Taşıma API'si ext_customer_id ister — registration_id ile arandıysa çöz
    resolved_ext = ""
    for r in rows:
        if r.get("ext_customer_id"):
            resolved_ext = r["ext_customer_id"]
            break

    return {
        "query": query,
        "ext_customer_id": resolved_ext or (query if matched_field == "ext_customer_id" else ""),
        "matched_by": matched_field,
        "rows": rows,
        "count": len(rows),
        "group_by": used_group,
        "period": used_period,
        "currency": currency,
    }


def move_affiliate(
    conn,
    *,
    ext_customer_id,
    affiliate_id=None,
    deal_id=None,
    utm_source=None,
    utm_medium=None,
    use_default=False,
):
    """Oyuncuyu yeni affiliate / deal altına taşı (cid 30062).

    affiliate_id ve deal_id boşsa (veya use_default=True) ayardaki
    default_affiliate_id kullanılır — normal link / organik (kanal yok).
    TAP API null affiliate kabul etmez; Direct/Organic house ID ile temsil edilir.
    İkisi doluysa deal_id baskın.
    """
    if not is_int_configured(conn):
        raise SmarticoError(
            "Üye taşıma ayarları eksik. int-api token, label_id ve brand_id gerekli."
        )
    ext_id = (ext_customer_id or "").strip()
    if not ext_id:
        raise ValueError("ext_customer_id (casino oyuncu ID) gerekli.")

    cfg = get_int_config(conn)
    deal = None
    aff = None
    used_default = False
    if deal_id is not None and str(deal_id).strip() != "":
        try:
            deal = int(deal_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("deal_id sayı olmalı.") from exc
    if affiliate_id is not None and str(affiliate_id).strip() != "":
        try:
            aff = int(affiliate_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("affiliate_id sayı olmalı.") from exc

    if deal is None and aff is None:
        # Boş hedef → normal link (kanal yok / organik)
        if cfg.get("default_affiliate_id") is None:
            raise ValueError(
                "Affiliate ID boş = normal link. Normal link Affiliate ID ayarlanmamış — "
                "int-api Ayarlar'dan MARKOBET_DEFAULT (41105) gir."
            )
        aff = int(cfg["default_affiliate_id"])
        used_default = True
    elif use_default and deal is None:
        if cfg.get("default_affiliate_id") is None:
            raise ValueError("Normal link Affiliate ID (default_affiliate_id) ayarlanmamış.")
        aff = int(cfg["default_affiliate_id"])
        used_default = True

    # affiliate_id tek başına Smartico'da ConstraintViolation veriyor → home deal şart
    if deal is None and aff is not None:
        home_deal = fetch_affiliate_home_deal_id(conn, aff)
        if home_deal is None:
            raise SmarticoError(
                f"Affiliate #{aff} için home deal bulunamadı. "
                "Deal ID'yi elle gir veya Smartico rapor API key'ini kontrol et."
            )
        deal = home_deal

    body = {
        "cid": _MOVE_AFFILIATE_CID,
        "brand_id": cfg["brand_id"],
        "ext_customer_id": ext_id,
        "deal_id": deal,
    }
    # deal_id baskın; affiliate_id opsiyonel ek bilgi
    if aff is not None:
        body["affiliate_id"] = aff
    utm_s = (utm_source or "").strip()
    utm_m = (utm_medium or "").strip()
    if utm_s:
        body["utm_source"] = utm_s
    if utm_m:
        body["utm_medium"] = utm_m

    payload = _int_api_post(conn, body)
    try:
        err_i = int(payload.get("errCode", 0))
    except (TypeError, ValueError):
        err_i = -1
    if err_i != 0:
        detail = (
            payload.get("errMsg")
            or payload.get("message")
            or payload.get("error")
            or ""
        ).strip()
        raise SmarticoError(
            detail or f"Üye taşınamadı (errCode={err_i}). Smartico support ile kontrol et."
        )

    msg = payload.get("message") or "Affiliate taşındı."
    if used_default:
        msg = "Normal linke (kanal yok) taşındı. " + msg

    return {
        "ok": True,
        "cid": payload.get("cid"),
        "errCode": err_i,
        "new_registration_id": payload.get("new_registration_id"),
        "message": msg,
        "call_uid": payload.get("call_uid"),
        "ext_customer_id": ext_id,
        "affiliate_id": aff,
        "deal_id": deal,
        "brand_id": cfg["brand_id"],
        "used_default": used_default,
    }
