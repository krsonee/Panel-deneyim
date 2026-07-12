"""Makrobet davet mail şablonu — deploy'da otomatik seed edilir.

Logo: harici CDN hotlink engelliyor → HTML wordmark (MAKRO + BET) kullanılıyor.
Promolar: küçük banner kırpımları yerine tipografi kartları.
"""

DAVET_TEST_NAME = "Davet test"

DAVET_TEST_SUBJECT = "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!"

PROMO_LINK = "{{link:sc:https://makrobet804.com/tr/pages/promotions}}"

C_BG = "#061c3d"
C_CARD = "#0b2347"
C_ROW = "#0f2d55"
C_TEXT = "#e8efff"
C_MUTED = "#8fa3cc"
C_GOLD = "#ffd53e"
C_DARK = "#10152b"
C_ACCENT = "#4a8fe7"

PROMOS = [
    {"title": "%100 Kayıp Bonusu", "desc": "Sıfır riskle yatırım senden, güvence Makrobet'ten."},
    {"title": "Arkadaşını Getir", "desc": "Arkadaşının aldığı yatırım bonusunu sana da ekleyelim."},
    {"title": "Makro Görev", "desc": "Günlük görevleri tamamla, Görev Kasa ödülünü kaçırma."},
    {"title": "Happy Hours", "desc": "Her yatırıma ek sürpriz — Mutlu Saatler."},
    {"title": "Amusnet Yarışı", "desc": "500.000₺ ödüllü yarışta zirve için yerini ayırt."},
    {"title": "Kripto Ultra Kasa", "desc": "Kripto yatır, havale çek — Ultra Kasa fırsatı."},
]


def _logo_html():
    """Site logosu — CDN 403 verdiği için e-postada güvenilir HTML wordmark."""
    return f"""<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center">
  <tr>
    <td style="font-family:Arial,Helvetica,sans-serif;font-size:26px;font-weight:900;color:{C_TEXT};letter-spacing:3px;line-height:1;padding-right:8px;">MAKRO</td>
    <td style="background-color:{C_GOLD};border-radius:7px;padding:6px 12px;">
      <span style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:{C_DARK};letter-spacing:1px;">BET</span>
    </td>
  </tr>
</table>"""


def _promo_rows_html():
    rows = []
    for i, p in enumerate(PROMOS, 1):
        rows.append(
            f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:7px;">
  <tr>
    <td style="background-color:{C_ROW};border-radius:8px;border:1px solid rgba(255,213,62,0.12);border-left:3px solid {C_GOLD};">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr>
          <td width="34" style="padding:11px 0 11px 12px;vertical-align:top;">
            <div style="width:22px;height:22px;border-radius:50%;background:rgba(255,213,62,0.14);border:1px solid rgba(255,213,62,0.35);text-align:center;line-height:22px;font-size:10px;font-weight:800;color:{C_GOLD};">{i}</div>
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
      <td align="center" style="padding:22px 12px;">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;width:100%;">
          <!-- Logo -->
          <tr>
            <td style="background-color:{C_CARD};padding:20px 22px 16px;text-align:center;border-radius:12px 12px 0 0;border:1px solid rgba(255,213,62,0.14);border-bottom:1px solid rgba(255,213,62,0.08);">
              <a href="{PROMO_LINK}" style="text-decoration:none;">{_logo_html()}</a>
            </td>
          </tr>
          <!-- Karşılama -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:18px 24px 10px;">
              <p style="margin:0 0 5px;font-size:9px;color:{C_GOLD};font-weight:700;text-transform:uppercase;letter-spacing:1.4px;">Özel davet</p>
              <h1 style="margin:0;font-size:19px;line-height:1.35;color:{C_TEXT};font-weight:700;">Merhaba {{{{name}}}},</h1>
              <p style="margin:8px 0 0;font-size:12px;line-height:1.55;color:{C_MUTED};">Makrobet'te güncel promosyonlar, yüksek oranlar ve hızlı ödeme seni bekliyor.</p>
            </td>
          </tr>
          <!-- 3.000 TL hero -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:8px 24px 16px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:linear-gradient(160deg,#12325e 0%,{C_BG} 100%);border-radius:11px;border:2px solid {C_GOLD};">
                <tr>
                  <td style="padding:18px 16px;text-align:center;">
                    <p style="margin:0 0 8px;font-size:9px;font-weight:700;color:{C_GOLD};text-transform:uppercase;letter-spacing:1px;">★ Yeni üyelere özel ★</p>
                    <p style="margin:0;font-size:32px;font-weight:900;color:{C_GOLD};line-height:1;">3.000 TL</p>
                    <p style="margin:5px 0 0;font-size:14px;font-weight:800;color:{C_TEXT};letter-spacing:0.5px;">DENEME KASASI</p>
                    <p style="margin:12px 0 0;font-size:11px;line-height:1.5;color:{C_MUTED};max-width:380px;display:inline-block;">Kayıt ol, deneme kasanı al ve risk almadan slot &amp; casino deneyimini yaşa.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Promolar -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:2px 24px 14px;">
              <p style="margin:0 0 8px;font-size:9px;font-weight:700;color:{C_GOLD};text-transform:uppercase;letter-spacing:1px;">Diğer promosyonlar</p>
              {_promo_rows_html()}
            </td>
          </tr>
          <!-- CTA -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.1);border-right:1px solid rgba(255,213,62,0.1);padding:6px 24px 20px;text-align:center;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center">
                <tr>
                  <td style="border-radius:9px;background-color:{C_GOLD};">
                    <a href="{PROMO_LINK}" style="display:inline-block;padding:12px 30px;font-size:13px;font-weight:700;color:{C_DARK};text-decoration:none;border-radius:9px;">Promosyonları İncele</a>
                  </td>
                </tr>
              </table>
              <p style="margin:10px 0 0;font-size:10px;color:#5d6f94;">makrobet804.com/tr/pages/promotions</p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color:#071528;border-radius:0 0 12px 12px;border:1px solid rgba(255,213,62,0.08);border-top:none;padding:13px 24px;text-align:center;">
              <p style="margin:0;font-size:9px;color:#5d6f94;line-height:1.5;">18+ · Kumar bağımlılık yapabilir — sorumlu oyun.</p>
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
