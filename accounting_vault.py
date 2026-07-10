"""Kasa (vault) defter mantığı — USDT/TL bakiye, Excel-style zenginleştirme."""

DEFAULT_VAULT_METHODS = [
    "Devir",
    "Masraf",
    "Virman",
    "Kasa Aktarım",
    "Espaycash kk",
    "Mega cüzdan",
    "Paypa Havale",
    "Garanti kredi kart",
    "Garanti Fast",
    "Kolay havale",
    "En Hızlı Havale",
    "all havale",
    "Flux Havale",
    "garanti qr",
]

VAULT_PALETTE = ["#6366f1", "#22c55e", "#f59e0b", "#06b6d4", "#f43f5e", "#a855f7"]
VAULT_ICONS = ["💰", "🏦", "🔐", "💎", "🪙", "📦"]

# Exodus soğuk cüzdan — TRC20 USDT ağ ücreti miktarla orantılı değil; Exodus ekranından doğrulanmalı.
EXODUS_TRC20_FEE_NOTE = (
    "Exodus otomatik bağlanamaz. TRC20 USDT gönderiminde Network Fee genelde sabittir — "
    "Exodus onay ekranındaki ücreti girin veya aşağıdaki tahmini kullanın."
)


def normalize_fee(row):
    return max(0.0, _f(row.get("fee_usdt")))


def suggest_exodus_trc20_fee(usdt_amount, direction):
    """Giden USDT için Exodus TRC20 tahmini fee (manuel doğrulama gerekir)."""
    direction = (direction or "").strip().lower()
    amount = _f(usdt_amount)
    if direction != "out" or amount <= 0:
        return 0.0, "Gelen işlemde fee genelde alıcıdan kesilmez."
    if amount >= 50000:
        fee = 2.0
    elif amount >= 5000:
        fee = 1.5
    else:
        fee = 1.0
    return fee, EXODUS_TRC20_FEE_NOTE


def wallet_usdt_delta(usdt_in, usdt_out, fee_usdt=0.0):
    """Kasadan net USDT hareketi — giden işlemde fee ek maliyet."""
    fee = max(0.0, _f(fee_usdt))
    if usdt_out > 0:
        return -(usdt_out + fee)
    if usdt_in > 0:
        return usdt_in - fee
    return 0.0


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_usdt_parts(row):
    """Gelen / giden USDT — eski kayıtları geriye dönük doldurur."""
    usdt_in = _f(row.get("usdt_in"))
    usdt_out = _f(row.get("usdt_out"))
    if usdt_in > 0 or usdt_out > 0:
        return usdt_in, usdt_out

    amt_usd = abs(_f(row.get("amount_usd") or row.get("amount")))
    tx_type = (row.get("tx_type") or "").lower()
    if tx_type == "in":
        return amt_usd, 0.0
    if tx_type == "out":
        return 0.0, amt_usd
    return 0.0, 0.0


def tl_signed_for_row(row, usdt_in=None, usdt_out=None, fee_usdt=None):
    if usdt_in is None or usdt_out is None:
        usdt_in, usdt_out = normalize_usdt_parts(row)
    if fee_usdt is None:
        fee_usdt = normalize_fee(row)

    rate = _f(row.get("rate_usd_try"))
    if rate > 0 and (usdt_in > 0 or usdt_out > 0):
        delta = wallet_usdt_delta(usdt_in, usdt_out, fee_usdt)
        return round(delta * rate, 2)

    amount_try = abs(_f(row.get("amount_try")))
    if amount_try <= 0:
        return 0.0
    tx_type = (row.get("tx_type") or "").lower()
    if tx_type == "out" or usdt_out > 0:
        return -amount_try
    if tx_type == "in" or usdt_in > 0:
        return amount_try
    return amount_try if usdt_in >= usdt_out else -amount_try


def enrich_vault_transaction(row, vault_lookup=None):
    """Tek satırı Excel sütunlarına map eder."""
    data = dict(row)
    usdt_in, usdt_out = normalize_usdt_parts(data)
    fee_usdt = normalize_fee(data)
    tl_signed = tl_signed_for_row(data, usdt_in, usdt_out, fee_usdt)
    wallet_delta = wallet_usdt_delta(usdt_in, usdt_out, fee_usdt)
    vault_id = data.get("vault_id")
    vault_name = data.get("vault_name") or ""
    if vault_lookup and vault_id:
        vault_name = vault_lookup.get(vault_id, {}).get("name") or vault_name

    method = (data.get("method_name") or "").strip()
    if not method and data.get("tx_type"):
        method = "Giriş" if data["tx_type"] == "in" else "Çıkış"

    data.update(
        {
            "vault_name": vault_name,
            "method_name": method,
            "usdt_in": round(usdt_in, 2),
            "usdt_out": round(usdt_out, 2),
            "usdt_out_display": round(-usdt_out, 2) if usdt_out else 0.0,
            "fee_usdt": round(fee_usdt, 2),
            "wallet_usdt_delta": round(wallet_delta, 2),
            "tl_signed": tl_signed,
            "rate_display": _f(data.get("rate_usd_try")),
        }
    )
    return data


