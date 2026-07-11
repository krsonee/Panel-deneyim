"""Pronet proforma fatura — sağlayıcı komisyonları ve sabit ücretler."""

from accounting_period import is_period_locked
from database import execute, fetchall, fetchone, insert_returning_id, iso, scalar, utcnow

SECTION_SPORT = "sport"
SECTION_CASINO = "casino"
SECTION_SPECIAL = "special"

# Sağlayıcı şablonları (Haziran 2025 faturasından)
SEED_PROVIDERS = [
    # Spor
    ("sport", "Spor Bahisleri", 20, 10),
    ("sport", "Bonus Ödemesi", 20, 20),
    ("sport", "Sanal Futbol / Tenis / Basketbol", 25, 30),
    ("sport", "Goldenrace", 18, 40),
    ("sport", "Ultraplay", 16, 50),
    ("sport", "Binary", 20, 60),
    # Casino
    ("casino", "Canlı Casino (Xprogaming) + Tips", 25, 100),
    ("casino", "Evolution Canlı Casino", 25, 110),
    ("casino", "Netent Casino", 25, 120),
    ("casino", "Klas Poker", 25, 125),
    ("casino", "Bet On Poker", 25, 130),
    ("casino", "Lucky Streak + Tips", 19, 140),
    ("casino", "Ezugi + Tips", 19, 150),
    ("casino", "BetSoft", 18, 160),
    ("casino", "Nolimit City", 22, 170),
    ("casino", "LiveGames + Jackpot Cont.", 15, 180),
    ("casino", "MicroGaming", 25, 190),
    ("casino", "Endorphina", 20, 200),
    ("casino", "Phoenix7", 18, 210),
    ("casino", "Spinomenal", 19, 220),
    ("casino", "VivoGaming", 17, 230),
    ("casino", "Tom Horn", 19, 240),
    ("casino", "Playson", 18, 250),
    ("casino", "Helio Gaming", 0, 260),
    ("casino", "Amatic", 20, 270),
    ("casino", "Concept Gaming", 19, 280),
    ("casino", "Game Art", 18, 290),
    ("casino", "Iconic21", 17, 300),
    ("casino", "Amusnet + Jackpot Cont.", 25, 310),
    ("casino", "Blueprint Gaming + Jackpot Cont.", 22, 320),
    ("casino", "Gaming Corps", 16, 330),
    ("casino", "Pragmatic Play + Jackpot Cont.", 18, 340),
    ("casino", "Red Rake", 18, 350),
    ("casino", "Relax Gaming", 18, 360),
    ("casino", "Ortiz Gaming", 19, 370),
    ("casino", "Espresso Games", 17, 380),
    ("casino", "Booming Games", 18, 390),
    ("casino", "PG Soft", 18, 400),
    ("casino", "Big Time Gaming", 25, 410),
    ("casino", "Lotto Instant Win", 21, 420),
    ("casino", "VoltEnt + Jackpot Cont.", 20, 430),
    ("casino", "3 Oaks Gaming", 18, 440),
    ("casino", "Novomatic", 20, 450),
    ("casino", "EvoPlay Entertainment", 25, 460),
    ("casino", "Hacksaw Gaming", 20, 470),
    ("casino", "HoGaming", 17, 480),
    ("casino", "Spribe", 20, 490),
    ("casino", "KA Gaming", 17, 500),
    ("casino", "Spade Gaming", 20, 510),
    ("casino", "Red Tiger", 22, 520),
    ("casino", "Fazi", 20, 530),
    ("casino", "Nucleus Gaming", 19, 540),
    ("casino", "MrSlotty", 17, 550),
    ("casino", "Platipus", 17, 560),
    ("casino", "Popiplay", 15, 570),
    ("casino", "Ruby Play", 17, 580),
    ("casino", "Ace Gaming", 18, 590),
    ("casino", "True Lab", 18, 600),
    ("casino", "Play'n GO + Jackpot Cont.", 20, 610),
    ("casino", "Fugaso", 19, 620),
    ("casino", "SmartSoft", 19, 630),
    ("casino", "TVBET", 18, 640),
    ("casino", "ESA Gaming", 20, 650),
    ("casino", "Vibra Gaming", 19, 660),
    ("casino", "Yggdrasil", 21, 670),
    ("casino", "Pragmatic Play Live", 21, 680),
    ("casino", "Habanero", 17, 690),
    ("casino", "Swintt", 19, 700),
    ("casino", "Winfinity", 20, 710),
    ("casino", "Rich88", 17, 720),
    ("casino", "Sa Gaming", 17, 730),
    ("casino", "Slotopia EvoPlay", 18, 740),
    ("casino", "YGT", 18, 750),
    ("casino", "AccaMax + Jackpot Cont.", 18, 760),
    ("casino", "EGTD + Jackpot Cont.", 19, 770),
    ("casino", "BetSolutions", 16, 780),
    ("casino", "Microgaming Live", 25, 790),
    ("casino", "Simple Play + Jackpot Cont.", 15, 800),
    ("casino", "UcaX", 12, 810),
    ("casino", "Fa Chai", 16, 820),
    ("casino", "Popok", 15, 830),
    ("casino", "CreedRoomz", 17, 840),
    ("casino", "Pascal", 15, 850),
    ("casino", "Lava Casino", 17, 860),
    ("casino", "Fashion TV", 17, 870),
    ("casino", "Eclipse Casino", 17, 880),
    ("special", "ProClub Jackpot", 0, 900),
]

