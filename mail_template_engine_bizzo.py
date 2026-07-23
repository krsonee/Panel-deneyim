"""Bizzo Casino 2026 HTML email engine — high-conversion deposit presets.

CTA / tüm tıklanabilir alanlar: {{link:sc:https://girbize.com/}}
Logo: __BIZZO_LOGO__
"""

from __future__ import annotations

from typing import Sequence

# ── 2026 design tokens ─────────────────────────────────────────────────────
BG = "#1A0B2E"
CARD = "#271342"
ROW = "#2E1748"
ORANGE = "#FF9900"
ORANGE_DEEP = "#FF5500"
NEON = "#00FF87"
NEON_SOFT = "rgba(0, 255, 135, 0.08)"
NEON_BORDER = "rgba(0, 255, 135, 0.3)"
TEXT = "#FFFFFF"
MUTED = "#C4B5FD"
BORDER = "#3D2460"
CTA_INK = "#1A0B2E"
NOTICE_BG = "#2A1A08"
NOTICE_GOLD = "#FFD27A"

FONT = "Arial, Helvetica, sans-serif"
MAX_W = 600

AFF = "https://girbize.com/"
CTA = "{{link:sc:https://girbize.com/}}"
LOGO = "__BIZZO_LOGO__"


def notice_spam() -> str:
    """Sleek dark-amber toast — gold text, no raw URLs."""
    return f"""
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:0 12px 12px;">
        <table role="presentation" width="{MAX_W}" cellpadding="0" cellspacing="0" border="0"
          bgcolor="{NOTICE_BG}"
          style="width:100%;max-width:{MAX_W}px;background-color:{NOTICE_BG};
          border:1px solid #6A4A12;border-radius:14px;">
          <tr>
            <td align="center" style="padding:11px 16px;font-family:{FONT};font-size:12px;
              line-height:1.5;color:{NOTICE_GOLD};">
              Spam klasöründeyse <strong style="color:{NOTICE_GOLD};">butonlar çalışmaz</strong>.
              Önce <strong style="color:{NOTICE_GOLD};">Spam değil</strong> deyin, sonra tıklayın.
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
        f'<span style="display:inline-block;background:{NEON_SOFT};color:{NEON};'
        f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.1em;"
        f"text-transform:uppercase;padding:7px 16px;border-radius:999px;"
        f'border:1px solid {NEON_BORDER};">{label}</span>'
    )


def cta_button(label: str) -> str:
    """Pill CTA — orange gradient + solid fallback for Outlook."""
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:0 auto;">
  <tr>
    <td align="center" bgcolor="{ORANGE}"
      style="background-color:{ORANGE};background-image:linear-gradient(90deg,{ORANGE},{ORANGE_DEEP});
      border-radius:99px;mso-padding-alt:0;">
      <a href="{CTA}" target="_blank" rel="noopener"
        style="display:inline-block;background-color:{ORANGE};
        background-image:linear-gradient(90deg,{ORANGE},{ORANGE_DEEP});
        color:{CTA_INK};font-family:{FONT};font-size:15px;font-weight:800;line-height:1.2;
        text-decoration:none;padding:15px 30px;border-radius:99px;">{label}</a>
    </td>
  </tr>
</table>"""


