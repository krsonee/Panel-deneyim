"""Muhasebe döviz kuru ve çoklu para birimi dönüşümü."""

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.client import RemoteDisconnected

CURRENCIES = ("TRY", "USD", "EUR")
CURRENCY_SYMBOLS = {"TRY": "₺", "USD": "$", "EUR": "€"}

_SETTING_MANUAL = "exchange_manual"
_SETTING_USD = "exchange_usd_try"
_SETTING_EUR = "exchange_eur_try"

_HTTP_HEADERS = {"User-Agent": "MakroPanel/1.0"}
_FETCH_TIMEOUT = 4

# Kısa süreli önbellek yalnızca arka arkaya gelen istekleri azaltır; kayıt anında kullanılmaz.
_SOFT_CACHE_SECONDS = 15

_rate_cache = {
    "fetched_at": None,
    "usd_try": 34.25,
    "eur_try": 37.10,
    "date": None,
    "source": "fallback",
}


def parse_currency(value):
    code = (value or "TRY").strip().upper()
    if code not in CURRENCIES:
        return None
    return code


def _mid_rate(buying, selling):
    buying = float(buying or 0)
    selling = float(selling or 0)
    if buying > 0 and selling > 0:
        return round((buying + selling) / 2, 6)
    rate = buying or selling
    if rate <= 0:
        raise ValueError("invalid rate")
    return round(rate, 6)


