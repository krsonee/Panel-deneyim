"""Makrobet 2026 mailing şablonları (5 adet) — panel seed."""
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

SEED_FLAG = "seeded_makrobet_templates_v2026"

TEMPLATES = [
    {
        "name": '2026 · Davet Mailingi',
        "subject": "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!",
        "html_body": """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Makrobet’te yerin hazır</title></head>
<body style="margin:0;padding:0;background:#040e1f;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;"><tr>
<td align="center" style="padding:10px 16px;font-family:Georgia,'Times New Roman',serif;font-size:12px;line-height:1.45;color:#fff;">
<span style="color:#ffd400;">⚠</span>&nbsp;Butonlar için <strong style="color:#ffd400;">Spam olmadığını bildir</strong> seçeneğine tıklayın.
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#040e1f;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#061c3d;border:1px solid #2a4a7a;border-radius:18px;overflow:hidden;">
<tr><td style="height:3px;background:#ffd400;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td align="center" style="padding:26px 28px 10px;"><img src="__MAIL_LOGO__" alt="Makrobet" width="176" style="display:block;margin:0 auto;border:0;max-width:176px;height:auto;"></td></tr>
<tr><td align="center" style="padding:0 28px 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#ffd400;">Özel davet · 2026</td></tr>
<tr><td align="center" style="padding:0 28px 12px;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.2;font-weight:700;color:#fff;letter-spacing:-0.02em;">Makrobet’te yerin hazır</td></tr>
<tr><td align="center" style="padding:0 28px 18px;">
<table role="presentation" cellpadding="0" cellspacing="0" style="background:linear-gradient(180deg,#122a52 0%,#0a1f3d 100%);border:1px solid #ffd400;border-radius:14px;min-width:260px;">
<tr><td align="center" style="padding:18px 28px 6px;font-family:Georgia,'Times New Roman',serif;font-size:34px;line-height:1;font-weight:700;color:#ffd400;letter-spacing:-0.02em;">3.000 TL</td></tr>
<tr><td align="center" style="padding:0 22px 16px;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#e6f0fe;">DENEME KASASI</td></tr>
</table></td></tr>
<tr><td style="padding:0 28px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#e6f0fe;">Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>Seni Makrobet’e özel davet ediyoruz. Kayıt ol, <strong style='color:#ffd400;'>3.000 TL deneme kasası</strong> ile başla; sonra sitedeki canlı kampanyalarla devam et.</td></tr>
<tr><td style="padding:0 24px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">1</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">3.000 TL Deneme Kasası</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Yeni üyelere özel başlangıç kasası — kayıt sonrası hemen keşfet.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">2</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Arkadaşını Getir</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Arkadaşının aldığı yatırım bonusunu sana da ekleyelim.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">3</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">%100 Kayıp Bonusu</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Sıfır riskle yatırım senden, güvence Makrobet’ten.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">4</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Amusnet Yarışı</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">500.000₺ ödüllü yarışta adını duyur.</div>
</td>
</tr></table></td></tr></table></td></tr>
<tr><td align="center" style="padding:4px 24px 18px;"><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Happy Hours</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Makro Görev</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Kripto Ultra Kasa</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">VIP Club</span></td></tr>
<tr><td align="center" style="padding:8px 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="display:inline-block;background:#ffd400;color:#061c3d;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;text-decoration:none;padding:14px 28px;border-radius:10px;letter-spacing:0.02em;">Hemen Kayıt Ol</a>
</td></tr>
<tr><td align="center" style="padding:0 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;color:#ffd400;text-decoration:none;">Promosyonları incele →</a>
</td></tr>
<tr><td style="padding:14px 28px 22px;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.5;color:#9db3d4;text-align:center;">
18+ · Sorumlu oyun · Şartlar ve çevrim koşulları geçerlidir · Makrobet 2026
</td></tr>
</table></td></tr></table>
</body></html>""",
        "text_body": "Merhaba {{name}},\n\nMakrobet'e özel davetlisin. 3.000 TL deneme kasası + canlı promosyonlar.\n\nKayıt: https://makrovip.com/Vipmail\n\n18+ Makrobet",
    },
    {
        "name": '2026 · Pasif Üye Geri Getirme',
        "subject": '{{name}}, hesabın seni bekliyor — özel dönüş fırsatları',
        "html_body": """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hesabın seni bekliyor</title></head>
<body style="margin:0;padding:0;background:#040e1f;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;"><tr>
<td align="center" style="padding:10px 16px;font-family:Georgia,'Times New Roman',serif;font-size:12px;line-height:1.45;color:#fff;">
<span style="color:#ffd400;">⚠</span>&nbsp;Butonlar için <strong style="color:#ffd400;">Spam olmadığını bildir</strong> seçeneğine tıklayın.
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#040e1f;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#061c3d;border:1px solid #2a4a7a;border-radius:18px;overflow:hidden;">
<tr><td style="height:3px;background:#ffd400;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td align="center" style="padding:26px 28px 10px;"><img src="__MAIL_LOGO__" alt="Makrobet" width="176" style="display:block;margin:0 auto;border:0;max-width:176px;height:auto;"></td></tr>
<tr><td align="center" style="padding:0 28px 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#ffd400;">Seni özledik · geri dönüş</td></tr>
<tr><td align="center" style="padding:0 28px 12px;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.2;font-weight:700;color:#fff;letter-spacing:-0.02em;">Hesabın seni bekliyor</td></tr>

<tr><td style="padding:0 28px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#e6f0fe;">Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>Bir süredir görüşemedik. Dönüşünü kolaylaştırmak için <strong style='color:#ffd400;'>promosyonlar sayfasından</strong> seçtiğimiz en güçlü geri dönüş fırsatlarını derledik.</td></tr>
<tr><td style="padding:0 24px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">1</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">%100 Kayıp Bonusu</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Sıfır riskli güvence — yatırıma güvenle dön.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">2</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Happy Hours / Mutlu Saatler</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Seçili saatlerde her yatırıma ekstra sürpriz.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">3</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Makro Görev</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Günlük görevleri tamamla, Görev Kasa ödülünü kap.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">4</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Prim & Çevrim Bonusları</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Aktif dönem kampanyalarıyla bakiyeni güçlendir.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">5</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">VIP Club</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Sadakat avantajları ve özel destek hattı.</div>
</td>
</tr></table></td></tr></table></td></tr>
<tr><td align="center" style="padding:4px 24px 18px;"><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Makro Kasa</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Bilet Etkinliği</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Görev Bonusu</span></td></tr>
<tr><td align="center" style="padding:8px 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="display:inline-block;background:#ffd400;color:#061c3d;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;text-decoration:none;padding:14px 28px;border-radius:10px;letter-spacing:0.02em;">Hesabıma Dön</a>
</td></tr>
<tr><td align="center" style="padding:0 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;color:#ffd400;text-decoration:none;">Promosyonları incele →</a>
</td></tr>
<tr><td style="padding:14px 28px 22px;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.5;color:#9db3d4;text-align:center;">
18+ · Sorumlu oyun · Şartlar ve çevrim koşulları geçerlidir · Makrobet 2026
</td></tr>
</table></td></tr></table>
</body></html>""",
        "text_body": 'Merhaba {{name}},\n\nSeni özledik. %100 Kayıp, Happy Hours, Makro Görev ve VIP ile geri dön.\n\nhttps://makrovip.com/Vipmail\n\n18+ Makrobet',
    },
    {
        "name": '2026 · Memnuniyet Bonusu',
        "subject": '{{name}}, senin için memnuniyet jesti hazırladık',
        "html_body": """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Senin için ekstra bir jest yaptık</title></head>
<body style="margin:0;padding:0;background:#040e1f;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;"><tr>
<td align="center" style="padding:10px 16px;font-family:Georgia,'Times New Roman',serif;font-size:12px;line-height:1.45;color:#fff;">
<span style="color:#ffd400;">⚠</span>&nbsp;Butonlar için <strong style="color:#ffd400;">Spam olmadığını bildir</strong> seçeneğine tıklayın.
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#040e1f;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#061c3d;border:1px solid #2a4a7a;border-radius:18px;overflow:hidden;">
<tr><td style="height:3px;background:#ffd400;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td align="center" style="padding:26px 28px 10px;"><img src="__MAIL_LOGO__" alt="Makrobet" width="176" style="display:block;margin:0 auto;border:0;max-width:176px;height:auto;"></td></tr>
<tr><td align="center" style="padding:0 28px 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#ffd400;">Özel ilgi · memnuniyet</td></tr>
<tr><td align="center" style="padding:0 28px 12px;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.2;font-weight:700;color:#fff;letter-spacing:-0.02em;">Senin için ekstra bir jest yaptık</td></tr>
<tr><td align="center" style="padding:0 28px 18px;">
<table role="presentation" cellpadding="0" cellspacing="0" style="background:linear-gradient(180deg,#122a52 0%,#0a1f3d 100%);border:1px solid #ffd400;border-radius:14px;min-width:260px;">
<tr><td align="center" style="padding:18px 28px 6px;font-family:Georgia,'Times New Roman',serif;font-size:34px;line-height:1;font-weight:700;color:#ffd400;letter-spacing:-0.02em;">MEMNUNİYET</td></tr>
<tr><td align="center" style="padding:0 22px 16px;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#e6f0fe;">ÖZEL JEST</td></tr>
</table></td></tr>
<tr><td style="padding:0 28px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#e6f0fe;">Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>Yakın zamanda yatırımın oldu ancak çekim tarafında aksaklık yaşadıysan üzülme — <strong style='color:#ffd400;'>memnuniyet bonusun</strong> hesabına tanımlanıyor. Yanına da şu an sitede öne çıkan fırsatları ekledik.</td></tr>
<tr><td style="padding:0 24px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">1</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Memnuniyet Bonusu</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Çekim/deneyim aksamalarına özel jest — destekten talep et / hesabını kontrol et.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">2</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">%100 Kayıp Bonusu</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Riski Makrobet üstlensin, sen oyuna odaklan.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">3</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Happy Hours</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Yatırımına ek kasa / ekstra fırsat pencereleri.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">4</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Canlı Destek 7/24</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">vipmakro.com üzerinden hızlı çözüm.</div>
</td>
</tr></table></td></tr></table></td></tr>
<tr><td align="center" style="padding:4px 24px 18px;"><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Prim Bonusu</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Çevrim Bonusu</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">VIP Club</span></td></tr>
<tr><td align="center" style="padding:8px 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="display:inline-block;background:#ffd400;color:#061c3d;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;text-decoration:none;padding:14px 28px;border-radius:10px;letter-spacing:0.02em;">Bonusu Kontrol Et</a>
</td></tr>
<tr><td align="center" style="padding:0 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;color:#ffd400;text-decoration:none;">Promosyonları incele →</a>
</td></tr>
<tr><td style="padding:14px 28px 22px;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.5;color:#9db3d4;text-align:center;">
18+ · Sorumlu oyun · Şartlar ve çevrim koşulları geçerlidir · Makrobet 2026
</td></tr>
</table></td></tr></table>
</body></html>""",
        "text_body": 'Merhaba {{name}},\n\nYakın yatırım/çekim deneyimin için memnuniyet bonusun tanımlı. Ayrıca %100 Kayıp ve Happy Hours aktif.\n\nhttps://makrovip.com/Vipmail\n\n18+ Makrobet',
    },
    {
        "name": '2026 · Yeni Üye İlk Yatırım',
        "subject": '{{name}}, ilk yatırımın için özel başlangıç paketleri',
        "html_body": """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deneme bitti — asıl oyun şimdi başlıyor</title></head>
<body style="margin:0;padding:0;background:#040e1f;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;"><tr>
<td align="center" style="padding:10px 16px;font-family:Georgia,'Times New Roman',serif;font-size:12px;line-height:1.45;color:#fff;">
<span style="color:#ffd400;">⚠</span>&nbsp;Butonlar için <strong style="color:#ffd400;">Spam olmadığını bildir</strong> seçeneğine tıklayın.
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#040e1f;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#061c3d;border:1px solid #2a4a7a;border-radius:18px;overflow:hidden;">
<tr><td style="height:3px;background:#ffd400;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td align="center" style="padding:26px 28px 10px;"><img src="__MAIL_LOGO__" alt="Makrobet" width="176" style="display:block;margin:0 auto;border:0;max-width:176px;height:auto;"></td></tr>
<tr><td align="center" style="padding:0 28px 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#ffd400;">İlk adım · yatırım</td></tr>
<tr><td align="center" style="padding:0 28px 12px;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.2;font-weight:700;color:#fff;letter-spacing:-0.02em;">Deneme bitti — asıl oyun şimdi başlıyor</td></tr>

<tr><td style="padding:0 28px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#e6f0fe;">Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>Üyeliğin hazır. İlk yatırımını yapıp <strong style='color:#ffd400;'>promosyonlar sayfasındaki</strong> başlangıç paketlerini açmana tek adım kaldı.</td></tr>
<tr><td style="padding:0 24px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">1</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">İlk Yatırım Fırsatları</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Hoş geldin / yatırım bonuslarıyla güçlü başlangıç.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">2</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Happy Hours</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Mutlu saatlerde yatırımlara ekstra katkı.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">3</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Kripto Ultra Kasa</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Kripto yatır, havale çek — Ultra Kasa ödülü.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">4</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Makro Görev</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">İlk görevlerini tamamla, kasa ödüllerini biriktir.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">5</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">%100 Kayıp Güvencesi</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">İlk adımını daha rahat at.</div>
</td>
</tr></table></td></tr></table></td></tr>
<tr><td align="center" style="padding:4px 24px 18px;"><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Prim Bonusu</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Çevrim Bonusu</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Makro Kasa</span></td></tr>
<tr><td align="center" style="padding:8px 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="display:inline-block;background:#ffd400;color:#061c3d;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;text-decoration:none;padding:14px 28px;border-radius:10px;letter-spacing:0.02em;">İlk Yatırımı Yap</a>
</td></tr>
<tr><td align="center" style="padding:0 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;color:#ffd400;text-decoration:none;">Promosyonları incele →</a>
</td></tr>
<tr><td style="padding:14px 28px 22px;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.5;color:#9db3d4;text-align:center;">
18+ · Sorumlu oyun · Şartlar ve çevrim koşulları geçerlidir · Makrobet 2026
</td></tr>
</table></td></tr></table>
</body></html>""",
        "text_body": 'Merhaba {{name}},\n\nÜyeliğin hazır. İlk yatırım + Happy Hours, Kripto Ultra Kasa, Makro Görev.\n\nhttps://makrovip.com/Vipmail\n\n18+ Makrobet',
    },
    {
        "name": '2026 · Turnuva & Bilet Etkinlikleri',
        "subject": '{{name}}, Bilet · Amusnet · Manager Rolling seni bekliyor',
        "html_body": """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bu haftanın sahnesi senin</title></head>
<body style="margin:0;padding:0;background:#040e1f;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;"><tr>
<td align="center" style="padding:10px 16px;font-family:Georgia,'Times New Roman',serif;font-size:12px;line-height:1.45;color:#fff;">
<span style="color:#ffd400;">⚠</span>&nbsp;Butonlar için <strong style="color:#ffd400;">Spam olmadığını bildir</strong> seçeneğine tıklayın.
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#040e1f;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#061c3d;border:1px solid #2a4a7a;border-radius:18px;overflow:hidden;">
<tr><td style="height:3px;background:#ffd400;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td align="center" style="padding:26px 28px 10px;"><img src="__MAIL_LOGO__" alt="Makrobet" width="176" style="display:block;margin:0 auto;border:0;max-width:176px;height:auto;"></td></tr>
<tr><td align="center" style="padding:0 28px 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#ffd400;">Etkinlik arenası · 2026</td></tr>
<tr><td align="center" style="padding:0 28px 12px;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.2;font-weight:700;color:#fff;letter-spacing:-0.02em;">Bu haftanın sahnesi senin</td></tr>

<tr><td style="padding:0 28px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#e6f0fe;">Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>Sadece klasik bonus değil — <strong style='color:#ffd400;'>turnuva, bilet ve toplu etkinlikler</strong> ile ödül havuzlarına katıl. Takvimdeki öne çıkanlar:</td></tr>
<tr><td style="padding:0 24px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">1</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Bilet Etkinliği</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Etkinlik biletlerini topla, özel çekiliş / ödül turlarına gir.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">2</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Amusnet Yarışı</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">500.000₺ ödüllü yarış — liderlik için erken gir.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">3</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Manager Rolling</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Toplu rolling / manager etkinlikleriyle çarpanlı kazanç penceresi.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">4</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Makro Görev</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Günlük görevlerle etkinlik puanı ve kasa biriktir.</div>
</td>
</tr></table></td></tr><tr><td style="padding:0 0 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2d55;border:1px solid #2a4a7a;border-left:3px solid #ffd400;border-radius:10px;">
<tr>
<td width="40" valign="top" style="padding:14px 0 14px 14px;"><div style="width:26px;height:26px;border-radius:50%;background:rgba(255,212,0,0.12);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:26px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#ffd400;">5</div></td>
<td style="padding:13px 16px 13px 8px;">
<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:#ffd400;line-height:1.25;">Happy Hours</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9db3d4;line-height:1.45;margin-top:4px;">Etkinlik saatlerinde ekstra ivme.</div>
</td>
</tr></table></td></tr></table></td></tr>
<tr><td align="center" style="padding:4px 24px 18px;"><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Turnuva</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Makro Kasa</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">VIP Club</span><span style="display:inline-block;margin:3px 4px;padding:7px 11px;border-radius:999px;border:1px solid #2a4a7a;background:#0f2d55;color:#e6f0fe;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;">Görev Bonusu</span></td></tr>
<tr><td align="center" style="padding:8px 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="display:inline-block;background:#ffd400;color:#061c3d;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;text-decoration:none;padding:14px 28px;border-radius:10px;letter-spacing:0.02em;">Etkinliklere Katıl</a>
</td></tr>
<tr><td align="center" style="padding:0 28px 10px;">
<a href="{{link:sc:https://makrovip.com/Vipmail}}" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;color:#ffd400;text-decoration:none;">Promosyonları incele →</a>
</td></tr>
<tr><td style="padding:14px 28px 22px;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.5;color:#9db3d4;text-align:center;">
18+ · Sorumlu oyun · Şartlar ve çevrim koşulları geçerlidir · Makrobet 2026
</td></tr>
</table></td></tr></table>
</body></html>""",
        "text_body": 'Merhaba {{name}},\n\nBilet Etkinliği, Amusnet Yarışı, Manager Rolling ve Makro Görev bu hafta sahnede.\n\nhttps://makrovip.com/Vipmail\n\n18+ Makrobet',
    },
]


def seed_makrobet_2026_templates(conn, overwrite=True):
    """Eksik 2026 şablonlarını ekler; overwrite ile HTML günceller."""
    now = iso(utcnow())
    added = 0
    updated = 0
    for item in TEMPLATES:
        name = item["name"]
        exists = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (name,))
        if exists:
            if overwrite:
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
