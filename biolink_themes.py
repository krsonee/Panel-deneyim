"""Bio Sayfa — tasarım temaları ve bölüm ayırıcı (heading) stilleri kataloğu."""

from __future__ import annotations

# makrobet804.com marka paleti (mail / site ile uyumlu)
_MB_BG = "#061c3d"
_MB_CARD = "#0b2347"
_MB_ROW = "#0f2d55"
_MB_TEXT = "#e8efff"
_MB_MUTED = "#8fa3cc"
_MB_GOLD = "#ffd53e"
_MB_BLUE = "#4a8fe7"
_MB_DARK = "#10152b"


def _theme(
    name,
    *,
    bg,
    text,
    muted,
    card_bg,
    card_border,
    card_hover,
    accent,
    category="Koyu",
    style="classic",
    accent2=None,
    animated=False,
    animation="",
    brand_logo=True,
):
    out = {
        "name": name,
        "bg": bg,
        "text": text,
        "muted": muted,
        "card_bg": card_bg,
        "card_border": card_border,
        "card_hover": card_hover,
        "accent": accent,
        "category": category,
        "style": style,
        "brand_logo": True,
    }
    if accent2:
        out["accent2"] = accent2
    if animated:
        out["animated"] = True
        out["animation"] = animation or "aurora"
    return out