def _fetch_truncgil():
    req = urllib.request.Request(
        "https://finans.truncgil.com/v4/today.json",
        headers=_HTTP_HEADERS,
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    usd = data.get("USD") or {}
    eur = data.get("EUR") or {}
    usd_try = _mid_rate(usd.get("Buying"), usd.get("Selling"))
    eur_try = _mid_rate(eur.get("Buying"), eur.get("Selling"))
    return usd_try, eur_try, datetime.now(timezone.utc).isoformat(), "truncgil-live"


def _fetch_tcmb():
    req = urllib.request.Request(
        "https://www.tcmb.gov.tr/kurlar/today.xml",
        headers=_HTTP_HEADERS,
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        root = ET.fromstring(resp.read())
    usd_try = eur_try = None
    date_label = root.get("Date") or root.get("Tarih")
    for cur in root.findall("Currency"):
        kod = cur.get("Kod")
        if kod == "USD":
            usd_try = _mid_rate(cur.findtext("ForexBuying"), cur.findtext("ForexSelling"))
        elif kod == "EUR":
            eur_try = _mid_rate(cur.findtext("ForexBuying"), cur.findtext("ForexSelling"))
    if not usd_try or not eur_try:
        raise ValueError("tcmb missing rates")
    return usd_try, eur_try, date_label, "tcmb"


def _fetch_er_api():
    req = urllib.request.Request(
        "https://open.er-api.com/v6/latest/USD",
        headers=_HTTP_HEADERS,
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if data.get("result") != "success":
        raise ValueError("er-api unsuccessful")
    usd_try = float(data["rates"]["TRY"])
    eur_per_usd = float(data["rates"]["EUR"])
    if usd_try <= 0 or eur_per_usd <= 0:
        raise ValueError("er-api invalid rates")
    eur_try = round(usd_try / eur_per_usd, 6)
    return usd_try, eur_try, data.get("time_last_update_utc"), "er-api"


def _fetch_frankfurter():
    req = urllib.request.Request(
        "https://api.frankfurter.app/latest?from=USD&to=TRY,EUR",
        headers=_HTTP_HEADERS,
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    usd_try = float(data["rates"]["TRY"])
    eur_per_usd = float(data["rates"]["EUR"])
    if usd_try <= 0 or eur_per_usd <= 0:
        raise ValueError("frankfurter invalid rates")
    eur_try = round(usd_try / eur_per_usd, 6)
    return usd_try, eur_try, data.get("date"), "frankfurter"


def _fetch_exchangerate_host():
    req = urllib.request.Request(
        "https://api.exchangerate.host/latest?base=USD&symbols=TRY,EUR",
        headers=_HTTP_HEADERS,
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if not data.get("success", True):
        raise ValueError("exchangerate.host unsuccessful")
    usd_try = float(data["rates"]["TRY"])
    eur_per_usd = float(data["rates"]["EUR"])
    if usd_try <= 0 or eur_per_usd <= 0:
        raise ValueError("exchangerate.host invalid rates")
    eur_try = round(usd_try / eur_per_usd, 6)
    return usd_try, eur_try, data.get("date"), "exchangerate.host"


_FETCH_ERRORS = (
    urllib.error.URLError,
    urllib.error.HTTPError,
    RemoteDisconnected,
    ConnectionError,
    TimeoutError,
    KeyError,
    ValueError,
    TypeError,
    json.JSONDecodeError,
)


def _fetch_live_rates():
    errors = []
    for fetch in (_fetch_truncgil, _fetch_tcmb, _fetch_er_api, _fetch_frankfurter, _fetch_exchangerate_host):
        try:
            return fetch()
        except _FETCH_ERRORS as exc:
            errors.append(str(exc))
            continue
        except OSError as exc:
            errors.append(str(exc))
            continue
    raise RuntimeError("; ".join(errors[-3:]) if errors else "no providers")


def _parse_iso_date(value):
    raw = (value or "").strip()[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _fetch_tcmb_for_date(day):
    """TCMB arşiv XML — hafta sonu/tatilde bülten yoksa ValueError."""
    yyyymm = day.strftime("%Y%m")
    ddmmyyyy = day.strftime("%d%m%Y")
    url = f"https://www.tcmb.gov.tr/kurlar/{yyyymm}/{ddmmyyyy}.xml"
    req = urllib.request.Request(url, headers=_HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        root = ET.fromstring(resp.read())
    usd_try = eur_try = None
    date_label = root.get("Date") or root.get("Tarih") or day.isoformat()
    for cur in root.findall("Currency"):
        kod = cur.get("Kod")
        if kod == "USD":
            usd_try = _mid_rate(cur.findtext("ForexBuying"), cur.findtext("ForexSelling"))
        elif kod == "EUR":
            eur_try = _mid_rate(cur.findtext("ForexBuying"), cur.findtext("ForexSelling"))
    if not usd_try or not eur_try:
        raise ValueError("tcmb archive missing rates")
    return usd_try, eur_try, date_label, "tcmb-archive"


def _fetch_frankfurter_for_date(day):
    iso = day.isoformat()
    url = f"https://api.frankfurter.app/{iso}?from=USD&to=TRY,EUR"
    req = urllib.request.Request(url, headers=_HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    usd_try = float(data["rates"]["TRY"])
    eur_per_usd = float(data["rates"]["EUR"])
    if usd_try <= 0 or eur_per_usd <= 0:
        raise ValueError("frankfurter historical invalid")
    eur_try = round(usd_try / eur_per_usd, 6)
    return usd_try, eur_try, data.get("date") or iso, "frankfurter-historical"


def fetch_rates_for_date(date_value):
    """Belirli bir günün USD/TL ve EUR/TL kurunu getirir.

    Hafta sonu / tatilde TCMB bülteni yoksa önceki iş günlerine (max 10 gün) bakar.
    Bugün veya gelecek tarih için canlı kur kullanılır.
    """
    day = _parse_iso_date(date_value)
    if day is None:
        return fetch_exchange_rates(fresh=True)

    today = datetime.now(timezone.utc).date()
    if day >= today:
        return fetch_exchange_rates(fresh=True)

    last_err = None
    for back in range(0, 11):
        probe = day - timedelta(days=back)
        for fetch in (_fetch_tcmb_for_date, _fetch_frankfurter_for_date):
            try:
                usd_try, eur_try, label, source = fetch(probe)
                return {
                    "fetched_at": datetime.now(timezone.utc),
                    "usd_try": usd_try,
                    "eur_try": eur_try,
                    "date": label,
                    "source": source,
                    "as_of": probe.isoformat(),
                    "requested": day.isoformat(),
                }
            except _FETCH_ERRORS as exc:
                last_err = exc
                continue
            except OSError as exc:
                last_err = exc
                continue
    # Son çare: canlı kur
    live = fetch_exchange_rates(fresh=True)
    live["requested"] = day.isoformat()
    live["source"] = f"{live.get('source') or 'live'}+fallback"
    if last_err:
        live["note"] = str(last_err)
    return live


def _cache_result(now, usd_try, eur_try, date, source):
    global _rate_cache
    _rate_cache = {
        "fetched_at": now,
        "usd_try": usd_try,
        "eur_try": eur_try,
        "date": date,
        "source": source,
    }
    return dict(_rate_cache)


def fetch_exchange_rates(force=False, fresh=False):
    """Canlı kurları getirir.

    fresh=True veya force=True: her seferinde API'den anlık kur çeker.
    Aksi halde en fazla 15 sn kısa önbellek (aynı sayfa yüklemesinde).
    """
    global _rate_cache
    now = datetime.now(timezone.utc)
    live = force or fresh
    has_cached = (
        _rate_cache.get("usd_try")
        and _rate_cache.get("eur_try")
        and _rate_cache.get("source") not in (None, "fallback")
    )
    if (
        not live
        and has_cached
        and _rate_cache.get("fetched_at")
        and now - _rate_cache["fetched_at"] < timedelta(seconds=_SOFT_CACHE_SECONDS)
    ):
        return dict(_rate_cache)

    try:
        usd_try, eur_try, date, source = _fetch_live_rates()
        return _cache_result(now, usd_try, eur_try, date, source)
    except Exception:
        if has_cached:
            cached = dict(_rate_cache)
            cached["source"] = cached.get("source") or "cache"
            return cached
        return _cache_result(
            now,
            _rate_cache.get("usd_try") or 34.25,
            _rate_cache.get("eur_try") or 37.10,
            _rate_cache.get("date"),
            "fallback",
        )


def _read_settings(conn):
    from database import fetchall

    rows = fetchall(conn, "SELECT key, value FROM acc_settings")
    return {r["key"]: r["value"] for r in rows}


def _apply_manual(result, settings):
    if settings.get(_SETTING_MANUAL) != "1":
        result["is_manual"] = False
        return
    try:
        usd = float(settings[_SETTING_USD])
        eur = float(settings[_SETTING_EUR])
    except (KeyError, TypeError, ValueError):
        result["is_manual"] = False
        return
    if usd <= 0 or eur <= 0:
        result["is_manual"] = False
        return
    result["usd_try"] = usd
    result["eur_try"] = eur
    result["is_manual"] = True
    result["source"] = "manual"


def get_effective_rates(conn=None, force_auto=False):
    auto = fetch_exchange_rates(force=force_auto)
    result = {
        "usd_try": auto["usd_try"],
        "eur_try": auto["eur_try"],
        "auto_usd_try": auto["usd_try"],
        "auto_eur_try": auto["eur_try"],
        "date": auto.get("date"),
        "auto_source": auto.get("source"),
        "source": auto.get("source"),
        "is_manual": False,
    }
    if conn is not None:
        _apply_manual(result, _read_settings(conn))
        return result
    try:
        from database import get_db

        with closing(get_db()) as db_conn:
            _apply_manual(result, _read_settings(db_conn))
    except Exception:
        pass
    return result


def save_manual_rates(conn, usd_try, eur_try):
    from database import iso, upsert_setting, utcnow

    usd_try = round(float(usd_try), 4)
    eur_try = round(float(eur_try), 4)
    if usd_try <= 0 or eur_try <= 0:
        raise ValueError("Kurlar pozitif olmalı")
    upsert_setting(conn, _SETTING_MANUAL, "1")
    upsert_setting(conn, _SETTING_USD, str(usd_try))
    upsert_setting(conn, _SETTING_EUR, str(eur_try))
    upsert_setting(conn, "exchange_updated_at", iso(utcnow()))


def clear_manual_rates(conn):
    from database import upsert_setting

    upsert_setting(conn, _SETTING_MANUAL, "0")


def convert_to_all(amount, currency, rates=None):
    rates = rates or fetch_exchange_rates()
    amount = round(float(amount), 2)
    currency = parse_currency(currency) or "TRY"
    usd_try = float(rates["usd_try"])
    eur_try = float(rates["eur_try"])

    if currency == "TRY":
        try_amt = amount
        usd_amt = round(amount / usd_try, 2)
        eur_amt = round(amount / eur_try, 2)
    elif currency == "USD":
        usd_amt = amount
        try_amt = round(amount * usd_try, 2)
        eur_amt = round(try_amt / eur_try, 2)
    else:
        eur_amt = amount
        try_amt = round(amount * eur_try, 2)
        usd_amt = round(try_amt / usd_try, 2)

    return {
        "currency": currency,
        "amount": amount,
        "TRY": try_amt,
        "USD": usd_amt,
        "EUR": eur_amt,
        "rate_usd_try": usd_try,
        "rate_eur_try": eur_try,
    }


def amount_field_for_currency(currency):
    currency = parse_currency(currency) or "TRY"
    return {"TRY": "amount_try", "USD": "amount_usd", "EUR": "amount_eur"}[currency]


def format_money(amount, currency="TRY"):
    sym = CURRENCY_SYMBOLS.get(currency, currency + " ")
    n = float(amount or 0)
    body = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sym}{body}"
