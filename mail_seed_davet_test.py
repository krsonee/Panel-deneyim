"""Makrobet davet mail şablonu — deploy'da otomatik seed edilir.

Canlı site verisi (makrobet804.com/tr/pages/promotions — Playwright scrape):
  - Arka plan: #021532
  - Metin: #edf0ff
  - CTA buton: #ffd53e / metin #0f1328, radius 10px
  - Logo: https://makrobet804.com/cdn/makrobet/upload_files/logo.png
  - Promo görselleri: gateway.makroz.org/cdn/makrobet/...
"""

DAVET_TEST_NAME = "Davet test"

DAVET_TEST_SUBJECT = "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!"

LOGO_URL = "https://makrobet804.com/cdn/makrobet/upload_files/logo.png"
PROMO_LINK = "{{link:sc:https://makrobet804.com/tr/pages/promotions}}"

PROMOS = [
    {
        "title": "%100 KAYIP BONUSU",
        "desc": "Sıfır Riskle Yatırım Senden, Güvence Makrobet'ten!",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/100KaypWeb-b93d6f94-ba47-49d3-bfee-2f59a54f3402.png",
    },
    {
        "title": "ARKADAŞINI GETİR BONUSU!",
        "desc": "Arkadaşının aldığı yatırım bonusunu sana da ekleyelim!",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/ArkadasWeb-4419cecd-2bcc-4030-918e-07c39b2a6090.png",
    },
    {
        "title": "MAKRO GÖREV",
        "desc": "Makro Görev ile günlük görevlerini tamamla — Görev Kasa ödülünü kaçırma!",
        "img": "https://gateway.makroz.org/cdn/makrobet/promotion-posts/41/cover_mobile.png",
    },
    {
        "title": "YATIRIMA EK KASA HAPPY HOURS",
        "desc": "Makrobet'te Her Yatırıma Bir Sürpriz!",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/YatEkCase-7646aa0d-c9de-4e4f-a28b-27ae4ee8a2e4.png",
    },
    {
        "title": "MAKROBET 500.000₺ ÖDÜLLÜ AMUSNET YARIŞI",
        "desc": "Makrobet yarışında yerini al, dev kazanç sağla. Zirvedeki yerini ayırmak için hemen katıl!",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/Race-e1e97157-150a-4c10-84f9-b1feb9cd4824.png",
    },
    {
        "title": "KRİPTO YATIR, HAVALE ÇEK — ULTRA KASA",
        "desc": "Kripto yatırımlarına özel 10.000 ₺ değerinde Ultra Kasa kazan!",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/K&HWeb-970f7a17-d9d0-48f0-a61f-459610227bd3.png",
    },
]


