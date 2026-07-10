"""Muhasebe modülü API rotaları — Link Takip altyapısından bağımsız."""

from contextlib import closing
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from accounting_fx import CURRENCIES, convert_to_all, fetch_exchange_rates, parse_currency
from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    insert_returning_id,
    integrity_error_type,
    iso,
    scalar,
    utcnow,
)

MODULE_ACCESS = ("module.accounting",)
ACC_READ = ("module.accounting", "accounting.dashboard")


def create_accounting_blueprint(permission_required):
    bp = Blueprint("accounting", __name__, url_prefix="/api/accounting")

    def acc_perm(*keys):
        return permission_required(*keys)

    def parse_amount(value):
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if amount < 0:
            return None
        return round(amount, 2)

    def parse_date(value):
        value = (value or "").strip()
        if not value:
            return None
        try:
            datetime.strptime(value[:10], "%Y-%m-%d")
            return value[:10]
        except ValueError:
            return None

    def date_clause(column, period):
        period = (period or "all").strip().lower()
        now = utcnow()
        if period == "today":
            return f" AND {column} >= ?", (now.strftime("%Y-%m-%d"),)
        if period == "month":
            return f" AND {column} >= ?", (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d"),)
        if period == "30days":
            start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            return f" AND {column} >= ?", (start,)
        return "", ()

    def build_money(amount, currency, rates=None):
        currency = parse_currency(currency)
        if not currency:
            return None, "Para birimi seçin: TRY, USD veya EUR."
        amount = parse_amount(amount)
        if amount is None:
            return None, "Geçerli tutar girin."
        return convert_to_all(amount, currency, rates), None

    def kpi_for_period(conn, period):
        dep_sql, dep_params = date_clause("tx_date", period)
        wdr_sql, wdr_params = date_clause("tx_date", period)
        exp_sql, exp_params = date_clause("expense_date", period)
        result = {}
        for cur in CURRENCIES:
            amt = f"amount_{cur.lower()}"
            comm = f"commission_amount_{cur.lower()}"
            sal = f"salary_{cur.lower()}"
            deposits = scalar(
                conn,
                f"SELECT COALESCE(SUM({amt}), 0) FROM acc_finance_transactions WHERE tx_type = 'deposit'{dep_sql}",
                dep_params,
            ) or 0
            withdrawals = scalar(
                conn,
                f"SELECT COALESCE(SUM({amt}), 0) FROM acc_finance_transactions WHERE tx_type = 'withdrawal'{wdr_sql}",
                wdr_params,
            ) or 0
            commission = scalar(
                conn,
                f"SELECT COALESCE(SUM({comm}), 0) FROM acc_finance_transactions WHERE 1=1{dep_sql}",
                dep_params,
            ) or 0
            expenses = scalar(
                conn,
                f"SELECT COALESCE(SUM({amt}), 0) FROM acc_expenses WHERE 1=1{exp_sql}",
                exp_params,
            ) or 0
            payroll = scalar(
                conn,
                f"SELECT COALESCE(SUM({sal}), 0) FROM acc_employees WHERE status = 'active'",
            ) or 0
            deposits = round(float(deposits), 2)
            withdrawals = round(float(withdrawals), 2)
            commission = round(float(commission), 2)
            expenses = round(float(expenses), 2)
            payroll = round(float(payroll), 2)
            result[cur] = {
                "total_deposits": deposits,
                "total_withdrawals": withdrawals,
                "total_commission": commission,
                "total_expenses": expenses,
                "payroll_monthly": payroll,
                "net_profit": round(deposits - withdrawals - commission - expenses, 2),
            }
        return result

    @bp.route("/exchange-rates", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def exchange_rates():
        rates = fetch_exchange_rates()
        return jsonify({
            "currencies": list(CURRENCIES),
            "usd_try": rates["usd_try"],
            "eur_try": rates["eur_try"],
            "date": rates.get("date"),
            "source": rates.get("source"),
        })

    @bp.route("/convert", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def convert_money():
        data = request.get_json(silent=True) or {}
        fx, err = build_money(data.get("amount"), data.get("currency"))
        if err:
            return jsonify({"error": err}), 400
        return jsonify({"converted": fx})

    @bp.route("/dashboard", methods=["GET"])
    @acc_perm(*ACC_READ)
    def dashboard():
        period = request.args.get("period", "all")
        rates = fetch_exchange_rates()
        with closing(get_db()) as conn:
            kpi = kpi_for_period(conn, period)
        return jsonify({
            "period": period,
            "kpi": kpi,
            "rates": {
                "usd_try": rates["usd_try"],
                "eur_try": rates["eur_try"],
                "date": rates.get("date"),
                "source": rates.get("source"),
            },
        })

    # ── Payment methods (komisyon oranları) ──

    @bp.route("/payment-methods", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_payment_methods():
        tx_type = (request.args.get("tx_type") or "").strip().lower()
        with closing(get_db()) as conn:
            if tx_type in ("deposit", "withdrawal"):
                rows = fetchall(
                    conn,
                    "SELECT * FROM acc_payment_methods WHERE tx_type = ? ORDER BY name ASC",
                    (tx_type,),
                )
            else:
                rows = fetchall(
                    conn,
                    "SELECT * FROM acc_payment_methods ORDER BY name ASC, tx_type ASC",
                )
        return jsonify({"payment_methods": [dict(r) for r in rows]})

    @bp.route("/payment-methods", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_payment_method():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        tx_type = (data.get("tx_type") or "").strip().lower()
        if not name:
            return jsonify({"error": "Payment adı zorunludur."}), 400
        if tx_type not in ("deposit", "withdrawal"):
            return jsonify({"error": "İşlem türü seçin: Yatırım veya Çekim."}), 400
        rate = parse_amount(data.get("commission_rate", 0))
        if rate is None:
            return jsonify({"error": "Geçerli komisyon oranı girin."}), 400
        now = iso(utcnow())
        try:
            with closing(get_db()) as conn:
                pid = insert_returning_id(
                    conn,
                    """
                    INSERT INTO acc_payment_methods (name, tx_type, commission_rate, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, tx_type, rate, now, now),
                )
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (pid,))
        except integrity_error_type():
            label = "Yatırım" if tx_type == "deposit" else "Çekim"
            return jsonify({"error": f"Bu payment için {label} komisyonu zaten tanımlı."}), 409
        return jsonify({"payment_method": dict(row)}), 201

    @bp.route("/payment-methods/<int:method_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_payment_method(method_id):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        rate = data.get("commission_rate")
        if rate is not None:
            rate = parse_amount(rate)
            if rate is None:
                return jsonify({"error": "Geçerli komisyon oranı girin."}), 400
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (method_id,))
            if not row:
                return jsonify({"error": "Payment bulunamadı."}), 404
            new_name = name or row["name"]
            new_rate = rate if rate is not None else row["commission_rate"]
            try:
                execute(
                    conn,
                    """
                    UPDATE acc_payment_methods
                    SET name = ?, commission_rate = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_name, new_rate, now, method_id),
                )
                conn.commit()
            except integrity_error_type():
                return jsonify({"error": "Bu payment ve işlem türü kombinasyonu zaten kayıtlı."}), 409
            row = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (method_id,))
        return jsonify({"payment_method": dict(row)})

    @bp.route("/payment-methods/<int:method_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_payment_method(method_id):
        with closing(get_db()) as conn:
            used = scalar(
                conn,
                "SELECT COUNT(*) FROM acc_finance_transactions WHERE payment_method_id = ?",
                (method_id,),
            )
            if used:
                return jsonify({"error": "Bu payment'a bağlı işlemler var, silinemez."}), 400
            execute(conn, "DELETE FROM acc_payment_methods WHERE id = ?", (method_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Site yatırım / çekim ──

    @bp.route("/transactions", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_transactions():
        period = request.args.get("period", "all")
        date_sql, date_params = date_clause("t.tx_date", period)
        with closing(get_db()) as conn:
            rows = fetchall(
                conn,
                f"""
                SELECT t.*, p.name AS payment_name
                FROM acc_finance_transactions t
                INNER JOIN acc_payment_methods p ON p.id = t.payment_method_id
                WHERE 1=1{date_sql}
                ORDER BY t.tx_date DESC, t.id DESC
                """,
                date_params,
            )
        return jsonify({"transactions": [dict(r) for r in rows], "period": period})

    @bp.route("/transactions", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_transaction():
        data = request.get_json(silent=True) or {}
        tx_date = parse_date(data.get("tx_date"))
        tx_type = (data.get("tx_type") or "").strip().lower()
        amount = parse_amount(data.get("amount"))
        payment_method_id = data.get("payment_method_id")

        if not tx_date:
            return jsonify({"error": "Geçerli tarih girin (YYYY-MM-DD)."}), 400
        if tx_type not in ("deposit", "withdrawal"):
            return jsonify({"error": "İşlem türü Yatırım veya Çekim olmalı."}), 400
        if amount is None or amount <= 0:
            return jsonify({"error": "Geçerli miktar girin."}), 400
        fx, err = build_money(amount, data.get("currency"))
        if err:
            return jsonify({"error": err}), 400
        try:
            payment_method_id = int(payment_method_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Payment yöntemi seçin."}), 400

        with closing(get_db()) as conn:
            pm = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (payment_method_id,))
            if not pm:
                return jsonify({"error": "Payment yöntemi bulunamadı."}), 404
            if pm.get("tx_type") and pm["tx_type"] != tx_type:
                return jsonify({"error": "Seçilen payment bu işlem türü için tanımlı değil."}), 400

            rate = float(pm["commission_rate"] or 0)
            commission_orig = round(fx["amount"] * rate / 100, 2)
            comm_fx = convert_to_all(commission_orig, fx["currency"], {"usd_try": fx["rate_usd_try"], "eur_try": fx["rate_eur_try"]})
            now = iso(utcnow())
            tid = insert_returning_id(
                conn,
                """
                INSERT INTO acc_finance_transactions
                (tx_date, payment_method_id, tx_type, amount, currency,
                 amount_try, amount_usd, amount_eur,
                 commission_rate, commission_amount,
                 commission_amount_try, commission_amount_usd, commission_amount_eur,
                 rate_usd_try, rate_eur_try, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_date, payment_method_id, tx_type, fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    rate, commission_orig,
                    comm_fx["TRY"], comm_fx["USD"], comm_fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], now,
                ),
            )
            conn.commit()
            row = fetchone(
                conn,
                """
                SELECT t.*, p.name AS payment_name
                FROM acc_finance_transactions t
                INNER JOIN acc_payment_methods p ON p.id = t.payment_method_id
                WHERE t.id = ?
                """,
                (tid,),
            )
        return jsonify({"transaction": dict(row)}), 201

    @bp.route("/transactions/<int:tx_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_transaction(tx_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_finance_transactions WHERE id = ?", (tx_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Gider kategorileri ──

    @bp.route("/expense-categories", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_expense_categories():
        with closing(get_db()) as conn:
            rows = fetchall(conn, "SELECT * FROM acc_expense_categories ORDER BY name ASC")
        return jsonify({"categories": [dict(r) for r in rows]})

    @bp.route("/expense-categories", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_expense_category():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Kategori adı zorunludur."}), 400
        now = iso(utcnow())
        try:
            with closing(get_db()) as conn:
                cid = insert_returning_id(
                    conn,
                    "INSERT INTO acc_expense_categories (name, created_at) VALUES (?, ?)",
                    (name, now),
                )
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_expense_categories WHERE id = ?", (cid,))
        except integrity_error_type():
            return jsonify({"error": "Bu kategori zaten var."}), 409
        return jsonify({"category": dict(row)}), 201

    @bp.route("/expense-categories/<int:cat_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_expense_category(cat_id):
        with closing(get_db()) as conn:
            used = scalar(conn, "SELECT COUNT(*) FROM acc_expenses WHERE category_id = ?", (cat_id,))
            if used:
                return jsonify({"error": "Bu kategoriye bağlı giderler var, silinemez."}), 400
            execute(conn, "DELETE FROM acc_expense_categories WHERE id = ?", (cat_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Cari giderler ──

    @bp.route("/expenses", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_expenses():
        period = request.args.get("period", "all")
        date_sql, date_params = date_clause("e.expense_date", period)
        with closing(get_db()) as conn:
            rows = fetchall(
                conn,
                f"""
                SELECT e.*, c.name AS category_name
                FROM acc_expenses e
                INNER JOIN acc_expense_categories c ON c.id = e.category_id
                WHERE 1=1{date_sql}
                ORDER BY e.expense_date DESC, e.id DESC
                """,
                date_params,
            )
        return jsonify({"expenses": [dict(r) for r in rows], "period": period})

    @bp.route("/expenses", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_expense():
        data = request.get_json(silent=True) or {}
        expense_date = parse_date(data.get("expense_date"))
        amount = parse_amount(data.get("amount"))
        description = (data.get("description") or "").strip()
        try:
            category_id = int(data.get("category_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Gider kategorisi seçin."}), 400

        if not expense_date:
            return jsonify({"error": "Geçerli tarih girin."}), 400
        if amount is None or amount <= 0:
            return jsonify({"error": "Geçerli tutar girin."}), 400
        fx, err = build_money(amount, data.get("currency"))
        if err:
            return jsonify({"error": err}), 400

        with closing(get_db()) as conn:
            cat = fetchone(conn, "SELECT id FROM acc_expense_categories WHERE id = ?", (category_id,))
            if not cat:
                return jsonify({"error": "Kategori bulunamadı."}), 404
            now = iso(utcnow())
            eid = insert_returning_id(
                conn,
                """
                INSERT INTO acc_expenses
                (expense_date, category_id, description, amount, currency,
                 amount_try, amount_usd, amount_eur, rate_usd_try, rate_eur_try, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expense_date, category_id, description, fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], now,
                ),
            )
            conn.commit()
            row = fetchone(
                conn,
                """
                SELECT e.*, c.name AS category_name
                FROM acc_expenses e
                INNER JOIN acc_expense_categories c ON c.id = e.category_id
                WHERE e.id = ?
                """,
                (eid,),
            )
        return jsonify({"expense": dict(row)}), 201

    @bp.route("/expenses/<int:expense_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_expense(expense_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_expenses WHERE id = ?", (expense_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Kasa takip ──

    @bp.route("/vault-transactions", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_vault_transactions():
        period = request.args.get("period", "all")
        date_sql, date_params = date_clause("tx_date", period)
        with closing(get_db()) as conn:
            rows = fetchall(
                conn,
                f"""
                SELECT * FROM acc_vault_transactions
                WHERE 1=1{date_sql}
                ORDER BY tx_date DESC, id DESC
                """,
                date_params,
            )
        return jsonify({"vault_transactions": [dict(r) for r in rows], "period": period})

    @bp.route("/vault-transactions", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_vault_transaction():
        data = request.get_json(silent=True) or {}
        tx_date = parse_date(data.get("tx_date"))
        vault_name = (data.get("vault_name") or "").strip()
        tx_type = (data.get("tx_type") or "").strip().lower()
        description = (data.get("description") or "").strip()
        amount = parse_amount(data.get("amount"))

        if not tx_date:
            return jsonify({"error": "Geçerli tarih girin."}), 400
        if not vault_name:
            return jsonify({"error": "Kasa adı zorunludur."}), 400
        if tx_type not in ("in", "out"):
            return jsonify({"error": "İşlem türü Giriş veya Çıkış olmalı."}), 400
        if amount is None or amount <= 0:
            return jsonify({"error": "Geçerli tutar girin."}), 400
        fx, err = build_money(amount, data.get("currency"))
        if err:
            return jsonify({"error": err}), 400

        now = iso(utcnow())
        with closing(get_db()) as conn:
            vid = insert_returning_id(
                conn,
                """
                INSERT INTO acc_vault_transactions
                (tx_date, vault_name, tx_type, description, amount, currency,
                 amount_try, amount_usd, amount_eur, rate_usd_try, rate_eur_try, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_date, vault_name, tx_type, description, fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], now,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_vault_transactions WHERE id = ?", (vid,))
        return jsonify({"vault_transaction": dict(row)}), 201

    @bp.route("/vault-transactions/<int:tx_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_vault_transaction(tx_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_vault_transactions WHERE id = ?", (tx_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Personel ──

    @bp.route("/employees", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_employees():
        with closing(get_db()) as conn:
            rows = fetchall(conn, "SELECT * FROM acc_employees ORDER BY name ASC")
            payroll = {}
            for cur in CURRENCIES:
                col = f"salary_{cur.lower()}"
                payroll[cur] = round(float(
                    scalar(conn, f"SELECT COALESCE(SUM({col}), 0) FROM acc_employees WHERE status = 'active'") or 0
                ), 2)
        return jsonify({
            "employees": [dict(r) for r in rows],
            "monthly_payroll_total": payroll,
        })

    @bp.route("/employees", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_employee():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        department = (data.get("department") or "").strip()
        start_date = parse_date(data.get("start_date"))
        salary = parse_amount(data.get("salary"))
        status = (data.get("status") or "active").strip().lower()

        if not name:
            return jsonify({"error": "Personel adı zorunludur."}), 400
        if not department:
            return jsonify({"error": "Departman zorunludur."}), 400
        if not start_date:
            return jsonify({"error": "Geçerli başlangıç tarihi girin."}), 400
        if salary is None:
            return jsonify({"error": "Geçerli maaş girin."}), 400
        fx, err = build_money(salary, data.get("currency"))
        if err:
            return jsonify({"error": err}), 400
        if status not in ("active", "left"):
            status = "active"

        now = iso(utcnow())
        with closing(get_db()) as conn:
            eid = insert_returning_id(
                conn,
                """
                INSERT INTO acc_employees
                (name, department, start_date, salary, currency,
                 salary_try, salary_usd, salary_eur, rate_usd_try, rate_eur_try, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name, department, start_date, fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], status, now,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (eid,))
        return jsonify({"employee": dict(row)}), 201

    @bp.route("/employees/<int:emp_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_employee(emp_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (emp_id,))
            if not row:
                return jsonify({"error": "Personel bulunamadı."}), 404

            name = (data.get("name") or row["name"]).strip()
            department = (data.get("department") or row["department"]).strip()
            start_date = parse_date(data.get("start_date")) or row["start_date"]
            status = (data.get("status") or row["status"]).strip().lower()
            if status not in ("active", "left"):
                status = row["status"]

            currency = data.get("currency") or row.get("currency") or "TRY"
            salary_val = data.get("salary") if data.get("salary") is not None else row["salary"]
            fx, err = build_money(salary_val, currency)
            if err:
                return jsonify({"error": err}), 400

            execute(
                conn,
                """
                UPDATE acc_employees
                SET name = ?, department = ?, start_date = ?, salary = ?, currency = ?,
                    salary_try = ?, salary_usd = ?, salary_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?, status = ?
                WHERE id = ?
                """,
                (
                    name, department, start_date, fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], status, emp_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (emp_id,))
        return jsonify({"employee": dict(row)})

    @bp.route("/employees/<int:emp_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_employee(emp_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_employees WHERE id = ?", (emp_id,))
            conn.commit()
        return jsonify({"ok": True})

    return bp
