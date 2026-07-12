"""Makrobet davet mail şablonu — deploy'da otomatik seed edilir."""

DAVET_TEST_NAME = "Davet test"

DAVET_TEST_SUBJECT = "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!"

DAVET_TEST_TEXT = """Merhaba {{name}},

Makrobet ailesine özel davetlisin!

YENİ ÜYELERE ÖZEL: 3.000 TL DENEME KASASI
Kayıt ol, deneme kasanı al ve kazanmaya hemen başla.

Neden Makrobet?
- Yüksek oranlı spor bahisleri & canlı bahis
- Binlerce slot ve canlı casino masaları
- Hızlı yatırım ve çekim
- 7/24 canlı destek
- Sürekli güncellenen promosyonlar

Hemen üye ol: {{link:sc:https://makrobet804.com}}

18 yaşından büyükler içindir. Sorumlu oyun.
"""

DAVET_TEST_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Makrobet Davet</title>
</head>
<body style="margin:0;padding:0;background-color:#070b12;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#070b12;">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;">
          <tr>
            <td style="background:linear-gradient(135deg,#0f1724 0%,#1a2332 100%);border-radius:16px 16px 0 0;border:1px solid #2a3548;border-bottom:none;padding:28px 32px;text-align:center;">
              <div style="font-size:32px;font-weight:800;letter-spacing:2px;color:#fbbf24;text-shadow:0 2px 12px rgba(251,191,36,0.35);">MAKROBET</div>
              <div style="font-size:13px;color:#94a3b8;margin-top:6px;letter-spacing:1px;text-transform:uppercase;">Güvenilir Bahis &amp; Casino</div>
            </td>
          </tr>
          <tr>
            <td style="background-color:#0f1724;border-left:1px solid #2a3548;border-right:1px solid #2a3548;padding:32px 32px 24px;">
              <p style="margin:0 0 8px;font-size:14px;color:#fbbf24;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Özel davet</p>
              <h1 style="margin:0 0 16px;font-size:26px;line-height:1.3;color:#f8fafc;font-weight:800;">Merhaba {{name}},<br>sana özel fırsat hazır!</h1>
              <p style="margin:0;font-size:15px;line-height:1.6;color:#cbd5e1;">Makrobet'in yüksek oranları, geniş oyun seçenekleri ve hızlı ödeme altyapısıyla kazanmaya bir adım uzaktasın.</p>
            </td>
          </tr>
          <tr>
            <td style="background-color:#0f1724;border-left:1px solid #2a3548;border-right:1px solid #2a3548;padding:0 32px 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:linear-gradient(135deg,#1e3a1e 0%,#14532d 50%,#166534 100%);border-radius:14px;border:2px solid #22c55e;">
                <tr>
                  <td style="padding:24px 28px;text-align:center;">
                    <div style="font-size:12px;font-weight:700;color:#86efac;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Yeni üyelere özel</div>
                    <div style="font-size:36px;font-weight:900;color:#ffffff;line-height:1.1;">3.000 TL</div>
                    <div style="font-size:18px;font-weight:700;color:#bbf7d0;margin-top:4px;">DENEME KASASI</div>
                    <p style="margin:14px 0 0;font-size:13px;line-height:1.5;color:#d1fae5;">Hemen kayıt ol, deneme kasanı al ve risk almadan oynamaya başla.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background-color:#0f1724;border-left:1px solid #2a3548;border-right:1px solid #2a3548;padding:8px 32px 28px;">
              <p style="margin:0 0 16px;font-size:13px;font-weight:700;color:#fbbf24;text-transform:uppercase;letter-spacing:0.5px;">Neden Makrobet?</p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td width="50%" valign="top" style="padding:0 8px 12px 0;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#151e2e;border-radius:10px;border:1px solid #2a3548;">
                      <tr><td style="padding:14px 16px;">
                        <div style="font-size:20px;margin-bottom:6px;">⚽</div>
                        <div style="font-size:14px;font-weight:700;color:#f8fafc;">Spor Bahisleri</div>
                        <div style="font-size:12px;color:#94a3b8;margin-top:4px;line-height:1.4;">Yüksek oranlar, canlı bahis ve geniş market seçenekleri</div>
                      </td></tr>
                    </table>
                  </td>
                  <td width="50%" valign="top" style="padding:0 0 12px 8px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#151e2e;border-radius:10px;border:1px solid #2a3548;">
                      <tr><td style="padding:14px 16px;">
                        <div style="font-size:20px;margin-bottom:6px;">🎰</div>
                        <div style="font-size:14px;font-weight:700;color:#f8fafc;">Casino &amp; Slot</div>
                        <div style="font-size:12px;color:#94a3b8;margin-top:4px;line-height:1.4;">Binlerce slot, canlı casino ve popüler sağlayıcılar</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td width="50%" valign="top" style="padding:0 8px 12px 0;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#151e2e;border-radius:10px;border:1px solid #2a3548;">
                      <tr><td style="padding:14px 16px;">
                        <div style="font-size:20px;margin-bottom:6px;">💳</div>
                        <div style="font-size:14px;font-weight:700;color:#f8fafc;">Hızlı İşlem</div>
                        <div style="font-size:12px;color:#94a3b8;margin-top:4px;line-height:1.4;">Anında yatırım, hızlı çekim ve güvenli ödeme yöntemleri</div>
                      </td></tr>
                    </table>
                  </td>
                  <td width="50%" valign="top" style="padding:0 0 12px 8px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#151e2e;border-radius:10px;border:1px solid #2a3548;">
                      <tr><td style="padding:14px 16px;">
                        <div style="font-size:20px;margin-bottom:6px;">🎁</div>
                        <div style="font-size:14px;font-weight:700;color:#f8fafc;">Promosyonlar</div>
                        <div style="font-size:12px;color:#94a3b8;margin-top:4px;line-height:1.4;">Hoş geldin bonusu, kayıp iadesi ve özel kampanyalar</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td colspan="2" valign="top">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#151e2e;border-radius:10px;border:1px solid #2a3548;">
                      <tr><td style="padding:14px 16px;">
                        <div style="font-size:20px;margin-bottom:6px;">💬</div>
                        <div style="font-size:14px;font-weight:700;color:#f8fafc;">7/24 Canlı Destek</div>
                        <div style="font-size:12px;color:#94a3b8;margin-top:4px;line-height:1.4;">Her an yanındayız — soruların için profesyonel destek ekibi</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background-color:#0f1724;border-left:1px solid #2a3548;border-right:1px solid #2a3548;padding:8px 32px 36px;text-align:center;">
              <a href="{{link:sc:https://makrobet804.com}}" style="display:inline-block;background:linear-gradient(180deg,#fbbf24 0%,#f59e0b 100%);color:#0f1724;font-size:17px;font-weight:800;text-decoration:none;padding:16px 40px;border-radius:999px;box-shadow:0 8px 24px rgba(251,191,36,0.35);letter-spacing:0.3px;">HEMEN ÜYE OL</a>
              <p style="margin:16px 0 0;font-size:12px;color:#64748b;">Promosyonlar ve bonus detayları için siteye giriş yapabilirsin.</p>
            </td>
          </tr>
          <tr>
            <td style="background-color:#0a0f18;border-radius:0 0 16px 16px;border:1px solid #2a3548;border-top:none;padding:20px 32px;text-align:center;">
              <p style="margin:0 0 8px;font-size:11px;color:#64748b;line-height:1.5;">Bu e-posta sana özel bir davet olarak gönderilmiştir.<br>makrobet804.com</p>
              <p style="margin:0;font-size:10px;color:#475569;">18 yaşından büyükler içindir. Kumar bağımlılık yapabilir — sorumlu oyun.</p>
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
