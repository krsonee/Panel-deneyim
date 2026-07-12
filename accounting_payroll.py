"""Personel maaş hak edişi ve günlük yevmiye hesapları."""

import calendar
import unicodedata
from datetime import date, datetime, timedelta, timezone

from accounting_period import parse_period, utc_today

DEFAULT_SALARY_CATEGORIES = {
    "office": "Ofis personeli",
    "turkey": "Türkiye çalışanlar",
    "crypto": "Kripto maaş alacaklar",
}

CURRENCIES = ("TRY", "USD", "EUR")


def normalize_category_map(category_map):
    if not category_map:
        return [
            {"slug": slug, "name": name, "is_office": slug == "office"}
            for slug, name in DEFAULT_SALARY_CATEGORIES.items()
        ]
    rows = []
    for item in category_map:
        rows.append({
            "slug": item["slug"],
            "name": item.get("name") or item["slug"],
            "is_office": bool(item.get("is_office")),
        })
    return rows


def category_lookup(category_map):
    rows = normalize_category_map(category_map)
    by_slug = {row["slug"]: row for row in rows}
    office_slugs = {row["slug"] for row in rows if row.get("is_office")}
    return by_slug, office_slugs, [row["slug"] for row in rows]


def category_label(slug, category_map=None):
    by_slug, _, _ = category_lookup(category_map)
    row = by_slug.get((slug or "").lower())
    return row["name"] if row else slug or "—"


def parse_employee_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def period_date_range(period, reference=None):
    """Hak ediş hesabı için dönem aralığı. Devam eden/gelecekteki aylarda
    bitiş tarihi bugünle sınırlanır (henüz yaşanmamış günler tahakkuk etmez);
    tamamlanmış geçmiş aylarda tam ay aralığı döner."""
    start, end, key = parse_period(period, reference)
    reference = reference or utc_today()
    if key == "all":
        return date(reference.year, 1, 1), reference
    if start is None:
        return reference.replace(day=1), reference
    if end and end > reference:
        end = reference
    return start, end


def employee_active_on(emp, day):
    start = parse_employee_date(emp.get("start_date"))
    if not start or day < start:
        return False
    if (emp.get("status") or "").lower() == "left":
        end = parse_employee_date(emp.get("end_date"))
        if end and day > end:
            return False
    return True


def employee_daily_amount(emp, day, currency="TRY"):
    currency = (currency or "TRY").upper()
    col = f"salary_{currency.lower()}"
    monthly = float(emp.get(col) or 0)
    if monthly <= 0:
        return 0.0
    days_in_month = calendar.monthrange(day.year, day.month)[1]
    return round(monthly / days_in_month, 2)


def employee_accrual_for_range(emp, start, end, currency="TRY"):
    total = 0.0
    day = start
    while day <= end:
        if employee_active_on(emp, day):
            total += employee_daily_amount(emp, day, currency)
        day += timedelta(days=1)
    return round(total, 2)


def is_office_employee(emp, category_map=None):
    slug = (emp.get("salary_category") or "turkey").lower()
    _, office_slugs, _ = category_lookup(category_map)
    return slug in office_slugs


OFFICE_SALARY_FIELDS = (
    "salary", "bank_salary", "crypto_salary", "advance_amount", "bonus_amount",
    "salary_try", "salary_usd", "salary_eur", "net_salary", "office_remaining",
)

EXECUTIVE_SALARY_NAMES = frozenset({"onder", "dalton", "suzi"})


