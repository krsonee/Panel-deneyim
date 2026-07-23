"""Bizzo Casino HTML email template engine — yatırım odaklı preset’ler.

Kaynak: https://www.bizzocasino168.com/promotions
Placeholder: __BIZZO_LOGO__, {{name}}, {{link:sc:https://www.bizzocasino168.com}}
"""

from __future__ import annotations

from typing import Sequence

# Site / logo ile aynı palet
BG = "#2b1234"          # logo köşe: rgb(43,18,52)
CARD = "#1a0f24"
ROW = "#3a1f4a"
GREEN = "#2ecc71"
ORANGE = "#ff9f1a"
TEXT = "#ffffff"
MUTED = "#c4b0d4"
BORDER = "#5a3a6e"
CTA_INK = "#1a0a10"
NOTICE_BG = "#2a1a08"

FONT = "Arial, Helvetica, sans-serif"
MAX_W = 600

SITE = "https://www.bizzocasino168.com"
CTA = "{{link:sc:https://www.bizzocasino168.com}}"
LOGO = "__BIZZO_LOGO__"


def notice_spam() -> str:
    return f"""
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:0 12px 12px;">
        <table role="presentation" width="{MAX_W}" cellpadding="0" cellspacing="0" border="0"
          bgcolor="{NOTICE_BG}"
          style="width:100%;max-width:{MAX_W}px;background-color:{NOTICE_BG};border:1px solid #6a4a10;border-radius:12px;">
          <tr>
            <td align="center" style="padding:12px 16px;font-family:{FONT};font-size:12px;line-height:1.5;color:{ORANGE};">
              Spam klasöründeyse <strong style="color:{ORANGE};">butonlar çalışmaz</strong>.
              Önce <strong style="color:{ORANGE};">Spam değil</strong> deyin, sonra tıklayın.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>"""


def logo_block(width: int = 200) -> str:
    return (
        f'<a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;border:0;">'
        f'<img src="{LOGO}" alt="Bizzo Casino" width="{width}" border="0" '
        f'style="display:block;margin:0 auto;border:0;outline:none;'
        f'background-color:{BG};max-width:{width}px;width:{width}px;height:auto;"></a>'
    )


def badge(label: str) -> str:
    return (
        f'<span style="display:inline-block;background:{GREEN};color:{BG};'
        f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.08em;"
        f'text-transform:uppercase;padding:6px 14px;border-radius:999px;">{label}</span>'
    )


def cta_button(label: str, *, color: str = ORANGE, ink: str = CTA_INK) -> str:
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:0 auto;">
  <tr>
    <td align="center" bgcolor="{color}" style="background-color:{color};border-radius:12px;">
      <a href="{CTA}" target="_blank" rel="noopener"
        style="display:inline-block;background-color:{color};color:{ink};
        font-family:{FONT};font-size:15px;font-weight:800;line-height:1.2;
        text-decoration:none;padding:14px 28px;border-radius:12px;">{label}</a>
    </td>
  </tr>
</table>"""


def cta_row(label: str, *, color: str = ORANGE) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:8px 20px 18px;">
              {cta_button(label, color=color)}
            </td>
          </tr>"""


