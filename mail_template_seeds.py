"""MakroBet markasına uygun hazır mailing şablonları.

Görsel referans: https://makrobet.com/tr/pages/promotions
Logo: makrobet.com CDN’den indirilip /static/mailing/makrobet-logo.png
Palet: site body #061c3d · metin #e6f0fe · CTA altın #ffd400
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

SEED_FLAG = "seeded_makrobet_templates_v6"

# Aff panel tracking link (çoğu HTML CTA buraya)
AFF_URL = "https://makrovip.com/Vipmail"
AFF_TOKEN = "{{link:sc:https://makrovip.com/Vipmail}}"

# Şans bonusu şablonuna özel WhatsApp / VIP destek
WHATSAPP_URL = "https://vipmakro.com"
WHATSAPP_TOKEN = "{{link:sc:https://vipmakro.com}}"

# Geriye dönük isimler — varsayılan aff
PROMO_URL = AFF_URL
SITE_URL = AFF_URL
VIP_URL = AFF_URL
CTA_TOKEN = AFF_TOKEN
CTA_SITE = AFF_TOKEN
CTA_VIP = AFF_TOKEN
CTA_CASINO = AFF_TOKEN
CTA_SPORT = AFF_TOKEN
CTA_PROMO = AFF_TOKEN
CTA_LIVE = AFF_TOKEN

# Site ile aynı (promosyonlar sayfası)
_MB_BG = "#061c3d"
_MB_CARD = "#0a2448"
_MB_ROW = "#0f2d55"
_MB_TEXT = "#e6f0fe"
_MB_MUTED = "#9db3d4"
_MB_GOLD = "#ffd400"
_MB_BORDER = "#2a4a7a"

# Preview + gönderimde absolute URL’e çevrilir
_LOGO_PLACEHOLDER = "__MAIL_LOGO__"


def _spam_tip_banner():
    """Gmail/Outlook’ta spam klasöründe butonlar çalışmasın diye uyarı şeridi."""
    return f"""
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;">
    <tr>
      <td align="center" style="padding:11px 18px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:12px;line-height:1.45;color:#ffffff;">
        <span style="color:{_MB_GOLD};font-size:13px;vertical-align:middle;">⚠</span>
        &nbsp;Butonların tıklanabilir olması için
        <strong style="color:{_MB_GOLD};">Spam olmadığını bildir</strong>
        seçeneğine tıklayın.
      </td>
    </tr>
  </table>"""


def _promo_chip(label):
    return (
        f'<td style="padding:4px;">'
        f'<span style="display:inline-block;background:{_MB_ROW};color:{_MB_TEXT};'
        f"font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;"
        f'padding:7px 10px;border-radius:8px;border:1px solid {_MB_BORDER};white-space:nowrap;">'
        f"{label}</span></td>"
    )


def _html_shell(
    title,
    eyebrow,
    headline,
    body_html,
    cta_label,
    cta_token,
    note="",
    badge="Special",
    secondary_label="",
    secondary_token="",
    extra_html="",
):
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
            <td style="padding:6px 28px 0;font-family:Urbanist,Arial,Helvetica,sans-serif;">
              <span style="display:inline-block;background:{_MB_GOLD};color:{_MB_BG};font-size:11px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;padding:5px 12px;border-radius:999px;">{badge}</span>
            </td>
          </tr>"""
    secondary_block = ""
    if secondary_label and secondary_token:
        secondary_block = f"""
          <tr>
            <td align="center" style="padding:0 28px 20px;">
              <a href="{secondary_token}" style="display:inline-block;background:transparent;color:{_MB_GOLD};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-decoration:none;padding:11px 22px;border-radius:8px;border:1px solid {_MB_GOLD};">
                {secondary_label}
              </a>
            </td>
          </tr>"""
    else:
        secondary_block = f"""
          <tr>
            <td align="center" style="padding:0 28px 20px;">
              <a href="{CTA_PROMO}" style="display:inline-block;background:transparent;color:{_MB_GOLD};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-decoration:none;padding:11px 22px;border-radius:8px;border:1px solid {_MB_GOLD};">
                Tüm Promosyonlar
              </a>
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
  {_spam_tip_banner()}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_MB_BG};">
    <tr>
      <td align="center" style="padding:20px 12px 28px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:{_MB_CARD};border-radius:12px;overflow:hidden;border:1px solid {_MB_BORDER};">
          <tr>
            <td align="center" style="padding:22px 28px 10px;background:{_MB_BG};">
              <img src="{_LOGO_PLACEHOLDER}" alt="Makrobet" width="168" height="39" style="display:block;margin:0 auto;max-width:168px;width:168px;height:auto;border:0;outline:none;text-decoration:none;">
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
          {extra_html}
          <tr>
            <td align="center" style="padding:6px 28px 10px;">
              <a href="{cta_token}" style="display:inline-block;background:{_MB_GOLD};color:{_MB_BG};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;text-decoration:none;padding:14px 32px;border-radius:8px;">
                {cta_label}
              </a>
            </td>
          </tr>
          {secondary_block}
          {note_block}
          <tr>
            <td style="padding:16px 28px 22px;border-top:1px solid {_MB_BORDER};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:11px;line-height:1.55;color:{_MB_MUTED};text-align:center;">
              18+ · Sorumlu bahis · Şartlar ve çevrim koşulları geçerlidir.<br>
              Makrobet · <a href="{CTA_PROMO}" style="color:{_MB_GOLD};text-decoration:none;">Promosyonlar</a>
              · <a href="{CTA_VIP}" style="color:{_MB_GOLD};text-decoration:none;">VIP Destek</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


_SANS_EXTRA = f"""
          <tr>
            <td style="padding:0 24px 18px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_MB_BG};border-radius:10px;border:1px solid {_MB_BORDER};">
                <tr>
                  <td style="padding:14px 16px 6px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:{_MB_GOLD};">
                    Diğer aktif kampanyalar
                  </td>
                </tr>
                <tr>
                  <td style="padding:4px 12px 14px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" align="center">
                      <tr>
                        {_promo_chip("Prim Bonusu")}
                        {_promo_chip("Çevrim Bonusu")}
                        {_promo_chip("Görev Bonusu")}
                      </tr>
                      <tr>
                        {_promo_chip("Makro Kasa")}
                        {_promo_chip("Bilet Etkinliği")}
                        {_promo_chip("VIP Club")}
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
"""


HTML_TEMPLATES = [
    {
        "name": "HTML · Şans Bonusu Eklendi",
        "subject": "{{name}}, hesabına şans bonusu eklendi — hemen talep et",
        "html_body": _html_shell(
            "Şans Bonusu",
            "Hesap bildirimi",
            "Hesabına şans bonusu eklendi",
            f"""
            Merhaba <strong style="color:#fff;">{{{{name}}}}</strong>,<br><br>
            <strong style="color:{_MB_GOLD};font-size:17px;">Hesabına şans bonusu eklendi.</strong><br><br>
            Bonusunu almak için hemen
            <a href="{WHATSAPP_TOKEN}" style="color:{_MB_GOLD};font-weight:800;text-decoration:underline;">vipmakro.com</a>
            üzerinden WhatsApp destek hattımızdan talep et,
            ya da
            <a href="{AFF_TOKEN}" style="color:{_MB_GOLD};font-weight:800;text-decoration:underline;">makrovip.com/Vipmail</a>
            ile siteye bağlanıp talep oluştur.<br><br>
            Aynı dönemde prim bonusu, çevrim bonusu, görev bonusu, Makro Kasa ve bilet etkinlikleri de aktif olabilir —
            vurgu senin <strong style="color:{_MB_GOLD};">şans bonusunda</strong>.
            """,
            "WhatsApp’tan Talep Et",
            WHATSAPP_TOKEN,
            note="Talep sonrası bonus hesabına tanımlanır. Şartlar ve çevrim koşulları geçerlidir.",
            badge="Şans Bonusu",
            secondary_label="Siteye Bağlan · Talep Et",
            secondary_token=AFF_TOKEN,
            extra_html=_SANS_EXTRA,
        ),
        "text_body": f"""Merhaba {{{{name}}}},

