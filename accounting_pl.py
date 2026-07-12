"""Aylık P&L (Kâr/Zarar) raporu — merkeze her ay iletilen özet finans raporu.

Excel'deki "P&L" sekmesinin dijital karşılığı. Yedi sabit bölüm var; her
bölümün toplamı, o bölümdeki satırların toplamıdır (Excel'de de böyle).
GİDERLER = PERSONEL + SABİT + DEĞİŞKEN + REKLAM-MARKETING + KOMİSYON.
NET = GELİRLER - GİDERLER - ÜÇÜNCÜ ŞİRKET ÖDEMELERİ.

PRONET FATURASI / PRONET ÖDENEN / ASIL NET satırları Excel'de de elle
girilen çapraz kontrol satırları olduğu için (gerçekleşen ödemeye göre
değişir, formülle türetilemez) acc_pl_meta üzerinde manuel alanlar olarak
tutulur.
"""

from database import execute, fetchall, fetchone, insert_returning_id, iso, scalar, utcnow

SECTION_GELIRLER = "gelirler"
SECTION_PERSONEL = "personel"
SECTION_SABIT = "sabit"
SECTION_DEGISKEN = "degisken"
SECTION_REKLAM = "reklam"
SECTION_KOMISYON = "komisyon"
SECTION_UCUNCU_SIRKET = "ucuncu_sirket"

SECTION_ORDER = (
    SECTION_GELIRLER,
    SECTION_PERSONEL,
    SECTION_SABIT,
    SECTION_DEGISKEN,
    SECTION_REKLAM,
    SECTION_KOMISYON,
    SECTION_UCUNCU_SIRKET,
)

SECTION_LABELS = {
    SECTION_GELIRLER: "GELİRLER",
    SECTION_PERSONEL: "PERSONEL GİDERLERİ",
    SECTION_SABIT: "SABİT GİDERLER",
    SECTION_DEGISKEN: "DEĞİŞKEN GİDERLER",
    SECTION_REKLAM: "REKLAM - MARKETING GİDERLERİ",
    SECTION_KOMISYON: "YATIRIM - ÇEKİM KOMİSYONLARI",
    SECTION_UCUNCU_SIRKET: "ÜÇÜNCÜ ŞİRKET ÖDEMELERİ",
}

# GİDERLER toplamına giren bölümler (GELİRLER ve ÜÇÜNCÜ ŞİRKET hariç, onlar ayrı satırda gösterilir).
EXPENSE_SECTIONS = (SECTION_PERSONEL, SECTION_SABIT, SECTION_DEGISKEN, SECTION_REKLAM, SECTION_KOMISYON)

# Mayıs 2026 raporundan itibaren Excel'e "Kâr Payı Dağılımı" (Yönetim Payı / Kalan / Ortak A / Ortak B) bloğu
# eklendi. Önceki aylarda bu blok yok; bu yüzden bu tarihten önceki dönemlerde panelde gösterilmez.
PROFIT_SPLIT_FROM_PERIOD = "2026-05"


def _row_dict(row):
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _empty_meta(period):
    return {
        "period": period,
        "notes": "",
        "pronet_fatura_label": "",
        "pronet_fatura_amount": 0.0,
        "pronet_odenen_amount": 0.0,
        "asil_net_amount": 0.0,
        "yonetim_payi_label": "",
        "yonetim_payi_amount": 0.0,
        "kalan_amount": 0.0,
        "ortak_a_label": "",
        "ortak_a_amount": 0.0,
        "ortak_b_label": "",
        "ortak_b_amount": 0.0,
        "updated_at": None,
    }


def ensure_pl_meta(conn, period):
    exists = scalar(conn, "SELECT COUNT(*) FROM acc_pl_meta WHERE period = ?", (period,))
    if not exists:
        now = iso(utcnow())
        execute(
            conn,
            """
            INSERT INTO acc_pl_meta
            (period, notes, pronet_fatura_label, pronet_fatura_amount, pronet_odenen_amount, asil_net_amount,
             yonetim_payi_label, yonetim_payi_amount, kalan_amount, ortak_a_label, ortak_a_amount,
             ortak_b_label, ortak_b_amount, updated_at)
            VALUES (?, '', '', 0, 0, 0, '', 0, 0, '', 0, '', 0, ?)
            """,
            (period, now),
        )
        conn.commit()


def build_pl_payload(conn, period):
    ensure_pl_meta(conn, period)
    meta = _row_dict(fetchone(conn, "SELECT * FROM acc_pl_meta WHERE period = ?", (period,))) or _empty_meta(period)

    rows = fetchall(
        conn,
        "SELECT * FROM acc_pl_lines WHERE period = ? ORDER BY section_key, sort_order, id",
        (period,),
    )
    lines = [_row_dict(r) for r in rows]

    section_totals = {}
    sections = []
    for key in SECTION_ORDER:
        items = [l for l in lines if l.get("section_key") == key]
        total = round(sum(float(l.get("amount") or 0) for l in items), 2)
        section_totals[key] = total
        sections.append({
            "key": key,
            "label": SECTION_LABELS[key],
            "items": items,
            "total": total,
        })

    gelirler = section_totals.get(SECTION_GELIRLER, 0.0)
    giderler = round(sum(section_totals.get(k, 0.0) for k in EXPENSE_SECTIONS), 2)
    ucuncu_sirket = section_totals.get(SECTION_UCUNCU_SIRKET, 0.0)
    net = round(gelirler - giderler - ucuncu_sirket, 2)

    return {
        "period": period,
        "meta": meta,
        "sections": sections,
        "summary": {
            "gelirler": gelirler,
            "giderler": giderler,
            "ucuncu_sirket": ucuncu_sirket,
            "net": net,
        },
        "show_profit_split": period >= PROFIT_SPLIT_FROM_PERIOD,
    }