def _promo_cards_html():
    cards = []
    for p in PROMOS:
        cards.append(
            f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:12px;background-color:#0a2244;border-radius:12px;overflow:hidden;border:1px solid rgba(255,213,62,0.18);">
  <tr><td style="padding:0;line-height:0;">
    <img src="{p['img']}" alt="{p['title']}" width="536" style="display:block;width:100%;max-width:100%;height:auto;border:0;">
  </td></tr>
  <tr><td style="padding:14px 16px 18px;">
    <div style="font-size:13px;font-weight:800;color:#ffd53e;text-transform:uppercase;letter-spacing:0.3px;line-height:1.35;">{p['title']}</div>
    <div style="font-size:13px;color:#edf0ff;margin-top:6px;line-height:1.55;">{p['desc']}</div>
  </td></tr>
</table>"""
        )
    return "\n".join(cards)


DAVET_TEST_TEXT = f"""Merhaba {{{{name}}}},

Makrobet ailesine özel davetlisin!

★ YENİ ÜYELERE ÖZEL: 3.000 TL DENEME KASASI ★
Kayıt ol, deneme kasanı al ve hemen oynamaya başla.

Güncel promosyonlar:
{chr(10).join('- ' + p['title'] + ' — ' + p['desc'] for p in PROMOS)}

Tüm promosyonları gör: {PROMO_LINK}

18 yaşından büyükler içindir. Sorumlu oyun.
"""

DAVET_TEST_HTML = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Makrobet Davet</title>
</head>
<body style="margin:0;padding:0;background-color:#021532;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#021532;">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;">
          <!-- Logo -->
          <tr>
            <td style="background-color:#021532;padding:28px 32px 20px;text-align:center;border-radius:16px 16px 0 0;border:1px solid rgba(255,213,62,0.2);border-bottom:none;">
              <img src="{LOGO_URL}" alt="Makrobet" width="220" style="display:inline-block;max-width:220px;width:100%;height:auto;border:0;">
            </td>
          </tr>
          <!-- Greeting -->
          <tr>
            <td style="background-color:#0a2244;border-left:1px solid rgba(255,213,62,0.15);border-right:1px solid rgba(255,213,62,0.15);padding:24px 32px 12px;">
              <p style="margin:0 0 8px;font-size:11px;color:#ffd53e;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;">Özel davet</p>
              <h1 style="margin:0 0 12px;font-size:23px;line-height:1.35;color:#edf0ff;font-weight:700;">Merhaba {{{{name}}}},<br>sana özel fırsatlar hazır!</h1>
              <p style="margin:0;font-size:14px;line-height:1.65;color:#b8c4e8;">Makrobet'te güncel promosyonlar, yüksek oranlar ve hızlı ödeme altyapısıyla kazanmaya bir adım uzaktasın.</p>
            </td>
          </tr>
          <!-- 3000 TL HERO -->
          <tr>
            <td style="background-color:#0a2244;border-left:1px solid rgba(255,213,62,0.15);border-right:1px solid rgba(255,213,62,0.15);padding:8px 32px 24px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:linear-gradient(145deg,#12305c 0%,#021532 100%);border-radius:14px;border:2px solid #ffd53e;box-shadow:0 0 36px rgba(255,213,62,0.22);">
                <tr>
                  <td style="padding:30px 22px;text-align:center;">
                    <div style="display:inline-block;background:rgba(255,213,62,0.14);border:1px solid rgba(255,213,62,0.4);border-radius:999px;padding:5px 14px;font-size:11px;font-weight:700;color:#ffd53e;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;">Yeni üyelere özel</div>
                    <div style="font-size:50px;font-weight:900;color:#ffd53e;line-height:1;">3.000 TL</div>
                    <div style="font-size:22px;font-weight:800;color:#edf0ff;margin-top:8px;letter-spacing:0.5px;">DENEME KASASI</div>
                    <p style="margin:16px 0 0;font-size:14px;line-height:1.55;color:#b8c4e8;">Hemen kayıt ol, deneme kasanı al ve risk almadan slot &amp; casino oyunlarını dene.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Site promosyonları -->
          <tr>
            <td style="background-color:#0a2244;border-left:1px solid rgba(255,213,62,0.15);border-right:1px solid rgba(255,213,62,0.15);padding:4px 32px 20px;">
              <p style="margin:0 0 14px;font-size:12px;font-weight:700;color:#ffd53e;text-transform:uppercase;letter-spacing:1px;">Güncel Promosyonlar</p>
              {_promo_cards_html()}
            </td>
          </tr>
          <!-- CTA -->
          <tr>
            <td style="background-color:#0a2244;border-left:1px solid rgba(255,213,62,0.15);border-right:1px solid rgba(255,213,62,0.15);padding:4px 32px 28px;text-align:center;">
              <a href="{PROMO_LINK}" style="display:inline-block;background-color:#ffd53e;color:#0f1328;font-size:15px;font-weight:700;text-decoration:none;padding:14px 36px;border-radius:10px;box-shadow:0 4px 18px rgba(255,213,62,0.35);">Detayları Gör</a>
              <p style="margin:14px 0 0;font-size:11px;color:#7d8cb0;">Tüm promosyonlar makrobet804.com/tr/pages/promotions adresinde.</p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color:#010d20;border-radius:0 0 16px 16px;border:1px solid rgba(255,213,62,0.12);border-top:none;padding:18px 32px;text-align:center;">
              <p style="margin:0 0 6px;font-size:11px;color:#7d8cb0;line-height:1.5;">Bu e-posta sana özel bir davet olarak gönderilmiştir.<br>makrobet804.com</p>
              <p style="margin:0;font-size:10px;color:#5c6a8a;">18 yaşından büyükler içindir. Kumar bağımlılık yapabilir — sorumlu oyun.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def ensure_davet_test_template(conn):
    from database import execute, fetchone, insert_returning_id, iso, utcnow

    now = iso(utcnow())
    existing = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (DAVET_TEST_NAME,))
    if existing:
        execute(
            conn,
            """
            UPDATE mail_templates
            SET subject = ?, html_body = ?, text_body = ?, updated_at = ?
            WHERE id = ?
            """,
            (DAVET_TEST_SUBJECT, DAVET_TEST_HTML, DAVET_TEST_TEXT, now, existing["id"]),
        )
        return existing["id"]
    return insert_returning_id(
        conn,
        """
        INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (DAVET_TEST_NAME, DAVET_TEST_SUBJECT, DAVET_TEST_HTML, DAVET_TEST_TEXT, now, now),
    )
