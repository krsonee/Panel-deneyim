"""Ödeme yöntemi komisyon faturası — yatırım/çekim işlemlerinden dönem özeti."""

from accounting_period import date_clause
from database import fetchall


def build_payment_invoices(conn, period, resolve_commission_rate):
    """Dönem için ödeme sağlayıcı komisyon özetini üret."""
    date_sql, date_params = date_clause("t.tx_date", period)
    rows = fetchall(
        conn,
        f"""
        SELECT
            p.id AS payment_method_id,
            p.name AS provider_name,
            t.tx_type,
            COUNT(*) AS tx_count,
            COALESCE(SUM(t.amount_try), 0) AS volume_try,
            COALESCE(SUM(t.commission_amount_try), 0) AS commission_try
        FROM acc_finance_transactions t
        INNER JOIN acc_payment_methods p ON p.id = t.payment_method_id
        WHERE 1=1{date_sql}
        GROUP BY p.id, p.name, t.tx_type
        ORDER BY LOWER(p.name), t.tx_type
        """,
        date_params,
    )

    providers = {}
    for row in rows:
        name = row["provider_name"]
        if name not in providers:
            providers[name] = {
                "provider_name": name,
                "deposit_volume_try": 0.0,
                "withdrawal_volume_try": 0.0,
                "deposit_commission_try": 0.0,
                "withdrawal_commission_try": 0.0,
                "deposit_rate": None,
                "withdrawal_rate": None,
                "deposit_tx_count": 0,
                "withdrawal_tx_count": 0,
                "tx_count": 0,
            }
        item = providers[name]
        tx_type = row["tx_type"]
        vol = round(float(row["volume_try"] or 0), 2)
        comm = round(float(row["commission_try"] or 0), 2)
        count = int(row["tx_count"] or 0)
        rate = resolve_commission_rate(conn, row["payment_method_id"], period=period)
        if tx_type == "deposit":
            item["deposit_volume_try"] = vol
            item["deposit_commission_try"] = comm
            item["deposit_rate"] = rate
            item["deposit_tx_count"] = count
        else:
            item["withdrawal_volume_try"] = vol
            item["withdrawal_commission_try"] = comm
            item["withdrawal_rate"] = rate
            item["withdrawal_tx_count"] = count
        item["tx_count"] += count
        item["total_commission_try"] = round(
            item["deposit_commission_try"] + item["withdrawal_commission_try"], 2
        )

    provider_list = sorted(providers.values(), key=lambda x: x["provider_name"].lower())
    totals = {
        "deposit_volume_try": round(sum(p["deposit_volume_try"] for p in provider_list), 2),
        "withdrawal_volume_try": round(sum(p["withdrawal_volume_try"] for p in provider_list), 2),
        "commission_try": round(sum(p["total_commission_try"] for p in provider_list), 2),
        "tx_count": sum(p["tx_count"] for p in provider_list),
        "provider_count": len(provider_list),
    }
    return {"providers": provider_list, "totals": totals}
