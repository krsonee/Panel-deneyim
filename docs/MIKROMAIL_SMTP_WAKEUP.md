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

Panel tüm bölge host'larını dener ve hata mesajında **her host'un** cevabını yazar.
Alibaba ek kodları (Kasım 2026 gözlemi):

- `535 [@ud010301]` → bu bölgede sender adresi tanımlı değil (normal, diğer bölgeler için)
- `535 [@ud010201]` → sender bu bölgede var, SMTP şifresi yanlış
- `551 Main account unavailable [@ud010102]` → sender tanınıyor ama o bölgede gönderime kapalı

551 veren host'un bölgesinde (vipozelileti.com için Singapur) kontrol:

1. **Sender Addresses** → adres satırı durumu (normal/dondurulmuş), gerekirse **Set SMTP Password** + 10 dk.
2. **Email Domains** → domain `Verified` mi (SPF/DKIM/ownership TXT değişmiş olabilir → Verify).
3. **Overview** → Account Status. Normal değilse 限制外发 → **Request Unblock / 申请解封** (tek hak).
4. Shell: `python scripts/smtp_diag.py` (login + MAIL FROM, DATA yok) — login'de mi zarfta mı 551
   geldiğini ve Alibaba Rapor AccessKey'i varsa API UserStatus'u gösterir; 551'de çıkış kodu 3.

---

## Render env kontrol

`mikromail` ve `mikromail-worker` için **aynı** `MAILING_SECRET_KEY` olmalı (generateValue ayrı ayrı üretmesin).

---

## Başarı kriteri

SMTP test yeşil: `SMTP login OK · user=... @ host...`  
Sonra kampanya log: `sent` (failed/535 değil)
