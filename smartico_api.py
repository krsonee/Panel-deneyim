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
