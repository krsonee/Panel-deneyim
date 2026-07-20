"""Makrobet davet / deneme test şablonu — deploy'da otomatik seed edilir.

Logo: panel /static/mailing/makrobet-logo.png (__MAIL_LOGO__)
CTA: https://makrovip.com/Vipmail (aff)
Palet: site ile aynı — #061c3d · #ffd400 · #e6f0fe
"""

DAVET_TEST_NAME = "Davet test"

DAVET_TEST_SUBJECT = "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!"

AFF_URL = "https://makrovip.com/Vipmail"
AFF_TOKEN = "{{link:sc:https://makrovip.com/Vipmail}}"

C_BG = "#061c3d"
C_CARD = "#0a2448"
C_ROW = "#0f2d55"
C_TEXT = "#e6f0fe"
C_MUTED = "#9db3d4"
C_GOLD = "#ffd400"
C_DARK = "#061c3d"
C_BORDER = "#2a4a7a"

_LOGO = "__MAIL_LOGO__"

PROMOS = [
    {"title": "%100 Kayıp Bonusu", "desc": "Sıfır riskle yatırım senden, güvence Makrobet'ten."},
    {"title": "Arkadaşını Getir", "desc": "Arkadaşının aldığı yatırım bonusunu sana da ekleyelim."},
    {"title": "Makro Görev", "desc": "Günlük görevleri tamamla, Görev Kasa ödülünü kaçırma."},
    {"title": "Happy Hours", "desc": "Her yatırıma ek sürpriz — Mutlu Saatler."},
    {"title": "Amusnet Yarışı", "desc": "500.000₺ ödüllü yarışta zirve için yerini ayırt."},
    {"title": "Kripto Ultra Kasa", "desc": "Kripto yatır, havale çek — Ultra Kasa fırsatı."},
]


def _spam_tip():
    return f"""
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;">
    <tr>
      <td align="center" style="padding:11px 18px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:12px;line-height:1.45;color:#ffffff;">
        <span style="color:{C_GOLD};font-size:13px;vertical-align:middle;">⚠</span>
        &nbsp;Butonların tıklanabilir olması için
        <strong style="color:{C_GOLD};">Spam olmadığını bildir</strong>
        seçeneğine tıklayın.
      </td>
    </tr>
  </table>"""


def _logo_html():
    return (
        f'<img src="{_LOGO}" alt="Makrobet" width="168" height="39" '
        f'style="display:block;margin:0 auto;max-width:168px;width:168px;height:auto;'
        f'border:0;outline:none;text-decoration:none;">'
    )


def _promo_rows_html():
    rows = []
    for i, p in enumerate(PROMOS, 1):
        rows.append(
            f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:7px;">
  <tr>
    <td style="background-color:{C_ROW};border-radius:8px;border:1px solid {C_BORDER};border-left:3px solid {C_GOLD};">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr>
          <td width="34" style="padding:11px 0 11px 12px;vertical-align:top;">
            <div style="width:22px;height:22px;border-radius:50%;background:rgba(255,212,0,0.14);border:1px solid rgba(255,212,0,0.4);text-align:center;line-height:22px;font-size:10px;font-weight:800;color:{C_GOLD};">{i}</div>
          </td>
          <td style="padding:10px 14px 10px 4px;vertical-align:top;">
            <div style="font-size:12px;font-weight:700;color:{C_GOLD};line-height:1.3;">{p['title']}</div>
            <div style="font-size:11px;color:{C_MUTED};margin-top:3px;line-height:1.45;">{p['desc']}</div>
          </td>
        </tr>
      </table>
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
{chr(10).join(str(i + 1) + '. ' + p['title'] + ' — ' + p['desc'] for i, p in enumerate(PROMOS))}

Hemen katıl: {AFF_URL}

18 yaşından büyükler içindir. Sorumlu oyun.
"""

DAVET_TEST_HTML = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Makrobet Deneme Bonusu</title>
</head>
<body style="margin:0;padding:0;background-color:{C_BG};font-family:Urbanist,Arial,Helvetica,sans-serif;">
  {_spam_tip()}
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:{C_BG};">
    <tr>
      <td align="center" style="padding:20px 12px 28px;">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;width:100%;background:{C_CARD};border-radius:12px;overflow:hidden;border:1px solid {C_BORDER};">
          <tr>
            <td style="background-color:{C_BG};padding:22px 22px 12px;text-align:center;">
              <a href="{AFF_TOKEN}" style="text-decoration:none;">{_logo_html()}</a>
            </td>
          </tr>
          <tr>
            <td style="padding:6px 24px 0;font-family:Urbanist,Arial,Helvetica,sans-serif;">
              <span style="display:inline-block;background:{C_GOLD};color:{C_DARK};font-size:11px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;padding:5px 12px;border-radius:999px;">Deneme Bonusu</span>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 24px 8px;">
              <p style="margin:0 0 5px;font-size:11px;color:{C_GOLD};font-weight:700;text-transform:uppercase;letter-spacing:1.2px;">Özel davet</p>
              <h1 style="margin:0;font-size:22px;line-height:1.3;color:#ffffff;font-weight:800;">Merhaba {{{{name}}}},</h1>
              <p style="margin:8px 0 0;font-size:14px;line-height:1.6;color:{C_TEXT};">Makrobet'te güncel promosyonlar, yüksek oranlar ve hızlı ödeme seni bekliyor.</p>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 24px 16px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:{C_BG};border-radius:11px;border:2px solid {C_GOLD};">
                <tr>
                  <td style="padding:20px 16px;text-align:center;">
                    <p style="margin:0 0 8px;font-size:10px;font-weight:800;color:{C_GOLD};text-transform:uppercase;letter-spacing:1px;">★ Yeni üyelere özel ★</p>
                    <p style="margin:0;font-size:34px;font-weight:900;color:{C_GOLD};line-height:1;">3.000 TL</p>
                    <p style="margin:6px 0 0;font-size:15px;font-weight:800;color:#ffffff;letter-spacing:0.5px;">DENEME KASASI</p>
                    <p style="margin:12px 0 0;font-size:12px;line-height:1.55;color:{C_MUTED};max-width:380px;display:inline-block;">Kayıt ol, deneme kasanı al ve risk almadan slot &amp; casino deneyimini yaşa.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:2px 24px 14px;">
              <p style="margin:0 0 8px;font-size:10px;font-weight:800;color:{C_GOLD};text-transform:uppercase;letter-spacing:1px;">Diğer promosyonlar</p>
              {_promo_rows_html()}
            </td>
          </tr>
          <tr>
            <td style="padding:6px 24px 10px;text-align:center;">
              <a href="{AFF_TOKEN}" style="display:inline-block;background:{C_GOLD};color:{C_DARK};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;text-decoration:none;padding:14px 32px;border-radius:8px;">Deneme Bonusu Al</a>
            </td>
          </tr>
          <tr>
            <td style="padding:0 24px 20px;text-align:center;">
              <a href="{AFF_TOKEN}" style="display:inline-block;background:transparent;color:{C_GOLD};font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-decoration:none;padding:11px 22px;border-radius:8px;border:1px solid {C_GOLD};">Siteye Bağlan · makrovip.com/Vipmail</a>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 24px 22px;border-top:1px solid {C_BORDER};text-align:center;">
              <p style="margin:0;font-size:11px;color:{C_MUTED};line-height:1.55;">18+ · Sorumlu bahis · Şartlar ve çevrim koşulları geçerlidir.<br>
              Makrobet · <a href="{AFF_TOKEN}" style="color:{C_GOLD};text-decoration:none;">makrovip.com/Vipmail</a></p>
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
