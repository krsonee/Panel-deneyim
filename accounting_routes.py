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
    employee_accrual_for_range,
    employee_active_in_period,
    employee_daily_amount,
    enrich_employee_row,
    filter_payroll_employees,
    is_executive_salary_employee,
    redact_employee_for_view,
    validate_advance_amount,
    validate_office_amounts,
    validate_payment_split,
)
from accounting_period import (
    MONTH_PERIOD_RE,
    date_clause,
    default_accounting_period,
    is_period_locked,
    month_period_end_iso,
    month_period_from_date,
    parse_period,
    period_date_range,
    period_label,
)
from accounting_invoices import build_payment_invoices
from accounting_pronet import build_invoice_payload, calc_commission, reseed_period_from_history
from accounting_pl import (
    SECTION_LABELS as PL_SECTION_LABELS,
    add_line as pl_add_line,
    build_pl_payload,
    delete_line as pl_delete_line,
    reseed_period_from_history as pl_reseed_period_from_history,
    update_line as pl_update_line,
    upsert_meta as pl_upsert_meta,
)
from accounting_vault import (
    VAULT_ICONS,
    VAULT_PALETTE,
    build_vault_dashboard,
    build_vault_tx_payload,
    collect_method_suggestions,
    compute_running_balances,
    enrich_vault_transaction,
    suggest_exodus_trc20_fee,
)
from permissions import has_permission
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


def valid_month_period(period):
    raw = (period or "").strip()
    return raw if MONTH_PERIOD_RE.match(raw) else None


def resolve_commission_rate(conn, payment_method_id, ref_date=None, period=None):
    month = valid_month_period(period) or month_period_from_date(ref_date)
    if month:
        row = fetchone(
            conn,
            """
            SELECT commission_rate FROM acc_payment_method_rates
            WHERE payment_method_id = ? AND period = ?
            """,
            (payment_method_id, month),
        )
        if row is not None:
            return float(row["commission_rate"] or 0)
    pm = fetchone(conn, "SELECT commission_rate FROM acc_payment_methods WHERE id = ?", (payment_method_id,))
    return float(pm["commission_rate"] or 0) if pm else 0.0


def upsert_period_commission_rate(conn, payment_method_id, period, rate):
    month = valid_month_period(period)
    if not month:
        return False
    now = iso(utcnow())
    existing = fetchone(
        conn,
        "SELECT id FROM acc_payment_method_rates WHERE payment_method_id = ? AND period = ?",
        (payment_method_id, month),
    )
    if existing:
        execute(
            conn,
            """
            UPDATE acc_payment_method_rates
            SET commission_rate = ?, updated_at = ?
            WHERE id = ?
            """,
            (rate, now, existing["id"]),
        )
    else:
        insert_returning_id(
            conn,
            """
            INSERT INTO acc_payment_method_rates
            (payment_method_id, period, commission_rate, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (payment_method_id, month, rate, now, now),
        )
    return True


def payment_method_period_usage(conn, period):
    """Dönemde işlem sayısı: {payment_method_id: tx_count}."""
    month = valid_month_period(period)
    if not month:
        return {}
    date_sql, date_params = date_clause("tx_date", month)
    rows = fetchall(
        conn,
        f"""
        SELECT payment_method_id, COUNT(*) AS cnt
        FROM acc_finance_transactions
        WHERE 1=1{date_sql}
        GROUP BY payment_method_id
        """,
        date_params,
    )
    return {int(r["payment_method_id"]): int(r["cnt"] or 0) for r in rows}


def payment_method_tx_count(conn, payment_method_id, period=None, period_usage=None):
    if period_usage is not None:
        return period_usage.get(int(payment_method_id), 0)
    month = valid_month_period(period)
    if month:
        date_sql, date_params = date_clause("tx_date", month)
        params = (payment_method_id,) + date_params
        return int(
            scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM acc_finance_transactions
                WHERE payment_method_id = ?{date_sql}
                """,
                params,
            )
            or 0
        )
    return int(
        scalar(
            conn,
            "SELECT COUNT(*) FROM acc_finance_transactions WHERE payment_method_id = ?",
            (payment_method_id,),
        )
        or 0
    )


def enrich_payment_method(conn, row, period=None, period_usage=None):
    data = dict(row)
    data["global_commission_rate"] = float(data.get("commission_rate") or 0)
    month = valid_month_period(period)
    data["period"] = month
    data["period_rate_override"] = False
    if month:
        pr = fetchone(
            conn,
            """
            SELECT commission_rate FROM acc_payment_method_rates
            WHERE payment_method_id = ? AND period = ?
            """,
            (data["id"], month),
        )
        if pr is not None:
            data["commission_rate"] = float(pr["commission_rate"] or 0)
            data["period_rate_override"] = True
    cnt = payment_method_tx_count(conn, data["id"], period, period_usage)
    data["period_tx_count"] = cnt
    manual_active = data.get("manual_active")
    if manual_active is not None:
        data["period_active"] = bool(manual_active)
    else:
        data["period_active"] = cnt > 0
    data["manual_active"] = None if manual_active is None else bool(manual_active)
    return data


def compute_finance_commission(conn, payment_method_id, tx_date, fx, commission_rate_override=None):
    if commission_rate_override is not None:
        rate = float(commission_rate_override)
    else:
        rate = resolve_commission_rate(conn, payment_method_id, ref_date=tx_date)
    commission_orig = round(fx["amount"] * rate / 100, 2)
    comm_fx = convert_to_all(
        commission_orig,
        fx["currency"],
        {"usd_try": fx["rate_usd_try"], "eur_try": fx["rate_eur_try"]},
    )
    return rate, commission_orig, comm_fx


def insert_finance_transaction(
    conn,
    tx_date,
    payment_method_id,
    tx_type,
    fx,
    commission_rate_override=None,
):
    pm = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (payment_method_id,))
    if not pm:
        return None, "Payment yöntemi bulunamadı."
    if pm.get("tx_type") and pm["tx_type"] != tx_type:
        return None, "Seçilen payment bu işlem türü için tanımlı değil."
    rate, commission_orig, comm_fx = compute_finance_commission(
        conn, payment_method_id, tx_date, fx, commission_rate_override
    )
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
    return dict(row), None


def fetch_employee_departments(conn):
    return [dict(r) for r in fetchall(conn, "SELECT * FROM acc_employee_departments ORDER BY name ASC")]


def fetch_salary_categories(conn):
    rows = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_salary_categories ORDER BY name ASC")]
    for row in rows:
        row["is_office"] = bool(row.get("is_office"))
    return rows


def fetch_vaults(conn, active_only=True):
    sql = "SELECT * FROM acc_vaults"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY sort_order ASC, id ASC"
    return [dict(r) for r in fetchall(conn, sql)]


def fetch_vault_methods(conn):
    return [
        dict(r)
        for r in fetchall(
            conn,
            "SELECT * FROM acc_vault_methods ORDER BY sort_order ASC, name ASC",
        )
    ]


def fetch_vault_operation_types(conn):
    return [
        dict(r)
        for r in fetchall(
            conn,
            "SELECT * FROM acc_vault_operation_types ORDER BY sort_order ASC, name ASC",
        )
    ]


def vault_lookup_map(vaults):
    return {v["id"]: v for v in vaults}


def group_transactions_by_vault(rows):
    grouped = {}
    for row in rows:
        vid = row.get("vault_id")
        if vid is None:
            continue
        grouped.setdefault(vid, []).append(dict(row))
    return grouped


def unique_salary_slug(conn, base_slug):
    slug = base_slug
    n = 2
    while scalar(conn, "SELECT COUNT(*) FROM acc_salary_categories WHERE slug = ?", (slug,)):
        slug = f"{base_slug}_{n}"[:48]
        n += 1
    return slug


def calc_ggr_commission(ggr_amount, commission_rate):
    """GGR (Stake - Winning) üzerinden komisyon. Aylık toplamda negatif GGR için komisyon 0 kabul edilir."""
    ggr = float(ggr_amount or 0)
    rate = float(commission_rate or 0)
    if ggr <= 0:
        return 0.0
    return round(ggr * rate / 100.0, 2)


