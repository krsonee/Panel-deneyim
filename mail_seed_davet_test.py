"""Makrobet davet mail şablonu — deploy'da otomatik seed edilir.

Marka renkleri (makrobet804.com yükleme ekranından):
  - Arka plan: #1c1f33 (koyu lacivert)
  - Altın vurgu: #fcc64d
  - Beyaz: #ffffff
  - Logo: beyaz italik "Makro" + altın kalın "bet"
"""

DAVET_TEST_NAME = "Davet test"

DAVET_TEST_SUBJECT = "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!"

DAVET_TEST_TEXT = """Merhaba {{name}},

Makrobet ailesine özel davetlisin!

★ YENİ ÜYELERE ÖZEL: 3.000 TL DENEME KASASI ★
Kayıt ol, deneme kasanı al ve hemen oynamaya başla.

Makrobet'te seni neler bekliyor?
- 3.000 TL deneme kasası (yeni üyeler)
- Hoş geldin & yatırım bonusları
- Yüksek oranlı spor & canlı bahis
- Binlerce slot ve canlı casino
- Kayıp iadesi promosyonları
- Free spin fırsatları
- Hızlı yatırım ve çekim
- 7/24 canlı destek

Hemen üye ol: {{link:sc:https://makrobet804.com/tr/promo}}

18 yaşından büyükler içindir. Sorumlu oyun.
"""

