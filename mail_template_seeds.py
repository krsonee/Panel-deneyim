"""MakroBet markasına uygun hazır mailing şablonları (tek seferlik seed)."""

from __future__ import annotations

from database import (
    fetchone,
    get_mail_setting,
    insert_returning_id,
    iso,
    upsert_mail_setting,
    utcnow,
)

SEED_FLAG = "seeded_makrobet_templates_v2"
CTA = "https://makrobet805.com/tr/"
CTA_TOKEN = "{{link:sc:https://makrobet805.com/tr/}}"
CTA_CASINO = "{{link:sc:https://makrobet805.com/tr/game/casino}}"
CTA_SPORT = "{{link:sc:https://makrobet805.com/tr/sport/live}}"
CTA_PROMO = "{{link:sc:https://makrobet805.com/tr/contents/promotions}}"


def _html_shell(title, eyebrow, headline, body_html, cta_label, cta_token, note=""):
    note_block = ""
    if note:
        note_block = f"""
          <tr>
            <td style="padding:0 28px 8px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;color:#9aa3b5;">
              {note}
            </td>
          </tr>"""
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#070d1a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#070d1a;">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#0d142b;border-radius:16px;overflow:hidden;border:1px solid #1c2744;">
          <tr>
            <td style="padding:22px 28px 10px;text-align:center;">
              <div style="font-family:Georgia,'Times New Roman',serif;font-size:34px;font-weight:700;letter-spacing:0.5px;">
                <span style="color:#ffffff;">Makro</span><span style="color:#ffd400;">bet</span>
              </div>
              <div style="width:8px;height:8px;background:#e11d2e;transform:rotate(45deg);margin:10px auto 0;"></div>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 28px 0;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#ffd400;">
              {eyebrow}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 28px 12px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:28px;line-height:1.25;font-weight:700;color:#ffffff;">
              {headline}
            </td>
          </tr>
          <tr>
            <td style="padding:0 28px 18px;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:15px;line-height:1.65;color:#d5dbe8;">
              {body_html}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:4px 28px 22px;">
              <a href="{cta_token}" style="display:inline-block;background:#ffd400;color:#0d142b;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:15px;font-weight:700;text-decoration:none;padding:14px 28px;border-radius:999px;">
                {cta_label}
              </a>
            </td>
          </tr>
          {note_block}
          <tr>
            <td style="padding:18px 28px 24px;border-top:1px solid #1c2744;font-family:Urbanist,Arial,Helvetica,sans-serif;font-size:11px;line-height:1.55;color:#7b8499;text-align:center;">
              18+ · Sorumlu bahis · Şartlar ve çevrim koşulları geçerlidir.<br>
              Makrobet · {CTA.replace('https://','')}
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
        "subject": "{{name}}, Makrobet'e hoş geldin — casino başlangıç fırsatı seni bekliyor",
        "html_body": _html_shell(
            "Hoş Geldin",
            "Yeni üye",
            "Casino tarafında güçlü bir başlangıç yap",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Makrobet ailesine hoş geldin. Slot ve canlı casino’da ilk yatırımlarına özel
            <strong style="color:#ffd400;">hoş geldin avantajları</strong> seni bekliyor.
            Hesabına gir, kampanyayı seç ve oynamaya başla.
            """,
            "Kampanyayı İncele",
            CTA_CASINO,
            "Güncel oran ve şartlar için site üzerindeki Promosyonlar / Bonuslar bölümünü kontrol et.",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Spor Yatırım Bonusu",
        "subject": "{{name}}, spor yatırımlarına ekstra güç — canlı bahiste avantaj",
        "html_body": _html_shell(
            "Spor Bonusu",
            "Canlı bahis",
            "Kuponunu güçlendirecek yatırım fırsatı",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Spor ve canlı bahis tarafında aktif kampanyalarla yatırımlarına
            <strong style="color:#ffd400;">ekstra bonus</strong> yakalayabilirsin.
            Maç öncesi veya canlı — seçim senin.
            """,
            "Canlı Bahise Git",
            CTA_SPORT,
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Casino Kayıp İadesi",
        "subject": "{{name}}, kayıpların peşindeyiz — casino iade fırsatına bak",
        "html_body": _html_shell(
            "Kayıp iadesi",
            "Casino",
            "Şans dönsün diye bir fırsat daha",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Casino / canlı casino’da yaşanan kayıplar için dönemsel
            <strong style="color:#ffd400;">iade (cashback)</strong> kampanyalarını kaçırma.
            Detayları kontrol et, uygunsa bonusunu talep et.
            """,
            "Detayları Gör",
            CTA_PROMO,
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Freebet + Freespin",
        "subject": "{{name}}, günlük freebet & freespin şansı — Makrobet",
        "html_body": _html_shell(
            "Günlük çekiliş",
            "Hediyeler",
            "Freebet ve freespin seni bekliyor olabilir",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Makrobet’te günlük hediye / çekiliş tarzı kampanyalarla
            <strong style="color:#ffd400;">freebet</strong> ve
            <strong style="color:#ffd400;">freespin</strong> fırsatları dönüyor.
            Hesabına uğra, aktif kampanyaları yakala.
            """,
            "Hemen Katıl",
            CTA_TOKEN,
        ),
        "text_body": "",
    },
    {
        "name": "HTML · VIP Özel Davet",
        "subject": "{{name}}, sana özel VIP ayrıcalıklar — Makrobet",
        "html_body": _html_shell(
            "VIP",
            "Özel seçim",
            "Seçili üyelere özel davet",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Seni Makrobet VIP deneyimine davet ediyoruz: öncelikli destek,
            özel kampanyalar ve kişiselleştirilmiş fırsatlar.
            <strong style="color:#ffd400;">Tek tıkla</strong> hesabına dön.
            """,
            "VIP’ye Göz At",
            CTA_TOKEN,
            "Bu ileti seçili üyelere yönelik bilgilendirme amaçlıdır.",
        ),
        "text_body": "",
    },
    {
        "name": "HTML · Canlı Casino Hafta Sonu",
        "subject": "{{name}}, hafta sonu canlı casino temposu Makrobet’te",
        "html_body": _html_shell(
            "Hafta sonu",
            "Canlı casino",
            "Masa oyunlarında geceye hazır mısın?",
            """
            Merhaba <strong style="color:#fff;">{{name}}</strong>,<br><br>
            Rulet, blackjack ve canlı masalar hafta sonu için hazır.
            Aktif bonuslarını kontrol et, masanı seç,
            <strong style="color:#ffd400;">canlı casino</strong>’ya bağlan.
            """,
            "Canlı Casino’yu Aç",
            "{{link:sc:https://makrobet805.com/tr/game/live-casino}}",
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

{CTA_CASINO}

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


def seed_makrobet_mail_templates(conn, force_missing=False):
    """Eksik Makrobet şablonlarını ekler.

    Eski v1 flag yüzünden HTML’ler hiç eklenmemiş olabilir — isme göre
    eksikleri her boot’ta (veya force_missing ile) tamamlar.
    """
    now = iso(utcnow())
    added = 0
    # force_missing veya henüz v2 işaretlenmemişse eksikleri doldur
    already = (get_mail_setting(conn, SEED_FLAG, "") or "").strip() == "1"
    if already and not force_missing:
        # Yine de eksik isimleri kontrol et (ucuz SELECT)
        pass
    for item in HTML_TEMPLATES + TEXT_TEMPLATES:
        name = item["name"]
        exists = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (name,))
        if exists:
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
    return added