THEMES = {
    # ── Mevcut / marka ──────────────────────────────────────
    "carbon": _theme(
        "Karbon",
        bg="linear-gradient(160deg, #05070a 0%, #0d1117 45%, #111827 100%)",
        text="#f5f7fa", muted="#9aa4b2",
        card_bg="rgba(255,255,255,0.06)", card_border="rgba(255,255,255,0.12)",
        card_hover="rgba(255,255,255,0.11)", accent="#22d3a8",
        category="Koyu", style="classic",
    ),
    "midnight": _theme(
        "Gece Mavisi",
        bg="linear-gradient(160deg, #060b18 0%, #0b1a3a 50%, #10265c 100%)",
        text="#f2f6ff", muted="#9db3d9",
        card_bg="rgba(255,255,255,0.07)", card_border="rgba(120,170,255,0.25)",
        card_hover="rgba(255,255,255,0.13)", accent="#38bdf8",
        category="Koyu", style="glass",
    ),
    "emerald": _theme(
        "Zümrüt",
        bg="linear-gradient(160deg, #04140f 0%, #0b2e22 50%, #114b36 100%)",
        text="#f1fbf6", muted="#9ecbb3",
        card_bg="rgba(255,255,255,0.06)", card_border="rgba(180,255,210,0.2)",
        card_hover="rgba(255,255,255,0.12)", accent="#f5c451",
        category="Doğa", style="soft",
    ),
    "royal": _theme(
        "Kraliyet Moru",
        bg="linear-gradient(160deg, #140a24 0%, #2c1250 50%, #451a72 100%)",
        text="#f8f3ff", muted="#c6aee3",
        card_bg="rgba(255,255,255,0.08)", card_border="rgba(230,180,255,0.25)",
        card_hover="rgba(255,255,255,0.14)", accent="#f472b6",
        category="Mor", style="glow",
    ),
    "sunset": _theme(
        "Gün Batımı",
        bg="linear-gradient(160deg, #2b0f1e 0%, #7a1e3d 45%, #d9622f 100%)",
        text="#fff8f2", muted="#f3c7ae",
        card_bg="rgba(255,255,255,0.10)", card_border="rgba(255,230,210,0.28)",
        card_hover="rgba(255,255,255,0.16)", accent="#ffd166",
        category="Sıcak", style="lift",
    ),
    "minimal": _theme(
        "Minimal Beyaz",
        bg="linear-gradient(160deg, #ffffff 0%, #f3f5f8 100%)",
        text="#12151b", muted="#5b6472",
        card_bg="#ffffff", card_border="rgba(15,20,30,0.10)",
        card_hover="#f4f6f9", accent="#2563eb",
        category="Açık", style="outline",
    ),
    "makrovip": _theme(
        "MakroVIP",
        bg="radial-gradient(1200px 600px at 50% -10%, #1a3a6e 0%, #061c3d 45%, #030912 100%)",
        text="#f5f8ff", muted="#8fa8cc",
        card_bg="rgba(255,255,255,0.07)", card_border="rgba(212,175,55,0.28)",
        card_hover="rgba(255,255,255,0.12)", accent="#d4af37",
        category="Marka", style="neon",
    ),
    "makrobet": _theme(
        "★ Makrobet",
        bg=_MB_BG, text=_MB_TEXT, muted=_MB_MUTED,
        card_bg="rgba(11, 35, 71, 0.88)", card_border="rgba(255, 213, 62, 0.38)",
        card_hover="rgba(15, 45, 85, 0.95)", accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="neon", animated=True, animation="makrobet", brand_logo=True,
    ),
    "mb_classic": _theme(
        "Makrobet Klasik",
        bg=_MB_BG, text=_MB_TEXT, muted=_MB_MUTED,
        card_bg=_MB_CARD, card_border="rgba(255, 213, 62, 0.32)",
        card_hover=_MB_ROW, accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="classic", brand_logo=True,
    ),
    "mb_804": _theme(
        "Makrobet 804",
        bg=f"radial-gradient(1100px 620px at 50% -12%, #1a4480 0%, {_MB_BG} 42%, #030912 100%)",
        text=_MB_TEXT, muted=_MB_MUTED,
        card_bg="rgba(11, 35, 71, 0.92)", card_border="rgba(255, 213, 62, 0.35)",
        card_hover="rgba(15, 45, 85, 0.98)", accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="neon", animated=True, animation="makrobet", brand_logo=True,
    ),
    "mb_neon": _theme(
        "Makrobet Neon",
        bg=f"radial-gradient(900px 520px at 50% -15%, {_MB_ROW}, {_MB_BG} 55%, {_MB_DARK})",
        text=_MB_TEXT, muted=_MB_MUTED,
        card_bg="rgba(255,255,255,0.05)", card_border="rgba(255, 213, 62, 0.42)",
        card_hover="rgba(255,255,255,0.10)", accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="neon", animated=True, animation="makrobet", brand_logo=True,
    ),
    "mb_altin": _theme(
        "Makrobet Altın",
        bg=f"radial-gradient(900px 520px at 50% -10%, #2a2208, {_MB_BG} 50%, {_MB_DARK})",
        text="#fff8eb", muted="#c4b07a",
        card_bg="rgba(255,213,62,0.08)", card_border="rgba(255,213,62,0.38)",
        card_hover="rgba(255,213,62,0.14)", accent=_MB_GOLD, accent2="#f59e0b",
        category="Makrobet", style="glow", animated=True, animation="gold", brand_logo=True,
    ),
    "mb_mavi": _theme(
        "Makrobet Mavi",
        bg=f"linear-gradient(165deg, {_MB_BG} 0%, {_MB_CARD} 45%, #1a4480 100%)",
        text=_MB_TEXT, muted="#9db8e8",
        card_bg="rgba(74,143,231,0.12)", card_border="rgba(74,143,231,0.38)",
        card_hover="rgba(74,143,231,0.20)", accent=_MB_BLUE, accent2=_MB_GOLD,
        category="Makrobet", style="glass", brand_logo=True,
    ),
    "mb_gece": _theme(
        "Makrobet Gece",
        bg=_MB_DARK, text=_MB_TEXT, muted=_MB_MUTED,
        card_bg=_MB_CARD, card_border="rgba(255,255,255,0.10)",
        card_hover=_MB_ROW, accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="solid", brand_logo=True,
    ),
    "mb_promo": _theme(
        "Makrobet Promo",
        bg=_MB_BG, text=_MB_TEXT, muted=_MB_MUTED,
        card_bg=_MB_ROW, card_border="rgba(255,213,62,0.12)",
        card_hover="#132f58", accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="lift", brand_logo=True,
    ),
    "mb_vip": _theme(
        "Makrobet VIP",
        bg=f"radial-gradient(1000px 560px at 50% -10%, #1a3a6e, {_MB_BG} 50%, #030912)",
        text="#f5f8ff", muted="#8fa8cc",
        card_bg="rgba(255,255,255,0.07)", card_border="rgba(212,175,55,0.35)",
        card_hover="rgba(255,255,255,0.12)", accent="#d4af37", accent2=_MB_GOLD,
        category="Makrobet", style="glow", animated=True, animation="gold", brand_logo=True,
    ),
    "mb_cam": _theme(
        "Makrobet Cam",
        bg=f"linear-gradient(160deg, {_MB_BG} 0%, {_MB_CARD} 50%, {_MB_BG} 100%)",
        text=_MB_TEXT, muted=_MB_MUTED,
        card_bg="rgba(74,143,231,0.10)", card_border="rgba(74,143,231,0.32)",
        card_hover="rgba(74,143,231,0.18)", accent=_MB_BLUE, accent2=_MB_GOLD,
        category="Makrobet", style="glass", brand_logo=True,
    ),
    "mb_soft": _theme(
        "Makrobet Soft",
        bg=f"linear-gradient(180deg, {_MB_CARD}, {_MB_BG})",
        text=_MB_TEXT, muted=_MB_MUTED,
        card_bg="rgba(255,255,255,0.06)", card_border="rgba(255,255,255,0.14)",
        card_hover="rgba(255,255,255,0.11)", accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="soft", brand_logo=True,
    ),
    "mb_outline": _theme(
        "Makrobet Outline",
        bg=_MB_BG, text=_MB_TEXT, muted=_MB_MUTED,
        card_bg="transparent", card_border="rgba(255,213,62,0.45)",
        card_hover="rgba(11,35,71,0.55)", accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="outline", brand_logo=True,
    ),
    "mb_canli": _theme(
        "Makrobet Canlı ★",
        bg=_MB_BG, text=_MB_TEXT, muted=_MB_MUTED,
        card_bg="rgba(11, 35, 71, 0.88)", card_border="rgba(255, 213, 62, 0.42)",
        card_hover="rgba(15, 45, 85, 0.95)", accent=_MB_GOLD, accent2=_MB_BLUE,
        category="Makrobet", style="neon", animated=True, animation="makrobet", brand_logo=True,
    ),
    "mb_spot": _theme(
        "Makrobet Spot Işık",
        bg=f"radial-gradient(800px 480px at 50% 0%, rgba(255,213,62,0.18), {_MB_BG} 55%, {_MB_DARK})",
        text=_MB_TEXT, muted=_MB_MUTED,
        card_bg=_MB_CARD, card_border="rgba(255,213,62,0.28)",
        card_hover=_MB_ROW, accent=_MB_GOLD, accent2="#fbbf24",
        category="Makrobet", style="chip", animated=True, animation="gold", brand_logo=True,
    ),
    "aurora": _theme(
        "★ Aurora",
        bg="#050810", text="#eef4ff", muted="#8ba4c9",
        card_bg="rgba(255,255,255,0.06)", card_border="rgba(120,200,255,0.22)",
        card_hover="rgba(255,255,255,0.11)", accent="#6ee7ff", accent2="#a78bfa",
        category="Animasyon", style="glass", animated=True, animation="aurora",
    ),
    "neon_pulse": _theme(
        "★ Neon Pulse",
        bg="#07050f", text="#f5f0ff", muted="#b8a8d9",
        card_bg="rgba(255,255,255,0.05)", card_border="rgba(168,85,247,0.35)",
        card_hover="rgba(255,255,255,0.10)", accent="#c084fc", accent2="#22d3ee",
        category="Animasyon", style="neon", animated=True, animation="neon",
    ),
    "gold_shimmer": _theme(
        "★ Altın Akış",
        bg="#0a0806", text="#fff8eb", muted="#c4a574",
        card_bg="rgba(255,255,255,0.06)", card_border="rgba(255,213,62,0.32)",
        card_hover="rgba(255,255,255,0.11)", accent="#ffd53e", accent2="#f59e0b",
        category="Animasyon", style="glow", animated=True, animation="gold",
    ),
    "ocean_wave": _theme(
        "★ Okyanus",
        bg="#031018", text="#e6f4ff", muted="#7eb8d4",
        card_bg="rgba(255,255,255,0.06)", card_border="rgba(56,189,248,0.28)",
        card_hover="rgba(255,255,255,0.11)", accent="#38bdf8", accent2="#0ea5e9",
        category="Animasyon", style="soft", animated=True, animation="ocean",
    ),
    # ── Yeni koyu iskeletler ────────────────────────────────
    "obsidian": _theme(
        "Obsidyen",
        bg="linear-gradient(165deg,#030303,#141414 55%,#1c1c1c)",
        text="#fafafa", muted="#a1a1aa",
        card_bg="rgba(255,255,255,0.05)", card_border="rgba(255,255,255,0.14)",
        card_hover="rgba(255,255,255,0.10)", accent="#a3e635",
        category="Koyu", style="solid",
    ),
    "graphite": _theme(
        "Grafit",
        bg="linear-gradient(180deg,#111827,#1f2937)",
        text="#f9fafb", muted="#9ca3af",
        card_bg="rgba(255,255,255,0.07)", card_border="rgba(156,163,175,0.28)",
        card_hover="rgba(255,255,255,0.12)", accent="#fb7185",
        category="Koyu", style="chip",
    ),
    "noir_gold": _theme(
        "Noir Altın",
        bg="radial-gradient(900px 500px at 50% 0%,#2a2112,#0a0907 60%)",
        text="#fff7e8", muted="#b8a07a",
        card_bg="rgba(255,215,120,0.06)", card_border="rgba(212,175,55,0.35)",
        card_hover="rgba(255,215,120,0.12)", accent="#eab308",
        category="Lüks", style="neon",
    ),
    "void_violet": _theme(
        "Void Mor",
        bg="linear-gradient(160deg,#0b0614,#1a0b2e 50%,#2d1250)",
        text="#f5f0ff", muted="#b4a0d9",
        card_bg="rgba(168,85,247,0.08)", card_border="rgba(192,132,252,0.35)",
        card_hover="rgba(168,85,247,0.16)", accent="#d946ef", accent2="#818cf8",
        category="Mor", style="glow",
    ),
    "cyber_mint": _theme(
        "Cyber Mint",
        bg="linear-gradient(155deg,#021411,#06332b 55%,#0a4a3c)",
        text="#ecfdf5", muted="#86efac",
        card_bg="rgba(16,185,129,0.08)", card_border="rgba(52,211,153,0.35)",
        card_hover="rgba(16,185,129,0.16)", accent="#34d399", accent2="#2dd4bf",
        category="Doğa", style="neon",
    ),
    "crimson_night": _theme(
        "Kızıl Gece",
        bg="linear-gradient(160deg,#1a0508,#3b0d14 50%,#5c1520)",
        text="#fff1f2", muted="#fda4af",
        card_bg="rgba(244,63,94,0.08)", card_border="rgba(251,113,133,0.35)",
        card_hover="rgba(244,63,94,0.15)", accent="#fb7185",
        category="Sıcak", style="lift",
    ),
    "steel_blue": _theme(
        "Çelik Mavi",
        bg="linear-gradient(165deg,#0b1220,#152238 50%,#1e3a5f)",
        text="#e8f1ff", muted="#93c5fd",
        card_bg="rgba(59,130,246,0.10)", card_border="rgba(96,165,250,0.32)",
        card_hover="rgba(59,130,246,0.18)", accent="#60a5fa",
        category="Koyu", style="split",
    ),
    "amber_haze": _theme(
        "Kehribar",
        bg="radial-gradient(800px 480px at 50% -5%,#3b2a12,#120e08 65%)",
        text="#fffbeb", muted="#fcd34d",
        card_bg="rgba(245,158,11,0.08)", card_border="rgba(251,191,36,0.35)",
        card_hover="rgba(245,158,11,0.15)", accent="#fbbf24",
        category="Sıcak", style="soft",
    ),
    "ice_slate": _theme(
        "Buzlu Slate",
        bg="linear-gradient(180deg,#0f172a,#1e293b)",
        text="#f1f5f9", muted="#94a3b8",
        card_bg="rgba(148,163,184,0.10)", card_border="rgba(148,163,184,0.28)",
        card_hover="rgba(148,163,184,0.18)", accent="#38bdf8",
        category="Koyu", style="glass",
    ),
    "berry_pop": _theme(
        "Berry Pop",
        bg="linear-gradient(150deg,#1a0612,#4a0d2e 45%,#7a1848)",
        text="#fff1f7", muted="#f9a8d4",
        card_bg="rgba(236,72,153,0.10)", card_border="rgba(244,114,182,0.35)",
        card_hover="rgba(236,72,153,0.18)", accent="#f472b6", accent2="#fb7185",
        category="Mor", style="chip",
    ),
    "forest_mist": _theme(
        "Orman Sisi",
        bg="linear-gradient(165deg,#07140c,#12301c 50%,#1a4530)",
        text="#ecfdf5", muted="#86efac",
        card_bg="rgba(34,197,94,0.08)", card_border="rgba(74,222,128,0.28)",
        card_hover="rgba(34,197,94,0.15)", accent="#4ade80",
        category="Doğa", style="classic",
    ),
    "lava_core": _theme(
        "Lav Çekirdeği",
        bg="radial-gradient(700px 420px at 50% 110%,#7c2d12,#1c0604 55%)",
        text="#fff7ed", muted="#fdba74",
        card_bg="rgba(234,88,12,0.10)", card_border="rgba(251,146,60,0.35)",
        card_hover="rgba(234,88,12,0.18)", accent="#fb923c",
        category="Sıcak", style="glow",
    ),
    "neon_lime": _theme(
        "Neon Lime",
        bg="linear-gradient(160deg,#050a04,#0f1a0a 55%,#142410)",
        text="#f7fee7", muted="#bef264",
        card_bg="rgba(132,204,22,0.08)", card_border="rgba(163,230,53,0.40)",
        card_hover="rgba(132,204,22,0.16)", accent="#a3e635", accent2="#22d3ee",
        category="Neon", style="neon",
    ),
    "sapphire": _theme(
        "Safir",
        bg="linear-gradient(160deg,#020617,#0c1a4a 50%,#12306e)",
        text="#eff6ff", muted="#93c5fd",
        card_bg="rgba(37,99,235,0.12)", card_border="rgba(59,130,246,0.40)",
        card_hover="rgba(37,99,235,0.20)", accent="#3b82f6",
        category="Koyu", style="solid",
    ),
    "rose_smoke": _theme(
        "Gül Dumanı",
        bg="linear-gradient(165deg,#1c0a12,#3a1524 50%,#4c1d30)",
        text="#fff1f2", muted="#fecdd3",
        card_bg="rgba(244,63,94,0.08)", card_border="rgba(251,113,133,0.28)",
        card_hover="rgba(244,63,94,0.14)", accent="#fb7185",
        category="Sıcak", style="soft",
    ),
    "teal_grid": _theme(
        "Teal Grid",
        bg="linear-gradient(180deg,#042f2e,#0f4c4a)",
        text="#f0fdfa", muted="#5eead4",
        card_bg="rgba(20,184,166,0.10)", card_border="rgba(45,212,191,0.35)",
        card_hover="rgba(20,184,166,0.18)", accent="#2dd4bf",
        category="Doğa", style="outline",
    ),
    "indigo_fog": _theme(
        "Indigo Sis",
        bg="linear-gradient(160deg,#0b1026,#1e1b4b 50%,#312e81)",
        text="#eef2ff", muted="#a5b4fc",
        card_bg="rgba(99,102,241,0.10)", card_border="rgba(129,140,248,0.35)",
        card_hover="rgba(99,102,241,0.18)", accent="#818cf8",
        category="Mor", style="glass",
    ),
    "copper": _theme(
        "Bakır",
        bg="radial-gradient(900px 500px at 40% 0%,#3b2414,#120a06 60%)",
        text="#fff7ed", muted="#fdba74",
        card_bg="rgba(194,120,60,0.10)", card_border="rgba(217,119,6,0.35)",
        card_hover="rgba(194,120,60,0.18)", accent="#f59e0b",
        category="Lüks", style="lift",
    ),
    "mono_ink": _theme(
        "Mono Mürekkep",
        bg="#000000",
        text="#ffffff", muted="#a3a3a3",
        card_bg="rgba(255,255,255,0.06)", card_border="rgba(255,255,255,0.18)",
        card_hover="rgba(255,255,255,0.12)", accent="#ffffff",
        category="Koyu", style="outline",
    ),
    "plasma": _theme(
        "Plasma",
        bg="linear-gradient(145deg,#0c0618,#2a0a3d 40%,#4c1d95 100%)",
        text="#faf5ff", muted="#d8b4fe",
        card_bg="rgba(168,85,247,0.12)", card_border="rgba(192,132,252,0.40)",
        card_hover="rgba(168,85,247,0.20)", accent="#e879f9", accent2="#22d3ee",
        category="Neon", style="glow",
    ),
    "arctic": _theme(
        "Arktik",
        bg="linear-gradient(180deg,#e8f4ff,#f5f9fc)",
        text="#0f172a", muted="#64748b",
        card_bg="#ffffff", card_border="rgba(14,165,233,0.22)",
        card_hover="#f0f9ff", accent="#0284c7",
        category="Açık", style="soft",
    ),
    "paper_cream": _theme(
        "Krem Kağıt",
        bg="linear-gradient(180deg,#faf6ef,#f3ebe0)",
        text="#1c1917", muted="#78716c",
        card_bg="#fffdf8", card_border="rgba(120,113,108,0.18)",
        card_hover="#f5efe6", accent="#b45309",
        category="Açık", style="classic",
    ),
    "mint_clean": _theme(
        "Nane Temiz",
        bg="linear-gradient(180deg,#f0fdf4,#ecfdf5)",
        text="#052e16", muted="#4d7c5a",
        card_bg="#ffffff", card_border="rgba(34,197,94,0.22)",
        card_hover="#f0fdf4", accent="#16a34a",
        category="Açık", style="chip",
    ),
    "blush": _theme(
        "Blush",
        bg="linear-gradient(180deg,#fff1f2,#ffe4e6)",
        text="#4c0519", muted="#9f1239",
        card_bg="#ffffff", card_border="rgba(244,63,94,0.20)",
        card_hover="#fff1f2", accent="#e11d48",
        category="Açık", style="soft",
    ),
    "sandstone": _theme(
        "Kumtaşı",
        bg="linear-gradient(165deg,#1c160f,#2a2118 50%,#3b2f22)",
        text="#faf6f0", muted="#d6c3a8",
        card_bg="rgba(255,237,213,0.08)", card_border="rgba(214,180,130,0.30)",
        card_hover="rgba(255,237,213,0.14)", accent="#d6a45a",
        category="Lüks", style="classic",
    ),
    "electric": _theme(
        "Elektrik",
        bg="linear-gradient(150deg,#050816,#0a1630 45%,#102a55)",
        text="#e0f2fe", muted="#7dd3fc",
        card_bg="rgba(14,165,233,0.10)", card_border="rgba(56,189,248,0.40)",
        card_hover="rgba(14,165,233,0.18)", accent="#22d3ee", accent2="#818cf8",
        category="Neon", style="neon",
    ),
    "velvet": _theme(
        "Kadife",
        bg="radial-gradient(900px 500px at 50% 0%,#3b0a2a,#12060f 60%)",
        text="#fdf2f8", muted="#f9a8d4",
        card_bg="rgba(219,39,119,0.10)", card_border="rgba(244,114,182,0.35)",
        card_hover="rgba(219,39,119,0.18)", accent="#f472b6",
        category="Lüks", style="glow",
    ),
    "moss": _theme(
        "Yosun",
        bg="linear-gradient(165deg,#0c1408,#1a2e12 55%,#243b1a)",
        text="#f7fee7", muted="#a3e635",
        card_bg="rgba(101,163,13,0.10)", card_border="rgba(163,230,53,0.30)",
        card_hover="rgba(101,163,13,0.18)", accent="#84cc16",
        category="Doğa", style="solid",
    ),
    "chrome": _theme(
        "Krom",
        bg="linear-gradient(180deg,#18181b,#27272a)",
        text="#fafafa", muted="#a1a1aa",
        card_bg="rgba(255,255,255,0.07)", card_border="rgba(161,161,170,0.35)",
        card_hover="rgba(255,255,255,0.12)", accent="#e4e4e7",
        category="Koyu", style="split",
    ),
    "peach_glow": _theme(
        "Şeftali",
        bg="linear-gradient(160deg,#2a120c,#5c2a1a 50%,#7c3a22)",
        text="#fff7ed", muted="#fdba74",
        card_bg="rgba(251,146,60,0.10)", card_border="rgba(253,186,116,0.35)",
        card_hover="rgba(251,146,60,0.18)", accent="#fdba74",
        category="Sıcak", style="lift",
    ),
    "deep_sea": _theme(
        "Derin Deniz",
        bg="radial-gradient(1000px 600px at 50% 100%,#0e4d6e,#021018 55%)",
        text="#e0f2fe", muted="#7dd3fc",
        card_bg="rgba(14,116,144,0.14)", card_border="rgba(34,211,238,0.30)",
        card_hover="rgba(14,116,144,0.22)", accent="#22d3ee",
        category="Doğa", style="glass",
    ),
    "orchid": _theme(
        "Orkide",
        bg="linear-gradient(155deg,#1a0a24,#3b1654 50%,#5b21b6)",
        text="#faf5ff", muted="#d8b4fe",
        card_bg="rgba(139,92,246,0.12)", card_border="rgba(167,139,250,0.40)",
        card_hover="rgba(139,92,246,0.20)", accent="#c4b5fd",
        category="Mor", style="chip",
    ),
    "coffee": _theme(
        "Kahve",
        bg="linear-gradient(165deg,#1c120c,#2c1c12 50%,#3d2818)",
        text="#faf6f1", muted="#d6b896",
        card_bg="rgba(180,140,90,0.10)", card_border="rgba(180,140,90,0.30)",
        card_hover="rgba(180,140,90,0.18)", accent="#d4a574",
        category="Lüks", style="classic",
    ),
    "skyline": _theme(
        "Skyline",
        bg="linear-gradient(180deg,#f8fafc,#e2e8f0)",
        text="#0f172a", muted="#64748b",
        card_bg="#ffffff", card_border="rgba(15,23,42,0.10)",
        card_hover="#f1f5f9", accent="#0ea5e9",
        category="Açık", style="lift",
    ),
    "matcha": _theme(
        "Matcha",
        bg="linear-gradient(160deg,#f7fee7,#ecfccb)",
        text="#14532d", muted="#4d7c0f",
        card_bg="#ffffff", card_border="rgba(101,163,13,0.22)",
        card_hover="#f7fee7", accent="#65a30d",
        category="Açık", style="outline",
    ),
    "inferno": _theme(
        "Inferno",
        bg="linear-gradient(150deg,#1a0500,#4a0e00 40%,#7c1d0a)",
        text="#fff7ed", muted="#fdba74",
        card_bg="rgba(220,38,38,0.12)", card_border="rgba(248,113,113,0.40)",
        card_hover="rgba(220,38,38,0.20)", accent="#f87171", accent2="#fbbf24",
        category="Sıcak", style="neon",
    ),
    "glacier": _theme(
        "Buzul",
        bg="linear-gradient(180deg,#082f49,#0c4a6e)",
        text="#e0f2fe", muted="#7dd3fc",
        card_bg="rgba(125,211,252,0.10)", card_border="rgba(125,211,252,0.35)",
        card_hover="rgba(125,211,252,0.18)", accent="#7dd3fc",
        category="Koyu", style="glass",
    ),
    "pastel_lilac": _theme(
        "Pastel Lila",
        bg="linear-gradient(180deg,#faf5ff,#f3e8ff)",
        text="#3b0764", muted="#7e22ce",
        card_bg="#ffffff", card_border="rgba(168,85,247,0.22)",
        card_hover="#faf5ff", accent="#9333ea",
        category="Açık", style="chip",
    ),
    "midnight_emerald": _theme(
        "Gece Zümrüt",
        bg="radial-gradient(900px 520px at 50% 0%,#064e3b,#022c22 55%,#011914)",
        text="#ecfdf5", muted="#6ee7b7",
        card_bg="rgba(16,185,129,0.10)", card_border="rgba(52,211,153,0.35)",
        card_hover="rgba(16,185,129,0.18)", accent="#34d399",
        category="Doğa", style="glow",
    ),
    "tokyo_night": _theme(
        "Tokyo Night",
        bg="linear-gradient(160deg,#0d1117,#161b22 50%,#1f2937)",
        text="#e6edf3", muted="#8b949e",
        card_bg="rgba(88,166,255,0.08)", card_border="rgba(88,166,255,0.28)",
        card_hover="rgba(88,166,255,0.14)", accent="#58a6ff", accent2="#f778ba",
        category="Neon", style="split",
    ),
    "casino_royale": _theme(
        "Casino Royale",
        bg="radial-gradient(1000px 560px at 50% -10%,#1a3a1a,#061206 50%,#030803)",
        text="#f0fff4", muted="#86efac",
        card_bg="rgba(34,197,94,0.08)", card_border="rgba(250,204,21,0.35)",
        card_hover="rgba(34,197,94,0.15)", accent="#facc15", accent2="#22c55e",
        category="Marka", style="neon",
    ),
}