def build_invoice_calc_payload(conn, period):
    """Fatura Hesaplama (günlük GGR takip) — Pronet Fatura alanından bağımsız, kendi tablolarını kullanır."""
    providers = fetchall(
        conn,
        """
        SELECT id, section, name, commission_rate
        FROM acc_invoice_calc_providers
        WHERE active = 1
        ORDER BY CASE section WHEN 'sport' THEN 0 WHEN 'casino' THEN 1 WHEN 'special' THEN 2 ELSE 3 END, sort_order, name
        """,
    )
    provider_list = [dict(p) for p in providers]
    provider_map = {p["id"]: p for p in provider_list}

    rows = fetchall(
        conn,
        """
        SELECT entry_date, provider_id, stake_amount, winning_amount
        FROM acc_invoice_calc_daily
        WHERE period = ?
        ORDER BY entry_date, provider_id
        """,
        (period,),
    )

    entries = {}
    provider_agg = {}
    daily_agg = {}

    for r in rows:
        pid = r["provider_id"]
        provider = provider_map.get(pid)
        if not provider:
            continue
        entry_date = r["entry_date"]
        stake = float(r["stake_amount"] or 0)
        winning = float(r["winning_amount"] or 0)
        ggr = stake - winning
        row_commission = calc_ggr_commission(ggr, provider["commission_rate"])

        entries.setdefault(entry_date, {})[str(pid)] = {
            "stake_amount": round(stake, 2),
            "winning_amount": round(winning, 2),
            "ggr_amount": round(ggr, 2),
            "commission_amount": row_commission,
        }

        pa = provider_agg.setdefault(pid, {"stake_amount": 0.0, "winning_amount": 0.0})
        pa["stake_amount"] += stake
        pa["winning_amount"] += winning

        da = daily_agg.setdefault(entry_date, {"stake_amount": 0.0, "winning_amount": 0.0, "commission_amount": 0.0})
        da["stake_amount"] += stake
        da["winning_amount"] += winning
        da["commission_amount"] += row_commission

    provider_totals = []
    for pid, agg in provider_agg.items():
        provider = provider_map.get(pid)
        if not provider:
            continue
        ggr = agg["stake_amount"] - agg["winning_amount"]
        commission = calc_ggr_commission(ggr, provider["commission_rate"])
        provider_totals.append({
            "provider_id": pid,
            "name": provider["name"],
            "section": provider["section"],
            "commission_rate": provider["commission_rate"],
            "stake_amount": round(agg["stake_amount"], 2),
            "winning_amount": round(agg["winning_amount"], 2),
            "ggr_amount": round(ggr, 2),
            "commission_amount": commission,
        })
    provider_totals.sort(key=lambda x: x["commission_amount"], reverse=True)

    daily_totals = []
    for entry_date, agg in sorted(daily_agg.items()):
        daily_totals.append({
            "entry_date": entry_date,
            "stake_amount": round(agg["stake_amount"], 2),
            "winning_amount": round(agg["winning_amount"], 2),
            "ggr_amount": round(agg["stake_amount"] - agg["winning_amount"], 2),
            "commission_amount": round(agg["commission_amount"], 2),
        })

    grand_total = {
        "stake_amount": round(sum(p["stake_amount"] for p in provider_totals), 2),
        "winning_amount": round(sum(p["winning_amount"] for p in provider_totals), 2),
        "ggr_amount": round(sum(p["ggr_amount"] for p in provider_totals), 2),
        "commission_amount": round(sum(p["commission_amount"] for p in provider_totals), 2),
    }

    return {
        "period": period,
        "providers": provider_list,
        "entries": entries,
        "provider_totals": provider_totals,
        "daily_totals": daily_totals,
        "grand_total": grand_total,
    }


def expense_category_totals(conn, period):
    """Dashboard için kategori bazlı cari gider toplamları (0 girişli kategoriler de dahil)."""
    exp_sql, exp_params = date_clause("e.expense_date", period)
    rows = fetchall(
        conn,
        f"""
        SELECT c.id, c.name,
               COALESCE(SUM(e.amount_try), 0) AS amount_try,
               COALESCE(SUM(e.amount_usd), 0) AS amount_usd,
               COALESCE(SUM(e.amount_eur), 0) AS amount_eur
        FROM acc_expense_categories c
        LEFT JOIN acc_expenses e ON e.category_id = c.id{exp_sql}
        GROUP BY c.id, c.name
        ORDER BY c.name
        """,
        exp_params,
    )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "amount_try": round(float(r["amount_try"] or 0), 2),
            "amount_usd": round(float(r["amount_usd"] or 0), 2),
            "amount_eur": round(float(r["amount_eur"] or 0), 2),
        }
        for r in rows
    ]


def staff_daily_wage_all(staff_row, day):
    """Personel (Ofis/Türkiye) sekmesi — TRY/USD/EUR günlük yevmiye (Maaş Ödemeleri ile aynı mantık)."""
    return {cur: employee_daily_amount(staff_row, day, cur) for cur in CURRENCIES}


def staff_period_accrual_all(staff_row, period, reference=None):
    """Personel (Ofis/Türkiye) sekmesi — seçili ay için TRY/USD/EUR toplam hak ediş."""
    period_start, period_end = period_date_range(period, reference)
    if not period_start:
        return {cur: 0.0 for cur in CURRENCIES}
    return {
        cur: employee_accrual_for_range(staff_row, period_start, period_end, cur)
        for cur in CURRENCIES
    }


