"""Fatura Hesaplama — Excel şablonu oluşturma ve toplu yükleme."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from io import BytesIO

from database import execute, fetchall, fetchone, insert_returning_id, iso, scalar, utcnow

SECTION_LABELS_TR = {
    "sport": "Spor Bahisleri",
    "casino": "Casino Bahisleri",
    "special": "Özel Kalemler",
}

HEADER_DATE = frozenset({"tarih", "entry_date", "date", "gun"})
HEADER_PROVIDER = frozenset({"saglayici", "provider", "provider_name", "saglayici_adi", "provider adi"})
HEADER_STAKE = frozenset({"stake", "stake_amount", "stake_try", "toplam stake", "stake try"})
HEADER_WINNING = frozenset({"winning", "winning_amount", "winning_try", "toplam winning", "winning try", "kazanc"})


def _norm_header(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    text = text.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text.replace(" ", "_")


def _parse_amount(value):
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        amount = float(value)
    else:
        text = str(value).strip().replace(".", "").replace(",", ".") if re.search(r",\d{1,2}$", str(value).strip()) else str(value).strip().replace(",", "")
        try:
            amount = float(text)
        except (TypeError, ValueError):
            return None
    if amount < 0:
        return None
    return round(amount, 2)


def _parse_entry_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _map_headers(header_row):
    mapping = {}
    for idx, raw in enumerate(header_row):
        key = _norm_header(raw)
        if key in HEADER_DATE or "tarih" in key:
            mapping["entry_date"] = idx
        elif key in HEADER_PROVIDER or key.startswith("saglayici"):
            mapping["provider_name"] = idx
        elif key in HEADER_STAKE or key.startswith("stake"):
            mapping["stake_amount"] = idx
        elif key in HEADER_WINNING or key.startswith("winning") or key.startswith("kazanc"):
            mapping["winning_amount"] = idx
    return mapping


def upsert_invoice_calc_daily_batch(conn, entry_date, rows, who=""):
    """rows: [{provider_id, stake_amount, winning_amount}, ...]"""
    period = entry_date[:7]
    now = iso(utcnow())
    who = (who or "").strip()
    valid_ids = {r["id"] for r in fetchall(conn, "SELECT id FROM acc_invoice_calc_providers")}
    saved = 0
    deleted = 0
    skipped = 0
    for item in rows:
        try:
            pid = int(item.get("provider_id"))
        except (TypeError, ValueError):
            skipped += 1
            continue
        if pid not in valid_ids:
            skipped += 1
            continue
        stake = _parse_amount(item.get("stake_amount"))
        winning = _parse_amount(item.get("winning_amount"))
        if stake is None or winning is None:
            skipped += 1
            continue
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
                deleted += 1
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
        saved += 1
    return {"saved": saved, "deleted": deleted, "skipped": skipped}


def generate_template_bytes(conn, entry_date):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    providers = fetchall(
        conn,
        """
        SELECT id, section, name, commission_rate
        FROM acc_invoice_calc_providers
        WHERE active = 1
        ORDER BY CASE section WHEN 'sport' THEN 0 WHEN 'casino' THEN 1 WHEN 'special' THEN 2 ELSE 3 END,
                 sort_order, name
        """,
    )
    existing = {}
    for row in fetchall(
        conn,
        """
        SELECT provider_id, stake_amount, winning_amount
        FROM acc_invoice_calc_daily
        WHERE entry_date = ?
        """,
        (entry_date,),
    ):
        existing[row["provider_id"]] = row

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Gunluk Veri"

    headers = ["Tarih", "Sağlayıcı", "Bölüm", "Oran %", "Stake (TRY)", "Winning (TRY)"]
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(bold=True, color="FFFFFF")
    for col, title in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    row_idx = 2
    for p in providers:
        ex = existing.get(p["id"], {})
        ws.cell(row=row_idx, column=1, value=entry_date)
        ws.cell(row=row_idx, column=2, value=p["name"])
        ws.cell(row=row_idx, column=3, value=SECTION_LABELS_TR.get(p["section"], p["section"]))
        ws.cell(row=row_idx, column=4, value=float(p["commission_rate"] or 0))
        stake_val = ex.get("stake_amount")
        win_val = ex.get("winning_amount")
        ws.cell(row=row_idx, column=5, value=float(stake_val) if stake_val else None)
        ws.cell(row=row_idx, column=6, value=float(win_val) if win_val else None)
        row_idx += 1

    widths = [12, 42, 18, 10, 16, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    info = wb.create_sheet("Aciklama")
    info["A1"] = "Fatura Hesaplama — Excel Yükleme Kılavuzu"
    info["A1"].font = Font(bold=True, size=14)
    lines = [
        "",
        "1. 'Gunluk Veri' sekmesindeki Stake / Winning sütunlarını Pronet panelinden doldurun.",
        "2. Tarih sütununu değiştirmeyin (tek gün) veya her satırda farklı gün kullanabilirsiniz.",
        "3. Sağlayıcı adlarını değiştirmeyin — paneldeki isimlerle birebir eşleşmelidir.",
        "4. Boş bırakılan satırlar (Stake=0, Winning=0) yüklenmez / mevcut kayıt silinir.",
        "5. Panel → Muhasebe → Fatura Hesaplama → Excel Yükle ile dosyayı yükleyin.",
        "",
        f"Şablon tarihi: {entry_date}",
        f"Sağlayıcı sayısı: {len(providers)}",
    ]
    for i, line in enumerate(lines, 2):
        info.cell(row=i, column=1, value=line)
    info.column_dimensions["A"].width = 90

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def import_workbook(conn, file_storage, who=""):
    import openpyxl

    filename = (file_storage.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise ValueError("Sadece .xlsx dosyası yükleyebilirsiniz.")

    raw = file_storage.read()
    if not raw:
        raise ValueError("Dosya boş.")
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("Dosya çok büyük (en fazla 15 MB).")

    wb = openpyxl.load_workbook(BytesIO(raw), read_only=True, data_only=True)
    try:
        ws = wb["Gunluk Veri"] if "Gunluk Veri" in wb.sheetnames else wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            raise ValueError("Excel dosyası boş.")

        col_map = _map_headers(header)
        if "provider_name" not in col_map:
            raise ValueError("Excel'de 'Sağlayıcı' sütunu bulunamadı.")
        if "stake_amount" not in col_map or "winning_amount" not in col_map:
            raise ValueError("Excel'de 'Stake (TRY)' ve 'Winning (TRY)' sütunları gerekli.")

        provider_rows = fetchall(conn, "SELECT id, name FROM acc_invoice_calc_providers")
        name_to_id = {r["name"].strip().lower(): r["id"] for r in provider_rows}

        grouped = {}
        unknown = []
        skipped_rows = 0
        parsed_rows = 0

        for values in rows_iter:
            if not values or all(v is None or str(v).strip() == "" for v in values):
                continue
            parsed_rows += 1

            def cell(key):
                idx = col_map.get(key)
                if idx is None or idx >= len(values):
                    return None
                return values[idx]

            entry_date = _parse_entry_date(cell("entry_date"))
            if not entry_date and "entry_date" not in col_map:
                raise ValueError("Excel'de 'Tarih' sütunu bulunamadı.")
            if not entry_date:
                skipped_rows += 1
                continue

            pname = str(cell("provider_name") or "").strip()
            if not pname:
                skipped_rows += 1
                continue
            pid = name_to_id.get(pname.lower())
            if not pid:
                unknown.append(pname)
                continue

            stake = _parse_amount(cell("stake_amount"))
            winning = _parse_amount(cell("winning_amount"))
            if stake is None or winning is None:
                skipped_rows += 1
                continue

            grouped.setdefault(entry_date, []).append({
                "provider_id": pid,
                "stake_amount": stake,
                "winning_amount": winning,
            })

        if not grouped:
            raise ValueError("İşlenecek satır bulunamadı. Stake/Winning değerlerini kontrol edin.")

        totals = {"saved": 0, "deleted": 0, "skipped": 0}
        dates = []
        for entry_date in sorted(grouped.keys()):
            result = upsert_invoice_calc_daily_batch(conn, entry_date, grouped[entry_date], who=who)
            totals["saved"] += result["saved"]
            totals["deleted"] += result["deleted"]
            totals["skipped"] += result["skipped"]
            dates.append(entry_date)

        conn.commit()
        unknown_unique = sorted(set(unknown))
        periods = sorted({d[:7] for d in dates})
        return {
            "ok": True,
            "dates": dates,
            "periods": periods,
            "parsed_rows": parsed_rows,
            "saved": totals["saved"],
            "deleted": totals["deleted"],
            "skipped_rows": skipped_rows + totals["skipped"],
            "unknown_providers": unknown_unique[:30],
            "unknown_count": len(unknown_unique),
        }
    finally:
        wb.close()