def cta_row(label: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:6px 20px 16px;">
              {cta_button(label)}
            </td>
          </tr>"""


def eyebrow(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 20px 6px;font-family:{FONT};font-size:11px;
              font-weight:800;letter-spacing:0.14em;text-transform:uppercase;color:{NEON};">{text}</td>
          </tr>"""


def headline(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 18px 8px;font-family:{FONT};font-size:23px;
              line-height:1.3;font-weight:800;color:{TEXT};">{text}</td>
          </tr>"""


def lead(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 22px 12px;font-family:{FONT};font-size:14px;
              line-height:1.55;color:{MUTED};">{text}</td>
          </tr>"""


def hero_glow(big: str, title: str, sub: str) -> str:
    """Neon glow hero — no harsh green stroke."""
    # Outlook-safe solid approx of rgba(0,255,135,0.08) on #1A0B2E → #152A28-ish
    solid_glow = "#152A28"
    return f"""
          <tr>
            <td style="padding:4px 18px 12px;">
              <a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                  bgcolor="{solid_glow}"
                  style="background-color:{NEON_SOFT};background:{NEON_SOFT};
                  border:1px solid {NEON_BORDER};border-radius:16px;">
                  <tr>
                    <td align="center" style="padding:22px 16px;">
                      <div style="font-family:{FONT};font-size:34px;font-weight:900;color:{NEON};line-height:1;">{big}</div>
                      <div style="font-family:{FONT};font-size:16px;font-weight:800;color:{TEXT};margin-top:8px;">{title}</div>
                      <div style="font-family:{FONT};font-size:13px;line-height:1.5;color:{MUTED};margin-top:8px;">{sub}</div>
                    </td>
                  </tr>
                </table>
              </a>
            </td>
          </tr>"""


def promo_card(title: str, desc: str) -> str:
    """List card — 4px orange accent bar + soft shadow."""
    return f"""
          <tr>
            <td style="padding:0 18px 9px;">
              <a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                  bgcolor="{ROW}"
                  style="background-color:{ROW};border:1px solid {BORDER};border-radius:16px;
                  box-shadow:0 8px 24px rgba(0,0,0,0.28);">
                  <tr>
                    <td width="4" bgcolor="{ORANGE}"
                      style="width:4px;background-color:{ORANGE};
                      background-image:linear-gradient(180deg,{ORANGE},{ORANGE_DEEP});
                      border-radius:16px 0 0 16px;font-size:0;line-height:0;">&nbsp;</td>
                    <td style="padding:14px 14px 14px 12px;">
                      <div style="font-family:{FONT};font-size:14px;font-weight:800;color:{ORANGE};line-height:1.3;">{title}</div>
                      <div style="font-family:{FONT};font-size:12px;color:{MUTED};line-height:1.5;margin-top:5px;">{desc}</div>
                    </td>
                  </tr>
                </table>
              </a>
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
          <tr>
            <td height="3" bgcolor="{ORANGE}"
              style="height:3px;line-height:3px;font-size:0;
              background-color:{ORANGE};background-image:linear-gradient(90deg,{ORANGE},{ORANGE_DEEP});">&nbsp;</td>
          </tr>
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


def _pack(
    *,
    name: str,
    subject: str,
    title: str,
    preheader: str,
    body: str,
    text: str,
) -> dict:
    return {
        "name": name,
        "subject": subject,
        "html_body": shell(title=title, preheader=preheader, body_rows=body),
        "text_body": text,
    }


# ── Presets ────────────────────────────────────────────────────────────────
def preset_ilk_yatirim() -> dict:
    items = [
        ("1000₺ Deneme Bonusu", "Pragmatic’te ısın — sonra ilk yatırımla asıl paketi aç."),
        ("%100 Slot Hoş Geldin", "İlk çekime kadar her yatırımda %100 · sadece 2x çevrim."),
        ("%100 Pragmatic Nakit", "50.000₺’ye kadar nakit katlama — yatırımınla anında aktif."),
        ("%100 Anlık İade", "50.000₺’ye varan iade güvencesi — riski Bizzo üstlenir."),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 10px;">{badge("HOŞ GELDİN AŞAMASI")}</td></tr>'
        + headline("{{name}}, İlk Yatırımında Kasanı 2'ye Katlamaya Hazır Mısın?")
        + hero_glow(
            "%100",
            "Çekim Yapana Kadar Sınırsız Slot Keyfi — Limitsiz Kazanç!",
            "Her yatırımda anında %100 · 2x çevrim · sıfır çekim limiti",
        )
        + cta_row("Sınırsız Bonusu Kap")
        + lead("Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — paket yatırımla açılır. Kaçırma:")
        + promo_cards(items)
        + cta_row("Anında Yatırım Yap")
    )
    return _pack(
        name="Bizzo · 2026 · İlk Yatırım Paketi",
        subject="{{name}}, ilk yatırımında kasanı 2'ye katla — sınırsız slot hoş geldin",
        title="Bizzo İlk Yatırım",
        preheader="Çekim yapana kadar sınırsız slot — limitsiz kazanç",
        body=body,
        text=(
            "Merhaba {{name}},\n\n"
            "İlk yatırımında kasanı 2'ye katla. Çekim yapana kadar sınırsız slot.\n"
            f"Yatırım: {AFF}\n"
        ),
    )


def preset_slot_hosgeldin() -> dict:
    items = [
        ("Anında %100 slot", "Her yatırdığın tutara eş bonus — çekim yapana kadar."),
        ("Sadece 2x çevrim", "Düşük çevrimle bakiye katlama hızlanır."),
        ("Sıfır çekim limiti", "Kazancını sınırlamadan büyüt, özgürce çek."),
        ("Deneme + Pragmatic", "Isın, yükle, Pragmatic %100 nakit paketini de aç."),
    ]
    body = (
        eyebrow("Slot hoş geldin")
        + headline("Sadece 2x Çevrimle Bakiye Katlama Devri Başladı!")
        + hero_glow(
            "2x",
            "Sıfır Çekim Limiti + Anında Tanımlanan %100 Slot Bonusu.",
            "İlk çekime kadar her yatırımda %100 — kaçırma.",
        )
        + cta_row("Sınırsız Bonusu Kap")
        + lead("Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — bakiye katlama için tek adım: yatırım.")
        + promo_cards(items)
        + cta_row("Anında Yatırım Yap")
    )
    return _pack(
        name="Bizzo · 2026 · %100 Slot Hoş Geldin",
        subject="{{name}}, 2x çevrimle bakiye katlama — %100 slot şimdi",
        title="Bizzo Slot Hoş Geldin",
        preheader="2x çevrim · sıfır çekim limiti · anında %100",
        body=body,
        text=(
            "Merhaba {{name}},\n\n"
            "2x çevrimle bakiye katlama: anında %100 slot, sıfır çekim limiti.\n"
            f"Yatırım: {AFF}\n"
        ),
    )


def preset_kayip_iade() -> dict:
    items = [
        ("%100 Instant Cash Back", "50.000₺’ye varan anlık iade — oyuna hemen dön."),
        ("%25’e varan kayıp", "Kayıplarına karşılık bonus; çekim sınırı yok."),
        ("%50 Duo seçeneği", "Yüksek yatırımda %25 anlık + %25 ertesi gün."),
        ("Yeniden yükle, katla", "İade sonrası yeni yatırımla slot / Pragmatic paketlerini aç."),
    ]
    body = (
        eyebrow("Kayıp / iade")
        + headline("Kaybetmek Yok — Instant Cash Back İle Anında Oyuna Dön!")
        + hero_glow(
            "%100",
            "50.000 TL'ye varan anlık iade güvencesiyle risk sıfırlandı.",
            "İade al · yeniden yatır · momentumu bozma",
        )
        + cta_row("Nakit İadeyi Al")
        + lead("Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — risk Bizzo’da, aksiyon sende.")
        + promo_cards(items)
        + cta_row("Anında Yatırım Yap")
    )
    return _pack(
        name="Bizzo · 2026 · Kayıp & Anlık İade",
        subject="{{name}}, instant cash back — 50.000₺'ye varan anlık iade",
        title="Bizzo Kayıp İade",
        preheader="Kaybetmek yok — anında oyuna dön",
        body=body,
        text=(
            "Merhaba {{name}},\n\n"
            "Instant cash back: 50.000₺'ye varan anlık iade.\n"
            f"Yatırım: {AFF}\n"
        ),
    )


def preset_duo_kayip() -> dict:
    items = [
        ("%25 anlık iade", "Yüksek yatırımında ilk destek anında hesabında."),
        ("%25 ertesi gün", "Ertesi gün ikinci dilim — toplam %50 güvence."),
        ("20.000₺+ yatırımlar", "Eşik üzeri yüklemelerde duo kayıp güçlenir."),
        ("Çekim sınırı yok", "Kayıp paketinde özgürce devam et, bakiyeyi büyüt."),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 10px;">{badge("YÜKSEK YATIRIM")}</td></tr>'
        + headline("Yüksek Yatırımlara Özel %50 Duo Kayıp Güvencesi")
        + hero_glow(
            "%50",
            "%25 Anlık İade + %25 Ertesi Gün Bakiye Desteği.",
            "20.000₺ ve üzeri yatırımlara özel — kaçırma.",
        )
        + cta_row("Anında Yatırım Yap")
        + lead("Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — yüksek yükle, duo güvenceyi aç.")
        + promo_cards(items)
        + cta_row("Yüksek Yatırımı Yap")
    )
    return _pack(
        name="Bizzo · 2026 · Duo Kayıp %50",
        subject="{{name}}, yüksek yatırıma özel %50 duo kayıp güvencesi",
        title="Bizzo Duo Kayıp",
        preheader="%25 anlık + %25 ertesi gün — toplam %50",
        body=body,
        text=(
            "Merhaba {{name}},\n\n"
            "%50 duo kayıp: %25 anlık + %25 ertesi gün.\n"
            f"Yatırım: {AFF}\n"
        ),
    )


def preset_kripto() -> dict:
    items = [
        ("USDT / kripto yükle", "Hızlı yatırım — %25 nakit hakkı doğar."),
        ("Havale ile çek", "Kesintisiz çekim yolunu aç, ekstra nakitı kap."),
        ("Pragmatic %100", "Aynı dönemde 50.000₺’ye kadar Pragmatic katlama."),
        ("Slot hoş geldin", "İlk çekime kadar her yatırımda %100 slot da yanında."),
    ]
    body = (
        eyebrow("Kripto + nakit")
        + headline("Kripto Yatırımlarına Özel %25 Nakit + Pragmatic Play %100 Katlama!")
        + hero_glow(
            "%25",
            "USDT ile yükle, Havale ile kesintisiz çek.",
            "Kripto avantajı + Pragmatic %100 nakit paketi",
        )
        + cta_row("Anında Yatırım Yap")
        + lead("Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — USDT yükle, çift avantajı kullan.")
        + promo_cards(items)
        + cta_row("Kripto ile Yatır")
    )
    return _pack(
        name="Bizzo · 2026 · Kripto Yatırım %25",
        subject="{{name}}, kripto yatırımlarına özel %25 nakit + Pragmatic %100",
        title="Bizzo Kripto Yatırım",
        preheader="USDT yükle · havale çek · %25 nakit",
        body=body,
        text=(
            "Merhaba {{name}},\n\n"
            "Kripto yatırımlarına özel %25 nakit + Pragmatic %100.\n"
            f"Yatırım: {AFF}\n"
        ),
    )


def preset_pragmatic_nakit() -> dict:
    items = [
        ("%100 Pragmatic nakit", "50.000₺’ye kadar katlama — yatırımınla anında tanım."),
        ("Sadece 2x çevrim", "Düşük çevrim + sıfır çekim limiti."),
        ("200x nakit ödül", "Günün oyununda 200x+ → kazancının %50’si nakit (3x)."),
        ("Kripto yolu", "USDT ile yükle, havale ile çek — %25 ekstra nakit hakkı."),
    ]
    body = (
        eyebrow("Pragmatic / nakit")
        + headline("Kripto Yatırımlarına Özel %25 Nakit + Pragmatic Play %100 Katlama!")
        + hero_glow(
            "%100",
            "USDT ile yükle, Havale ile kesintisiz çek.",
            "Pragmatic 50.000₺’ye kadar %100 · 2x çevrim",
        )
        + cta_row("Nakit Bonusu Kap")
        + lead("Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — nakit katlama yatırımla başlar.")
        + promo_cards(items)
        + cta_row("Anında Yatırım Yap")
    )
    return _pack(
        name="Bizzo · 2026 · Pragmatic %100 Nakit",
        subject="{{name}}, Pragmatic %100 katlama + kripto %25 nakit",
        title="Bizzo Pragmatic Nakit",
        preheader="Pragmatic %100 · USDT yükle · havale çek",
        body=body,
        text=(
            "Merhaba {{name}},\n\n"
            "Pragmatic %100 katlama + kripto %25 nakit.\n"
            f"Yatırım: {AFF}\n"
        ),
    )


def preset_davet_deneme() -> dict:
    """Davet teması — 1000₺ deneme + 5.000₺ çekim imkanı."""
    items = [
        (
            "%100 Slot Hoş Geldin",
            "Çekim yapana kadar her yatırımda %100 — sadece 2x çevrim, sıfır çekim limiti.",
        ),
        (
            "%100 Anlık İade",
            "50.000₺’ye varan instant cash back — kaybetmek yok hissi.",
        ),
        (
            "%100 Pragmatic Nakit",
            "50.000₺’ye kadar Pragmatic Play nakit katlama — yatırımınla aç.",
        ),
        (
            "%50 Duo Kayıp",
            "Yüksek yatırımlarda %25 anlık + %25 ertesi gün güvence.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 10px;">{badge("ÖZEL DAVET")}</td></tr>'
        + headline("{{name}}, Seni 1.000₺ Deneme Bonusuyla Davet Ediyoruz!")
        + hero_glow(
            "1.000₺",
            "Deneme Bonusu + 5.000₺ Çekim İmkanı",
            "Kayıt ol, denemeyi kap — kazancını 5.000₺’ye kadar çek",
        )
        + cta_row("Daveti Kabul Et — Denemeyi Kap")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — özel davetlisin. "
            "1.000₺ deneme ile başla, 5.000₺ çekim hakkını kullan; ardından paketleri aç:"
        )
        + promo_cards(items)
        + cta_row("Hemen Katıl — 1.000₺ Deneme")
    )
    return _pack(
        name="Bizzo · 2026 · Davet · 1000₺ Deneme",
        subject="{{name}}, özel davet — 1.000₺ deneme + 5.000₺ çekim imkanı",
        title="Bizzo Davet Deneme",
        preheader="1.000₺ deneme bonusu · 5.000₺ çekim imkanı",
        body=body,
        text=(
            "Merhaba {{name}},\n\n"
            "Özel davet: 1.000₺ deneme bonusu + 5.000₺ çekim imkanı.\n"
            f"Katıl: {AFF}\n"
        ),
    )


PRESET_BUILDERS = (
    preset_davet_deneme,
    preset_ilk_yatirim,
    preset_slot_hosgeldin,
    preset_kayip_iade,
    preset_duo_kayip,
    preset_kripto,
    preset_pragmatic_nakit,
)


def build_all_presets() -> list[dict]:
    return [fn() for fn in PRESET_BUILDERS]
