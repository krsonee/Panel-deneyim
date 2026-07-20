"""MakroBet markasına uygun hazır mailing şablonları.

Görsel referans: https://makrobet.com/tr/pages/promotions
Palet: biolink_themes (_MB_*) — navy #061c3d · altın #ffd53e · metin #e8efff
"""

from __future__ import annotations

from database import (
    execute,
    fetchone,
    get_mail_setting,
    insert_returning_id,
    iso,
    upsert_mail_setting,
    utcnow,
)

SEED_FLAG = "seeded_makrobet_templates_v3"

# Site promosyon sayfası (kullanıcı referansı)
PROMO_URL = "https://makrobet.com/tr/pages/promotions"
CTA = PROMO_URL
CTA_TOKEN = "{{link:sc:https://makrobet.com/tr/pages/promotions}}"
CTA_CASINO = "{{link:sc:https://makrobet.com/tr/game/casino}}"
CTA_SPORT = "{{link:sc:https://makrobet.com/tr/sport/live}}"
CTA_PROMO = CTA_TOKEN
CTA_LIVE = "{{link:sc:https://makrobet.com/tr/game/live-casino}}"

# Marka (site ile aynı)
_MB_BG = "#061c3d"
_MB_CARD = "#0b2347"
_MB_ROW = "#0f2d55"
_MB_TEXT = "#e8efff"
_MB_MUTED = "#8fa3cc"
_MB_GOLD = "#ffd53e"
_MB_BORDER = "rgba(255,213,62,0.35)"

# CDN logo (site); e-posta istemcileri çoğu zaman çekebilir
_LOGO_CDN = "https://makrobet.com/cdn/makrobet/upload_files/logo.png"


def _html_shell(title, eyebrow, headline, body_html, cta_label, cta_token, note="", badge="Special"):
    note_block = ""
    if note:
        note_block = f"""
          <tr>
            <td style="padding:0 28px 10px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;color:{_MB_MUTED};">
              {note}
            </td>
          </tr>"""
    badge_block = ""
    if badge:
        badge_block = f"""
          <tr>
            <td style="padding:4px 28px 0;font-family:Urbanist,Arial,Helvetica,sans-serif;">
              <span style="display:inline-block;background:{_MB_GOLD};color:{_MB_BG};font-size:11px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;padding:5px 12px;border-radius:999px;">{badge}</span>
            </td>
          </tr>"""
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{_MB_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_MB_BG};">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:{_MB_CARD};border-radius:14px;overflow:hidden;border:1px solid {_MB_BORDER};">
          <tr>
            <td align="center" style="padding:26px 28px 12px;background:{_MB_BG};">
              <img src="{_LOGO_CDN}" alt="Makrobet" width="168" style="display:block;margin:0 auto 8px;max-width:168px;height:auto;border:0;">
              <div style="font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:26px;font-weight:800;letter-spacing:0.02em;line-height:1;color:{_MB_GOLD};">
                Makrobet
              </div>
            </td>
          </tr>
          {badge_block}
          <tr>
            <td style="padding:14px 28px 0;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:{_MB_GOLD};">
              {eyebrow}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 28px 12px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:26px;line-height:1.25;font-weight:800;color:#ffffff;">
              {headline}
            </td>
          </tr>
          <tr>
            <td style="padding:0 28px 18px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:15px;line-height:1.65;color:{_MB_TEXT};">
              {body_html}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:6px 28px 10px;">
              <a href="{cta_token}" style="display:inline-block;background:{_MB_GOLD};color:{_MB_BG};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;text-decoration:none;padding:14px 32px;border-radius:8px;">
                {cta_label}
              </a>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:0 28px 22px;">
              <a href="{CTA_PROMO}" style="display:inline-block;background:transparent;color:{_MB_GOLD};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-decoration:none;padding:10px 22px;border-radius:8px;border:1px solid {_MB_GOLD};">
                Tüm Promosyonlar
              </a>
            </td>
          </tr>
          {note_block}
          <tr>
            <td style="padding:16px 28px 22px;border-top:1px solid {_MB_ROW};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:11px;line-height:1.55;color:{_MB_MUTED};text-align:center;">
              18+ · Sorumlu bahis · Şartlar ve çevrim koşulları geçerlidir.<br>
              Makrobet · <a href="{CTA_TOKEN}" style="color:{_MB_GOLD};text-decoration:none;">Promosyonlar</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