def upsert_meta(conn, period, notes=None, pronet_fatura_label=None,
                 pronet_fatura_amount=None, pronet_odenen_amount=None, asil_net_amount=None,
                 yonetim_payi_label=None, yonetim_payi_amount=None, kalan_amount=None,
                 ortak_a_label=None, ortak_a_amount=None, ortak_b_label=None, ortak_b_amount=None):
    ensure_pl_meta(conn, period)
    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE acc_pl_meta
        SET notes = COALESCE(?, notes),
            pronet_fatura_label = COALESCE(?, pronet_fatura_label),
            pronet_fatura_amount = COALESCE(?, pronet_fatura_amount),
            pronet_odenen_amount = COALESCE(?, pronet_odenen_amount),
            asil_net_amount = COALESCE(?, asil_net_amount),
            yonetim_payi_label = COALESCE(?, yonetim_payi_label),
            yonetim_payi_amount = COALESCE(?, yonetim_payi_amount),
            kalan_amount = COALESCE(?, kalan_amount),
            ortak_a_label = COALESCE(?, ortak_a_label),
            ortak_a_amount = COALESCE(?, ortak_a_amount),
            ortak_b_label = COALESCE(?, ortak_b_label),
            ortak_b_amount = COALESCE(?, ortak_b_amount),
            updated_at = ?
        WHERE period = ?
        """,
        (
            notes, pronet_fatura_label, pronet_fatura_amount, pronet_odenen_amount, asil_net_amount,
            yonetim_payi_label, yonetim_payi_amount, kalan_amount, ortak_a_label, ortak_a_amount,
            ortak_b_label, ortak_b_amount, now, period,
        ),
    )
    conn.commit()


def add_line(conn, period, section_key, label, amount, sort_order=None):
    if section_key not in SECTION_LABELS:
        return None
    label = (label or "").strip()
    if not label:
        return None
    now = iso(utcnow())
    if sort_order is None:
        max_order = scalar(
            conn,
            "SELECT COALESCE(MAX(sort_order), 0) FROM acc_pl_lines WHERE period = ? AND section_key = ?",
            (period, section_key),
        ) or 0
        sort_order = max_order + 10
    new_id = insert_returning_id(
        conn,
        """
        INSERT INTO acc_pl_lines (period, section_key, label, amount, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (period, section_key, label, amount or 0, sort_order, now, now),
    )
    conn.commit()
    return new_id


def update_line(conn, line_id, period, label=None, amount=None):
    row = fetchone(conn, "SELECT * FROM acc_pl_lines WHERE id = ? AND period = ?", (line_id, period))
    if not row:
        return False
    now = iso(utcnow())
    label = label.strip() if isinstance(label, str) else None
    execute(
        conn,
        """
        UPDATE acc_pl_lines
        SET label = COALESCE(?, label), amount = COALESCE(?, amount), updated_at = ?
        WHERE id = ?
        """,
        (label if label else None, amount, now, line_id),
    )
    conn.commit()
    return True


def delete_line(conn, line_id, period):
    row = fetchone(conn, "SELECT id FROM acc_pl_lines WHERE id = ? AND period = ?", (line_id, period))
    if not row:
        return False
    execute(conn, "DELETE FROM acc_pl_lines WHERE id = ?", (line_id,))
    conn.commit()
    return True


def reseed_period_from_history(conn, period):
    """accounting_pl_seed_data.py içindeki (Excel'den aktarılmış) veriyi bir dönem için yeniden yükler."""
    from accounting_pl_seed_data import PL_LINES, PL_META

    if period not in PL_LINES:
        return False

    now = iso(utcnow())
    execute(conn, "DELETE FROM acc_pl_lines WHERE period = ?", (period,))
    execute(conn, "DELETE FROM acc_pl_meta WHERE period = ?", (period,))

    meta = PL_META.get(period, {})
    execute(
        conn,
        """
        INSERT INTO acc_pl_meta
        (period, notes, pronet_fatura_label, pronet_fatura_amount, pronet_odenen_amount, asil_net_amount,
         yonetim_payi_label, yonetim_payi_amount, kalan_amount, ortak_a_label, ortak_a_amount,
         ortak_b_label, ortak_b_amount, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            period,
            meta.get("notes", ""),
            meta.get("pronet_fatura_label", ""),
            meta.get("pronet_fatura_amount", 0),
            meta.get("pronet_odenen_amount", 0),
            meta.get("asil_net_amount", 0),
            meta.get("yonetim_payi_label", ""),
            meta.get("yonetim_payi_amount", 0),
            meta.get("kalan_amount", 0),
            meta.get("ortak_a_label", ""),
            meta.get("ortak_a_amount", 0),
            meta.get("ortak_b_label", ""),
            meta.get("ortak_b_amount", 0),
            now,
        ),
    )

    for section_key, items in PL_LINES[period].items():
        for idx, (label, amount) in enumerate(items):
            insert_returning_id(
                conn,
                """
                INSERT INTO acc_pl_lines (period, section_key, label, amount, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (period, section_key, label, amount, (idx + 1) * 10, now, now),
            )
    conn.commit()
    return True