def eyebrow(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 20px 6px;font-family:{FONT};font-size:11px;
              font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:{GREEN};">{text}</td>
          </tr>"""


def headline(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 20px 10px;font-family:{FONT};font-size:22px;
              line-height:1.3;font-weight:800;color:{TEXT};">{text}</td>
          </tr>"""


def lead(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 22px 14px;font-family:{FONT};font-size:14px;
              line-height:1.55;color:{MUTED};">{text}</td>
          </tr>"""


def feature_box(big: str, title: str, sub: str) -> str:
    return f"""
          <tr>
            <td style="padding:4px 20px 14px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{CARD}" style="background-color:{CARD};border-radius:16px;border:2px solid {GREEN};">
                <tr>
                  <td align="center" style="padding:22px 16px;">
                    <div style="font-family:{FONT};font-size:32px;font-weight:900;color:{GREEN};line-height:1;">{big}</div>
                    <div style="font-family:{FONT};font-size:16px;font-weight:800;color:{TEXT};margin-top:8px;">{title}</div>
                    <div style="font-family:{FONT};font-size:13px;line-height:1.5;color:{MUTED};margin-top:8px;">{sub}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_card(title: str, desc: str) -> str:
    return f"""
          <tr>
            <td style="padding:0 20px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{ROW}"
                style="background-color:{ROW};border:1px solid {BORDER};border-left:3px solid {ORANGE};border-radius:12px;">
                <tr>
                  <td style="padding:13px 14px;">
                    <div style="font-family:{FONT};font-size:14px;font-weight:800;color:{ORANGE};line-height:1.3;">{title}</div>
                    <div style="font-family:{FONT};font-size:12px;color:{MUTED};line-height:1.5;margin-top:5px;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_cards(items: Sequence[tuple[str, str]]) -> str:
    return "".join(promo_card(t, d) for t, d in items)


def footer_legal() -> str:
    return f"""
          <tr>
            <td align="center" style="padding:12px 20px 22px;font-family:{FONT};font-size:11px;
              line-height:1.5;color:{MUTED};border-top:1px solid {BORDER};">
              Spam’de butonlar kilitli · Spam değil deyip tekrar dene<br>
              18+ · Sorumlu oyun · Oyun bağımlılığa yol açabilir · Bizzo Casino
            </td>
          </tr>"""


def shell(*, title: str, body_rows: str, preheader: str = "") -> str:
    pre = (
        f'<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;'
        f'opacity:0;overflow:hidden;mso-hide:all;">{preheader}&nbsp;&#847;&nbsp;&#847;</div>'
        if preheader
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="color-scheme" content="dark">
  <title>{title}</title>
  <!--[if mso]>
  <style>table,td{{font-family:Arial,sans-serif !important;}}</style>
  <![endif]-->
  <style type="text/css">
    body,table,td,a{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
    table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;}}
    img{{-ms-interpolation-mode:bicubic;border:0;outline:none;text-decoration:none;display:block;}}
    body{{margin:0 !important;padding:0 !important;width:100% !important;background:{BG};}}
    a[x-apple-data-detectors]{{color:inherit !important;text-decoration:none !important;}}
    @media only screen and (max-width:620px){{
      .bz-shell{{width:100% !important;}}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{BG};font-family:{FONT};">
  {pre}
  {notice_spam()}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}" style="background-color:{BG};">
    <tr>
      <td align="center" style="padding:8px 10px 32px;">
        <table role="presentation" class="bz-shell" width="{MAX_W}" cellpadding="0" cellspacing="0" border="0"
          bgcolor="{CARD}"
          style="width:100%;max-width:{MAX_W}px;background-color:{CARD};border:1px solid {BORDER};border-radius:16px;">
          <tr><td height="3" bgcolor="{ORANGE}" style="height:3px;line-height:3px;font-size:0;background-color:{ORANGE};">&nbsp;</td></tr>
          <tr>
            <td align="center" bgcolor="{BG}" style="padding:22px 20px 12px;background-color:{BG};">
              {logo_block()}
            </td>
          </tr>
          {body_rows}
          {footer_legal()}
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ── Deposit-driving presets (promotions page) ──────────────────────────────
def preset_ilk_yatirim() -> dict:
    items = [
        (
            "1000₺ Deneme Bonusu",
            "Pragmatic Play’de risk almadan dene; sonra ilk yatırımla asıl paketi aç.",
        ),
        (
            "%100 Slot Hoş Geldin",
            "İlk çekime kadar her yatırımda %100 bonus — sadece 2x çevrim, çekim limiti yok.",
        ),
        (
            "%100 Pragmatic Nakit",
            "50.000₺’ye kadar Pragmatic Play nakit bonusunu yatırımınla aktifleştir.",
        ),
        (
            "%100 Anlık İade",
            "50.000₺’ye varan anlık iade — kaybetmek yok hissi, yeniden yatırım güveni.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 10px;">{badge("İLK YATIRIM")}</td></tr>'
        + eyebrow("Hoş geldin paketi")
        + headline("{{name}}, ilk yatırımınla paketi ikiye katla")
        + feature_box(
            "%100",
            "Çekim yapana kadar sınırsız slot hoş geldin",
            "Her yatırımda anında %100 · 2x çevrim · sıfır çekim limiti",
        )
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — Bizzo promosyonları "
            "yatırım yaptıkça açılır. İlk adımı at:"
        )
        + promo_cards(items)
        + cta_row("İlk Yatırımı Yap")
    )
    return {
        "name": "Bizzo · 2026 · İlk Yatırım Paketi",
        "subject": "{{name}}, ilk yatırımınla %100 slot hoş geldin seni bekliyor",
        "html_body": shell(
            title="Bizzo İlk Yatırım",
            preheader="İlk yatırımda %100 slot hoş geldin — 2x çevrim",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "İlk yatırımınla %100 slot hoş geldin + Pragmatic nakit paketi.\n"
            f"Yatırım yap: {SITE}\n"
        ),
    }


def preset_slot_hosgeldin() -> dict:
    items = [
        (
            "Her yatırımda %100",
            "İlk çekimini yapana kadar her yatırdığın tutara eş bonus yazılır.",
        ),
        (
            "Sadece 2x çevrim",
            "Düşük çevrimle bonusunu hızlı çevir, kazancını büyüt.",
        ),
        (
            "Sıfır çekim limiti",
            "Çekim limiti yok — kazancını sınırlamadan katla.",
        ),
        (
            "1000₺ Deneme + Pragmatic",
            "Deneme ile ısın, yatırımla Pragmatic %100 nakit bonusunu da aç.",
        ),
    ]
    body = (
        eyebrow("Slot hoş geldin")
        + headline("Çekim yapana kadar %100 sınırsız bonus")
        + feature_box(
            "2x",
            "Çevrim şartı · çekim limiti yok",
            "İlk çekime kadar her yatırımda anında %100 slot bonusu",
        )
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — bu paket yalnızca "
            "yatırım yapan üyelerde aktif. Hemen yükle, bonusunu al:"
        )
        + promo_cards(items)
        + cta_row("Yatırım Yap — Bonusu Al")
    )
    return {
        "name": "Bizzo · 2026 · %100 Slot Hoş Geldin",
        "subject": "{{name}}, çekim yapana kadar her yatırımda %100 bonus",
        "html_body": shell(
            title="Bizzo Slot Hoş Geldin",
            preheader="Her yatırımda %100 — 2x çevrim, çekim limiti yok",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Çekim yapana kadar her yatırımda %100 slot hoş geldin.\n"
            f"Yatırım: {SITE}\n"
        ),
    }


def preset_kayip_iade() -> dict:
    items = [
        (
            "%100 Anlık İade",
            "50.000₺’ye varan anlık iade fırsatı — kaybını telafi edip yeniden yükle.",
        ),
        (
            "%25’e varan kayıp bonusu",
            "Kayıplarına karşılık bonus; çekim sınırı yok, yeniden yatırım için güç.",
        ),
        (
            "%50 Duo Kayıp",
            "20.000₺+ yatırımlarda %25 anlık + %25 ertesi gün — toplam %50.",
        ),
        (
            "Slot / Pragmatic paketleri",
            "İade sonrası yeni yatırımınla %100 slot ve Pragmatic nakit bonuslarını da kullan.",
        ),
    ]
    body = (
        eyebrow("Kayıp / iade")
        + headline("Kaybetmek yok — yatır, iade al, devam et")
        + feature_box(
            "%100",
            "Anlık iade fırsatı",
            "50.000₺’ye varan iade · yeniden yatırım için güvenli zemin",
        )
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — kayıplarını Bizzo "
            "telafi eder. İade + yeni yatırım döngüsünü aç:"
        )
        + promo_cards(items)
        + cta_row("Yatırım Yap — İadeyi Kullan")
    )
    return {
        "name": "Bizzo · 2026 · Kayıp & Anlık İade",
        "subject": "{{name}}, %100 anlık iade + kayıp bonuslarıyla yeniden yükle",
        "html_body": shell(
            title="Bizzo Kayıp Bonusu",
            preheader="%100 anlık iade · %25–%50 kayıp bonusu",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "%100 anlık iade ve kayıp bonusları seni bekliyor.\n"
            f"Yatırım: {SITE}\n"
        ),
    }


def preset_duo_kayip() -> dict:
    items = [
        (
            "%25 anlık + %25 ertesi gün",
            "Toplam %50 duo kayıp — yüksek yatırımını koruyan paket.",
        ),
        (
            "20.000₺ ve üzeri yatırımlar",
            "Eşik üzeri yüklemelerde duo kayıp otomatik güçlenir.",
        ),
        (
            "Çekim sınırı yok",
            "Kayıp bonusunda çekim sınırı bulunmaz — özgürce devam et.",
        ),
        (
            "Yanında %100 slot hoş geldin",
            "İlk çekime kadar her yatırımda %100 slot bonusu da aktif kalabilir.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 10px;">{badge("YÜKSEK YATIRIM")}</td></tr>'
        + eyebrow("Duo kayıp")
        + headline("%50’ye varan duo kayıp — yatırımı büyüt")
        + feature_box(
            "%50",
            "Duo kayıp bonusu",
            "20.000₺+ yatırımlarda %25 anlık + %25 ertesi gün",
        )
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — bakiyeni büyüt, "
            "duo kayıp güvencesiyle oyna:"
        )
        + promo_cards(items)
        + cta_row("Yüksek Yatırım Yap")
    )
    return {
        "name": "Bizzo · 2026 · Duo Kayıp %50",
        "subject": "{{name}}, 20.000₺+ yatırımlarda %50 duo kayıp seni bekliyor",
        "html_body": shell(
            title="Bizzo Duo Kayıp",
            preheader="%50 duo kayıp — 20.000₺ ve üzeri yatırımlar",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "20.000₺+ yatırımlarda %50 duo kayıp.\n"
            f"Yatırım: {SITE}\n"
        ),
    }


def preset_kripto() -> dict:
    items = [
        (
            "Kripto yatır",
            "USDT / kripto ile yatırım yap — işlem hızlı, bonus hakkı doğar.",
        ),
        (
            "Havale ile çek",
            "Çekimi havale ile tamamla, %25 ekstra nakit hakkını kullan.",
        ),
        (
            "%25 ekstra nakit",
            "Kripto→havale döngüsünde çekimlerin daha değerli hale gelir.",
        ),
        (
            "Üstüne slot / Pragmatic",
            "Aynı dönemde %100 slot hoş geldin ve Pragmatic nakit paketlerini de aç.",
        ),
    ]
    body = (
        eyebrow("Kripto yatırım")
        + headline("Kripto yatır, havale çek — %25 bonus kazan")
        + feature_box(
            "%25",
            "Kripto yatır · havale çek",
            "Çekimini daha değerli yap — ekstra nakit hakkı",
        )
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — kripto ile yükle, "
            "havale ile çek, %25 ekstra nakit kap:"
        )
        + promo_cards(items)
        + cta_row("Kripto ile Yatırım Yap")
    )
    return {
        "name": "Bizzo · 2026 · Kripto Yatırım %25",
        "subject": "{{name}}, kripto yatır havale çek — %25 ekstra nakit",
        "html_body": shell(
            title="Bizzo Kripto Yatırım",
            preheader="Kripto yatır, havale çek, %25 bonus kazan",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Kripto yatır · havale çek · %25 ekstra nakit.\n"
            f"Yatırım: {SITE}\n"
        ),
    }


def preset_pragmatic_nakit() -> dict:
    items = [
        (
            "%100 Pragmatic Play nakit",
            "50.000₺’ye kadar %100 nakit — yatırımınla hemen aktifleştir.",
        ),
        (
            "Sadece 2x çevrim",
            "Düşük çevrim + sıfır çekim limiti — kazancı kesintisiz çek.",
        ),
        (
            "200x nakit ödül",
            "Günün seçili oyununda 200x+ kazanca, kazancının %50’si nakit ödül (3x çevrim).",
        ),
        (
            "Slot hoş geldin ile birleşir",
            "İlk çekime kadar her yatırımda %100 slot bonusu da yanında.",
        ),
    ]
    body = (
        eyebrow("Pragmatic / nakit")
        + headline("Pragmatic’e özel %100 nakit — yatırımla aç")
        + feature_box(
            "%100",
            "Pragmatic Play nakit bonusu",
            "50.000₺’ye kadar · 2x çevrim · sıfır çekim limiti",
        )
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — nakit bonuslar "
            "yatırım sonrası tanımlanır. Hemen yükle:"
        )
        + promo_cards(items)
        + cta_row("Yatırım Yap — Nakit Bonusu Al")
    )
    return {
        "name": "Bizzo · 2026 · Pragmatic %100 Nakit",
        "subject": "{{name}}, Pragmatic’te 50.000₺’ye kadar %100 nakit bonus",
        "html_body": shell(
            title="Bizzo Pragmatic Nakit",
            preheader="%100 Pragmatic nakit · 200x nakit ödül",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Pragmatic %100 nakit (50.000₺’ye kadar) + 200x nakit ödül.\n"
            f"Yatırım: {SITE}\n"
        ),
    }


PRESET_BUILDERS = (
    preset_ilk_yatirim,
    preset_slot_hosgeldin,
    preset_kayip_iade,
    preset_duo_kayip,
    preset_kripto,
    preset_pragmatic_nakit,
)


def build_all_presets() -> list[dict]:
    return [fn() for fn in PRESET_BUILDERS]
