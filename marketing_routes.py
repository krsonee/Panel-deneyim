"""Marketing modülü API rotaları — kanal / affiliate anlaşmaları (tamamen manuel giriş).

Şimdilik hiçbir dış sisteme (Smartico vb.) bağlı değil; ileride otomatik entegrasyon
eklenebilmesi için her anlaşma satırında bir "kanal referans kodu" alanı tutuluyor.
"""

from contextlib import closing
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from database import execute, fetchall, fetchone, get_db, insert_returning_id, iso, utcnow

MODULE_ACCESS = ("module.marketing",)
MKT_DEALS = ("marketing.deals", "module.marketing")

CURRENCIES = ("TRY", "USD", "EUR")
PAYMENT_STATUSES = ("pending", "paid", "cancelled")
DEAL_STATUSES = ("active", "paused", "ended")


def create_marketing_blueprint(permission_required):
    bp = Blueprint("marketing", __name__, url_prefix="/api/marketing")

    def mkt_perm(*keys):
        return permission_required(*keys)

    def current_who():
        return (session.get("admin_display_name") or session.get("admin_username") or "").strip()

    def parse_date(value):
        value = (value or "").strip()
        if not value:
            return None
        try:
            datetime.strptime(value[:10], "%Y-%m-%d")
            return value[:10]
        except ValueError:
            return None

    def parse_amount(value):
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if amount < 0:
            return None
        return round(amount, 2)

    def parse_rate(value):
        try:
            rate = float(value)
        except (TypeError, ValueError):
            return None
        if rate < 0:
            return None
        return round(rate, 3)

    def parse_currency(value):
        value = (value or "TRY").strip().upper()
        return value if value in CURRENCIES else None

    def deal_payload(data, existing=None):
        existing = existing or {}
        out = {}
        agreement_date = parse_date(data.get("agreement_date") if "agreement_date" in data else existing.get("agreement_date"))
        if not agreement_date:
            return None, "Geçerli anlaşma tarihi girin."
        out["agreement_date"] = agreement_date

        name = (data.get("channel_name") if "channel_name" in data else existing.get("channel_name") or "")
        name = (name or "").strip()
        if not name:
            return None, "Kanal adı girin."
        out["channel_name"] = name

        out["channel_type"] = ((data.get("channel_type") if "channel_type" in data else existing.get("channel_type")) or "").strip()
        out["channel_ref_code"] = ((data.get("channel_ref_code") if "channel_ref_code" in data else existing.get("channel_ref_code")) or "").strip()

        currency = parse_currency(data.get("fixed_fee_currency") if "fixed_fee_currency" in data else existing.get("fixed_fee_currency"))
        if not currency:
            return None, "Para birimi TRY, USD veya EUR olmalı."
        out["fixed_fee_currency"] = currency

        fee = parse_amount(data.get("fixed_fee") if "fixed_fee" in data else existing.get("fixed_fee"))
        if fee is None:
            return None, "Geçerli sabit ücret tutarı girin."
        out["fixed_fee"] = fee

        rate = parse_rate(data.get("affiliate_commission_rate") if "affiliate_commission_rate" in data else existing.get("affiliate_commission_rate"))
        if rate is None:
            return None, "Geçerli affiliate komisyon oranı girin (%)."
        out["affiliate_commission_rate"] = rate

        payment_status = ((data.get("payment_status") if "payment_status" in data else existing.get("payment_status")) or "pending").strip().lower()
        if payment_status not in PAYMENT_STATUSES:
            return None, "Ödeme durumu geçersiz."
        out["payment_status"] = payment_status

        status = ((data.get("status") if "status" in data else existing.get("status")) or "active").strip().lower()
        if status not in DEAL_STATUSES:
            return None, "Anlaşma durumu geçersiz."
        out["status"] = status

        out["notes"] = ((data.get("notes") if "notes" in data else existing.get("notes")) or "").strip()
        return out, None

    def summarize(rows):
        totals_by_currency = {}
        active_channels = set()
        for r in rows:
            if r["status"] == "active":
                active_channels.add(r["channel_name"])
            cur = r["fixed_fee_currency"] or "TRY"
            totals_by_currency[cur] = round(totals_by_currency.get(cur, 0) + float(r["fixed_fee"] or 0), 2)
        return {
            "total_fixed_fee_by_currency": totals_by_currency,
            "active_channel_count": len(active_channels),
            "deal_count": len(rows),
        }

    @bp.route("/deals", methods=["GET"])
    @mkt_perm(*MKT_DEALS)
    def list_deals():
        month = (request.args.get("month") or "").strip()
        with closing(get_db()) as conn:
            if month and len(month) == 7:
                rows = [dict(r) for r in fetchall(
                    conn,
                    "SELECT * FROM mkt_deals WHERE agreement_date >= ? AND agreement_date < ? ORDER BY agreement_date DESC, id DESC",
                    (month + "-01", month + "-32"),
                )]
            else:
                rows = [dict(r) for r in fetchall(conn, "SELECT * FROM mkt_deals ORDER BY agreement_date DESC, id DESC")]
        return jsonify({"deals": rows, "summary": summarize(rows)})

    @bp.route("/deals", methods=["POST"])
    @mkt_perm(*MKT_DEALS)
    def create_deal():
        data = request.get_json(silent=True) or {}
        payload, err = deal_payload(data)
        if err:
            return jsonify({"error": err}), 400
        now = iso(utcnow())
        who = current_who()
        with closing(get_db()) as conn:
            new_id = insert_returning_id(
                conn,
                """
                INSERT INTO mkt_deals
                (agreement_date, channel_name, channel_type, channel_ref_code,
                 fixed_fee, fixed_fee_currency, affiliate_commission_rate,
                 payment_status, status, notes, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["agreement_date"], payload["channel_name"], payload["channel_type"],
                    payload["channel_ref_code"], payload["fixed_fee"], payload["fixed_fee_currency"],
                    payload["affiliate_commission_rate"], payload["payment_status"], payload["status"],
                    payload["notes"], who, now, now,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mkt_deals WHERE id = ?", (new_id,))
        return jsonify({"deal": dict(row)}), 201

    @bp.route("/deals/<int:deal_id>", methods=["PUT"])
    @mkt_perm(*MKT_DEALS)
    def update_deal(deal_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mkt_deals WHERE id = ?", (deal_id,))
            if not row:
                return jsonify({"error": "Anlaşma bulunamadı."}), 404
            payload, err = deal_payload(data, existing=dict(row))
            if err:
                return jsonify({"error": err}), 400
            execute(
                conn,
                """
                UPDATE mkt_deals SET
                    agreement_date = ?, channel_name = ?, channel_type = ?, channel_ref_code = ?,
                    fixed_fee = ?, fixed_fee_currency = ?, affiliate_commission_rate = ?,
                    payment_status = ?, status = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["agreement_date"], payload["channel_name"], payload["channel_type"],
                    payload["channel_ref_code"], payload["fixed_fee"], payload["fixed_fee_currency"],
                    payload["affiliate_commission_rate"], payload["payment_status"], payload["status"],
                    payload["notes"], iso(utcnow()), deal_id,
                ),
            )
            conn.commit()
            updated = fetchone(conn, "SELECT * FROM mkt_deals WHERE id = ?", (deal_id,))
        return jsonify({"deal": dict(updated)})

    @bp.route("/deals/<int:deal_id>", methods=["DELETE"])
    @mkt_perm(*MKT_DEALS)
    def delete_deal(deal_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mkt_deals WHERE id = ?", (deal_id,))
            conn.commit()
        return jsonify({"ok": True})

    return bp
