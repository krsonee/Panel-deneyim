"""Muhasebe döviz kuru ve çoklu para birimi dönüşümü."""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CURRENCIES = ("TRY", "USD", "EUR")
CURRENCY_SYMBOLS = {"TRY": "₺", "USD": "$", "EUR": "€"}

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