DEFAULT_THEME = "makrobet"
DEFAULT_HEADING_STYLE = "classic"
DEFAULT_BRAND_LOGO = "/static/biolink/logo/logo-400.png"
DEFAULT_BANNER = "/static/biolink/banners/banner-468x60.gif"

BRAND_LOGOS = [
    {"key": "logo-400", "label": "Logo 400px", "url": "/static/biolink/logo/logo-400.png", "w": 400, "h": 93},
    {"key": "logo-600", "label": "Logo 600px", "url": "/static/biolink/logo/logo-600.png", "w": 600, "h": 139},
    {"key": "logo-200", "label": "Logo 200px", "url": "/static/biolink/logo/logo-200.png", "w": 200, "h": 46},
    {"key": "logo-full", "label": "Logo Full PNG", "url": "/static/biolink/logo/Logo.png", "w": 6114, "h": 1426},
    {"key": "logo-svg", "label": "Logo SVG", "url": "/static/biolink/logo/Logo.svg", "w": 0, "h": 0},
    {"key": "logo-avatar", "label": "Logo Avatar (kare)", "url": "/static/biolink/logo/logo-avatar-512.png", "w": 512, "h": 512},
]

BRAND_BANNERS = [
    # Yatay bannerlar
    {"key": "468x60", "label": "468×60 (önerilen)", "url": "/static/biolink/banners/banner-468x60.gif", "w": 468, "h": 60},
    {"key": "400x60", "label": "400×60", "url": "/static/biolink/banners/banner-400x60.gif", "w": 400, "h": 60},
    {"key": "468x50", "label": "468×50", "url": "/static/biolink/banners/banner-468x50.gif", "w": 468, "h": 50},
    {"key": "150x50", "label": "150×50", "url": "/static/biolink/banners/banner-150x50.gif", "w": 150, "h": 50},
    {"key": "728x90", "label": "728×90", "url": "/static/biolink/banners/banner-728x90.gif", "w": 728, "h": 90},
    {"key": "1000x50", "label": "1000×50", "url": "/static/biolink/banners/banner-1000x50.gif", "w": 1000, "h": 50},
    {"key": "1000x100", "label": "1000×100", "url": "/static/biolink/banners/banner-1000x100.gif", "w": 1000, "h": 100},
    {"key": "1200x90", "label": "1200×90", "url": "/static/biolink/banners/banner-1200x90.gif", "w": 1200, "h": 90},
    {"key": "1550x100", "label": "1550×100", "url": "/static/biolink/banners/banner-1550x100.gif", "w": 1550, "h": 100},
    {"key": "2000x160", "label": "2000×160", "url": "/static/biolink/banners/banner-2000x160.gif", "w": 2000, "h": 160},
    {"key": "1080x1080", "label": "1080×1080 (kare)", "url": "/static/biolink/banners/banner-1080x1080.gif", "w": 1080, "h": 1080},
    # Dikey bannerlar
    {"key": "136x728", "label": "136×728 (dikey)", "url": "/static/biolink/banners/banner-136x728.gif", "w": 136, "h": 728},
    {"key": "120x600", "label": "120×600 (dikey)", "url": "/static/biolink/banners/banner-120x600.gif", "w": 120, "h": 600},
    {"key": "160x600", "label": "160×600 (dikey)", "url": "/static/biolink/banners/banner-160x600.gif", "w": 160, "h": 600},
    {"key": "300x600", "label": "300×600 (dikey)", "url": "/static/biolink/banners/banner-300x600.gif", "w": 300, "h": 600},
]


