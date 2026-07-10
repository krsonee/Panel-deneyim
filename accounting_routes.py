"""Muhasebe modülü API rotaları — Link Takip altyapısından bağımsız."""

import re
from contextlib import closing
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request, session

from accounting_fx import (
    CURRENCIES,
    convert_to_all,
    fetch_exchange_rates,
    parse_currency,
)
from accounting_payroll import (
    category_lookup,
    compute_payroll_daily,
    enrich_employee_row,
    redact_employee_for_view,
    validate_office_amounts,
)
from accounting_period import date_clause, default_accounting_period, period_label
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
ACC_OFFICE_SALARIES = "accounting.payroll.office_salaries"


def slugify_name(value):
    value = (value or "").strip().lower()
    tr = str.maketrans("çğıöşü", "cgiosu")
    value = value.translate(tr)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return (value.strip("_")[:48] or "kategori")


def fetch_employee_departments(conn):
    return [dict(r) for r in fetchall(conn, "SELECT * FROM acc_employee_departments ORDER BY name ASC")]


def fetch_salary_categories(conn):
    rows = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_salary_categories ORDER BY name ASC")]
    for row in rows:
        row["is_office"] = bool(row.get("is_office"))
    return rows


def unique_salary_slug(conn, base_slug):
    slug = base_slug
    n = 2
    while scalar(conn, "SELECT COUNT(*) FROM acc_salary_categories WHERE slug = ?", (slug,)):
        slug = f"{base_slug}_{n}"[:48]
        n += 1
    return slug


