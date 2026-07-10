"""Muhasebe döviz kuru ve çoklu para birimi dönüşümü."""

import json
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone

CURRENCIES = ("TRY", "USD", "EUR")
CURRENCY_SYMBOLS = {"TRY": "₺", "USD": "$", "EUR": "€"}

_SETTING_MANUAL = "exchange_manual"
_SETTING_USD = "exchange_usd_try"
_SETTING_EUR = "exchange_eur_try"

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


def fetch_exchange_rates(force=False):
    global _rate_cache
    now = datetime.now(timezone.utc)
    if (
        not force
        and _rate_cache.get("fetched_at")
        and now - _rate_cache["fetched_at"] < timedelta(hours=1)
    ):
        return dict(_rate_cache)

    try:
        req = urllib.request.Request(
            "https://api.frankfurter.app/latest?from=USD&to=TRY,EUR",
            headers={"User-Agent": "MakroPanel/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        usd_try = float(data["rates"]["TRY"])
        eur_per_usd = float(data["rates"]["EUR"])
        eur_try = round(usd_try / eur_per_usd, 6)
        _rate_cache = {
            "fetched_at": now,
            "usd_try": usd_try,
            "eur_try": eur_try,
            "date": data.get("date"),
            "source": "frankfurter",
        }
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TypeError):
        if not _rate_cache.get("fetched_at"):
            _rate_cache["fetched_at"] = now
        _rate_cache["source"] = _rate_cache.get("source") or "fallback"

    return dict(_rate_cache)


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
    rates = rates or get_effective_rates()
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