SEED_FIXED_FEES = [
    ("Betasist", 250, "monthly", 10),
    ("Domain Güvenlik Paketi", 1000, "monthly", 20),
    ("Live Match Tracker", 3500, "monthly", 30),
    ("Panelfront (içerik yönetim sistemi)", 2500, "monthly", 40),
    ("Smartico CRM", 3000, "monthly", 50),
    ("Smartico Afiliate Software License", 2000, "monthly", 60),
    ("Statistic Center", 1500, "monthly", 70),
    ("Streaming", 5000, "monthly", 80),
]

# Haziran 2025 fatura satırları (volume, jackpot) — provider name ile eşleşir
HAZIRAN_2025_VOLUMES = {
    "Spor Bahisleri": (2018147, 0),
    "Bonus Ödemesi": (-403629, 0),
    "Sanal Futbol / Tenis / Basketbol": (43747, 0),
    "Goldenrace": (0, 0),
    "Ultraplay": (207, 0),
    "Binary": (239, 0),
    "Canlı Casino (Xprogaming) + Tips": (0, 0),
    "Evolution Canlı Casino": (4084900, 0),
    "Netent Casino": (112359, 0),
    "Klas Poker": (158975, 0),
    "Bet On Poker": (10284, 0),
    "Lucky Streak + Tips": (2, 0),
    "Ezugi + Tips": (222649, 0),
    "BetSoft": (122550, 0),
    "Nolimit City": (255650, 0),
    "LiveGames + Jackpot Cont.": (172698, 1471),
    "MicroGaming": (81667, 0),
    "Endorphina": (301492, 0),
    "Phoenix7": (6380, 0),
    "Spinomenal": (3135, 0),
    "VivoGaming": (33900, 0),
    "Tom Horn": (22650, 0),
    "Playson": (974029, 0),
    "Helio Gaming": (0, 0),
    "Amatic": (40681, 0),
    "Concept Gaming": (2447, 0),
    "Game Art": (28267, 0),
    "Iconic21": (34167, 0),
    "Amusnet + Jackpot Cont.": (2655535, 768088),
    "Blueprint Gaming + Jackpot Cont.": (314, 27),
    "Gaming Corps": (-349125, 0),
    "Pragmatic Play + Jackpot Cont.": (16348238, 11576),
    "Red Rake": (0, 0),
    "Relax Gaming": (13628, 0),
    "Ortiz Gaming": (0, 0),
    "Espresso Games": (41410, 0),
    "Booming Games": (1051596, 0),
    "PG Soft": (407009, 0),
    "Big Time Gaming": (1989, 0),
    "Lotto Instant Win": (44, 0),
    "VoltEnt + Jackpot Cont.": (1289245, 308649),
    "3 Oaks Gaming": (173404, 0),
    "Novomatic": (270733, 0),
    "EvoPlay Entertainment": (75666, 0),
    "Hacksaw Gaming": (962636, 0),
    "HoGaming": (0, 0),
    "Spribe": (742452, 0),
    "KA Gaming": (-246, 0),
    "Spade Gaming": (22987, 0),
    "Red Tiger": (546037, 0),
    "Fazi": (333248, 0),
    "Nucleus Gaming": (3134, 0),
    "MrSlotty": (-306, 0),
    "Platipus": (-19868, 0),
    "Popiplay": (71914, 0),
    "Ruby Play": (281288, 0),
    "Ace Gaming": (-3197, 0),
    "True Lab": (0, 0),
    "Play'n GO + Jackpot Cont.": (8269, 0),
    "Fugaso": (38503, 0),
    "SmartSoft": (290615, 0),
    "TVBET": (851, 0),
    "ESA Gaming": (-2544, 0),
    "Vibra Gaming": (-4111, 0),
    "Yggdrasil": (16279, 0),
    "Pragmatic Play Live": (4138670, 0),
    "Habanero": (149091, 0),
    "Swintt": (915, 0),
    "Winfinity": (0, 0),
    "Rich88": (8231, 0),
    "Sa Gaming": (110, 0),
    "Slotopia EvoPlay": (394, 0),
    "YGT": (0, 0),
    "AccaMax + Jackpot Cont.": (192481, 22720),
    "EGTD + Jackpot Cont.": (8747005, 1903549),
    "BetSolutions": (1590, 0),
    "Microgaming Live": (57182, 0),
    "Simple Play + Jackpot Cont.": (617, 134),
    "UcaX": (68444, 0),
    "Fa Chai": (4451, 0),
    "Popok": (21186, 0),
    "CreedRoomz": (764, 0),
    "Pascal": (1149, 0),
    "Lava Casino": (120, 0),
    "Fashion TV": (0, 0),
    "Eclipse Casino": (0, 0),
    "ProClub Jackpot": (1494982, 0),
}