Hesabına şans bonusu eklendi.

WhatsApp’tan talep et: {WHATSAPP_URL}
Siteye bağlan · talep et: {AFF_URL}

Ayrıca: Prim Bonusu · Çevrim Bonusu · Görev Bonusu · Makro Kasa · Bilet Etkinliği

18+ · Makrobet
""",
    },
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
            <strong style="color:#ffd400;">hoş geldin bonusları</strong> seni bekliyor.
            """,
            "Bonusları Gör",
            CTA_PROMO,
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
            <strong style="color:#ffd400;">ekstra bonus</strong> yakalayabilirsin.
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
            <strong style="color:#ffd400;">iade (cashback)</strong> kampanyaları aktif olabilir.
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
            Hesabına gir, <strong style="color:#ffd400;">aktif promosyonları</strong> yakala.
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
            Seni <strong style="color:#ffd400;">Makro VIP Club</strong> deneyimine davet ediyoruz:
            öncelikli destek, özel kampanyalar ve kişiselleştirilmiş fırsatlar.
            """,
            "VIP Destek",
            CTA_VIP,
            badge="VIP",
            secondary_label="Promosyonlar",
            secondary_token=CTA_PROMO,
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
            <strong style="color:#ffd400;">Canlı casino</strong>’ya bağlan.
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
            <strong style="color:#ffd400;">güncel bonusları</strong> inceleyebilirsin.
            """,
            "Tüm Promosyonlar",
            CTA_PROMO,
            badge="Promosyon",
            secondary_label="VIP Destek / WhatsApp",
            secondary_token=CTA_VIP,
        ),
        "text_body": "",
    },
]


