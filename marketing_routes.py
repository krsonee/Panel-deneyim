"""Marketing modülü — kanal anlaşmaları ve aylık ödeme planı takibi."""

import calendar
from contextlib import closing
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session

from database import execute, fetchall, fetchone, get_db, insert_returning_id, iso, utcnow

MODULE_ACCESS = ("module.marketing",)
MKT_DEALS = ("marketing.deals",)

CURRENCIES = ("TRY", "USD", "EUR")
DEAL_STATUSES = ("active", "paused", "ended")
PAYMENT_STATUSES = ("pending", "paid", "skipped")
REMINDER_LOOKBACK_DAYS = 20
REMINDER_AHEAD_DAYS = 3

MONTH_NAMES_TR = (
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)


def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def period_add(period_yyyy_mm, months=1):
    y, m = map(int, period_yyyy_mm.split("-"))
    m += months
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def periods_between(start_period, end_period):
    cur = start_period
    while cur <= end_period:
        yield cur
        cur = period_add(cur, 1)


def due_date_for_period(agreement_date, period_yyyy_mm):
    y, m = map(int, period_yyyy_mm.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    day = min(agreement_date.day, last_day)
    return date(y, m, day)


def period_label_tr(period_yyyy_mm):
    y, m = map(int, period_yyyy_mm.split("-"))
    return f"{MONTH_NAMES_TR[m]} {y}"


def ensure_deal_payments(conn, deal):
    """Aktif anlaşma için başlangıç ayından itibaren ödeme satırlarını oluştur / uzat."""
    deal = dict(deal)
    if deal.get("status") != "active":
        return
    agreement_date = parse_iso_date(deal.get("agreement_date"))
    if not agreement_date:
        return
    start_period = agreement_date.strftime("%Y-%m")
    today = date.today()
    horizon = period_add(today.strftime("%Y-%m"), 2)
    end_period = horizon
    end_date = parse_iso_date(deal.get("end_date"))
    if end_date:
        end_period = min(end_period, end_date.strftime("%Y-%m"))
    now = iso(utcnow())
    amount = float(deal.get("fixed_fee") or 0)
    currency = deal.get("fixed_fee_currency") or "TRY"
    deal_id = deal["id"]
    for period in periods_between(start_period, end_period):
        due = due_date_for_period(agreement_date, period)
        if end_date and due > end_date:
            continue
        existing = fetchone(
            conn,
            "SELECT id FROM mkt_deal_payments WHERE deal_id = ? AND period = ?",
            (deal_id, period),
        )
        if existing:
            continue
        insert_returning_id(
            conn,
            """
            INSERT INTO mkt_deal_payments
            (deal_id, period, due_date, amount, currency, status, paid_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
            """,
            (deal_id, period, due.isoformat(), amount, currency, now, now),
        )


def payment_summary_for_deal(conn, deal_id):
    rows = fetchall(
        conn,
        "SELECT status, due_date FROM mkt_deal_payments WHERE deal_id = ? ORDER BY period ASC",
        (deal_id,),
    )
    today = date.today()
    lookback_from = today - timedelta(days=REMINDER_LOOKBACK_DAYS)
    paid = pending = overdue = 0
    next_due = None
    for r in rows:
        st = r["status"]
        if st == "paid":
            paid += 1
        elif st == "pending":
            pending += 1
            due = parse_iso_date(r["due_date"])
            if due and due < today and due >= lookback_from:
                overdue += 1
            if due and (next_due is None or due < next_due):
                next_due = due
    return {
        "paid_count": paid,
        "pending_count": pending,
        "overdue_count": overdue,
        "next_due_date": next_due.isoformat() if next_due else None,
    }


def enrich_deal(conn, row):
    deal = dict(row)
    ensure_deal_payments(conn, deal)
    deal["payment_summary"] = payment_summary_for_deal(conn, deal["id"])
    payments = fetchall(
        conn,
        """
        SELECT p.*, d.channel_name, d.channel_type, d.status AS deal_status
        FROM mkt_deal_payments p
        JOIN mkt_deals d ON d.id = p.deal_id
        WHERE p.deal_id = ?
        ORDER BY p.period ASC
        """,
        (deal["id"],),
    )
    deal["payments"] = [dict(p) for p in payments]
    return deal


def create_marketing_blueprint(permission_required):
    bp = Blueprint("marketing", __name__, url_prefix="/api/marketing")

    def mkt_perm(*keys):
        return permission_required(*keys)

    def current_who():
        return (session.get("admin_display_name") or session.get("admin_username") or "").strip()

    def parse_date(value):
        d = parse_iso_date(value)
        return d.isoformat() if d else None

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
        agreement_date = parse_date(
            data.get("agreement_date") if "agreement_date" in data else existing.get("agreement_date")
        )
        if not agreement_date:
            return None, "Geçerli anlaşma / ilk ödeme tarihi girin."
        out["agreement_date"] = agreement_date

        name = (data.get("channel_name") if "channel_name" in data else existing.get("channel_name") or "")
        name = (name or "").strip()
        if not name:
            return None, "Kanal adı girin."
        out["channel_name"] = name

        out["channel_type"] = (
            (data.get("channel_type") if "channel_type" in data else existing.get("channel_type")) or ""
        ).strip()
        out["channel_ref_code"] = (
            (data.get("channel_ref_code") if "channel_ref_code" in data else existing.get("channel_ref_code")) or ""
        ).strip()

        currency = parse_currency(
            data.get("fixed_fee_currency") if "fixed_fee_currency" in data else existing.get("fixed_fee_currency")
        )
        if not currency:
            return None, "Para birimi TRY, USD veya EUR olmalı."
        out["fixed_fee_currency"] = currency

        fee = parse_amount(data.get("fixed_fee") if "fixed_fee" in data else existing.get("fixed_fee"))
        if fee is None:
            return None, "Geçerli sabit ücret tutarı girin."
        out["fixed_fee"] = fee

        rate = parse_rate(
            data.get("affiliate_commission_rate")
            if "affiliate_commission_rate" in data
            else existing.get("affiliate_commission_rate")
        )
        if rate is None:
            return None, "Geçerli affiliate komisyon oranı girin (%)."
        out["affiliate_commission_rate"] = rate

        if "status" in data:
            status = (data.get("status") or "active").strip().lower()
            if status not in DEAL_STATUSES:
                return None, "Anlaşma durumu geçersiz."
            out["status"] = status

        out["notes"] = (
            (data.get("notes") if "notes" in data else existing.get("notes")) or ""
        ).strip()
        return out, None

    def summarize(deals):
        active_channels = set()
        pending_this_month = 0
        overdue = 0
        month = date.today().strftime("%Y-%m")
        for d in deals:
            if d.get("status") == "active":
                active_channels.add(d["channel_name"])
            ps = d.get("payment_summary") or {}
            overdue += ps.get("overdue_count") or 0
            for p in d.get("payments") or []:
                if p.get("period") == month and p.get("status") == "pending":
                    pending_this_month += 1
        return {
            "active_channel_count": len(active_channels),
            "deal_count": len(deals),
            "pending_this_month": pending_this_month,
            "overdue_count": overdue,
        }

    @bp.route("/deals", methods=["GET"])
    @mkt_perm(*MKT_DEALS)
    def list_deals():
        with closing(get_db()) as conn:
            rows = [dict(r) for r in fetchall(conn, "SELECT * FROM mkt_deals ORDER BY agreement_date DESC, id DESC")]
            deals = [enrich_deal(conn, r) for r in rows]
            conn.commit()
        return jsonify({"deals": deals, "summary": summarize(deals)})

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
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'active', ?, ?, ?, ?)
                """,
                (
                    payload["agreement_date"], payload["channel_name"], payload["channel_type"],
                    payload["channel_ref_code"], payload["fixed_fee"], payload["fixed_fee_currency"],
                    payload["affiliate_commission_rate"], payload["notes"], who, now, now,
                ),
            )
            row = fetchone(conn, "SELECT * FROM mkt_deals WHERE id = ?", (new_id,))
            ensure_deal_payments(conn, dict(row))
            conn.commit()
            deal = enrich_deal(conn, row)
        return jsonify({"deal": deal}), 201

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
            status = payload.get("status", row["status"])
            execute(
                conn,
                """
                UPDATE mkt_deals SET
                    agreement_date = ?, channel_name = ?, channel_type = ?, channel_ref_code = ?,
                    fixed_fee = ?, fixed_fee_currency = ?, affiliate_commission_rate = ?,
                    status = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["agreement_date"], payload["channel_name"], payload["channel_type"],
                    payload["channel_ref_code"], payload["fixed_fee"], payload["fixed_fee_currency"],
                    payload["affiliate_commission_rate"], status, payload["notes"],
                    iso(utcnow()), deal_id,
                ),
            )
            updated = fetchone(conn, "SELECT * FROM mkt_deals WHERE id = ?", (deal_id,))
            ensure_deal_payments(conn, dict(updated))
            execute(
                conn,
                "UPDATE mkt_deal_payments SET amount = ?, currency = ?, updated_at = ? WHERE deal_id = ? AND status = 'pending'",
                (payload["fixed_fee"], payload["fixed_fee_currency"], iso(utcnow()), deal_id),
            )
            conn.commit()
            deal = enrich_deal(conn, updated)
        return jsonify({"deal": deal})

    @bp.route("/deals/<int:deal_id>/end", methods=["POST"])
    @mkt_perm(*MKT_DEALS)
    def end_deal(deal_id):
        data = request.get_json(silent=True) or {}
        end_date = parse_date(data.get("end_date")) or date.today().isoformat()
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mkt_deals WHERE id = ?", (deal_id,))
            if not row:
                return jsonify({"error": "Anlaşma bulunamadı."}), 404
            execute(
                conn,
                "UPDATE mkt_deals SET status = 'ended', end_date = ?, updated_at = ? WHERE id = ?",
                (end_date, now, deal_id),
            )
            execute(
                conn,
                """
                UPDATE mkt_deal_payments SET status = 'skipped', updated_at = ?
                WHERE deal_id = ? AND status = 'pending' AND due_date > ?
                """,
                (now, deal_id, end_date),
            )
            conn.commit()
            updated = fetchone(conn, "SELECT * FROM mkt_deals WHERE id = ?", (deal_id,))
            deal = enrich_deal(conn, updated)
        return jsonify({"deal": deal})

    @bp.route("/deals/<int:deal_id>", methods=["DELETE"])
    @mkt_perm(*MKT_DEALS)
    def delete_deal(deal_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mkt_deal_payments WHERE deal_id = ?", (deal_id,))
            execute(conn, "DELETE FROM mkt_deals WHERE id = ?", (deal_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/payments", methods=["GET"])
    @mkt_perm(*MKT_DEALS)
    def list_payments():
        month = (request.args.get("month") or "").strip()
        if not month or len(month) != 7:
            month = date.today().strftime("%Y-%m")
        with closing(get_db()) as conn:
            deals = [dict(r) for r in fetchall(conn, "SELECT * FROM mkt_deals")]
            for d in deals:
                ensure_deal_payments(conn, d)
            conn.commit()
            rows = fetchall(
                conn,
                """
                SELECT p.*, d.channel_name, d.channel_type, d.channel_ref_code,
                       d.affiliate_commission_rate, d.status AS deal_status, d.end_date AS deal_end_date
                FROM mkt_deal_payments p
                JOIN mkt_deals d ON d.id = p.deal_id
                WHERE p.period = ?
                ORDER BY p.due_date ASC, d.channel_name ASC
                """,
                (month,),
            )
        payments = [dict(r) for r in rows]
        return jsonify({
            "period": month,
            "period_label": period_label_tr(month),
            "payments": payments,
        })

    @bp.route("/payments/<int:payment_id>", methods=["PUT"])
    @mkt_perm(*MKT_DEALS)
    def update_payment(payment_id):
        data = request.get_json(silent=True) or {}
        status = (data.get("status") or "").strip().lower()
        if status not in PAYMENT_STATUSES:
            return jsonify({"error": "Durum 'pending', 'paid' veya 'skipped' olmalı."}), 400
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mkt_deal_payments WHERE id = ?", (payment_id,))
            if not row:
                return jsonify({"error": "Ödeme kaydı bulunamadı."}), 404
            paid_at = now if status == "paid" else None
            execute(
                conn,
                "UPDATE mkt_deal_payments SET status = ?, paid_at = ?, updated_at = ? WHERE id = ?",
                (status, paid_at, now, payment_id),
            )
            conn.commit()
            updated = fetchone(
                conn,
                """
                SELECT p.*, d.channel_name, d.status AS deal_status
                FROM mkt_deal_payments p
                JOIN mkt_deals d ON d.id = p.deal_id
                WHERE p.id = ?
                """,
                (payment_id,),
            )
        return jsonify({"payment": dict(updated)})

    @bp.route("/reminders", methods=["GET"])
    @mkt_perm(*MKT_DEALS)
    def payment_reminders():
        """Ödeme tarihinden 3 gün önce başlayarak hatırlat; gecikmişlerde en fazla 20 gün geriye bak."""
        today = date.today()
        remind_until = today + timedelta(days=REMINDER_AHEAD_DAYS)
        lookback_from = today - timedelta(days=REMINDER_LOOKBACK_DAYS)
        with closing(get_db()) as conn:
            deals = [dict(r) for r in fetchall(conn, "SELECT * FROM mkt_deals WHERE status = 'active'")]
            for d in deals:
                ensure_deal_payments(conn, d)
            conn.commit()
            rows = fetchall(
                conn,
                """
                SELECT p.*, d.channel_name, d.channel_type, d.fixed_fee_currency
                FROM mkt_deal_payments p
                JOIN mkt_deals d ON d.id = p.deal_id
                WHERE p.status = 'pending' AND d.status = 'active'
                  AND p.due_date <= ? AND p.due_date >= ?
                ORDER BY p.due_date ASC
                """,
                (remind_until.isoformat(), lookback_from.isoformat()),
            )
        reminders = []
        for r in rows:
            due = parse_iso_date(r["due_date"])
            if not due:
                continue
            days_until = (due - today).days
            reminders.append({
                **dict(r),
                "days_until": days_until,
                "is_overdue": days_until < 0,
                "period_label": period_label_tr(r["period"]),
            })
        return jsonify({"reminders": reminders, "today": today.isoformat()})

    return bp