# Haziran 2025 Pronet faturası — satır komisyonları (PDF ile birebir)
HAZIRAN_2025_COMMISSIONS = {
    "3 Oaks Gaming": 31213.0,
    "AccaMax + Jackpot Cont.": 57366.0,
    "Ace Gaming": 0.0,
    "Amatic": 8136.0,
    "Amusnet + Jackpot Cont.": 1431971.0,
    "Bet On Poker": 2571.0,
    "BetSoft": 22059.0,
    "BetSolutions": 254.0,
    "Big Time Gaming": 497.0,
    "Binary": 48.0,
    "Blueprint Gaming + Jackpot Cont.": 96.0,
    "Bonus Ödemesi": -403629.0,
    "Booming Games": 189287.0,
    "Canlı Casino (Xprogaming) + Tips": 0.0,
    "Concept Gaming": 465.0,
    "CreedRoomz": 130.0,
    "EGTD + Jackpot Cont.": 3565480.0,
    "ESA Gaming": 0.0,
    "Eclipse Casino": 0.0,
    "Endorphina": 60298.0,
    "Espresso Games": 7040.0,
    "EvoPlay Entertainment": 18917.0,
    "Evolution Canlı Casino": 1021225.0,
    "Ezugi + Tips": 42303.0,
    "Fa Chai": 712.0,
    "Fashion TV": 0.0,
    "Fazi": 66650.0,
    "Fugaso": 7315.0,
    "Game Art": 5088.0,
    "Gaming Corps": 0.0,
    "Goldenrace": 0.0,
    "Habanero": 25345.0,
    "Hacksaw Gaming": 192527.0,
    "HoGaming": 0.0,
    "Iconic21": 5808.0,
    "KA Gaming": 0.0,
    "Klas Poker": 403631.0,
    "Lava Casino": 20.0,
    "LiveGames + Jackpot Cont.": 27376.0,
    "Lotto Instant Win": 9.0,
    "Lucky Streak + Tips": 0.0,
    "MicroGaming": 20417.0,
    "Microgaming Live": 14296.0,
    "MrSlotty": 0.0,
    "Netent Casino": 28090.0,
    "Nolimit City": 56243.0,
    "Novomatic": 54147.0,
    "Nucleus Gaming": 595.0,
    "Ortiz Gaming": 0.0,
    "PG Soft": 73262.0,
    "Pascal": 172.0,
    "Phoenix7": 1148.0,
    "Platipus": 0.0,
    "Play'n GO + Jackpot Cont.": 1654.0,
    "Playson": 175325.0,
    "Popiplay": 10787.0,
    "Popok": 3178.0,
    "Pragmatic Play + Jackpot Cont.": 2954259.0,
    "Pragmatic Play Live": 869121.0,
    "ProClub Jackpot": 2547622.0,
    "Red Rake": 0.0,
    "Red Tiger": 120128.0,
    "Relax Gaming": 2453.0,
    "Rich88": 1399.0,
    "Ruby Play": 47819.0,
    "Sa Gaming": 19.0,
    "Sanal Futbol / Tenis / Basketbol": 10937.0,
    "Simple Play + Jackpot Cont.": 227.0,
    "Slotopia EvoPlay": 71.0,
    "SmartSoft": 55217.0,
    "Spade Gaming": 4597.0,
    "Spinomenal": 596.0,
    "Spor Bahisleri": 322904.0,
    "Spribe": 148490.0,
    "Swintt": 174.0,
    "TVBET": 153.0,
    "Tom Horn": 4304.0,
    "True Lab": 0.0,
    "UcaX": 8213.0,
    "Ultraplay": 33.0,
    "Vibra Gaming": 0.0,
    "VivoGaming": 5763.0,
    "VoltEnt + Jackpot Cont.": 566498.0,
    "Winfinity": 0.0,
    "YGT": 0.0,
    "Yggdrasil": 3419.0,
}


