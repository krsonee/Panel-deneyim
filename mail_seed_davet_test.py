"""Makrobet davet mail şablonu — deploy'da otomatik seed edilir."""

DAVET_TEST_NAME = "Davet test"

DAVET_TEST_SUBJECT = "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!"

LOGO_URL = "https://makrobet804.com/cdn/makrobet/upload_files/logo-black.png"
PROMO_LINK = "{{link:sc:https://makrobet804.com/tr/pages/promotions}}"

C_BG = "#061c3d"
C_CARD = "#0b2347"
C_ROW = "#0f2d55"
C_TEXT = "#e8efff"
C_MUTED = "#8fa3cc"
C_GOLD = "#ffd53e"
C_DARK = "#10152b"

PROMOS = [
    {
        "title": "%100 Kayıp Bonusu",
        "desc": "Sıfır riskle yatırım senden, güvence Makrobet'ten.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/100KaypWeb-b93d6f94-ba47-49d3-bfee-2f59a54f3402.png",
    },
    {
        "title": "Arkadaşını Getir",
        "desc": "Arkadaşının bonusunu sana da ekleyelim.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/ArkadasWeb-4419cecd-2bcc-4030-918e-07c39b2a6090.png",
    },
    {
        "title": "Makro Görev",
        "desc": "Günlük görevleri tamamla, Görev Kasa ödülünü al.",
        "img": "https://gateway.makroz.org/cdn/makrobet/promotion-posts/41/cover_mobile.png",
    },
    {
        "title": "Happy Hours",
        "desc": "Her yatırıma ek sürpriz fırsatlar.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/YatEkCase-7646aa0d-c9de-4e4f-a28b-27ae4ee8a2e4.png",
    },
    {
        "title": "Amusnet Yarışı",
        "desc": "500.000₺ ödüllü yarışta yerini ayırt.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/Race-e1e97157-150a-4c10-84f9-b1feb9cd4824.png",
    },
    {
        "title": "Kripto Ultra Kasa",
        "desc": "Kripto yatır, havale çek — Ultra Kasa kazan.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/K&HWeb-970f7a17-d9d0-48f0-a61f-459610227bd3.png",
    },
]


def _promo_rows_html():
    rows = []
    for p in PROMOS:
        rows.append(
            f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:6px;background-color:{C_ROW};border-radius:8px;border:1px solid rgba(255,213,62,0.1);">
  <tr>
    <td width="100" style="padding:8px 10px;vertical-align:middle;">
      <img src="{p['img']}" alt="{p['title']}" width="88" height="36" style="display:block;width:88px;height:36px;border-radius:5px;border:0;">
    </td>
    <td style="padding:8px 12px 8px 0;vertical-align:middle;">
      <div style="font-size:11px;font-weight:700;color:{C_GOLD};line-height:1.25;">{p['title']}</div>
      <div style="font-size:10px;color:{C_MUTED};margin-top:2px;line-height:1.35;">{p['desc']}</div>
    </td>
  </tr>
</table>"""
        )
    return "\n".join(rows)


DAVET_TEST_TEXT = f"""Merhaba {{{{name}}}},

Makrobet ailesine özel davetlisin!

★ 3.000 TL DENEME KASASI ★
Kayıt ol, deneme kasanı al ve hemen oynamaya başla.

Güncel promosyonlar:
{chr(10).join('- ' + p['title'] + ' — ' + p['desc'] for p in PROMOS)}

Tüm promosyonlar: {PROMO_LINK}

18 yaşından büyükler içindir. Sorumlu oyun.
"""

DAVET_TEST_HTML = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Makrobet Davet</title>
</head>
<body style="margin:0;padding:0;background-color:{C_BG};font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:{C_BG};">
    <tr>
      <td align="center" style="padding:20px 10px;">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;width:100%;">
          <tr>
            <td style="background-color:{C_CARD};padding:16px 20px;text-align:center;border-radius:12px 12px 0 0;border:1px solid rgba(255,213,62,0.15);border-bottom:none;">
              <a href="{PROMO_LINK}" style="text-decoration:none;">
                <img src="{LOGO_URL}" alt="Makrobet" width="150" height="30" style="display:inline-block;width:150px;max-width:150px;height:30px;border:0;">
              </a>
            </td>
          </tr>
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:16px 22px 8px;">
              <p style="margin:0 0 4px;font-size:9px;color:{C_GOLD};font-weight:700;text-transform:uppercase;letter-spacing:1.2px;">Özel davet</p>
              <h1 style="margin:0;font-size:18px;line-height:1.35;color:{C_TEXT};font-weight:700;">Merhaba {{{{name}}}},</h1>
              <p style="margin:8px 0 0;font-size:12px;line-height:1.55;color:{C_MUTED};">Makrobet'te seni güncel promosyonlar ve hızlı ödeme altyapısı bekliyor.</p>
            </td>
          </tr>
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:8px 22px 14px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#102a52;border-radius:10px;border:2px solid {C_GOLD};">
                <tr>
                  <td style="padding:16px 14px;text-align:center;">
                    <p style="margin:0 0 6px;font-size:9px;font-weight:700;color:{C_GOLD};text-transform:uppercase;letter-spacing:0.8px;">Yeni üyelere özel</p>
                    <p style="margin:0;font-size:28px;font-weight:900;color:{C_GOLD};line-height:1;">3.000 TL</p>
                    <p style="margin:4px 0 0;font-size:13px;font-weight:700;color:{C_TEXT};letter-spacing:0.3px;">DENEME KASASI</p>
                    <p style="margin:10px 0 0;font-size:11px;line-height:1.45;color:{C_MUTED};">Kayıt ol, deneme kasanı al ve risk almadan oyunları dene.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:4px 22px 12px;">
              <p style="margin:0 0 6px;font-size:9px;font-weight:700;color:{C_GOLD};text-transform:uppercase;letter-spacing:0.8px;">Diğer promosyonlar</p>
              {_promo_rows_html()}
            </td>
          </tr>
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:4px 22px 18px;text-align:center;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center">
                <tr>
                  <td style="border-radius:9px;background-color:{C_GOLD};">
                    <a href="{PROMO_LINK}" style="display:inline-block;padding:11px 26px;font-size:13px;font-weight:700;color:{C_DARK};text-decoration:none;border-radius:9px;">Promosyonları Gör</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background-color:#071528;border-radius:0 0 12px 12px;border:1px solid rgba(255,213,62,0.08);border-top:none;padding:12px 22px;text-align:center;">
              <p style="margin:0;font-size:9px;color:#64748b;line-height:1.45;">18+ · Sorumlu oyun · makrobet804.com</p>
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