def create_accounting_blueprint(permission_required):
    bp = Blueprint("accounting", __name__, url_prefix="/api/accounting")

    def acc_perm(*keys):
        return permission_required(*keys)

    def can_view_office_salaries():
        return has_permission(session.get("admin_permissions"), ACC_OFFICE_SALARIES)

    def permissions_meta():
        return {"can_view_office_salaries": can_view_office_salaries()}

    def payroll_include_office():
        return can_view_office_salaries()

    def prepare_employee_row(row, period, category_map=None):
        enriched = enrich_employee_row(dict(row), period)
        return redact_employee_for_view(enriched, can_view_office_salaries(), category_map)

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

    def parse_rate(value):
        if value is None or value == "":
            return None
        try:
            rate = float(value)
        except (TypeError, ValueError):
            return None
        if rate <= 0:
            return None
        return round(rate, 6)

    def rates_from_request(data, fallback=None):
        usd = parse_rate(data.get("rate_usd_try"))
        eur = parse_rate(data.get("rate_eur_try"))
        if (usd and not eur) or (eur and not usd):
            return None, "USD/TL ve EUR/TL birlikte girilmeli veya ikisi de boş bırakılmalı."
        if usd and eur:
            return {"usd_try": usd, "eur_try": eur}, None
        if fallback:
            return fallback, None
        auto = fetch_exchange_rates()
        return {"usd_try": auto["usd_try"], "eur_try": auto["eur_try"]}, None

    def build_money(amount, currency, rates=None):
        currency = parse_currency(currency)
        if not currency:
            return None, "Para birimi seçin: TRY, USD veya EUR."
        amount = parse_amount(amount)
        if amount is None:
            return None, "Geçerli tutar girin."
        if rates is None:
            rates = fetch_exchange_rates()
        return convert_to_all(amount, currency, rates), None

    def used_rates_payload(fx):
        return {"usd_try": fx["rate_usd_try"], "eur_try": fx["rate_eur_try"]}

    def rates_json(rates):
        return {
            "currencies": list(CURRENCIES),
            "usd_try": rates["usd_try"],
            "eur_try": rates["eur_try"],
            "date": rates.get("date"),
            "source": rates.get("source"),
        }

    def parse_salary_category(value, category_slugs):
        cat = (value or "turkey").strip().lower()
        if cat not in category_slugs:
            return None
        return cat

    def parse_department(value, department_names):
        dept = (value or "").strip()
        if dept not in department_names:
            return None
        return dept

    def parse_office_amount(value):
        if value is None or value == "":
            return 0.0
        amount = parse_amount(value)
        if amount is None:
            return None
        return amount

    def validate_employee_dates(status, start_date, end_date):
        if status == "left":
            if not end_date:
                return "Ayrılan personel için çıkış tarihi zorunludur."
            if end_date < start_date:
                return "Çıkış tarihi işe başlangıçtan önce olamaz."
        elif end_date:
            return "Aktif personelde çıkış tarihi girilemez."
        return None

    def employee_payload(data, existing=None, salary_categories=None, department_names=None):
        existing = existing or {}
        _, office_slugs, cat_slugs = category_lookup(salary_categories)
        dept_names = department_names or []
        name = (data.get("name") or existing.get("name") or "").strip()
        department = parse_department(
            data.get("department") if "department" in data else existing.get("department"),
            dept_names,
        )
        start_date = parse_date(data.get("start_date")) or existing.get("start_date")
        status = (data.get("status") or existing.get("status") or "active").strip().lower()
        if status not in ("active", "left"):
            status = existing.get("status") or "active"
        end_date = parse_date(data.get("end_date")) if "end_date" in data else existing.get("end_date")
        if status == "active":
            end_date = None
        salary_category = parse_salary_category(
            data.get("salary_category") if "salary_category" in data else existing.get("salary_category"),
            cat_slugs,
        )
        if not salary_category:
            return None, "Geçerli maaş kategorisi seçin."
        is_office = salary_category in office_slugs

        salary = parse_amount(data.get("salary")) if data.get("salary") is not None else existing.get("salary")
        if salary is None:
            return None, "Geçerli maaş girin."

        bank = parse_office_amount(data.get("bank_salary")) if "bank_salary" in data else existing.get("bank_salary", 0)
        crypto = parse_office_amount(data.get("crypto_salary")) if "crypto_salary" in data else existing.get("crypto_salary", 0)
        advance = parse_office_amount(data.get("advance_amount")) if "advance_amount" in data else existing.get("advance_amount", 0)
        if bank is None or crypto is None or advance is None:
            return None, "Ofis personeli ödeme tutarları geçersiz."

        if not is_office:
            bank = crypto = advance = 0.0

        if not name:
            return None, "Personel adı zorunludur."
        if not department:
            return None, "Departman seçin veya yeni departman ekleyin."
        if not start_date:
            return None, "Geçerli başlangıç tarihi girin."

        date_err = validate_employee_dates(status, start_date, end_date)
        if date_err:
            return None, date_err

        office_err = validate_office_amounts(salary, bank, crypto, advance, is_office)
        if office_err:
            return None, office_err

        return {
            "name": name,
            "department": department,
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "salary_category": salary_category,
            "salary": salary,
            "bank_salary": bank,
            "crypto_salary": crypto,
            "advance_amount": advance,
            "currency": data.get("currency") or existing.get("currency") or "TRY",
        }, None

    def payroll_context(conn):
        departments = fetch_employee_departments(conn)
        salary_categories = fetch_salary_categories(conn)
        return departments, salary_categories

    def period_from_request():
        period = (request.args.get("period") or "").strip()
        return period or default_accounting_period()

    def period_meta(period):
        return {"period": period, "period_label": period_label(period)}

    def kpi_for_period(conn, period):
        dep_sql, dep_params = date_clause("tx_date", period)
        wdr_sql, wdr_params = date_clause("tx_date", period)
        exp_sql, exp_params = date_clause("expense_date", period)
        employees = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_employees")]
        _, salary_categories = payroll_context(conn)
        payroll_data = compute_payroll_daily(
            employees, period, include_office=payroll_include_office(), category_map=salary_categories
        )
        payroll_accrual = payroll_data["period_accrual"]
        result = {}
        for cur in CURRENCIES:
            amt = f"amount_{cur.lower()}"
            comm = f"commission_amount_{cur.lower()}"
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
            payroll = payroll_accrual.get(cur, 0)
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
        return jsonify(rates_json(fetch_exchange_rates()))

    @bp.route("/convert", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def convert_money():
        data = request.get_json(silent=True) or {}
        rates, rate_err = rates_from_request(data)
        if rate_err:
            return jsonify({"error": rate_err}), 400
        fx, err = build_money(data.get("amount"), data.get("currency"), rates)
        if err:
            return jsonify({"error": err}), 400
        return jsonify({"converted": fx})

    @bp.route("/dashboard", methods=["GET"])
    @acc_perm(*ACC_READ)
    def dashboard():
        period = period_from_request()
        with closing(get_db()) as conn:
            kpi = kpi_for_period(conn, period)
            employees = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_employees")]
            departments, salary_categories = payroll_context(conn)
        payroll_daily = compute_payroll_daily(
            employees, period, include_office=payroll_include_office(), category_map=salary_categories
        )
        return jsonify({
            **period_meta(period),
            "kpi": kpi,
            "rates": rates_json(fetch_exchange_rates()),
            "payroll_daily": payroll_daily,
            "departments": departments,
            "salary_categories": salary_categories,
            **permissions_meta(),
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
        period = period_from_request()
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
        return jsonify({**period_meta(period), "transactions": [dict(r) for r in rows]})

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
        rates, rate_err = rates_from_request(data)
        if rate_err:
            return jsonify({"error": rate_err}), 400
        fx, err = build_money(amount, data.get("currency"), rates)
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
        return jsonify({"transaction": dict(row), "rates": used_rates_payload(fx)}), 201

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
        period = period_from_request()
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
        return jsonify({**period_meta(period), "expenses": [dict(r) for r in rows]})

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
        rates, rate_err = rates_from_request(data)
        if rate_err:
            return jsonify({"error": rate_err}), 400
        fx, err = build_money(amount, data.get("currency"), rates)
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
        return jsonify({"expense": dict(row), "rates": used_rates_payload(fx)}), 201

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
        period = period_from_request()
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
        return jsonify({**period_meta(period), "vault_transactions": [dict(r) for r in rows]})

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
        rates, rate_err = rates_from_request(data)
        if rate_err:
            return jsonify({"error": rate_err}), 400
        fx, err = build_money(amount, data.get("currency"), rates)
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
        return jsonify({"vault_transaction": dict(row), "rates": used_rates_payload(fx)}), 201

    @bp.route("/vault-transactions/<int:tx_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_vault_transaction(tx_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_vault_transactions WHERE id = ?", (tx_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Personel seçenekleri ──

    @bp.route("/employee-departments", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_employee_departments():
        with closing(get_db()) as conn:
            rows = fetch_employee_departments(conn)
        return jsonify({"departments": rows})

    @bp.route("/employee-departments", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_employee_department():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Departman adı zorunludur."}), 400
        now = iso(utcnow())
        try:
            with closing(get_db()) as conn:
                did = insert_returning_id(
                    conn,
                    "INSERT INTO acc_employee_departments (name, created_at) VALUES (?, ?)",
                    (name, now),
                )
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_employee_departments WHERE id = ?", (did,))
        except integrity_error_type():
            return jsonify({"error": "Bu departman zaten var."}), 409
        return jsonify({"department": dict(row)}), 201

    @bp.route("/employee-departments/<int:dept_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_employee_department(dept_id):
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_employee_departments WHERE id = ?", (dept_id,))
            if not row:
                return jsonify({"error": "Departman bulunamadı."}), 404
            used = scalar(conn, "SELECT COUNT(*) FROM acc_employees WHERE department = ?", (row["name"],))
            if used:
                return jsonify({"error": "Bu departmana bağlı personel var, silinemez."}), 400
            execute(conn, "DELETE FROM acc_employee_departments WHERE id = ?", (dept_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/salary-categories", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_salary_categories():
        with closing(get_db()) as conn:
            rows = fetch_salary_categories(conn)
        return jsonify({"salary_categories": rows})

    @bp.route("/salary-categories", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_salary_category():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Kategori adı zorunludur."}), 400
        is_office = 1 if data.get("is_office") else 0
        now = iso(utcnow())
        try:
            with closing(get_db()) as conn:
                base_slug = slugify_name(name)
                slug = unique_salary_slug(conn, base_slug)
                cid = insert_returning_id(
                    conn,
                    """
                    INSERT INTO acc_salary_categories (slug, name, is_office, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (slug, name, is_office, now),
                )
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_salary_categories WHERE id = ?", (cid,))
        except integrity_error_type():
            return jsonify({"error": "Bu kategori adı zaten var."}), 409
        item = dict(row)
        item["is_office"] = bool(item.get("is_office"))
        return jsonify({"salary_category": item}), 201

    @bp.route("/salary-categories/<int:cat_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_salary_category(cat_id):
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_salary_categories WHERE id = ?", (cat_id,))
            if not row:
                return jsonify({"error": "Kategori bulunamadı."}), 404
            used = scalar(
                conn,
                "SELECT COUNT(*) FROM acc_employees WHERE salary_category = ?",
                (row["slug"],),
            )
            if used:
                return jsonify({"error": "Bu kategoriye bağlı personel var, silinemez."}), 400
            execute(conn, "DELETE FROM acc_salary_categories WHERE id = ?", (cat_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Personel ──

    @bp.route("/employees", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_employees():
        period = period_from_request()
        with closing(get_db()) as conn:
            rows = fetchall(conn, "SELECT * FROM acc_employees ORDER BY name ASC")
            departments, salary_categories = payroll_context(conn)
            employees = [prepare_employee_row(r, period, salary_categories) for r in rows]
            payroll_data = compute_payroll_daily(
                [dict(r) for r in rows],
                period,
                include_office=payroll_include_office(),
                category_map=salary_categories,
            )
        return jsonify({
            **period_meta(period),
            "employees": employees,
            "monthly_payroll_total": payroll_data["period_accrual"],
            "payroll_accrual": payroll_data["period_accrual"],
            "departments": departments,
            "salary_categories": salary_categories,
            **permissions_meta(),
        })

    @bp.route("/employees", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_employee():
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            departments, salary_categories = payroll_context(conn)
            dept_names = [d["name"] for d in departments]
            payload, err = employee_payload(data, salary_categories=salary_categories, department_names=dept_names)
        if err:
            return jsonify({"error": err}), 400
        rates, rate_err = rates_from_request(data)
        if rate_err:
            return jsonify({"error": rate_err}), 400
        fx, err = build_money(payload["salary"], payload["currency"], rates)
        if err:
            return jsonify({"error": err}), 400

        now = iso(utcnow())
        with closing(get_db()) as conn:
            eid = insert_returning_id(
                conn,
                """
                INSERT INTO acc_employees
                (name, department, start_date, end_date, salary, currency,
                 salary_try, salary_usd, salary_eur, rate_usd_try, rate_eur_try,
                 salary_category, bank_salary, crypto_salary, advance_amount,
                 status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"], payload["department"], payload["start_date"], payload["end_date"],
                    fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"],
                    payload["salary_category"], payload["bank_salary"], payload["crypto_salary"],
                    payload["advance_amount"], payload["status"], now,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (eid,))
        return jsonify({
            "employee": prepare_employee_row(row, "all", salary_categories),
            "rates": used_rates_payload(fx),
            **permissions_meta(),
        }), 201

    @bp.route("/employees/<int:emp_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_employee(emp_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (emp_id,))
            if not row:
                return jsonify({"error": "Personel bulunamadı."}), 404

            departments, salary_categories = payroll_context(conn)
            dept_names = [d["name"] for d in departments]
            payload, err = employee_payload(
                data, dict(row), salary_categories=salary_categories, department_names=dept_names
            )
            if err:
                return jsonify({"error": err}), 400

            fallback = None
            if row.get("rate_usd_try") and row.get("rate_eur_try"):
                fallback = {"usd_try": float(row["rate_usd_try"]), "eur_try": float(row["rate_eur_try"])}
            rates, rate_err = rates_from_request(data, fallback=fallback)
            if rate_err:
                return jsonify({"error": rate_err}), 400
            fx, err = build_money(payload["salary"], payload["currency"], rates)
            if err:
                return jsonify({"error": err}), 400

            execute(
                conn,
                """
                UPDATE acc_employees
                SET name = ?, department = ?, start_date = ?, end_date = ?, salary = ?, currency = ?,
                    salary_try = ?, salary_usd = ?, salary_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?, salary_category = ?,
                    bank_salary = ?, crypto_salary = ?, advance_amount = ?, status = ?
                WHERE id = ?
                """,
                (
                    payload["name"], payload["department"], payload["start_date"], payload["end_date"],
                    fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], payload["salary_category"],
                    payload["bank_salary"], payload["crypto_salary"], payload["advance_amount"],
                    payload["status"], emp_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (emp_id,))
        return jsonify({"employee": prepare_employee_row(row, "all", salary_categories), **permissions_meta()})

    @bp.route("/employees/<int:emp_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_employee(emp_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_employees WHERE id = ?", (emp_id,))
            conn.commit()
        return jsonify({"ok": True})

    return bp