def normalize_person_name(name):
    s = unicodedata.normalize("NFKD", (name or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def is_executive_salary_employee(emp):
    return normalize_person_name(emp.get("name")) in EXECUTIVE_SALARY_NAMES


def filter_payroll_employees(employees, can_view_office, can_view_executive, category_map=None):
    """Toplam/KPI hesabına dahil edilecek personel (gizli maaşlar hariç)."""
    _, office_slugs, _ = category_lookup(category_map)
    rows = []
    for emp in employees:
        row = dict(emp)
        if not can_view_executive and is_executive_salary_employee(row):
            continue
        slug = (row.get("salary_category") or "turkey").lower()
        if not can_view_office and slug in office_slugs:
            continue
        rows.append(row)
    return rows


def _apply_salary_redaction(row, full_hide_name=False):
    for field in OFFICE_SALARY_FIELDS:
        row[field] = None
    row["accrual"] = {cur: None for cur in CURRENCIES}
    row["net_accrual"] = {cur: None for cur in CURRENCIES}
    row["advance_by_currency"] = {cur: None for cur in CURRENCIES}
    row["payment_remaining"] = None
    row["office_remaining"] = None
    row["crypto_wallet"] = None
    row["bank_iban"] = None
    row["bank_account_name"] = None
    if full_hide_name:
        row["salary_hidden"] = True
        row["salary_redacted"] = False
    else:
        row["salary_hidden"] = False
        row["salary_redacted"] = True
    return row


def redact_employee_for_view(emp, can_view_office, category_map=None, can_view_executive=True):
    row = dict(emp)
    if not can_view_executive and is_executive_salary_employee(row):
        return _apply_salary_redaction(row, full_hide_name=False)
    if can_view_office or not is_office_employee(row, category_map):
        row["salary_hidden"] = False
        row["salary_redacted"] = False
        return row
    return _apply_salary_redaction(row, full_hide_name=True)


def compute_payroll_daily(employees, period="month", reference=None, include_office=True, category_map=None):
    by_slug, office_slugs, cat_slugs = category_lookup(category_map)
    start, end = period_date_range(period, reference)
    days = []
    day = start
    while day <= end:
        totals = {cur: 0.0 for cur in CURRENCIES}
        by_category = {slug: {cur: 0.0 for cur in CURRENCIES} for slug in cat_slugs}
        active_count = 0
        office_count = 0
        for emp in employees:
            if not employee_active_on(emp, day):
                continue
            cat = (emp.get("salary_category") or "turkey").lower()
            if cat not in by_category:
                by_category[cat] = {cur: 0.0 for cur in CURRENCIES}
                cat_slugs.append(cat)
            is_office = cat in office_slugs
            active_count += 1
            if is_office:
                office_count += 1
            if is_office and not include_office:
                continue
            for cur in CURRENCIES:
                amt = employee_daily_amount(emp, day, cur)
                totals[cur] += amt
                by_category[cat][cur] += amt
        days.append({
            "date": day.isoformat(),
            "active_count": active_count,
            "office_count": office_count,
            "office_hidden": not include_office and office_count > 0,
            "totals": {cur: round(totals[cur], 2) for cur in CURRENCIES},
            "by_category": {
                cat: {cur: round(by_category[cat][cur], 2) for cur in CURRENCIES}
                for cat in by_category
            },
        })
        day += timedelta(days=1)

    period_accrual = {
        cur: round(sum(row["totals"][cur] for row in days), 2)
        for cur in CURRENCIES
    }
    by_category_accrual = {}
    for cat in cat_slugs:
        by_category_accrual[cat] = {
            cur: round(sum(row["by_category"].get(cat, {}).get(cur, 0) for row in days), 2)
            for cur in CURRENCIES
        }

    return {
        "period": period,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "days": days,
        "period_accrual": period_accrual,
        "by_category_accrual": by_category_accrual,
        "office_totals_hidden": not include_office,
        "category_labels": {slug: by_slug.get(slug, {}).get("name", slug) for slug in cat_slugs},
    }


def employee_active_in_period(emp, period="month", reference=None):
    """Seçili dönemde en az bir gün aktif olan personel."""
    from accounting_period import parse_period

    start, end, key = parse_period(period, reference)
    if key == "all" or start is None:
        return True
    day = start
    while day <= end:
        if employee_active_on(emp, day):
            return True
        day += timedelta(days=1)
    return False


def amount_in_currency(emp, amount, currency):
    amount = float(amount or 0)
    if amount <= 0:
        return 0.0
    emp_currency = (emp.get("currency") or "TRY").upper()
    currency = (currency or "TRY").upper()
    if emp_currency == currency:
        return round(amount, 2)
    salary = float(emp.get("salary") or 0)
    if salary <= 0:
        return 0.0
    monthly = float(emp.get(f"salary_{currency.lower()}") or 0)
    return round(amount * (monthly / salary), 2)


def advance_in_currency(emp, currency):
    return amount_in_currency(emp, emp.get("advance_amount"), currency)


def bonus_in_currency(emp, currency):
    return amount_in_currency(emp, emp.get("bonus_amount"), currency)


def enrich_employee_row(emp, period="month", reference=None):
    reference = reference or utc_today()
    _, _, key = parse_period(period, reference)
    if key == "all":
        start = parse_employee_date(emp.get("start_date")) or reference
        end = reference
        if (emp.get("status") or "").lower() == "left":
            left_end = parse_employee_date(emp.get("end_date"))
            if left_end:
                end = min(end, left_end)
    else:
        start, end = period_date_range(period, reference)
    row = dict(emp)
    accrual = {}
    bonus_by_currency = {cur: bonus_in_currency(row, cur) for cur in CURRENCIES}
    for cur in CURRENCIES:
        base = employee_accrual_for_range(row, start, end, cur)
        accrual[cur] = round(base + bonus_by_currency[cur], 2)
    row["accrual"] = accrual
    row["bonus_by_currency"] = bonus_by_currency
    row["accrual_base"] = {
        cur: round(accrual[cur] - bonus_by_currency[cur], 2) for cur in CURRENCIES
    }
    advance_by_currency = {cur: advance_in_currency(row, cur) for cur in CURRENCIES}
    row["advance_by_currency"] = advance_by_currency
    row["net_accrual"] = {
        cur: round(max(accrual[cur] - advance_by_currency[cur], 0), 2) for cur in CURRENCIES
    }
    salary = float(row.get("salary") or 0)
    advance = float(row.get("advance_amount") or 0)
    bank = float(row.get("bank_salary") or 0)
    crypto = float(row.get("crypto_salary") or 0)
    row["net_salary"] = round(max(salary - advance, 0), 2)
    remaining = round(max(salary - advance - bank - crypto, 0), 2)
    row["office_remaining"] = remaining
    row["payment_remaining"] = remaining
    return row


def validate_advance_amount(salary, advance):
    advance = float(advance or 0)
    salary = float(salary or 0)
    if advance < 0:
        return "Avans negatif olamaz."
    if round(advance, 2) > round(salary, 2):
        return "Avans maaşı geçemez."
    return None


def validate_payment_split(salary, bank, crypto, advance):
    salary = float(salary or 0)
    bank = float(bank or 0)
    crypto = float(crypto or 0)
    advance = float(advance or 0)
    if bank < 0 or crypto < 0 or advance < 0:
        return "Banka, kripto ve avans negatif olamaz."
    if round(bank + crypto + advance, 2) > round(salary, 2):
        return "Banka + Kripto + Avans toplamı maaşı geçemez."
    return None


def validate_office_amounts(salary, bank, crypto, advance, is_office=True):
    if not is_office:
        return validate_advance_amount(salary, advance)
    return validate_payment_split(salary, bank, crypto, advance)
