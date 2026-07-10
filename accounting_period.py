"""Muhasebe dönem filtresi — ay bazlı ve hızlı ön ayarlar."""

import calendar
import re
from datetime import date, datetime, timedelta, timezone

MONTH_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


def utc_today():
    return datetime.now(timezone.utc).date()


def parse_period(period, reference=None):
    """Dönem → (başlangıç, bitiş, etiket). all için (None, None, 'all')."""
    reference = reference or utc_today()
    raw = (period or "all").strip()
    key = raw.lower()

    if key == "all":
        return None, None, "all"
    if key == "today":
        return reference, reference, "today"
    if key == "30days":
        return reference - timedelta(days=29), reference, "30days"
    if key == "month":
        year, month = reference.year, reference.month
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        return start, date(year, month, last_day), "month"

    match = MONTH_PERIOD_RE.match(raw)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if month < 1 or month > 12:
            return None, None, "all"
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        return start, date(year, month, last_day), raw

    return None, None, "all"


def date_clause(column, period, reference=None):
    start, end, _ = parse_period(period, reference)
    if start is None:
        return "", ()
    if start == end:
        return f" AND {column} = ?", (start.isoformat(),)
    return f" AND {column} >= ? AND {column} <= ?", (start.isoformat(), end.isoformat())


def period_date_range(period, reference=None):
    return parse_period(period, reference)[:2]


def period_label(period, reference=None):
    start, end, key = parse_period(period, reference)
    if key == "all":
        return "Tüm Zamanlar"
    if key == "today":
        return "Bugün"
    if key == "30days":
        return "Son 30 Gün"
    if start and end:
        months_tr = (
            "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
        )
        if start.year == end.year and start.month == end.month and start.day == 1:
            last = calendar.monthrange(start.year, start.month)[1]
            if end.day == last:
                return f"{months_tr[start.month - 1]} {start.year}"
        if start == end:
            return start.strftime("%d.%m.%Y")
        return f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}"
    return key


def current_month_period(reference=None):
    reference = reference or utc_today()
    return f"{reference.year:04d}-{reference.month:02d}"


def default_accounting_period(reference=None):
    return current_month_period(reference)
