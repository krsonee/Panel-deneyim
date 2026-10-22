"""User-facing Turkish labels for menu buttons and messages.

Kept separate from prompt_builder.py: prompt_builder generates English
prompts for the AI providers (they perform best with English prompts),
while this module holds the Turkish strings shown to the human user in
Telegram. Both key off of the same enums in constants.py so they never
drift out of sync.
"""

from __future__ import annotations

from bot.utils.constants import CasinoTheme, MediaCategory, OutputType, SportsTheme

MEDIA_CATEGORY_LABELS: dict[MediaCategory, str] = {
    MediaCategory.CASINO: "🎰 Casino",
    MediaCategory.SPORTS: "⚽ Spor Bahis",
}

CASINO_THEME_LABELS: dict[CasinoTheme, str] = {
    CasinoTheme.SLOT_KEY_ART: "🎡 Slot Ana Görseli (Key Art)",
    CasinoTheme.FREESPIN_RAIN: "🌟 Freespin Yağmuru",
    CasinoTheme.MASCOT_3D: "🐯 3D Parlak Maskot",
    CasinoTheme.JACKPOT_BANNER: "💰 Jackpot / Büyük Ödül Banner",
}

CASINO_THEME_DESCRIPTIONS: dict[CasinoTheme, str] = {
    CasinoTheme.SLOT_KEY_ART: (
        "Slot oyununun ana tanıtım görseli: parlak semboller, altın çerçeve, "
        "royal blue arka plan."
    ),
    CasinoTheme.FREESPIN_RAIN: (
        "Ekrandan yağan altın/elmas sikkeler ve 'FREE SPINS' patlaması efekti."
    ),
    CasinoTheme.MASCOT_3D: (
        "Oyunun 3D, parlak (glossy) maskot karakteri — dinamik poz, canlı ifade."
    ),
    CasinoTheme.JACKPOT_BANNER: (
        "Büyük ödül / jackpot anını kutlayan patlamalı, altın ışıklı banner."
    ),
}

SPORTS_THEME_LABELS: dict[SportsTheme, str] = {
    SportsTheme.MATCHDAY_BANNER: "🏟️ Maç Günü Banner",
    SportsTheme.ODDS_BOARD: "📊 Oran Tablosu Görseli",
    SportsTheme.WINNING_TICKET: "🎫 Kazanan Kupon Kutlaması",
    SportsTheme.LIVE_ACTION: "🔥 Canlı Aksiyon Sahnesi",
}

SPORTS_THEME_DESCRIPTIONS: dict[SportsTheme, str] = {
    SportsTheme.MATCHDAY_BANNER: "İki takımı/sporcuyu karşı karşıya getiren dramatik maç günü afişi.",
    SportsTheme.ODDS_BOARD: "Bahis oranlarını gösteren, stadyum atmosferli dijital tabela görseli.",
    SportsTheme.WINNING_TICKET: "Kazanan bahis kuponunu kutlayan, konfeti ve ışık efektli sahne.",
    SportsTheme.LIVE_ACTION: "Maçın en gerilimli anını donduran, hızlı hareket hissi veren sahne.",
}

OUTPUT_TYPE_LABELS: dict[OutputType, str] = {
    OutputType.IMAGE: "🖼️ Görsel (DALL·E 3)",
    OutputType.VIDEO: "🎬 Video / Animasyon",
    OutputType.STICKER: "✨ Şeffaf Sticker (.webm)",
}

OUTPUT_TYPE_DESCRIPTIONS: dict[OutputType, str] = {
    OutputType.IMAGE: "Yüksek çözünürlüklü statik görsel üretir.",
    OutputType.VIDEO: "Kısa, sinematik bir animasyon/loop üretir (Luma / Runway).",
    OutputType.STICKER: "Arka planı şeffaflaştırılmış, Telegram'a hazır sticker üretir.",
}