HTML_TEMPLATES = [
    {
        "name": "HTML · Hoş Geldin Casino",
        "subject": "{{name}}, Makrobet'e hoş geldin — casino başlangıç fırsatı",
        "html_body": _html_shell(
            "Hoş Geldin",
            "Yeni üye · Casino",
            "Casino’da güçlü bir başlangıç yap",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Makrobet ailesine hoş geldin. Slot ve canlı casino’da ilk yatırımlarına özel
            <strong style="color:#ffd53e;">hoş geldin bonusları</strong> seni bekliyor.
            Promosyonlar sayfasından kampanyanı seç, oynamaya başla.
            """,
            "Bonusları Gör",
            CTA_PROMO,
            "Güncel oran ve şartlar Promosyonlar sayfasında.",
            badge="Hoş Geldin",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Spor Yatırım Bonusu",
        "subject": "{{name}}, spor yatırımlarına ekstra güç — Makrobet",
        "html_body": _html_shell(
            "Spor Bonusu",
            "Canlı bahis · Spor",
            "Kuponunu güçlendirecek yatırım fırsatı",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Spor ve canlı bahiste aktif kampanyalarla yatırımlarına
            <strong style="color:#ffd53e;">ekstra bonus</strong> yakalayabilirsin.
            Maç öncesi veya canlı — seçim senin.
            """,
            "Spor Bonuslarını Aç",
            CTA_SPORT,
            badge="Spor",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Casino Kayıp İadesi",
        "subject": "{{name}}, kayıp iadesi fırsatını kaçırma — Makrobet",
        "html_body": _html_shell(
            "Kayıp iadesi",
            "Casino · Cashback",
            "Şans dönsün diye bir fırsat daha",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Casino / canlı casino kayıpların için dönemsel
            <strong style="color:#ffd53e;">iade (cashback)</strong> kampanyaları aktif olabilir.
            Uygunluğu kontrol et, bonusunu talep et.
            """,
            "Detayları Gör",
            CTA_PROMO,
            badge="Cashback",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Freebet + Freespin",
        "subject": "{{name}}, freebet & freespin şansı — Makrobet",
        "html_body": _html_shell(
            "Hediyeler",
            "Freebet · Freespin",
            "Günlük hediyeler seni bekliyor olabilir",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Makrobet’te freebet ve freespin kampanyaları dönüyor.
            Hesabına gir, <strong style="color:#ffd53e;">aktif promosyonları</strong> yakala.
            """,
            "Promosyonlara Git",
            CTA_PROMO,
            badge="Special",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · VIP Özel Davet",
        "subject": "{{name}}, Makro VIP Club daveti — Makrobet",
        "html_body": _html_shell(
            "VIP",
            "Makro VIP Club",
            "Seçili üyelere özel ayrıcalıklar",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Seni <strong style="color:#ffd53e;">Makro VIP Club</strong> deneyimine davet ediyoruz:
            öncelikli destek, özel kampanyalar ve kişiselleştirilmiş fırsatlar.
            """,
            "VIP’ye Göz At",
            CTA_PROMO,
            "Bu ileti seçili üyelere yönelik bilgilendirme amaçlıdır.",
            badge="VIP",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Canlı Casino Hafta Sonu",
        "subject": "{{name}}, hafta sonu canlı casino — Makrobet",
        "html_body": _html_shell(
            "Hafta sonu",
            "Canlı casino",
            "Masa oyunlarında geceye hazır mısın?",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Rulet, blackjack ve canlı masalar hafta sonu için hazır.
            Aktif bonuslarını kontrol et, masanı seç,
            <strong style="color:#ffd53e;">canlı casino</strong>’ya bağlan.
            """,
            "Canlı Casino’yu Aç",
            CTA_LIVE,
            badge="Canlı",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Promosyonlar",
        "subject": "{{name}}, güncel Makrobet promosyonları seni bekliyor",
        "html_body": _html_shell(
            "Promosyonlar",
            "Tüm kampanyalar",
            "Bonus, freebet, cashback — hepsi bir arada",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Makrobet Promosyonlar sayfasında sana uygun
            <strong style="color:#ffd53e;">güncel bonusları</strong> inceleyebilirsin.
            Tek tıkla tüm kampanyalara ulaş.
            """,
            "Tüm Promosyonlar",
            CTA_PROMO,
            badge="Promosyon",
        ),
        "text_body": "",
    },
]


TEXT_TEMPLATES = [
    {
        "name": "Yazı · Hoş Geldin Kısa",
        "subject": "{{name}}, Makrobet'e hoş geldin!",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Makrobet'e hoş geldin. Casino ve spor tarafındaki güncel hoş geldin fırsatlarını kaçırma.

Kampanyaları incele:
{CTA_TOKEN}

İyi şanslar,
Makrobet ekibi
""",
    },
    {
        "name": "Yazı · Spor Yatırım",
        "subject": "{{name}}, spor yatırımına ekstra bakış",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Canlı bahis ve spor yatırımlarına özel kampanyalar aktif olabilir.
Kuponunu güçlendirmek için güncel spor bonuslarını kontrol et:

{CTA_SPORT}

Makrobet
""",
    },
    {
        "name": "Yazı · Kayıp İadesi",
        "subject": "{{name}}, kayıp iadesi fırsatını kontrol et",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Casino veya spor tarafında dönemsel kayıp iadesi / cashback kampanyaları bulunabilir.
Sana uyan bir kampanya var mı diye bakmanı öneririz:

{CTA_PROMO}

Şartlar ve çevrim koşulları geçerlidir.
Makrobet
""",
    },
    {
        "name": "Yazı · Freespin Hatırlatma",
        "subject": "{{name}}, freespin / freebet hatırlatması",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Hesabında bekleyen freespin veya freebet olabilir — ya da günlük hediye kampanyalarına katılma şansın açık olabilir.
Hemen kontrol et:

{CTA_PROMO}

Makrobet
""",
    },
    {
        "name": "Yazı · IVR Sonrası Takip",
        "subject": "{{name}}, aramamızın ardından — fırsatlar seni bekliyor",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Az önce / kısa süre önce seninle iletişim kurduk. Konuştuğumuz fırsatları ve güncel Makrobet kampanyalarını buradan inceleyebilirsin:

{CTA_TOKEN}

Sorun olursa canlı destek her zaman yanında.
Makrobet
""",
    },
    {
        "name": "Yazı · Yeniden Aktivasyon",
        "subject": "{{name}}, seni özledik — Makrobet'te yenilikler var",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Bir süredir görüşemedik. Spor, casino ve canlı casino tarafında seni bekleyen güncel fırsatlar olabilir.

Tekrar uğra:
{CTA_TOKEN}

18+ · Sorumlu bahis
Makrobet
""",
    },
]


def seed_makrobet_mail_templates(conn, force_missing=False, overwrite=False):
    """Eksik şablonları ekler; overwrite=True ise seed HTML’lerini site stiline günceller.

    v3 flag yoksa ilk boot’ta HTML seed’leri otomatik yenilenir (promosyon sayfası stili).
    """
    now = iso(utcnow())
    added = 0
    updated = 0
    _ = force_missing  # API uyumu
    already_v3 = (get_mail_setting(conn, SEED_FLAG, "") or "").strip() == "1"
    if not already_v3:
        overwrite = True
    for item in HTML_TEMPLATES + TEXT_TEMPLATES:
        name = item["name"]
        exists = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (name,))
        if exists:
            if overwrite and (item.get("html_body") or "").strip():
                execute(
                    conn,
                    """
                    UPDATE mail_templates
                    SET subject = ?, html_body = ?, text_body = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        item["subject"],
                        item.get("html_body") or "",
                        item.get("text_body") or "",
                        now,
                        exists["id"],
                    ),
                )
                updated += 1
            continue
        insert_returning_id(
            conn,
            """
            INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                item["subject"],
                item.get("html_body") or "",
                item.get("text_body") or "",
                now,
                now,
            ),
        )
        added += 1
    upsert_mail_setting(conn, SEED_FLAG, "1")
    try:
        conn.commit()
    except Exception:
        pass
    return {"added": added, "updated": updated}