def create_accounting_blueprint(permission_required, superadmin_required=None):
    bp = Blueprint("accounting", __name__, url_prefix="/api/accounting")

    def acc_perm(*keys):
        return permission_required(*keys)

    def acc_superadmin(view):
        if superadmin_required is None:
            return permission_required(*MODULE_ACCESS)(view)
        return superadmin_required(view)

    def can_view_office_salaries():
        return has_permission(session.get("admin_permissions"), ACC_OFFICE_SALARIES)

    def can_view_executive_salaries():
        return (session.get("admin_username") or "").strip().lower() == "admin"

    def permissions_meta():
        return {
            "can_view_office_salaries": can_view_office_salaries(),
            "can_view_executive_salaries": can_view_executive_salaries(),
        }

    def payroll_include_office():
        return can_view_office_salaries()

    def payroll_source_rows(rows, category_map):
        return filter_payroll_employees(
            rows,
            can_view_office_salaries(),
            can_view_executive_salaries(),
            category_map,
        )

    def prepare_employee_row(row, period, category_map=None):
        enriched = enrich_employee_row(dict(row), period)
        return redact_employee_for_view(
            enriched,
            can_view_office_salaries(),
            category_map,
            can_view_executive=can_view_executive_salaries(),
        )

    def guard_executive_salary_fields(data, existing):
        if can_view_executive_salaries() or not is_executive_salary_employee(existing):
            return data
        blocked = {
            "salary", "currency", "bank_salary", "crypto_salary", "advance_amount",
            "bonus_amount", "crypto_wallet", "bank_iban", "bank_account_name",
        }
        cleaned = dict(data)
        for key in blocked:
            cleaned.pop(key, None)
        return cleaned

    def stored_rates(row):
        if not row:
            return None
        try:
            usd = float(row.get("rate_usd_try") or 0)
            eur = float(row.get("rate_eur_try") or 0)
        except (TypeError, ValueError):
            return None
        if usd <= 0 or eur <= 0:
            return None
        return {"usd_try": usd, "eur_try": eur}

    def rates_from_request(data, stored=None):
        usd = parse_rate(data.get("rate_usd_try"))
        eur = parse_rate(data.get("rate_eur_try"))
        if (usd and not eur) or (eur and not usd):
            return None, "USD/TL ve EUR/TL birlikte girilmeli veya ikisi de boş bırakılmalı."
        if usd and eur:
            return {"usd_try": usd, "eur_try": eur}, None
        # Yeni kayıt veya formda kur bilerek boş bırakıldı → kayıt anındaki canlı kur
        if data.get("auto_rate") or stored is None:
            auto = fetch_exchange_rates(fresh=True)
            if auto.get("source") == "fallback":
                return None, "Güncel kur alınamadı. USD/TL ve EUR/TL değerlerini manuel girin."
            return {"usd_try": auto["usd_try"], "eur_try": auto["eur_try"]}, None
        # Güncelleme: kur gönderilmediyse kayıtlı kuru koru
        prev = stored_rates(stored)
        if prev:
            return prev, None
        auto = fetch_exchange_rates(fresh=True)
        if auto.get("source") == "fallback":
            return None, "Güncel kur alınamadı. USD/TL ve EUR/TL değerlerini manuel girin."
        return {"usd_try": auto["usd_try"], "eur_try": auto["eur_try"]}, None

    def parse_amount(value):
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if amount < 0:
            return None
        return round(amount, 2)

    def parse_signed_amount(value):
        """P&L raporu satırları (yatırım/gider gibi) negatif olabilir — parse_amount'tan farklı olarak izin verir."""
        try:
            amount = float(value)
        except (TypeError, ValueError):
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
        fetched_at = rates.get("fetched_at")
        return {
            "currencies": list(CURRENCIES),
            "usd_try": rates["usd_try"],
            "eur_try": rates["eur_try"],
            "date": rates.get("date"),
            "source": rates.get("source"),
            "fetched_at": fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else fetched_at,
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

        salary = parse_amount(data.get("salary")) if data.get("salary") is not None else existing.get("salary")
        if salary is None:
            return None, "Geçerli maaş girin."

        bank = parse_office_amount(data.get("bank_salary")) if "bank_salary" in data else existing.get("bank_salary", 0)
        crypto = parse_office_amount(data.get("crypto_salary")) if "crypto_salary" in data else existing.get("crypto_salary", 0)
        advance = parse_office_amount(data.get("advance_amount")) if "advance_amount" in data else existing.get("advance_amount", 0)
        bonus = parse_office_amount(data.get("bonus_amount")) if "bonus_amount" in data else existing.get("bonus_amount", 0)
        if bank is None or crypto is None or advance is None or bonus is None:
            return None, "Ödeme tutarları geçersiz."
        if bonus < 0:
            return None, "Prim negatif olamaz."

        crypto_wallet = (
            data.get("crypto_wallet") if "crypto_wallet" in data else existing.get("crypto_wallet") or ""
        )
        bank_iban = (data.get("bank_iban") if "bank_iban" in data else existing.get("bank_iban") or "")
        bank_account_name = (
            data.get("bank_account_name") if "bank_account_name" in data else existing.get("bank_account_name") or ""
        )
        location = (data.get("location") if "location" in data else existing.get("location") or "")
        notes = (data.get("notes") if "notes" in data else existing.get("notes") or "")
        crypto_wallet = (crypto_wallet or "").strip()[:120]
        bank_iban = (bank_iban or "").strip().replace(" ", "")[:34]
        bank_account_name = (bank_account_name or "").strip()[:120]
        location = (location or "").strip()[:80]
        notes = (notes or "").strip()[:500]

        if not name:
            return None, "Personel adı zorunludur."
        if not department:
            return None, "Departman seçin veya yeni departman ekleyin."
        if not start_date:
            return None, "Geçerli başlangıç tarihi girin."

        date_err = validate_employee_dates(status, start_date, end_date)
        if date_err:
            return None, date_err

        pay_err = validate_payment_split(salary, bank, crypto, advance)
        if pay_err:
            return None, pay_err

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
            "bonus_amount": bonus,
            "crypto_wallet": crypto_wallet,
            "bank_iban": bank_iban,
            "bank_account_name": bank_account_name,
            "location": location,
            "notes": notes,
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
            payroll_source_rows(employees, salary_categories),
            period,
            include_office=True,
            category_map=salary_categories,
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
            deposit_commission = scalar(
                conn,
                f"SELECT COALESCE(SUM({comm}), 0) FROM acc_finance_transactions WHERE tx_type = 'deposit'{dep_sql}",
                dep_params,
            ) or 0
            withdrawal_commission = scalar(
                conn,
                f"SELECT COALESCE(SUM({comm}), 0) FROM acc_finance_transactions WHERE tx_type = 'withdrawal'{wdr_sql}",
                wdr_params,
            ) or 0
            commission = float(deposit_commission or 0) + float(withdrawal_commission or 0)
            expenses = scalar(
                conn,
                f"SELECT COALESCE(SUM({amt}), 0) FROM acc_expenses WHERE 1=1{exp_sql}",
                exp_params,
            ) or 0
            payroll = payroll_accrual.get(cur, 0)
            deposits = round(float(deposits), 2)
            withdrawals = round(float(withdrawals), 2)
            deposit_commission = round(float(deposit_commission), 2)
            withdrawal_commission = round(float(withdrawal_commission), 2)
            commission = round(commission, 2)
            expenses = round(float(expenses), 2)
            payroll = round(float(payroll), 2)
            result[cur] = {
                "total_deposits": deposits,
                "total_withdrawals": withdrawals,
                "total_deposit_commission": deposit_commission,
                "total_withdrawal_commission": withdrawal_commission,
                "total_commission": commission,
                "total_expenses": expenses,
                "payroll_monthly": payroll,
                "net_profit": round(deposits - withdrawals - commission - expenses, 2),
            }
        return result

    @bp.route("/exchange-rates", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def exchange_rates():
        try:
            return jsonify(rates_json(fetch_exchange_rates()))
        except Exception:
            return jsonify(rates_json(fetch_exchange_rates(force=True)))

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
        month_period = valid_month_period(period) or default_accounting_period()
        with closing(get_db()) as conn:
            kpi = kpi_for_period(conn, period)
            employees = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_employees")]
            departments, salary_categories = payroll_context(conn)
            expense_categories = expense_category_totals(conn, period)
            staff_rows = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_staff")]
            personnel_accrual = {cur: 0.0 for cur in CURRENCIES}
            for r in staff_rows:
                row_accrual = staff_period_accrual_all(r, month_period)
                for cur in CURRENCIES:
                    personnel_accrual[cur] = round(personnel_accrual[cur] + row_accrual[cur], 2)
            invoice_calc_payload = build_invoice_calc_payload(conn, month_period)
        payroll_daily = compute_payroll_daily(
            payroll_source_rows(employees, salary_categories),
            period,
            include_office=True,
            category_map=salary_categories,
        )
        try:
            rates = rates_json(fetch_exchange_rates())
        except Exception:
            rates = rates_json(fetch_exchange_rates(force=True))
        return jsonify({
            **period_meta(period),
            "kpi": kpi,
            "rates": rates,
            "payroll_daily": payroll_daily,
            "departments": departments,
            "salary_categories": salary_categories,
            "expense_categories": expense_categories,
            "personnel_accrual": personnel_accrual,
            "invoice_calc_estimate_try": invoice_calc_payload["grand_total"]["commission_amount"],
            **permissions_meta(),
        })

    # ── Payment methods (komisyon oranları) ──

    @bp.route("/payment-methods", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_payment_methods():
        tx_type = (request.args.get("tx_type") or "").strip().lower()
        period = valid_month_period(request.args.get("period") or "")
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
            usage = payment_method_period_usage(conn, period) if period else None
            methods = [enrich_payment_method(conn, r, period, usage) for r in rows]
        payload = {"payment_methods": methods}
        if period:
            payload.update({"period": period, "period_label": period_label(period)})
        return jsonify(payload)

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
                period = valid_month_period(data.get("period") or "")
                if period:
                    upsert_period_commission_rate(conn, pid, period, rate)
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (pid,))
                method = enrich_payment_method(conn, row, period)
        except integrity_error_type():
            label = "Yatırım" if tx_type == "deposit" else "Çekim"
            return jsonify({"error": f"Bu payment için {label} komisyonu zaten tanımlı."}), 409
        return jsonify({"payment_method": method}), 201

    @bp.route("/payment-methods/<int:method_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_payment_method(method_id):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        rate = data.get("commission_rate")
        period = valid_month_period(data.get("period") or "")
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
            if period and rate is not None:
                upsert_period_commission_rate(conn, method_id, period, rate)
                execute(
                    conn,
                    "UPDATE acc_payment_methods SET name = ?, updated_at = ? WHERE id = ?",
                    (new_name, now, method_id),
                )
            else:
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
                except integrity_error_type():
                    return jsonify({"error": "Bu payment ve işlem türü kombinasyonu zaten kayıtlı."}), 409
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (method_id,))
            method = enrich_payment_method(conn, row, period)
        return jsonify({"payment_method": method})

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

    @bp.route("/payment-methods/<int:method_id>/status", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_payment_method_status(method_id):
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period") or "")
        if "manual_active" in data:
            raw = data.get("manual_active")
        elif "active" in data:
            raw = data.get("active")
        else:
            return jsonify({"error": "active veya manual_active belirtilmeli."}), 400
        manual_active = None if raw is None else (1 if bool(raw) else 0)
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (method_id,))
            if not row:
                return jsonify({"error": "Payment bulunamadı."}), 404
            execute(
                conn,
                "UPDATE acc_payment_methods SET manual_active = ?, updated_at = ? WHERE id = ?",
                (manual_active, now, method_id),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (method_id,))
            method = enrich_payment_method(conn, row, period)
        return jsonify({"payment_method": method})

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

            rate_override = data.get("commission_rate")
            if rate_override is not None:
                rate_override = parse_amount(rate_override)
                if rate_override is None:
                    return jsonify({"error": "Geçerli komisyon oranı girin."}), 400

            row, err = insert_finance_transaction(
                conn,
                tx_date,
                payment_method_id,
                tx_type,
                fx,
                commission_rate_override=rate_override,
            )
            if err:
                return jsonify({"error": err}), 400
            conn.commit()
        return jsonify({"transaction": row, "rates": used_rates_payload(fx)}), 201

    @bp.route("/transactions/bulk", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def bulk_create_transactions():
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period") or "")
        if not period:
            return jsonify({"error": "Geçerli dönem girin (YYYY-MM)."}), 400
        default_date = month_period_end_iso(period)
        if not default_date:
            return jsonify({"error": "Geçerli dönem girin (YYYY-MM)."}), 400
        items = data.get("items") or []
        if not items:
            return jsonify({"error": "En az bir işlem girin."}), 400

        created, errors = [], []
        with closing(get_db()) as conn:
            for idx, item in enumerate(items, 1):
                tx_date = parse_date(item.get("tx_date")) or default_date
                tx_type = (item.get("tx_type") or "").strip().lower()
                amount = parse_amount(item.get("amount"))
                if tx_type not in ("deposit", "withdrawal"):
                    errors.append({"index": idx, "error": "İşlem türü Yatırım veya Çekim olmalı."})
                    continue
                if amount is None or amount <= 0:
                    errors.append({"index": idx, "error": "Geçerli miktar girin."})
                    continue
                rates, rate_err = rates_from_request(item)
                if rate_err:
                    errors.append({"index": idx, "error": rate_err})
                    continue
                fx, err = build_money(amount, item.get("currency"), rates)
                if err:
                    errors.append({"index": idx, "error": err})
                    continue
                try:
                    payment_method_id = int(item.get("payment_method_id"))
                except (TypeError, ValueError):
                    errors.append({"index": idx, "error": "Payment yöntemi seçin."})
                    continue

                rate_override = item.get("commission_rate")
                if rate_override is not None:
                    rate_override = parse_amount(rate_override)
                    if rate_override is None:
                        errors.append({"index": idx, "error": "Geçerli komisyon oranı girin."})
                        continue

                row, ins_err = insert_finance_transaction(
                    conn,
                    tx_date,
                    payment_method_id,
                    tx_type,
                    fx,
                    commission_rate_override=rate_override,
                )
                if ins_err:
                    errors.append({"index": idx, "error": ins_err})
                else:
                    created.append(row)
            conn.commit()
        return jsonify({
            "period": period,
            "period_label": period_label(period),
            "created": len(created),
            "transactions": created,
            "errors": errors,
        }), 201 if created else 400

    @bp.route("/transactions/<int:tx_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_transaction(tx_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            existing = fetchone(conn, "SELECT * FROM acc_finance_transactions WHERE id = ?", (tx_id,))
            if not existing:
                return jsonify({"error": "İşlem bulunamadı."}), 404

            tx_date = parse_date(data.get("tx_date")) or existing.get("tx_date")
            tx_type = (data.get("tx_type") or existing.get("tx_type") or "").strip().lower()
            amount = parse_amount(data.get("amount")) if data.get("amount") is not None else existing.get("amount")
            currency = parse_currency(data.get("currency") or existing.get("currency"))

            if not tx_date:
                return jsonify({"error": "Geçerli tarih girin."}), 400
            if tx_type not in ("deposit", "withdrawal"):
                return jsonify({"error": "İşlem türü Yatırım veya Çekim olmalı."}), 400
            if amount is None or amount <= 0:
                return jsonify({"error": "Geçerli miktar girin."}), 400
            if not currency:
                return jsonify({"error": "Para birimi seçin: TRY, USD veya EUR."}), 400

            try:
                payment_method_id = int(
                    data.get("payment_method_id")
                    if data.get("payment_method_id") is not None
                    else existing["payment_method_id"]
                )
            except (TypeError, ValueError):
                return jsonify({"error": "Payment yöntemi seçin."}), 400

            rates, rate_err = rates_from_request(data, stored=dict(existing))
            if rate_err:
                return jsonify({"error": rate_err}), 400
            fx, err = build_money(amount, currency, rates)
            if err:
                return jsonify({"error": err}), 400

            pm = fetchone(conn, "SELECT * FROM acc_payment_methods WHERE id = ?", (payment_method_id,))
            if not pm:
                return jsonify({"error": "Payment yöntemi bulunamadı."}), 404
            if pm.get("tx_type") and pm["tx_type"] != tx_type:
                return jsonify({"error": "Seçilen payment bu işlem türü için tanımlı değil."}), 400

            rate_override = data.get("commission_rate")
            if rate_override is not None:
                rate_override = parse_amount(rate_override)
                if rate_override is None:
                    return jsonify({"error": "Geçerli komisyon oranı girin."}), 400
            elif "commission_rate" not in data:
                rate_override = existing.get("commission_rate")
            else:
                rate_override = None

            rate, commission_orig, comm_fx = compute_finance_commission(
                conn, payment_method_id, tx_date, fx, commission_rate_override=rate_override
            )
            execute(
                conn,
                """
                UPDATE acc_finance_transactions
                SET tx_date = ?, payment_method_id = ?, tx_type = ?, amount = ?, currency = ?,
                    amount_try = ?, amount_usd = ?, amount_eur = ?,
                    commission_rate = ?, commission_amount = ?,
                    commission_amount_try = ?, commission_amount_usd = ?, commission_amount_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?
                WHERE id = ?
                """,
                (
                    tx_date, payment_method_id, tx_type, fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    rate, commission_orig,
                    comm_fx["TRY"], comm_fx["USD"], comm_fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], tx_id,
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
                (tx_id,),
            )
        return jsonify({"transaction": dict(row), "rates": used_rates_payload(fx)})

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

    @bp.route("/expenses/<int:expense_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_expense(expense_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            existing = fetchone(conn, "SELECT * FROM acc_expenses WHERE id = ?", (expense_id,))
            if not existing:
                return jsonify({"error": "Gider bulunamadı."}), 404

            expense_date = parse_date(data.get("expense_date")) or existing.get("expense_date")
            description = (
                (data.get("description") if "description" in data else existing.get("description") or "")
            ).strip()
            try:
                category_id = int(data.get("category_id")) if data.get("category_id") is not None else int(existing["category_id"])
            except (TypeError, ValueError):
                return jsonify({"error": "Gider kategorisi seçin."}), 400

            amount = parse_amount(data.get("amount")) if data.get("amount") is not None else existing.get("amount")
            currency = parse_currency(data.get("currency") or existing.get("currency"))

            if not expense_date:
                return jsonify({"error": "Geçerli tarih girin."}), 400
            if amount is None or amount <= 0:
                return jsonify({"error": "Geçerli tutar girin."}), 400
            if not currency:
                return jsonify({"error": "Para birimi seçin: TRY, USD veya EUR."}), 400

            rates, rate_err = rates_from_request(data, stored=dict(existing))
            if rate_err:
                return jsonify({"error": rate_err}), 400
            fx, err = build_money(amount, currency, rates)
            if err:
                return jsonify({"error": err}), 400

            cat = fetchone(conn, "SELECT id FROM acc_expense_categories WHERE id = ?", (category_id,))
            if not cat:
                return jsonify({"error": "Kategori bulunamadı."}), 404

            execute(
                conn,
                """
                UPDATE acc_expenses
                SET expense_date = ?, category_id = ?, description = ?, amount = ?, currency = ?,
                    amount_try = ?, amount_usd = ?, amount_eur = ?, rate_usd_try = ?, rate_eur_try = ?
                WHERE id = ?
                """,
                (
                    expense_date, category_id, description, fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], expense_id,
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
                (expense_id,),
            )
        return jsonify({"expense": dict(row), "rates": used_rates_payload(fx)})

    @bp.route("/expenses/<int:expense_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_expense(expense_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_expenses WHERE id = ?", (expense_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Kasa takip ──

    @bp.route("/vaults", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_vaults():
        with closing(get_db()) as conn:
            vaults = fetch_vaults(conn, active_only=False)
            txs = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_vault_transactions ORDER BY tx_date ASC, id ASC")]
        lookup = vault_lookup_map(vaults)
        grouped = group_transactions_by_vault(txs)
        period = period_from_request()
        p_start, p_end = period_date_range(period)
        p_start_s = p_start.isoformat() if p_start else None
        p_end_s = p_end.isoformat() if p_end else None
        dashboard = build_vault_dashboard(vaults, grouped, p_start_s, p_end_s)
        return jsonify({"vaults": dashboard["vaults"], "totals": dashboard["totals"]})

    @bp.route("/vaults", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_vault():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Kasa adı zorunludur."}), 400
        description = (data.get("description") or "").strip()
        try:
            opening_usdt = float(data.get("opening_usdt") or 0)
            opening_try = float(data.get("opening_try") or 0)
        except (TypeError, ValueError):
            return jsonify({"error": "Açılış bakiyesi geçersiz."}), 400

        now = iso(utcnow())
        with closing(get_db()) as conn:
            count = scalar(conn, "SELECT COUNT(*) FROM acc_vaults") or 0
            color = (data.get("color") or VAULT_PALETTE[count % len(VAULT_PALETTE)]).strip()
            icon = (data.get("icon") or VAULT_ICONS[count % len(VAULT_ICONS)]).strip()
            try:
                vid = insert_returning_id(
                    conn,
                    """
                    INSERT INTO acc_vaults
                    (name, description, color, icon, opening_usdt, opening_try, sort_order, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (name, description, color, icon, opening_usdt, opening_try, count, now),
                )
                conn.commit()
            except Exception as exc:
                if integrity_error_type(exc):
                    return jsonify({"error": "Bu kasa adı zaten var."}), 409
                raise
            row = fetchone(conn, "SELECT * FROM acc_vaults WHERE id = ?", (vid,))
        return jsonify({"vault": dict(row)}), 201

    @bp.route("/vaults/<int:vault_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_vault(vault_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            existing = fetchone(conn, "SELECT * FROM acc_vaults WHERE id = ?", (vault_id,))
            if not existing:
                return jsonify({"error": "Kasa bulunamadı."}), 404

            fields = []
            params = []
            if "name" in data:
                name = (data.get("name") or "").strip()
                if not name:
                    return jsonify({"error": "Kasa adı boş olamaz."}), 400
                fields.append("name = ?")
                params.append(name)
            for key in ("description", "color", "icon"):
                if key in data:
                    fields.append(f"{key} = ?")
                    params.append((data.get(key) or "").strip())
            for key in ("opening_usdt", "opening_try", "sort_order", "is_active"):
                if key in data:
                    try:
                        val = int(data[key]) if key in ("sort_order", "is_active") else float(data[key])
                    except (TypeError, ValueError):
                        return jsonify({"error": f"{key} geçersiz."}), 400
                    fields.append(f"{key} = ?")
                    params.append(val)

            if not fields:
                return jsonify({"vault": dict(existing)})
            params.append(vault_id)
            try:
                execute(conn, f"UPDATE acc_vaults SET {', '.join(fields)} WHERE id = ?", params)
                conn.commit()
            except Exception as exc:
                if integrity_error_type(exc):
                    return jsonify({"error": "Bu kasa adı zaten var."}), 409
                raise
            row = fetchone(conn, "SELECT * FROM acc_vaults WHERE id = ?", (vault_id,))
        return jsonify({"vault": dict(row)})

    @bp.route("/vaults/<int:vault_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_vault(vault_id):
        with closing(get_db()) as conn:
            tx_count = scalar(
                conn,
                "SELECT COUNT(*) FROM acc_vault_transactions WHERE vault_id = ?",
                (vault_id,),
            )
            if tx_count:
                execute(conn, "UPDATE acc_vaults SET is_active = 0 WHERE id = ?", (vault_id,))
            else:
                execute(conn, "DELETE FROM acc_vaults WHERE id = ?", (vault_id,))
            conn.commit()
        return jsonify({"ok": True, "deactivated": bool(tx_count)})

    @bp.route("/vault-methods", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_vault_methods():
        with closing(get_db()) as conn:
            presets = fetch_vault_methods(conn)
            txs = fetchall(conn, "SELECT method_name FROM acc_vault_transactions")
        names = collect_method_suggestions([dict(r) for r in txs], [p["name"] for p in presets])
        return jsonify({"methods": names, "method_options": presets})

    @bp.route("/vault-methods", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_vault_method():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Yöntem adı zorunludur."}), 400
        now = iso(utcnow())
        try:
            with closing(get_db()) as conn:
                count = scalar(conn, "SELECT COUNT(*) FROM acc_vault_methods") or 0
                mid = insert_returning_id(
                    conn,
                    "INSERT INTO acc_vault_methods (name, sort_order, created_at) VALUES (?, ?, ?)",
                    (name, count, now),
                )
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_vault_methods WHERE id = ?", (mid,))
        except integrity_error_type():
            return jsonify({"error": "Bu yöntem zaten var."}), 409
        return jsonify({"method": dict(row)}), 201

    @bp.route("/vault-methods/<int:method_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_vault_method(method_id):
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_vault_methods WHERE id = ?", (method_id,))
            if not row:
                return jsonify({"error": "Yöntem bulunamadı."}), 404
            used = scalar(
                conn,
                "SELECT COUNT(*) FROM acc_vault_transactions WHERE method_name = ?",
                (row["name"],),
            )
            if used:
                return jsonify({"error": "Bu yönteme bağlı kasa hareketleri var, silinemez."}), 400
            execute(conn, "DELETE FROM acc_vault_methods WHERE id = ?", (method_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/vault-operation-types", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_vault_operation_types():
        with closing(get_db()) as conn:
            presets = fetch_vault_operation_types(conn)
            txs = fetchall(conn, "SELECT operation_type FROM acc_vault_transactions")
        names = collect_method_suggestions(
            [dict(r) for r in txs], [p["name"] for p in presets], field="operation_type"
        )
        return jsonify({"operation_types": names, "operation_type_options": presets})

    @bp.route("/vault-operation-types", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_vault_operation_type():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "İşlem başlığı zorunludur."}), 400
        now = iso(utcnow())
        try:
            with closing(get_db()) as conn:
                count = scalar(conn, "SELECT COUNT(*) FROM acc_vault_operation_types") or 0
                oid = insert_returning_id(
                    conn,
                    "INSERT INTO acc_vault_operation_types (name, sort_order, created_at) VALUES (?, ?, ?)",
                    (name, count, now),
                )
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_vault_operation_types WHERE id = ?", (oid,))
        except integrity_error_type():
            return jsonify({"error": "Bu işlem başlığı zaten var."}), 409
        return jsonify({"operation_type": dict(row)}), 201

    @bp.route("/vault-operation-types/<int:optype_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_vault_operation_type(optype_id):
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_vault_operation_types WHERE id = ?", (optype_id,))
            if not row:
                return jsonify({"error": "İşlem başlığı bulunamadı."}), 404
            used = scalar(
                conn,
                "SELECT COUNT(*) FROM acc_vault_transactions WHERE operation_type = ?",
                (row["name"],),
            )
            if used:
                return jsonify({"error": "Bu başlığa bağlı kasa hareketleri var, silinemez."}), 400
            execute(conn, "DELETE FROM acc_vault_operation_types WHERE id = ?", (optype_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/vault-transactions/suggest-fee", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def suggest_vault_fee():
        direction = (request.args.get("direction") or "out").strip().lower()
        try:
            amount = float(request.args.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0
        fee, note = suggest_exodus_trc20_fee(amount, direction)
        return jsonify({"fee_usdt": fee, "note": note, "auto": False})

    @bp.route("/vault-transactions", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_vault_transactions():
        period = period_from_request()
        vault_id = request.args.get("vault_id", type=int)
        date_sql, date_params = date_clause("tx_date", period)
        with closing(get_db()) as conn:
            vaults = fetch_vaults(conn, active_only=False)
            lookup = vault_lookup_map(vaults)
            all_rows = [
                dict(r)
                for r in fetchall(
                    conn,
                    """
                    SELECT * FROM acc_vault_transactions
                    ORDER BY tx_date ASC, id ASC
                    """,
                )
            ]
            filtered_rows = [
                dict(r)
                for r in fetchall(
                    conn,
                    f"""
                    SELECT * FROM acc_vault_transactions
                    WHERE 1=1{date_sql}
                    ORDER BY tx_date DESC, id DESC
                    """,
                    date_params,
                )
            ]
            methods = fetch_vault_methods(conn)
            optypes = fetch_vault_operation_types(conn)

        if vault_id:
            filtered_rows = [r for r in filtered_rows if r.get("vault_id") == vault_id]

        balance_by_id = {}
        grouped_full = group_transactions_by_vault(all_rows)
        for vid, vtxs in grouped_full.items():
            vault = lookup.get(vid)
            opening_usdt = vault.get("opening_usdt") if vault else 0
            opening_try = vault.get("opening_try") if vault else 0
            _, bmap = compute_running_balances(vtxs, opening_usdt, opening_try, lookup)
            balance_by_id.update(bmap)

        enriched = []
        for row in filtered_rows:
            item = enrich_vault_transaction(dict(row), lookup)
            bal = balance_by_id.get(row["id"])
            if bal:
                item["balance_usdt"] = bal.get("balance_usdt")
                item["balance_try"] = bal.get("balance_try")
            enriched.append(item)

        p_start, p_end = period_date_range(period)
        p_start_s = p_start.isoformat() if p_start else None
        p_end_s = p_end.isoformat() if p_end else None
        active_vaults = [v for v in vaults if v.get("is_active")]
        dashboard = build_vault_dashboard(active_vaults, grouped_full, p_start_s, p_end_s)
        method_names = collect_method_suggestions(all_rows, [m["name"] for m in methods])
        optype_names = collect_method_suggestions(
            all_rows, [o["name"] for o in optypes], field="operation_type"
        )

        return jsonify(
            {
                **period_meta(period),
                "vaults": dashboard["vaults"],
                "totals": dashboard["totals"],
                "methods": method_names,
                "method_options": methods,
                "operation_types": optype_names,
                "operation_type_options": optypes,
                "vault_transactions": enriched,
            }
        )

    def prepare_vault_tx_request(data):
        """POST/PUT için ortak doğrulama — (tx_date, vault_id, vault_name, payload) veya hata."""
        tx_date = parse_date(data.get("tx_date"))
        description = (data.get("description") or "").strip()
        method_name = (data.get("method_name") or "").strip()
        operation_type = (data.get("operation_type") or "").strip()

        if not tx_date:
            return None, (jsonify({"error": "Geçerli tarih girin."}), 400)

        direction = (data.get("direction") or data.get("tx_type") or "").strip().lower()
        usdt_amount = data.get("usdt_amount")
        if usdt_amount is None:
            usdt_amount = data.get("amount")

        rate_usd = parse_rate(data.get("rate_usd_try"))
        payload = None
        if direction in ("in", "out") and usdt_amount not in (None, ""):
            if not rate_usd:
                rates, rate_err = rates_from_request(data)
                if rate_err:
                    return None, (jsonify({"error": rate_err}), 400)
                rate_usd = rates["usd_try"]
            payload, err = build_vault_tx_payload(
                usdt_amount,
                direction,
                rate_usd,
                description,
                method_name,
                fee_usdt=data.get("fee_usdt"),
                operation_type=operation_type,
            )
            if err:
                return None, (jsonify({"error": err}), 400)
        else:
            tx_type = direction
            amount = parse_amount(data.get("amount"))
            if tx_type not in ("in", "out"):
                return None, (jsonify({"error": "İşlem yönü Gelen veya Giden olmalı."}), 400)
            if amount is None or amount <= 0:
                return None, (jsonify({"error": "Geçerli tutar girin."}), 400)
            rates, rate_err = rates_from_request(data)
            if rate_err:
                return None, (jsonify({"error": rate_err}), 400)
            fx, fx_err = build_money(amount, data.get("currency"), rates)
            if fx_err:
                return None, (jsonify({"error": fx_err}), 400)
            payload = {
                "tx_type": tx_type,
                "method_name": method_name,
                "operation_type": operation_type,
                "description": description,
                "usdt_in": fx["USD"] if tx_type == "in" else 0,
                "usdt_out": fx["USD"] if tx_type == "out" else 0,
                "amount": fx["amount"],
                "currency": fx["currency"],
                "amount_usd": fx["USD"],
                "amount_try": fx["TRY"],
                "amount_eur": fx["EUR"],
                "rate_usd_try": fx["rate_usd_try"],
                "rate_eur_try": fx["rate_eur_try"],
            }

        vault_id = data.get("vault_id")
        vault_name = (data.get("vault_name") or "").strip()
        with closing(get_db()) as conn:
            if vault_id:
                vault = fetchone(conn, "SELECT * FROM acc_vaults WHERE id = ?", (int(vault_id),))
                if not vault:
                    return None, (jsonify({"error": "Kasa bulunamadı."}), 404)
                vault_id = vault["id"]
                vault_name = vault["name"]
            elif vault_name:
                vault = fetchone(conn, "SELECT * FROM acc_vaults WHERE name = ?", (vault_name,))
                if not vault:
                    return None, (jsonify({"error": "Kasa bulunamadı."}), 404)
                vault_id = vault["id"]
            else:
                return None, (jsonify({"error": "Kasa seçin."}), 400)

        return (tx_date, vault_id, vault_name, payload), None

    def vault_tx_row_values(tx_date, vault_id, vault_name, payload):
        return (
            tx_date,
            vault_id,
            vault_name,
            payload["tx_type"],
            payload.get("method_name", ""),
            payload.get("operation_type", ""),
            payload.get("description", ""),
            payload["amount"],
            payload.get("currency", "USD"),
            payload.get("usdt_in", 0),
            payload.get("usdt_out", 0),
            payload.get("fee_usdt", 0),
            payload.get("amount_try", 0),
            payload.get("amount_usd", 0),
            payload.get("amount_eur", 0),
            payload.get("rate_usd_try", 0),
            payload.get("rate_eur_try", 0),
        )

    @bp.route("/vault-transactions", methods=["POST"])
    @acc_perm(*MODULE_ACCESS)
    def create_vault_transaction():
        data = request.get_json(silent=True) or {}
        prepared, err = prepare_vault_tx_request(data)
        if err:
            return err
        tx_date, vault_id, vault_name, payload = prepared

        with closing(get_db()) as conn:
            now = iso(utcnow())
            vid = insert_returning_id(
                conn,
                """
                INSERT INTO acc_vault_transactions
                (tx_date, vault_id, vault_name, tx_type, method_name, operation_type, description,
                 amount, currency, usdt_in, usdt_out, fee_usdt,
                 amount_try, amount_usd, amount_eur, rate_usd_try, rate_eur_try, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                vault_tx_row_values(tx_date, vault_id, vault_name, payload) + (now,),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_vault_transactions WHERE id = ?", (vid,))

        enriched = enrich_vault_transaction(dict(row))
        return jsonify(
            {
                "vault_transaction": enriched,
                "rates": {"usd_try": enriched.get("rate_display"), "eur_try": enriched.get("rate_eur_try")},
            }
        ), 201

    @bp.route("/vault-transactions/<int:tx_id>", methods=["PUT"])
    @acc_perm(*MODULE_ACCESS)
    def update_vault_transaction(tx_id):
        data = request.get_json(silent=True) or {}
        prepared, err = prepare_vault_tx_request(data)
        if err:
            return err
        tx_date, vault_id, vault_name, payload = prepared

        with closing(get_db()) as conn:
            existing = fetchone(conn, "SELECT id FROM acc_vault_transactions WHERE id = ?", (tx_id,))
            if not existing:
                return jsonify({"error": "Kayıt bulunamadı."}), 404
            execute(
                conn,
                """
                UPDATE acc_vault_transactions
                SET tx_date = ?, vault_id = ?, vault_name = ?, tx_type = ?, method_name = ?,
                    operation_type = ?, description = ?, amount = ?, currency = ?,
                    usdt_in = ?, usdt_out = ?, fee_usdt = ?,
                    amount_try = ?, amount_usd = ?, amount_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?
                WHERE id = ?
                """,
                vault_tx_row_values(tx_date, vault_id, vault_name, payload) + (tx_id,),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_vault_transactions WHERE id = ?", (tx_id,))

        enriched = enrich_vault_transaction(dict(row))
        return jsonify(
            {
                "vault_transaction": enriched,
                "rates": {"usd_try": enriched.get("rate_display"), "eur_try": enriched.get("rate_eur_try")},
            }
        )

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

    def fx_from_row(row):
        return {
            "amount": float(row["salary"]),
            "currency": row["currency"] or "TRY",
            "TRY": float(row["salary_try"] or 0),
            "USD": float(row["salary_usd"] or 0),
            "EUR": float(row["salary_eur"] or 0),
            "rate_usd_try": float(row["rate_usd_try"] or 0),
            "rate_eur_try": float(row["rate_eur_try"] or 0),
        }

    def needs_fx_recalc(data, row):
        if any(k in data for k in ("rate_usd_try", "rate_eur_try", "auto_rate")):
            return True
        if "salary" in data and round(float(data["salary"]), 2) != round(float(row["salary"]), 2):
            return True
        if "currency" in data and (data.get("currency") or "").upper() != (row.get("currency") or "TRY").upper():
            return True
        return False

    def apply_employee_update(conn, emp_id, payload, fx):
        execute(
            conn,
            """
            UPDATE acc_employees
            SET name = ?, department = ?, start_date = ?, end_date = ?, salary = ?, currency = ?,
                salary_try = ?, salary_usd = ?, salary_eur = ?,
                rate_usd_try = ?, rate_eur_try = ?, salary_category = ?,
                bank_salary = ?, crypto_salary = ?, advance_amount = ?, bonus_amount = ?,
                crypto_wallet = ?, bank_iban = ?, bank_account_name = ?,
                location = ?, notes = ?, status = ?
            WHERE id = ?
            """,
            (
                payload["name"], payload["department"], payload["start_date"], payload["end_date"],
                fx["amount"], fx["currency"],
                fx["TRY"], fx["USD"], fx["EUR"],
                fx["rate_usd_try"], fx["rate_eur_try"], payload["salary_category"],
                payload["bank_salary"], payload["crypto_salary"], payload["advance_amount"],
                payload["bonus_amount"],
                payload["crypto_wallet"], payload["bank_iban"], payload["bank_account_name"],
                payload["location"], payload["notes"],
                payload["status"], emp_id,
            ),
        )

    @bp.route("/employees", methods=["GET"])
    @acc_perm(*MODULE_ACCESS)
    def list_employees():
        period = period_from_request()
        with closing(get_db()) as conn:
            all_rows = fetchall(conn, "SELECT * FROM acc_employees ORDER BY department ASC, name ASC")
            departments, salary_categories = payroll_context(conn)
            rows = [
                r for r in all_rows
                if employee_active_in_period(dict(r), period)
            ]
            employees = [prepare_employee_row(r, period, salary_categories) for r in rows]
            payroll_data = compute_payroll_daily(
                payroll_source_rows([dict(r) for r in rows], salary_categories),
                period,
                include_office=True,
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
                 salary_category, bank_salary, crypto_salary, advance_amount, bonus_amount,
                 crypto_wallet, bank_iban, bank_account_name, location, notes, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"], payload["department"], payload["start_date"], payload["end_date"],
                    fx["amount"], fx["currency"],
                    fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"],
                    payload["salary_category"], payload["bank_salary"], payload["crypto_salary"],
                    payload["advance_amount"], payload["bonus_amount"], payload["crypto_wallet"],
                    payload["bank_iban"], payload["bank_account_name"], payload["location"],
                    payload["notes"], payload["status"], now,
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

            if set(data.keys()) == {"advance_amount"}:
                if not can_view_executive_salaries() and is_executive_salary_employee(dict(row)):
                    return jsonify({"error": "Bu personelin maaş bilgilerine erişim yetkiniz yok."}), 403
                advance = parse_office_amount(data.get("advance_amount"))
                if advance is None:
                    return jsonify({"error": "Geçerli avans tutarı girin."}), 400
                adv_err = validate_advance_amount(row["salary"], advance)
                if adv_err:
                    return jsonify({"error": adv_err}), 400
                execute(
                    conn,
                    "UPDATE acc_employees SET advance_amount = ? WHERE id = ?",
                    (advance, emp_id),
                )
                conn.commit()
                row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (emp_id,))
                return jsonify({
                    "employee": prepare_employee_row(row, "all", salary_categories),
                    **permissions_meta(),
                })

            data = guard_executive_salary_fields(data, dict(row))
            payload, err = employee_payload(
                data, dict(row), salary_categories=salary_categories, department_names=dept_names
            )
            if err:
                return jsonify({"error": err}), 400

            if needs_fx_recalc(data, dict(row)):
                rates, rate_err = rates_from_request(data, stored=dict(row))
                if rate_err:
                    return jsonify({"error": rate_err}), 400
                fx, err = build_money(payload["salary"], payload["currency"], rates)
                if err:
                    return jsonify({"error": err}), 400
            else:
                fx = fx_from_row(dict(row))
                fx["amount"] = payload["salary"]
                fx["currency"] = payload["currency"]

            apply_employee_update(conn, emp_id, payload, fx)
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_employees WHERE id = ?", (emp_id,))
        period = period_from_request()
        return jsonify({
            "employee": prepare_employee_row(row, period, salary_categories),
            **permissions_meta(),
        })

    @bp.route("/employees/<int:emp_id>", methods=["DELETE"])
    @acc_perm(*MODULE_ACCESS)
    def delete_employee(emp_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_employees WHERE id = ?", (emp_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/invoices", methods=["GET"])
    @acc_perm("accounting.invoices", *ACC_READ)
    def list_payment_invoices():
        period = valid_month_period(request.args.get("period") or "")
        if not period:
            period = valid_month_period(period_from_request()) or default_accounting_period()
        with closing(get_db()) as conn:
            payload = build_payment_invoices(conn, period, resolve_commission_rate)
        return jsonify({**period_meta(period), **payload})

    @bp.route("/pronet-invoice", methods=["GET"])
    @acc_perm(*ACC_READ)
    def get_pronet_invoice():
        period = valid_month_period(request.args.get("period")) or period_from_request()
        if not period or period == "all":
            period = default_accounting_period()
        with closing(get_db()) as conn:
            payload = build_invoice_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pronet-invoice/meta", methods=["PUT"])
    @acc_perm("accounting.invoices", *MODULE_ACCESS)
    def update_pronet_invoice_meta():
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period")) or period_from_request()
        if not period or period == "all":
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        if is_period_locked(period):
            return jsonify({"error": "Kilitli dönem — düzenlenemez."}), 403
        now = iso(utcnow())
        gross = parse_amount(data.get("gross_revenue_try"))
        eur_rate = parse_amount(data.get("eur_try_rate"))
        sms = parse_amount(data.get("sms_fee_try"))
        notes = (data.get("notes") or "").strip()
        with closing(get_db()) as conn:
            exists = scalar(conn, "SELECT COUNT(*) FROM acc_pronet_period_meta WHERE period = ?", (period,))
            if exists:
                execute(
                    conn,
                    """
                    UPDATE acc_pronet_period_meta
                    SET gross_revenue_try = COALESCE(?, gross_revenue_try),
                        eur_try_rate = COALESCE(?, eur_try_rate),
                        sms_fee_try = COALESCE(?, sms_fee_try),
                        notes = ?, updated_at = ?
                    WHERE period = ?
                    """,
                    (gross, eur_rate, sms, notes, now, period),
                )
            else:
                execute(
                    conn,
                    """
                    INSERT INTO acc_pronet_period_meta
                    (period, gross_revenue_try, eur_try_rate, sms_fee_try, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (period, gross or 0, eur_rate or 45.436, sms or 0, notes, now),
                )
            if eur_rate:
                fixed_lines = fetchall(
                    conn,
                    """
                    SELECT l.id, f.amount_eur
                    FROM acc_pronet_period_lines l
                    JOIN acc_pronet_fixed_fees f ON f.id = l.fixed_fee_id
                    WHERE l.period = ? AND l.line_kind = 'fixed'
                    """,
                    (period,),
                )
                for row in fixed_lines:
                    amount_try = round(float(row["amount_eur"]) * float(eur_rate), 2)
                    execute(
                        conn,
                        """
                        UPDATE acc_pronet_period_lines
                        SET volume_try = ?, commission_try = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (float(row["amount_eur"]), amount_try, now, row["id"]),
                    )
            conn.commit()
            payload = build_invoice_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pronet-invoice/lines", methods=["PUT"])
    @acc_perm("accounting.invoices", *MODULE_ACCESS)
    def update_pronet_invoice_lines():
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period")) or period_from_request()
        if not period or period == "all":
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        if is_period_locked(period):
            return jsonify({"error": "Kilitli dönem — düzenlenemez."}), 403
        items = data.get("lines") or []
        now = iso(utcnow())
        with closing(get_db()) as conn:
            for item in items:
                line_id = item.get("id")
                if not line_id:
                    continue
                row = fetchone(
                    conn,
                    "SELECT * FROM acc_pronet_period_lines WHERE id = ? AND period = ?",
                    (line_id, period),
                )
                if not row:
                    continue
                volume = parse_amount(item.get("volume_try"))
                jackpot = parse_amount(item.get("jackpot_try"))
                rate = parse_amount(item.get("commission_rate"))
                manual = item.get("manual_commission")
                manual_val = parse_amount(manual) if manual is not None and manual != "" else None
                if row["line_kind"] == "fixed":
                    continue
                vol = volume if volume is not None else float(row["volume_try"] or 0)
                jp = jackpot if jackpot is not None else float(row["jackpot_try"] or 0)
                rt = rate if rate is not None else float(row["commission_rate"] or 0)
                comm = calc_commission(vol, jp, rt, manual_val)
                execute(
                    conn,
                    """
                    UPDATE acc_pronet_period_lines
                    SET volume_try = ?, jackpot_try = ?, commission_rate = ?,
                        commission_try = ?, manual_commission = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (vol, jp, rt, comm, manual_val, now, line_id),
                )
            conn.commit()
            payload = build_invoice_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pronet-invoice/reseed", methods=["POST"])
    @acc_superadmin
    def reseed_pronet_invoice():
        """Gecmis PDF faturasindan okunan verilerle bir donemi yeniden yukler.
        Sadece superadmin yetkisi olan hesaplar kullanabilir, kilit kontrolunu
        kasitli olarak atlar (gecmis fatura verisi duzeltme/yukleme araci)."""
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period"))
        if not period:
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        with closing(get_db()) as conn:
            ok = reseed_period_from_history(conn, period)
            if not ok:
                return jsonify({"error": "Bu dönem için geçmiş fatura verisi tanımlı değil."}), 404
            payload = build_invoice_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pronet-providers/<int:provider_id>", methods=["PUT"])
    @acc_perm("accounting.invoices", *MODULE_ACCESS)
    def update_pronet_provider(provider_id):
        data = request.get_json(silent=True) or {}
        rate = parse_amount(data.get("commission_rate"))
        if rate is None:
            return jsonify({"error": "Geçerli komisyon oranı girin."}), 400
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT id FROM acc_pronet_providers WHERE id = ?", (provider_id,))
            if not row:
                return jsonify({"error": "Sağlayıcı bulunamadı."}), 404
            execute(
                conn,
                "UPDATE acc_pronet_providers SET commission_rate = ? WHERE id = ?",
                (rate, provider_id),
            )
            conn.commit()
        return jsonify({"ok": True, "commission_rate": rate})

    @bp.route("/pronet-fixed-fees/<int:fee_id>", methods=["PUT"])
    @acc_perm("accounting.invoices", *MODULE_ACCESS)
    def update_pronet_fixed_fee(fee_id):
        data = request.get_json(silent=True) or {}
        amount_eur = parse_amount(data.get("amount_eur"))
        if amount_eur is None:
            return jsonify({"error": "Geçerli EUR tutarı girin."}), 400
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT id FROM acc_pronet_fixed_fees WHERE id = ?", (fee_id,))
            if not row:
                return jsonify({"error": "Sabit ücret bulunamadı."}), 404
            execute(
                conn,
                "UPDATE acc_pronet_fixed_fees SET amount_eur = ? WHERE id = ?",
                (amount_eur, fee_id),
            )
            conn.commit()
        return jsonify({"ok": True, "amount_eur": amount_eur})

    # --- Fatura Hesaplama (günlük GGR takip) — Pronet Fatura alanından tamamen bağımsız ---

    @bp.route("/invoice-calc", methods=["GET"])
    @acc_perm("accounting.invoice_calc", *ACC_READ)
    def get_invoice_calc():
        period = valid_month_period(request.args.get("period")) or period_from_request()
        if not period or period == "all":
            period = default_accounting_period()
        with closing(get_db()) as conn:
            payload = build_invoice_calc_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/invoice-calc/day", methods=["PUT"])
    @acc_perm("accounting.invoice_calc", *MODULE_ACCESS)
    def save_invoice_calc_day():
        data = request.get_json(silent=True) or {}
        entry_date = parse_date(data.get("entry_date"))
        if not entry_date:
            return jsonify({"error": "Geçerli bir tarih girin."}), 400
        period = entry_date[:7]
        rows = data.get("rows") or []
        now = iso(utcnow())
        who = (session.get("admin_display_name") or session.get("admin_username") or "").strip()
        with closing(get_db()) as conn:
            valid_ids = {r["id"] for r in fetchall(conn, "SELECT id FROM acc_invoice_calc_providers")}
            for item in rows:
                try:
                    pid = int(item.get("provider_id"))
                except (TypeError, ValueError):
                    continue
                if pid not in valid_ids:
                    continue
                stake = parse_amount(item.get("stake_amount"))
                winning = parse_amount(item.get("winning_amount"))
                stake = stake if stake is not None else 0.0
                winning = winning if winning is not None else 0.0
                exists = scalar(
                    conn,
                    "SELECT COUNT(*) FROM acc_invoice_calc_daily WHERE entry_date = ? AND provider_id = ?",
                    (entry_date, pid),
                )
                if stake == 0 and winning == 0:
                    if exists:
                        execute(
                            conn,
                            "DELETE FROM acc_invoice_calc_daily WHERE entry_date = ? AND provider_id = ?",
                            (entry_date, pid),
                        )
                    continue
                if exists:
                    execute(
                        conn,
                        """
                        UPDATE acc_invoice_calc_daily
                        SET stake_amount = ?, winning_amount = ?, created_by = ?, updated_at = ?
                        WHERE entry_date = ? AND provider_id = ?
                        """,
                        (stake, winning, who, now, entry_date, pid),
                    )
                else:
                    insert_returning_id(
                        conn,
                        """
                        INSERT INTO acc_invoice_calc_daily
                        (period, entry_date, provider_id, stake_amount, winning_amount, created_by, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (period, entry_date, pid, stake, winning, who, now),
                    )
            conn.commit()
            payload = build_invoice_calc_payload(conn, period)
        payload["period_label"] = period_label(period)
        payload["saved_date"] = entry_date
        return jsonify(payload)

    @bp.route("/invoice-calc/providers/<int:provider_id>", methods=["PUT"])
    @acc_perm("accounting.invoice_calc", *MODULE_ACCESS)
    def update_invoice_calc_provider(provider_id):
        data = request.get_json(silent=True) or {}
        fields = []
        params = []
        if "commission_rate" in data:
            rate = parse_amount(data.get("commission_rate"))
            if rate is None:
                return jsonify({"error": "Geçerli komisyon oranı girin."}), 400
            fields.append("commission_rate = ?")
            params.append(rate)
        if "active" in data:
            fields.append("active = ?")
            params.append(1 if data.get("active") else 0)
        if not fields:
            return jsonify({"error": "Güncellenecek alan yok."}), 400
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT id FROM acc_invoice_calc_providers WHERE id = ?", (provider_id,))
            if not row:
                return jsonify({"error": "Sağlayıcı bulunamadı."}), 404
            params.append(provider_id)
            execute(conn, f"UPDATE acc_invoice_calc_providers SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()
            updated = fetchone(
                conn,
                "SELECT id, section, name, commission_rate, active FROM acc_invoice_calc_providers WHERE id = ?",
                (provider_id,),
            )
        return jsonify({"ok": True, "provider": dict(updated)})

    @bp.route("/pl-report", methods=["GET"])
    @acc_perm("accounting.pl_report", *ACC_READ)
    def get_pl_report():
        period = valid_month_period(request.args.get("period")) or period_from_request()
        if not period or period == "all":
            period = default_accounting_period()
        with closing(get_db()) as conn:
            payload = build_pl_payload(conn, period)
        payload["period_label"] = period_label(period)
        payload["sections_meta"] = PL_SECTION_LABELS
        return jsonify(payload)

    @bp.route("/pl-report/meta", methods=["PUT"])
    @acc_perm("accounting.pl_report", *MODULE_ACCESS)
    def update_pl_report_meta():
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period")) or period_from_request()
        if not period or period == "all":
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        notes = data.get("notes")
        pronet_fatura_label = data.get("pronet_fatura_label")
        pronet_fatura_amount = parse_signed_amount(data.get("pronet_fatura_amount")) if "pronet_fatura_amount" in data else None
        pronet_odenen_amount = parse_signed_amount(data.get("pronet_odenen_amount")) if "pronet_odenen_amount" in data else None
        asil_net_amount = parse_signed_amount(data.get("asil_net_amount")) if "asil_net_amount" in data else None
        yonetim_payi_label = data.get("yonetim_payi_label")
        yonetim_payi_amount = parse_signed_amount(data.get("yonetim_payi_amount")) if "yonetim_payi_amount" in data else None
        kalan_amount = parse_signed_amount(data.get("kalan_amount")) if "kalan_amount" in data else None
        ortak_a_label = data.get("ortak_a_label")
        ortak_a_amount = parse_signed_amount(data.get("ortak_a_amount")) if "ortak_a_amount" in data else None
        ortak_b_label = data.get("ortak_b_label")
        ortak_b_amount = parse_signed_amount(data.get("ortak_b_amount")) if "ortak_b_amount" in data else None
        with closing(get_db()) as conn:
            pl_upsert_meta(
                conn, period,
                notes=notes.strip() if isinstance(notes, str) else None,
                pronet_fatura_label=pronet_fatura_label.strip() if isinstance(pronet_fatura_label, str) else None,
                pronet_fatura_amount=pronet_fatura_amount,
                pronet_odenen_amount=pronet_odenen_amount,
                asil_net_amount=asil_net_amount,
                yonetim_payi_label=yonetim_payi_label.strip() if isinstance(yonetim_payi_label, str) else None,
                yonetim_payi_amount=yonetim_payi_amount,
                kalan_amount=kalan_amount,
                ortak_a_label=ortak_a_label.strip() if isinstance(ortak_a_label, str) else None,
                ortak_a_amount=ortak_a_amount,
                ortak_b_label=ortak_b_label.strip() if isinstance(ortak_b_label, str) else None,
                ortak_b_amount=ortak_b_amount,
            )
            payload = build_pl_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pl-report/lines", methods=["POST"])
    @acc_perm("accounting.pl_report", *MODULE_ACCESS)
    def create_pl_report_line():
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period")) or period_from_request()
        if not period or period == "all":
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        section_key = (data.get("section_key") or "").strip()
        if section_key not in PL_SECTION_LABELS:
            return jsonify({"error": "Geçersiz bölüm."}), 400
        label = (data.get("label") or "").strip()
        if not label:
            return jsonify({"error": "Kalem adı girin."}), 400
        amount = parse_signed_amount(data.get("amount"))
        if amount is None:
            return jsonify({"error": "Geçerli tutar girin."}), 400
        with closing(get_db()) as conn:
            new_id = pl_add_line(conn, period, section_key, label, amount)
            if new_id is None:
                return jsonify({"error": "Kalem eklenemedi."}), 400
            payload = build_pl_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pl-report/lines/<int:line_id>", methods=["PUT"])
    @acc_perm("accounting.pl_report", *MODULE_ACCESS)
    def update_pl_report_line(line_id):
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period")) or period_from_request()
        if not period or period == "all":
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        label = data.get("label")
        amount = parse_signed_amount(data.get("amount")) if "amount" in data else None
        with closing(get_db()) as conn:
            ok = pl_update_line(
                conn, line_id, period,
                label=label.strip() if isinstance(label, str) and label.strip() else None,
                amount=amount,
            )
            if not ok:
                return jsonify({"error": "Kalem bulunamadı."}), 404
            payload = build_pl_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pl-report/lines/<int:line_id>", methods=["DELETE"])
    @acc_perm("accounting.pl_report", *MODULE_ACCESS)
    def delete_pl_report_line(line_id):
        period = valid_month_period(request.args.get("period")) or period_from_request()
        if not period or period == "all":
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        with closing(get_db()) as conn:
            ok = pl_delete_line(conn, line_id, period)
            if not ok:
                return jsonify({"error": "Kalem bulunamadı."}), 404
            payload = build_pl_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    @bp.route("/pl-report/reseed", methods=["POST"])
    @acc_superadmin
    def reseed_pl_report():
        """Gecmis Excel PL raporundan aktarilan verilerle bir donemi yeniden yukler.
        Sadece superadmin kullanabilir (gecmis veri yukleme/duzeltme araci)."""
        data = request.get_json(silent=True) or {}
        period = valid_month_period(data.get("period"))
        if not period:
            return jsonify({"error": "Geçerli ay seçin (YYYY-MM)."}), 400
        with closing(get_db()) as conn:
            ok = pl_reseed_period_from_history(conn, period)
            if not ok:
                return jsonify({"error": "Bu dönem için geçmiş PL verisi tanımlı değil."}), 404
            payload = build_pl_payload(conn, period)
        payload["period_label"] = period_label(period)
        return jsonify(payload)

    # --- Personel (Ofis / Türkiye listesi) — Maaş Ödemeleri (acc_employees) alanından bağımsız ---

    def staff_payload(data, existing=None):
        existing = existing or {}
        category = (data.get("category", existing.get("category")) or "").strip().lower()
        if category not in ("office", "turkey"):
            return None, "Kategori 'Ofis Personeli' veya 'Türkiye Personeli' olmalı."
        name = (data.get("name", existing.get("name")) or "").strip()
        if not name:
            return None, "İsim girin."
        start_date = parse_date(data.get("start_date")) if "start_date" in data else existing.get("start_date")
        if not start_date:
            return None, "Geçerli işbaşı tarihi girin."
        currency = parse_currency(data.get("currency", existing.get("currency")) or "TRY")
        if not currency:
            return None, "Para birimi seçin: TRY, USD veya EUR."
        salary_key = "salary_amount" if "salary_amount" in data else "salary"
        if salary_key in data:
            salary = parse_amount(data.get(salary_key))
            if salary is None:
                return None, "Geçerli maaş tutarı girin."
        else:
            salary = float(existing.get(f"salary_{currency.lower()}") or existing.get("salary_try") or 0)
        status = (data.get("status", existing.get("status")) or "active").strip().lower()
        if status not in ("active", "left"):
            return None, "Durum 'active' veya 'left' olmalı."
        end_date = existing.get("end_date")
        if "end_date" in data:
            end_date = parse_date(data.get("end_date")) if data.get("end_date") else None
        if status == "left" and not end_date:
            end_date = datetime.now(timezone.utc).date().isoformat()
        department = data.get("department", existing.get("department", "")) or ""
        location = data.get("location", existing.get("location", "")) or ""
        notes = data.get("notes", existing.get("notes", "")) or ""
        return {
            "category": category,
            "name": name,
            "start_date": start_date,
            "end_date": end_date,
            "currency": currency,
            "salary": salary,
            "status": status,
            "department": department.strip(),
            "location": location.strip(),
            "notes": notes.strip(),
        }, None

    def enrich_staff_row(row, period):
        row = dict(row)
        row["daily_wage"] = staff_daily_wage_all(row, datetime.now(timezone.utc).date())
        # employee_active_on zaten 'left' durumundakiler için end_date'e kadarki günleri sayar,
        # ondan sonrasını otomatik hariç tutar — ayrılan personel de o aydaki çalıştığı günler için hak ediş görür.
        row["period_accrual"] = staff_period_accrual_all(row, period)
        return row

    @bp.route("/personnel", methods=["GET"])
    @acc_perm("accounting.personnel", *ACC_READ)
    def list_personnel():
        period = valid_month_period(request.args.get("period")) or period_from_request()
        period = valid_month_period(period) or default_accounting_period()
        with closing(get_db()) as conn:
            rows = [dict(r) for r in fetchall(conn, "SELECT * FROM acc_staff ORDER BY category, name")]
        totals = {
            "office": {cur: 0.0 for cur in CURRENCIES},
            "turkey": {cur: 0.0 for cur in CURRENCIES},
            "all": {cur: 0.0 for cur in CURRENCIES},
        }
        enriched = []
        for r in rows:
            row = enrich_staff_row(r, period)
            enriched.append(row)
            cat = row["category"] if row["category"] in ("office", "turkey") else "turkey"
            for cur in CURRENCIES:
                totals[cat][cur] = round(totals[cat][cur] + row["period_accrual"][cur], 2)
                totals["all"][cur] = round(totals["all"][cur] + row["period_accrual"][cur], 2)
        return jsonify({
            "period": period,
            "period_label": period_label(period),
            "staff": enriched,
            "totals": totals,
        })

    @bp.route("/personnel", methods=["POST"])
    @acc_perm("accounting.personnel", *MODULE_ACCESS)
    def create_personnel():
        data = request.get_json(silent=True) or {}
        payload, err = staff_payload(data)
        if err:
            return jsonify({"error": err}), 400
        rates, rate_err = rates_from_request(data)
        if rate_err:
            return jsonify({"error": rate_err}), 400
        fx, err = build_money(payload["salary"], payload["currency"], rates)
        if err:
            return jsonify({"error": err}), 400
        now = iso(utcnow())
        who = (session.get("admin_display_name") or session.get("admin_username") or "").strip()
        with closing(get_db()) as conn:
            new_id = insert_returning_id(
                conn,
                """
                INSERT INTO acc_staff
                (category, name, start_date, end_date, currency, salary_amount,
                 salary_try, salary_usd, salary_eur, rate_usd_try, rate_eur_try,
                 department, location, status, notes, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["category"], payload["name"], payload["start_date"], payload["end_date"],
                    fx["currency"], fx["amount"], fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"],
                    payload["department"], payload["location"], payload["status"], payload["notes"],
                    who, now, now,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM acc_staff WHERE id = ?", (new_id,))
        period = valid_month_period(request.args.get("period")) or default_accounting_period()
        return jsonify({
            "staff": enrich_staff_row(dict(row), period),
            "rates": used_rates_payload(fx),
        }), 201

    @bp.route("/personnel/<int:staff_id>", methods=["PUT"])
    @acc_perm("accounting.personnel", *MODULE_ACCESS)
    def update_personnel(staff_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM acc_staff WHERE id = ?", (staff_id,))
            if not row:
                return jsonify({"error": "Personel bulunamadı."}), 404
            existing = dict(row)
            payload, err = staff_payload(data, existing)
            if err:
                return jsonify({"error": err}), 400
            fx_fields = {"currency", "salary_amount", "salary", "rate_usd_try", "rate_eur_try"}
            if fx_fields & set(data.keys()):
                rates, rate_err = rates_from_request(data, stored=existing)
                if rate_err:
                    return jsonify({"error": rate_err}), 400
                fx, err = build_money(payload["salary"], payload["currency"], rates)
                if err:
                    return jsonify({"error": err}), 400
            else:
                fx = {
                    "amount": payload["salary"], "currency": payload["currency"],
                    "TRY": float(existing.get("salary_try") or 0),
                    "USD": float(existing.get("salary_usd") or 0),
                    "EUR": float(existing.get("salary_eur") or 0),
                    "rate_usd_try": float(existing.get("rate_usd_try") or 0),
                    "rate_eur_try": float(existing.get("rate_eur_try") or 0),
                }
            execute(
                conn,
                """
                UPDATE acc_staff SET
                    category = ?, name = ?, start_date = ?, end_date = ?,
                    currency = ?, salary_amount = ?, salary_try = ?, salary_usd = ?, salary_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?, department = ?, location = ?,
                    status = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["category"], payload["name"], payload["start_date"], payload["end_date"],
                    fx["currency"], fx["amount"], fx["TRY"], fx["USD"], fx["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"], payload["department"], payload["location"],
                    payload["status"], payload["notes"], iso(utcnow()), staff_id,
                ),
            )
            conn.commit()
            updated = fetchone(conn, "SELECT * FROM acc_staff WHERE id = ?", (staff_id,))
        period = valid_month_period(request.args.get("period")) or default_accounting_period()
        return jsonify({"staff": enrich_staff_row(dict(updated), period)})

    @bp.route("/personnel/<int:staff_id>", methods=["DELETE"])
    @acc_perm("accounting.personnel", *MODULE_ACCESS)
    def delete_personnel(staff_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM acc_staff WHERE id = ?", (staff_id,))
            conn.commit()
        return jsonify({"ok": True})

    return bp
