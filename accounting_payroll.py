"""Personel maaş hak edişi ve günlük yevmiye hesapları."""

import calendar
from datetime import date, datetime, timedelta, timezone

SALARY_CATEGORIES = {
    "office": "Ofis personeli",
    "turkey": "Türkiye çalışanlar",
    "crypto": "Kripto maaş alacaklar",
}

CURRENCIES = ("TRY", "USD", "EUR")


def parse_employee_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def period_date_range(period, reference=None):
    reference = reference or datetime.now(timezone.utc).date()
    period = (period or "all").strip().lower()
    if period == "today":
        return reference, reference
    if period == "month":
        return reference.replace(day=1), reference
    if period == "30days":
        return reference - timedelta(days=29), reference
    return reference.replace(day=1), reference


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


def is_office_employee(emp):
    return (emp.get("salary_category") or "turkey").lower() == "office"


OFFICE_SALARY_FIELDS = (
    "salary", "bank_salary", "crypto_salary", "advance_amount",
    "salary_try", "salary_usd", "salary_eur", "net_salary", "office_remaining",
)


def redact_employee_for_view(emp, can_view_office):
    row = dict(emp)
    if can_view_office or not is_office_employee(row):
        row["salary_hidden"] = False
        return row
    for field in OFFICE_SALARY_FIELDS:
        row[field] = None
    row["accrual"] = {cur: None for cur in CURRENCIES}
    row["salary_hidden"] = True
    return row


def compute_payroll_daily(employees, period="month", reference=None, include_office=True):
    start, end = period_date_range(period, reference)
    days = []
    day = start
    while day <= end:
        totals = {cur: 0.0 for cur in CURRENCIES}
        by_category = {key: {cur: 0.0 for cur in CURRENCIES} for key in SALARY_CATEGORIES}
        active_count = 0
        office_count = 0
        for emp in employees:
            if not employee_active_on(emp, day):
                continue
            cat = (emp.get("salary_category") or "turkey").lower()
            if cat not in by_category:
                cat = "turkey"
            is_office = cat == "office"
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
    for cat in SALARY_CATEGORIES:
        by_category_accrual[cat] = {
            cur: round(sum(row["by_category"][cat][cur] for row in days), 2)
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
    }


def enrich_employee_row(emp, period="month", reference=None):
    start, end = period_date_range(period, reference)
    row = dict(emp)
    accrual = {}
    for cur in CURRENCIES:
        accrual[cur] = employee_accrual_for_range(row, start, end, cur)
    row["accrual"] = accrual
    salary = float(row.get("salary") or 0)
    advance = float(row.get("advance_amount") or 0)
    bank = float(row.get("bank_salary") or 0)
    crypto = float(row.get("crypto_salary") or 0)
    row["net_salary"] = round(max(salary - advance, 0), 2)
    row["office_remaining"] = round(max(salary - advance - bank - crypto, 0), 2)
    return row


def validate_office_amounts(salary, bank, crypto, advance, category):
    if (category or "").lower() != "office":
        return None
    salary = float(salary or 0)
    bank = float(bank or 0)
    crypto = float(crypto or 0)
    advance = float(advance or 0)
    if bank < 0 or crypto < 0 or advance < 0:
        return "Ofis personeli ödeme tutarları negatif olamaz."
    if round(bank + crypto + advance, 2) > round(salary, 2):
        return "Banka + Kripto + Avans toplamı maaşı geçemez."
    return None
