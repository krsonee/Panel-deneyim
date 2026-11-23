# Mikromail SMTP — sabah nokta atışı

## Teşhis (gece testinden)

SMTP test: **tüm host/user 535**. Şifre uzunluğu 18 → panel şifreyi gönderiyor, Alibaba reddediyor.

Bu kod bug’ı değil; **credential / Alibaba hesap uyumsuzluğu**. Eski Makro panelde çalışan şifre `makropanel-db` içinde; Mikromail taze DB’ye taşınmadı veya Alibaba’da yeni set edilen şifre yanlış adrese/yanlış ürüne yazıldı.

---

## Yol A — En hızlı: Makro’daki çalışan SMTP’yi kopyala (önerilen)

1. Render → **makropanel-db** → Connect → **External Database URL** kopyala  
2. Render → **mikromail** service → **Shell** aç  
3. Çalıştır:

```bash
SOURCE_DATABASE_URL='BURAYA_MAKROPANEL_DB_URL' python scripts/copy_smtp_from_makropanel.py
```

4. Mikromail panel → Ayarlar → **SMTP test (login)**  
5. Yeşil olunca → 1 test kampanya

---

## Yol B — Alibaba’dan sıfır şifre (kopya işe yaramazsa)

1. Console: https://dm.console.alibabacloud.com/ (international) **veya** China hesabıysa ilgili dm console  
2. Sol: **Sender Addresses**  
3. Listede gerçekten `info@vipozelileti.com` var mı? Yoksa oluştur / onaylı mı bak  
4. O satırda **Set SMTP Password** → yeni şifre (not et)  
5. Üstte / hesapta **bölge (Region)** ne?
   - Hangzhou/CN → host `smtpdm.aliyun.com`
   - Singapore → `smtpdm-ap-southeast-1.aliyuncs.com`
   - Frankfurt → `smtpdm-eu-central-1.aliyuncs.com`
6. **10 dakika bekle**  
7. Mikromail Ayarlar:
   - User = **tam o sender adresi**
   - Password = yeni şifre (kutuya yaz, kaydet)
   - Host = bölgeye göre
   - Port `465`
8. Şifre kutusunda şifre dururken **SMTP test**

### Dikkat

- Alibaba **hesap login şifresi** ≠ DirectMail **SMTP password**
- `info@` şifresi set ettiysen User `noreply@` olamaz
- Domain NS/DNS 535’i açıklamaz (auth sunucu tarafı); ama gönderim sonrası spam/bounce için DNS gerekir

---

## 551 Main account unavailable (535 değil)

Hesap seviyesi blok: Alibaba DirectMail hesabının `UserStatus` değeri normal değil
(1 dondurulmuş, 2 borçlu, 4 dış gönderim kısıtlı/限制外发, 8 silinmiş). Şifre, host,
bölge veya sender adresi sorunu değil; başka host / başka domain denemek çözmez
(aynı hesaba bağlılar). Panel 551'de host denemeyi bırakır ve Alibaba Rapor
AccessKey'i varsa `DescAccountSummary` ile UserStatus'u hataya yazar.

1. DirectMail konsolu → **Overview / 概览** → Account Status. Normal değilse sebep bu.
2. 限制外发 ise aynı sayfada **Request Unblock / 申请解封** (tek hak). Tetikleyici
   genelde önceki gün ≥300 gönderimde geçersiz adres >%11, spam >%15 veya teslim %0,
   ya da seviye 1'de düşüş. Açıldıktan sonra listeyi scrub et, hacmi düşür.
3. Dondurulmuşsa self-servis yok → Alibaba destek bileti.
4. Shell: `python scripts/smtp_diag.py` (login + MAIL FROM, DATA yok) → 551 görürse
   çıkış kodu 3 ve API UserStatus satırı.

---

## Render env kontrol

`mikromail` ve `mikromail-worker` için **aynı** `MAILING_SECRET_KEY` olmalı (generateValue ayrı ayrı üretmesin).

---

## Başarı kriteri

SMTP test yeşil: `SMTP login OK · user=... @ host...`  
Sonra kampanya log: `sent` (failed/535 değil)