TEXT_TEMPLATES = [
    {
        "name": "Yazı · Şans Bonusu Eklendi",
        "subject": "{{name}}, hesabına şans bonusu eklendi — hemen talep et",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Hesabına şans bonusu eklendi.

WhatsApp’tan talep et: {WHATSAPP_URL}
Siteye bağlan · talep et: {AFF_URL}

Ayrıca aktif olabilir: Prim Bonusu · Çevrim Bonusu · Görev Bonusu · Makro Kasa · Bilet Etkinliği

18+ · Makrobet
""",
    },
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

Canlı bahis ve spor yatırımlarına özel kampanyalar aktif olabilir:
{CTA_SPORT}

Makrobet
""",
    },
    {
        "name": "Yazı · Kayıp İadesi",
        "subject": "{{name}}, kayıp iadesi fırsatını kontrol et",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Casino veya spor tarafında dönemsel kayıp iadesi / cashback kampanyaları bulunabilir:
{CTA_PROMO}

Makrobet
""",
    },
    {
        "name": "Yazı · Freespin Hatırlatma",
        "subject": "{{name}}, freespin / freebet hatırlatması",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Hesabında bekleyen freespin veya freebet olabilir:
{CTA_PROMO}

Makrobet
""",
    },
    {
        "name": "Yazı · IVR Sonrası Takip",
        "subject": "{{name}}, aramamızın ardından — fırsatlar seni bekliyor",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Konuştuğumuz fırsatları ve güncel Makrobet kampanyalarını buradan inceleyebilirsin:
{CTA_TOKEN}

VIP / aff link: {AFF_URL}
Makrobet
""",
    },
    {
        "name": "Yazı · Yeniden Aktivasyon",
        "subject": "{{name}}, seni özledik — Makrobet'te yenilikler var",
        "html_body": "",
        "text_body": f"""Merhaba {{{{name}}}},

Bir süredir görüşemedik. Güncel fırsatlar için:
{CTA_TOKEN}

18+ · Sorumlu bahis
Makrobet
""",
    },
]


def seed_makrobet_mail_templates(conn, force_missing=False, overwrite=False):
    """Eksik şablonları ekler; overwrite=True ise seed HTML’lerini günceller.

    v4 flag yoksa ilk boot’ta HTML seed’leri otomatik yenilenir.
    """
    now = iso(utcnow())
    added = 0
    updated = 0
    _ = force_missing
    already = (get_mail_setting(conn, SEED_FLAG, "") or "").strip() == "1"
    if not already:
        overwrite = True
    for item in HTML_TEMPLATES + TEXT_TEMPLATES:
        name = item["name"]
        exists = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (name,))
        if exists:
            if overwrite and ((item.get("html_body") or "").strip() or (item.get("text_body") or "").strip()):
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