DAVET_TEST_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Makrobet Davet</title>
</head>
<body style="margin:0;padding:0;background-color:#1c1f33;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#1c1f33;">
    <tr>
      <td align="center" style="padding:32px 12px;">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;">
          <!-- Logo header -->
          <tr>
            <td style="background-color:#1c1f33;border-radius:18px 18px 0 0;border:1px solid rgba(252,198,77,0.22);border-bottom:none;padding:36px 32px 28px;text-align:center;">
              <div style="line-height:1.1;margin-bottom:10px;">
                <span style="font-family:Georgia,'Times New Roman',serif;font-style:italic;font-size:42px;color:#ffffff;letter-spacing:-1px;">Makro</span><span style="font-family:Arial Black,Arial,sans-serif;font-size:42px;font-weight:900;color:#fcc64d;font-style:italic;letter-spacing:-1px;">bet</span>
              </div>
              <div style="font-size:12px;color:#9ca3c7;letter-spacing:2px;text-transform:uppercase;">Spor Bahisleri &amp; Casino</div>
            </td>
          </tr>
          <!-- Hero -->
          <tr>
            <td style="background-color:#252947;border-left:1px solid rgba(252,198,77,0.15);border-right:1px solid rgba(252,198,77,0.15);padding:28px 32px 20px;">
              <p style="margin:0 0 10px;font-size:12px;color:#fcc64d;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;">Özel davet</p>
              <h1 style="margin:0 0 14px;font-size:24px;line-height:1.35;color:#ffffff;font-weight:700;">Merhaba {{name}},<br>sana özel fırsatlar hazır!</h1>
              <p style="margin:0;font-size:14px;line-height:1.65;color:#c5c9dc;">Makrobet'te yüksek oranlar, binlerce oyun ve hızlı ödeme altyapısıyla kazanmaya bir adım uzaktasın.</p>
            </td>
          </tr>
          <!-- 3000 TL deneme kasası -->
          <tr>
            <td style="background-color:#252947;border-left:1px solid rgba(252,198,77,0.15);border-right:1px solid rgba(252,198,77,0.15);padding:4px 32px 24px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:linear-gradient(145deg,#2d3255 0%,#1c1f33 100%);border-radius:16px;border:2px solid #fcc64d;box-shadow:0 0 32px rgba(252,198,77,0.18);">
                <tr>
                  <td style="padding:26px 24px;text-align:center;">
                    <div style="display:inline-block;background:rgba(252,198,77,0.15);border:1px solid rgba(252,198,77,0.35);border-radius:999px;padding:5px 14px;font-size:11px;font-weight:700;color:#fcc64d;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;">Yeni üyelere özel</div>
                    <div style="font-size:44px;font-weight:900;color:#fcc64d;line-height:1;">3.000 TL</div>
                    <div style="font-size:20px;font-weight:800;color:#ffffff;margin-top:6px;letter-spacing:0.5px;">DENEME KASASI</div>
                    <p style="margin:14px 0 0;font-size:13px;line-height:1.55;color:#c5c9dc;">Hemen kayıt ol, deneme kasanı al ve risk almadan slot &amp; casino oyunlarını dene.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Promo özellikleri -->
          <tr>
            <td style="background-color:#252947;border-left:1px solid rgba(252,198,77,0.15);border-right:1px solid rgba(252,198,77,0.15);padding:4px 32px 24px;">
              <p style="margin:0 0 14px;font-size:12px;font-weight:700;color:#fcc64d;text-transform:uppercase;letter-spacing:1px;">Promosyonlar &amp; Avantajlar</p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td width="50%" valign="top" style="padding:0 6px 10px 0;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#1c1f33;border-radius:12px;border:1px solid rgba(252,198,77,0.12);">
                      <tr><td style="padding:14px 14px;">
                        <div style="font-size:18px;margin-bottom:5px;">🎁</div>
                        <div style="font-size:13px;font-weight:700;color:#ffffff;">Hoş Geldin Bonusu</div>
                        <div style="font-size:11px;color:#9ca3c7;margin-top:4px;line-height:1.45;">İlk yatırımına özel cazip hoş geldin fırsatları</div>
                      </td></tr>
                    </table>
                  </td>
                  <td width="50%" valign="top" style="padding:0 0 10px 6px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#1c1f33;border-radius:12px;border:1px solid rgba(252,198,77,0.12);">
                      <tr><td style="padding:14px 14px;">
                        <div style="font-size:18px;margin-bottom:5px;">⚽</div>
                        <div style="font-size:13px;font-weight:700;color:#ffffff;">Spor &amp; Canlı Bahis</div>
                        <div style="font-size:11px;color:#9ca3c7;margin-top:4px;line-height:1.45;">Yüksek oranlar ve geniş bahis marketleri</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td width="50%" valign="top" style="padding:0 6px 10px 0;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#1c1f33;border-radius:12px;border:1px solid rgba(252,198,77,0.12);">
                      <tr><td style="padding:14px 14px;">
                        <div style="font-size:18px;margin-bottom:5px;">🎰</div>
                        <div style="font-size:13px;font-weight:700;color:#ffffff;">Casino &amp; Slot</div>
                        <div style="font-size:11px;color:#9ca3c7;margin-top:4px;line-height:1.45;">Canlı casino masaları ve binlerce slot oyunu</div>
                      </td></tr>
                    </table>
                  </td>
                  <td width="50%" valign="top" style="padding:0 0 10px 6px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#1c1f33;border-radius:12px;border:1px solid rgba(252,198,77,0.12);">
                      <tr><td style="padding:14px 14px;">
                        <div style="font-size:18px;margin-bottom:5px;">🔄</div>
                        <div style="font-size:13px;font-weight:700;color:#ffffff;">Kayıp İadesi</div>
                        <div style="font-size:11px;color:#9ca3c7;margin-top:4px;line-height:1.45;">Spor ve casino kayıplarında iade promosyonları</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td width="50%" valign="top" style="padding:0 6px 10px 0;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#1c1f33;border-radius:12px;border:1px solid rgba(252,198,77,0.12);">
                      <tr><td style="padding:14px 14px;">
                        <div style="font-size:18px;margin-bottom:5px;">🎡</div>
                        <div style="font-size:13px;font-weight:700;color:#ffffff;">Free Spin</div>
                        <div style="font-size:11px;color:#9ca3c7;margin-top:4px;line-height:1.45;">Slot oyunlarında ücretsiz dönüş fırsatları</div>
                      </td></tr>
                    </table>
                  </td>
                  <td width="50%" valign="top" style="padding:0 0 10px 6px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#1c1f33;border-radius:12px;border:1px solid rgba(252,198,77,0.12);">
                      <tr><td style="padding:14px 14px;">
                        <div style="font-size:18px;margin-bottom:5px;">💳</div>
                        <div style="font-size:13px;font-weight:700;color:#ffffff;">Hızlı Ödeme</div>
                        <div style="font-size:11px;color:#9ca3c7;margin-top:4px;line-height:1.45;">Anında yatırım, hızlı çekim ve güvenli işlem</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td colspan="2" valign="top">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#1c1f33;border-radius:12px;border:1px solid rgba(252,198,77,0.12);">
                      <tr><td style="padding:14px 14px;">
                        <div style="font-size:18px;margin-bottom:5px;">💬</div>
                        <div style="font-size:13px;font-weight:700;color:#ffffff;">7/24 Canlı Destek</div>
                        <div style="font-size:11px;color:#9ca3c7;margin-top:4px;line-height:1.45;">Her an yanındayız — bonus ve işlemler için profesyonel destek</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- CTA -->
          <tr>
            <td style="background-color:#252947;border-left:1px solid rgba(252,198,77,0.15);border-right:1px solid rgba(252,198,77,0.15);padding:8px 32px 32px;text-align:center;">
              <a href="{{link:sc:https://makrobet804.com/tr/promo}}" style="display:inline-block;background:linear-gradient(180deg,#fcc64d 0%,#e5a830 100%);color:#1c1f33;font-size:16px;font-weight:900;text-decoration:none;padding:16px 44px;border-radius:999px;box-shadow:0 6px 28px rgba(252,198,77,0.4);letter-spacing:0.5px;text-transform:uppercase;">Hemen Üye Ol</a>
              <p style="margin:14px 0 0;font-size:11px;color:#7d84a0;">Tüm promosyonları görmek için promo sayfasını ziyaret et.</p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color:#161828;border-radius:0 0 18px 18px;border:1px solid rgba(252,198,77,0.12);border-top:none;padding:18px 32px;text-align:center;">
              <p style="margin:0 0 6px;font-size:11px;color:#7d84a0;line-height:1.5;">Bu e-posta sana özel bir davet olarak gönderilmiştir.<br>makrobet804.com</p>
              <p style="margin:0;font-size:10px;color:#5c6380;">18 yaşından büyükler içindir. Kumar bağımlılık yapabilir — sorumlu oyun.</p>
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