def brand_assets():
    return {"logos": list(BRAND_LOGOS), "banners": list(BRAND_BANNERS), "default_logo": DEFAULT_BRAND_LOGO, "default_banner": DEFAULT_BANNER}

# key, name, category — CSS class = hs-{key}
HEADING_STYLES = [
    ("classic", "Klasik çizgi", "Çizgi"),
    ("double", "Çift çizgi", "Çizgi"),
    ("thick", "Kalın çizgi", "Çizgi"),
    ("dashed", "Kesik çizgi", "Çizgi"),
    ("dotted", "Noktalı", "Çizgi"),
    ("fade", "Soluk çizgi", "Çizgi"),
    ("gradient", "Gradient çizgi", "Çizgi"),
    ("underline", "Alt çizgi", "Çizgi"),
    ("overline", "Üst çizgi", "Çizgi"),
    ("brackets", "Köşeli parantez", "Çerçeve"),
    ("parens", "Yuvarlak parantez", "Çerçeve"),
    ("chevrons", "Chevron", "Çerçeve"),
    ("box", "Kutu", "Çerçeve"),
    ("outline_box", "Boş kutu", "Çerçeve"),
    ("pill", "Pill rozet", "Rozet"),
    ("badge", "Badge", "Rozet"),
    ("chip", "Chip", "Rozet"),
    ("tag", "Etiket", "Rozet"),
    ("ribbon", "Kurdele", "Rozet"),
    ("flag", "Bayrak", "Rozet"),
    ("diamond", "Elmas ayraç", "Süs"),
    ("star", "Yıldız ayraç", "Süs"),
    ("dot", "Orta nokta", "Süs"),
    ("spark", "Kıvılcım", "Süs"),
    ("crown", "Taç", "Süs"),
    ("trophy", "Kupa", "Süs"),
    ("bolt", "Şimşek", "Süs"),
    ("heart", "Kalp", "Süs"),
    ("fire", "Ateş", "Süs"),
    ("gem", "Mücevher", "Süs"),
    ("glow", "Işıltı", "Efekt"),
    ("neon", "Neon", "Efekt"),
    ("shadow", "Gölge yazı", "Efekt"),
    ("emboss", "Kabartma", "Efekt"),
    ("glass", "Cam şerit", "Efekt"),
    ("blur_bar", "Blur bar", "Efekt"),
    ("accent_bar", "Sol şerit", "Blok"),
    ("left_rail", "Sol ray", "Blok"),
    ("split", "İki sütun çizgi", "Blok"),
    ("center_badge", "Orta rozet", "Blok"),
    ("stack", "Katmanlı", "Blok"),
    ("wave", "Dalga", "Blok"),
    ("slash", "Eğik çizgi", "Blok"),
    ("hash", "Hash kenar", "Blok"),
    ("minimal", "Minimal sade", "Minimal"),
    ("caps", "Büyük harf", "Minimal"),
    ("tiny", "Küçük etiket", "Minimal"),
    ("wide", "Geniş aralık", "Minimal"),
    ("italic", "İtalik vurgu", "Minimal"),
    ("serif", "Serif başlık", "Minimal"),
    ("uppercase_dots", "Noktalı caps", "Minimal"),
    ("gold_line", "Altın çizgi", "Lüks"),
    ("luxury", "Lüks çerçeve", "Lüks"),
    ("vip", "VIP şerit", "Lüks"),
    ("casino", "Casino ayırıcı", "Lüks"),
    ("spotlight", "Spotlight", "Lüks"),
]

HEADING_STYLE_KEYS = frozenset(k for k, _, _ in HEADING_STYLES)
HEADING_STYLE_META = {k: {"name": n, "category": c} for k, n, c in HEADING_STYLES}


def theme_list():
    return [
        {
            "key": k,
            "name": v["name"],
            "accent": v.get("accent"),
            "accent2": v.get("accent2") or v.get("accent"),
            "bg": v.get("bg"),
            "category": v.get("category") or "Koyu",
            "style": v.get("style") or "classic",
            "animated": bool(v.get("animated")),
            "brand_logo": bool(v.get("brand_logo")),
        }
        for k, v in THEMES.items()
    ]


def heading_style_list():
    return [
        {"key": k, "name": n, "category": c}
        for k, n, c in HEADING_STYLES
    ]


def normalize_heading_style(key):
    key = (key or "").strip().lower().replace(" ", "_")
    if key in HEADING_STYLE_KEYS:
        return key
    return DEFAULT_HEADING_STYLE