def compute_running_balances(transactions, opening_usdt=0.0, opening_try=0.0, vault_lookup=None):
    """Kronolojik kalan USDT / TL hesaplar."""
    ordered = sorted(transactions, key=lambda r: (r.get("tx_date") or "", int(r.get("id") or 0)))
    balance_usdt = _f(opening_usdt)
    balance_try = _f(opening_try)
    enriched = []

    for row in ordered:
        item = enrich_vault_transaction(row, vault_lookup)
        balance_usdt += item["wallet_usdt_delta"]
        balance_try += item["tl_signed"]
        item["balance_usdt"] = round(balance_usdt, 2)
        item["balance_try"] = round(balance_try, 2)
        enriched.append(item)

    by_id = {item["id"]: item for item in enriched if item.get("id") is not None}
    return enriched, by_id


def vault_period_stats(transactions, period_start=None, period_end=None):
    """Seçili dönemde giriş/çıkış özeti."""
    usdt_in = usdt_out = tl_in = tl_out = fee_total = 0.0
    count = 0
    for row in transactions:
        tx_date = row.get("tx_date") or ""
        if period_start and tx_date < period_start:
            continue
        if period_end and tx_date > period_end:
            continue
        usdt_in += _f(row.get("usdt_in"))
        usdt_out += _f(row.get("usdt_out"))
        fee_total += _f(row.get("fee_usdt"))
        tl = _f(row.get("tl_signed"))
        if tl >= 0:
            tl_in += tl
        else:
            tl_out += abs(tl)
        count += 1
    return {
        "tx_count": count,
        "usdt_in": round(usdt_in, 2),
        "usdt_out": round(usdt_out, 2),
        "fee_usdt": round(fee_total, 2),
        "tl_in": round(tl_in, 2),
        "tl_out": round(tl_out, 2),
        "net_usdt": round(usdt_in - usdt_out - fee_total, 2),
        "net_tl": round(tl_in - tl_out, 2),
    }


def build_vault_dashboard(vaults, transactions_by_vault, period_start=None, period_end=None):
    """Her kasa için güncel bakiye + dönem özeti."""
    cards = []
    total_usdt = total_try = 0.0
    total_period_in = total_period_out = 0.0

    for vault in vaults:
        vid = vault["id"]
        txs = transactions_by_vault.get(vid, [])
        _, balance_map = compute_running_balances(
            txs,
            opening_usdt=vault.get("opening_usdt"),
            opening_try=vault.get("opening_try"),
        )
        current_usdt = _f(vault.get("opening_usdt"))
        current_try = _f(vault.get("opening_try"))
        if balance_map:
            last = max(balance_map.values(), key=lambda r: (r.get("tx_date") or "", r.get("id") or 0))
            current_usdt = _f(last.get("balance_usdt"))
            current_try = _f(last.get("balance_try"))

        period_rows = [enrich_vault_transaction(row) for row in txs]
        stats = vault_period_stats(period_rows, period_start, period_end)

        total_usdt += current_usdt
        total_try += current_try
        total_period_in += stats["usdt_in"]
        total_period_out += stats["usdt_out"]

        cards.append(
            {
                **vault,
                "balance_usdt": round(current_usdt, 2),
                "balance_try": round(current_try, 2),
                "period": stats,
                "total_tx_count": len(txs),
            }
        )

    return {
        "vaults": cards,
        "totals": {
            "balance_usdt": round(total_usdt, 2),
            "balance_try": round(total_try, 2),
            "period_usdt_in": round(total_period_in, 2),
            "period_usdt_out": round(total_period_out, 2),
        },
    }


def build_vault_tx_payload(usdt_amount, direction, rate_usd_try, description="", method_name="", fee_usdt=0.0):
    """Yeni kasa kaydı için normalize edilmiş alanlar."""
    amount = _f(usdt_amount)
    if amount <= 0:
        return None, "Geçerli USDT tutarı girin."

    direction = (direction or "").strip().lower()
    if direction not in ("in", "out"):
        return None, "İşlem yönü Gelen veya Giden olmalı."

    fee = max(0.0, _f(fee_usdt))
    if fee < 0:
        return None, "Fee negatif olamaz."
    if direction == "in" and fee >= amount:
        return None, "Fee, gelen tutardan küçük olmalı."

    rate = _f(rate_usd_try)
    if rate <= 0:
        return None, "Geçerli kur (USD/TL) girin."

    usdt_in = amount if direction == "in" else 0.0
    usdt_out = amount if direction == "out" else 0.0
    wallet_delta = wallet_usdt_delta(usdt_in, usdt_out, fee)
    tl_signed = round(wallet_delta * rate, 2)
    tx_type = direction

    return {
        "tx_type": tx_type,
        "method_name": (method_name or "").strip(),
        "description": (description or "").strip(),
        "usdt_in": round(usdt_in, 2),
        "usdt_out": round(usdt_out, 2),
        "fee_usdt": round(fee, 2),
        "wallet_usdt_delta": round(wallet_delta, 2),
        "amount": round(amount, 2),
        "currency": "USD",
        "amount_usd": round(amount, 2),
        "amount_try": abs(tl_signed),
        "amount_eur": 0.0,
        "rate_usd_try": rate,
        "rate_eur_try": 0.0,
        "tl_signed": tl_signed,
    }, None


def collect_method_suggestions(rows, presets=None):
    """Form autocomplete — kayıtlı yöntemler + varsayılanlar."""
    seen = set()
    methods = []
    for name in presets or DEFAULT_VAULT_METHODS:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            methods.append(name)
    for row in rows or []:
        name = (row.get("method_name") or "").strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            methods.append(name)
    return methods