def calc_commission(volume_try, jackpot_try, commission_rate, manual_commission=None):
    if manual_commission is not None:
        return round(float(manual_commission), 2)
    volume = float(volume_try or 0)
    jackpot = float(jackpot_try or 0)
    rate = float(commission_rate or 0)
    if volume < 0:
        return 0.0
    base = volume * rate / 100.0
    return round(base + jackpot, 2)


def seed_pronet_templates(conn):
    now = iso(utcnow())
    for section, name, rate, sort_order in SEED_PROVIDERS:
        exists = scalar(
            conn,
            "SELECT COUNT(*) FROM acc_pronet_providers WHERE name = ?",
            (name,),
        )
        if not exists:
            insert_returning_id(
                conn,
                """
                INSERT INTO acc_pronet_providers
                (section, name, commission_rate, sort_order, active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (section, name, rate, sort_order, now),
            )
    for name, amount_eur, billing, sort_order in SEED_FIXED_FEES:
        exists = scalar(
            conn,
            "SELECT COUNT(*) FROM acc_pronet_fixed_fees WHERE name = ?",
            (name,),
        )
        if not exists:
            insert_returning_id(
                conn,
                """
                INSERT INTO acc_pronet_fixed_fees
                (name, amount_eur, billing_cycle, sort_order, active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (name, amount_eur, billing, sort_order, now),
            )
    conn.commit()


def ensure_period_lines(conn, period, eur_try_rate=45.436):
    """Seçili dönem için satır yoksa şablondan oluştur."""
    count = scalar(
        conn,
        "SELECT COUNT(*) FROM acc_pronet_period_lines WHERE period = ?",
        (period,),
    )
    if count:
        return

    now = iso(utcnow())
    meta_exists = scalar(
        conn,
        "SELECT COUNT(*) FROM acc_pronet_period_meta WHERE period = ?",
        (period,),
    )
    if not meta_exists:
        gross = 48886230 if period == "2025-06" else 0
        sms = 56384 if period == "2025-06" else 0
        execute(
            conn,
            """
            INSERT INTO acc_pronet_period_meta
            (period, gross_revenue_try, eur_try_rate, sms_fee_try, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (period, gross, eur_try_rate, sms, "", now),
        )

    providers = fetchall(
        conn,
        "SELECT * FROM acc_pronet_providers WHERE active = 1 ORDER BY sort_order, name",
    )
    for p in providers:
        vol, jp = HAZIRAN_2025_VOLUMES.get(p["name"], (0, 0)) if period == "2025-06" else (0, 0)
        rate = float(p["commission_rate"] or 0)
        manual_map = HAZIRAN_2025_COMMISSIONS if period == "2025-06" else {}
        manual = manual_map.get(p["name"])
        if manual is not None:
            comm = float(manual)
            manual_val = comm
        else:
            manual_val = None
            comm = calc_commission(vol, jp, rate, None)
        insert_returning_id(
            conn,
            """
            INSERT INTO acc_pronet_period_lines
            (period, line_kind, provider_id, fixed_fee_id, custom_label,
             volume_try, jackpot_try, tips_try, commission_rate, commission_try,
             manual_commission, created_at, updated_at)
            VALUES (?, 'provider', ?, NULL, NULL, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (period, p["id"], vol, jp, rate, comm, manual_val, now, now),
        )

    fixed_fees = fetchall(
        conn,
        "SELECT * FROM acc_pronet_fixed_fees WHERE active = 1 ORDER BY sort_order, name",
    )
    rate = float(eur_try_rate or 45.436)
    for fee in fixed_fees:
        amount_try = round(float(fee["amount_eur"]) * rate, 2)
        insert_returning_id(
            conn,
            """
            INSERT INTO acc_pronet_period_lines
            (period, line_kind, provider_id, fixed_fee_id, custom_label,
             volume_try, jackpot_try, tips_try, commission_rate, commission_try,
             manual_commission, created_at, updated_at)
            VALUES (?, 'fixed', NULL, ?, NULL, ?, 0, 0, 0, ?, NULL, ?, ?)
            """,
            (period, fee["id"], float(fee["amount_eur"]), amount_try, now, now),
        )
    conn.commit()


def _row_dict(row):
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def enrich_line(row, providers_by_id, fees_by_id):
    data = _row_dict(row)
    kind = data.get("line_kind") or "provider"
    if kind == "provider" and data.get("provider_id"):
        p = _row_dict(providers_by_id.get(data["provider_id"], {}))
        data["label"] = p.get("name", "")
        data["section"] = p.get("section", "")
        data["default_rate"] = float(p.get("commission_rate") or 0)
    elif kind == "fixed" and data.get("fixed_fee_id"):
        f = _row_dict(fees_by_id.get(data["fixed_fee_id"], {}))
        data["label"] = f.get("name", "")
        data["section"] = "fixed"
        data["amount_eur"] = float(f.get("amount_eur") or 0)
        data["billing_cycle"] = f.get("billing_cycle", "monthly")
    else:
        data["label"] = data.get("custom_label") or "—"
        data["section"] = "custom"
    rate = data.get("commission_rate")
    if rate is None and kind == "provider":
        rate = data.get("default_rate", 0)
    data["commission_rate"] = float(rate or 0)
    if kind != "fixed":
        manual = data.get("manual_commission")
        if manual is not None:
            data["commission_try"] = float(manual)
        else:
            data["commission_try"] = calc_commission(
                data.get("volume_try"),
                data.get("jackpot_try"),
                data["commission_rate"],
                None,
            )
    return data


def build_invoice_payload(conn, period):
    seed_pronet_templates(conn)
    meta = fetchone(conn, "SELECT * FROM acc_pronet_period_meta WHERE period = ?", (period,))
    eur_rate = float(meta["eur_try_rate"]) if meta else 45.436
    ensure_period_lines(conn, period, eur_rate)
    meta = fetchone(conn, "SELECT * FROM acc_pronet_period_meta WHERE period = ?", (period,))

    providers = fetchall(conn, "SELECT * FROM acc_pronet_providers")
    fees = fetchall(conn, "SELECT * FROM acc_pronet_fixed_fees")
    p_map = {p["id"]: _row_dict(p) for p in providers}
    f_map = {f["id"]: _row_dict(f) for f in fees}

    rows = fetchall(
        conn,
        """
        SELECT * FROM acc_pronet_period_lines
        WHERE period = ?
        ORDER BY id
        """,
        (period,),
    )
    lines = [enrich_line(r, p_map, f_map) for r in rows]

    sport = [l for l in lines if l.get("section") == SECTION_SPORT]
    casino = [l for l in lines if l.get("section") == SECTION_CASINO]
    special = [l for l in lines if l.get("section") == SECTION_SPECIAL]
    fixed = [l for l in lines if l.get("section") == "fixed"]

    sport_comm = sum(l["commission_try"] for l in sport)
    casino_volume = sum(max(float(l.get("volume_try") or 0), 0) for l in casino)
    casino_comm = sum(l["commission_try"] for l in casino)
    special_comm = sum(l["commission_try"] for l in special)
    fixed_total = sum(l["commission_try"] for l in fixed)
    sms_fee = float(meta["sms_fee_try"] or 0) if meta else 0
    provider_total = sport_comm + casino_comm + special_comm
    grand_total = provider_total + fixed_total + sms_fee
    gross = float(meta["gross_revenue_try"] or 0) if meta else 0
    eur_total = grand_total / eur_rate if eur_rate else 0

    locked = is_period_locked(period)
    return {
        "period": period,
        "locked": locked,
        "meta": {
            "gross_revenue_try": gross,
            "eur_try_rate": eur_rate,
            "sms_fee_try": sms_fee,
            "notes": (meta["notes"] or "") if meta else "",
        },
        "sections": {
            "sport": sport,
            "casino": casino,
            "special": special,
            "fixed": fixed,
        },
        "totals": {
            "sport_commission_try": round(sport_comm, 2),
            "casino_volume_try": round(casino_volume, 2),
            "casino_commission_try": round(casino_comm, 2),
            "special_commission_try": round(special_comm, 2),
            "casino_commission_total_try": round(casino_comm + special_comm, 2),
            "fixed_fees_try": round(fixed_total, 2),
            "sms_fee_try": round(sms_fee, 2),
            "provider_commission_try": round(provider_total, 2),
            "grand_total_try": round(grand_total, 2),
            "grand_total_eur": round(eur_total, 2),
        },
    }
