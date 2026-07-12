"""P&L raporu için geçmiş dönem verileri — merkeze iletilen Excel raporlarından aktarılmıştır.

Her yeni ay eklendiğinde PL_LINES ve PL_META sözlüklerine yeni bir "YYYY-MM"
anahtarı eklenip accounting_pl.reseed_period_from_history() ile yüklenir.
"""

from accounting_pl import (
    SECTION_DEGISKEN,
    SECTION_GELIRLER,
    SECTION_KOMISYON,
    SECTION_PERSONEL,
    SECTION_REKLAM,
    SECTION_SABIT,
    SECTION_UCUNCU_SIRKET,
)

# Kaynak: "Mkr PL Haziran 2025 .xlsx" -> "P&L" sekmesi
PL_LINES = {
    "2025-06": {
        SECTION_GELIRLER: [
            ("TOPLAM MÜŞTERİ BAKİYESİ 31 mayıs 2025", 2167602.96),
            ("TOPLAM MÜŞTERİ BAKİYESİ 30 haziran 2025", -3590162.47),
            ("YATIRIM", 140229296.47),
            ("ÇEKİM", -114228475.48),
            ("MAN. ARTIRMA", 9000),
            ("MAN. EKSİLTME", -13100),
            ("Haziran 2025 Jackpot Geri Ödeme", 2656883.52),
            ("Haziran 2025 Turnuva Kazançları", 30660.71),
            ("TEST YATIRIM", -1200),
            ("TEST ÇEKİM", 200),
        ],
        SECTION_PERSONEL: [
            ("Ofis personeli elden ödenen maaş", 1604022.81),
            ("Personel maaş ödemesi", 3012219.57),
            ("Personel prim ödemesi", 0),
        ],
        SECTION_SABIT: [
            ("Ofis kira + fatura", 252151.38),
            ("Live Chat ödemesi", 97875),
            ("Pronet CRM Haziran fatura ödemesi", 115739),
            ("T2M aylık ödeme", 10766.25),
            ("Sosyal medya VPS ödemesi", 1761.75),
            ("Dialogtab WhatsApp ödemesi", 35757),
        ],
        SECTION_DEGISKEN: [
            ("PBX call center arama programı kurulum ücreti", 157000),
            ("400 adet telegram numara alımı (pishing ve reklam çalışmaları)", 14798.7),
            ("Domain ve sunucu alım bakiyesi", 78300),
            ("Meta reklamlar (cloaker + hesap + bakiye)", 78300),
            ("Panel DA kurulum ücreti", 23490),
            ("5 adet Azerbaycan numarası (TG hesapları için)", 1370.25),
            ("4x telegram premium ödemesi", 4932.9),
            ("Semrush hesap açım bakiye ödemesi", 9787.5),
            ("Eleven Labs ödemesi", 1761.75),
            ("Social Camp ödemesi", 704.7),
            ("TG bot kurulum", 900.45),
            ("Makrobet paravan domainler", 8456.4),
            ("IG hesap alımı", 10179),
            ("TW hesap alımı", 10179),
            ("400 x sanal TG numarası", 14994.45),
            ("Supabase aylık ödeme", 6185.7),
            ("Sunucu 1 ödemesi", 3249.45),
            ("Sunucu 2 ödemesi", 3132),
            ("Sunucu 3 ödemesi", 7830),
            ("Reklam bütçesi", 78300),
            ("Sunucu 4 ödemesi", 7830),
            ("SSL paketi", 31320),
            ("Ofis mutfak gideri", 7830),
            ("1M SMS kredi ödemesi", 179698.5),
            ("PBX kontör yüklemesi", 50000),
            ("Sim kart numara alımı (Ukrayna Rusya)", 1969),
            ("Freelance grafik ödemesi", 12059.7),
            ("150 adet sanal numara telegram", 11466.6),
            ("Telegram boasting üye çekimi", 12065.8),
            ("Kelime backlink çalışması", 3134.72),
            ("Telegram hesap alımı", 1031.68),
            ("Meta ads kredi yüklemesi", 19835),
            ("Sanal kart alımı ve telegram boost ödemesi", 5363.55),
            ("Twitter hesap satın alımı", 3694.89),
            ("Telegram boasting üye çekimi", 4012.73),
            ("Freelance grafik ödemesi", 12120.7),
            ("Telegram boost + twitter hesap alımı", 7160.4),
            ("Meta reklam ödemesi", 10939.5),
            ("Telegram boost üye çekimi", 4030.91),
            ("Makro PBX call center programı kredi ödemesi", 50000),
        ],
        SECTION_REKLAM: [
            ("Bonus Cux kanal anlaşması", 15033.6),
            ("Makrobettv ve Betroztv aylık ödeme", 11808),
            ("Sosyal medya etkinlik (10 x pizza dağıtımı)", 4723.2),
            ("Tipster anlaşma ödemesi", 19680),
            ("Molakral youtuber anlaşma ödemesi", 59505),
            ("Grafik ajansı aylık ödeme", 39670),
            ("Superbonus kanal anlaşma ödemesi", 138845),
            ("Meta reklam ücreti", 39908.55),
            ("Meta ads kredi yüklemesi", 10898.25),
            ("Fuatbaba kanal anlaşması", 99775),
            ("Seo optimizasyon kanal anlaşması", 50000),
        ],
        SECTION_KOMISYON: [
            ("Yatırım komisyon miktarı", 5044554.15),
            ("Çekim komisyon miktarı", 569503.59),
        ],
        SECTION_UCUNCU_SIRKET: [
            ("Pronet", 14557838.34),
            ("Klaspoker", 677225.75),
            ("Haziran 2025 Jackpot Geri Ödeme", 2656883.52),
            ("Haziran 2025 Turnuva Kazançları", 30660.71),
            ("Youpay coin ödeme", 0),
        ],
    },
}

PL_META = {
    "2025-06": {
        "notes": "PRONET ÖDENEN: Pronet + turnuva ödemeleri toplamı eksi olarak yazılır.",
        "pronet_fatura_label": "PRONET FATURASI Haziran 2025 € 287.596,70",
        "pronet_fatura_amount": 12786549.28,
        "pronet_odenen_amount": -18599834.07,
        "asil_net_amount": 2967769.15,
    },
}
