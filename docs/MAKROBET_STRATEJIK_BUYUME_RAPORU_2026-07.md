# MAKROBET — Stratejik Büyüme, Gerileme ve Yol Haritası Raporu

**Rapor tarihi:** 31 Temmuz 2026  
**Kapsam:** Slack hariç tam denetim (finans + site UX + bonus + Telegram + kanal stratejisi)  
**Kaynaklar:** MakroPanel P&L (Haz 2025–May 2026), Pronet hacim (Tem 2025–Haz 2026), canlı site `makrobet808.com` (test kullanıcı `krsone`), Telegram `@makrobet` / `@makrobetofficial`, mailing şablonları

---

## 0. Yönetici Özeti — Tek Cümle

Yatırımlar düştü çünkü **Ağustos–Kasım 2025’te pahalı, ölçülmeyen trafikle hacim şişirildi; Ekim’de W/D %94,7 ile marj çöktü; sonrasında kalitesiz üye tabanı eridi ve bugün ürün/bonus karmaşası + kanal bağımlılığı büyümeyi kilitlemiş durumda.**

| Gösterge | Zirve | Dip / Son | Değişim |
|----------|------:|----------:|--------:|
| Aylık yatırım | 205,8M (Eki 2025) | 102,1M (Şub 2026) / 105,2M (May 2026) | **−%50** |
| W/D oranı | %81,5 (Haz 2025) | **%94,7 (Eki 2025)** → %82 (May) | Kriz ayı |
| Asıl net (en kötü) | +2,97M (Haz) | **−20,4M (Eki 2025)** | Operasyonel şok |
| Reklam / net depozit | %1,9 (Haz) | **%19,7 (Eki)** | 10× verimsizlik |
| Pronet GGR hacim | 64,7M (Eyl) | 41,6M (Haz 2026) | **−%36** |
| TG resmi kanal | — | ~11.108 abone (`@makrobetofficial`) | Zayıf ölçek |

---

## 1. Neden Yatırımlar Düştü? (Kök Neden Ağacı)

### 1.1 Birincil neden: “Büyüme tuzağı” → kalite çöküşü

```
Ağu–Eyl 2025: Agresif harcama (gerilla + SEO + Süperbonus + SMS)
        ↓
Eki 2025: Yatırım zirve AMA W/D %94,7 + jackpot 6,1M + asıl net −20M
        ↓
Kas–Şub: Hacim −%17 → −%23 → −%12 → dip 102M (kalitesiz üye churn)
        ↓
Mar–May 2026: Dalgalı toparlanma (Mart +%31) ama sürdürülemedi (May −%18)
```

**Kanıt — aylık momentum:**

| Ay | Yatırım | Momentum | W/D | Asıl Net | Reklam/NetDep |
|----|--------:|---------:|----:|---------:|--------------:|
| 2025-08 | 198,4M | **+%33** | 84% | −5,2M | 6,1% |
| 2025-10 | 205,8M | +%12 | **95%** | **−20,4M** | **19,7%** |
| 2025-12 | 130,2M | −%23 | 75% | +6,9M | 4,8% |
| 2026-02 | 102,1M | −%12 | 80% | −2,0M | 5,2% |
| 2026-04 | 128,0M | −%4 | **73%** | +5,9M | 4,2% |
| 2026-05 | 105,2M | −%18 | 82% | −3,2M | 5,1% |

**Yorum:** Ekim’de “yatırım arttı” yanılsaması var; gerçekte para **çekime kaçtı**. Aralık–Nisan’da W/D düzelince kâr geldi; Mayıs’ta tekrar bozuldu → büyüme motoru yok, sadece dalgalanma var.

### 1.2 İkincil nedenler (birlikte çalışıyor)

| # | Kök neden | Kanıt | Etki |
|---|-----------|-------|------|
| 1 | **Ölçülmeyen marketing** | CanBequit 834K, Gerilla ~1,45M, Google SEO 841K/ay — FTD/CPA yok | Para yanıyor, üye kalitesi belirsiz |
| 2 | **Jackpot / bonus sızıntısı** | Eki–Kas jackpot ~12,3M; Botto oto bonus 441K (Şub) | Marj erozyonu |
| 3 | **Kanal bağımlılığı** | Süperbonus tek başına 12 ayda ~4,6M (super+süper) | Tek kanal riski |
| 4 | **SMS/mailing patlaması** | 12 ayda ~6,6M SMS/data/mailing | Acquisition maliyeti şişti |
| 5 | **Ürün karmaşası** | 18+ paralel promo + menü kalabalığı | Yeni üye ne yapacağını bilmiyor |
| 6 | **Domain rotasyonu** | TG: “Domain güncellendi → makrobet808” | Güven + bookmark kaybı |
| 7 | **Bakım kesintileri** | TG’de planlı bakım duyuruları | Anlık churn / güven kırığı |

### 1.3 “Neden artık büyüyemiyor?” — teşhis

Büyüme durdu çünkü şu döngü kırılmadı:

1. **Acquisition** pahalı ve ROI’siz (reklam/net_dep Ekim’de %20)  
2. **Activation** zayıf (VIP Bronze’a %0,85 — test hesapta bile ilerleme yok; onboarding zayıf sinyal)  
3. **Retention** bonus odaklı ama şartlar ağır / manuel talep (canlı destek)  
4. **Revenue** W/D volatil; kaliteli net depozit ayları rastgele  
5. **Referral** “Arkadaşını getir” var ama ürün karmaşık → viral yayılım zayıf  

Bu bir **funnel hastalığı**, sadece “daha çok reklam” ile çözülmez.

---

## 2. Site Tasarımı & Arayüz Denetimi (Canlı UX)

**Ortam:** `https://makrobet808.com/tr/` — girişli test (`krsone`, bakiye 0,43₺)

### 2.1 Güçlü yanlar
- Koyu tema + sarı CTA endüstri standardı; okunabilir
- Casino / Spor toggle net
- Canlı destek (LiveChat) her sayfada
- VIP, Görev, Kasa, TV, News gibi **loyalty stack** mevcut
- App indirme (iOS/Android/Huawei) footer’da

### 2.2 Kritik UX sorunları (üye kaçıran)

| Sorun | Gözlem | Risk |
|-------|--------|------|
| **Promosyon URL kırığı** | `/tr/promotions` → **404** (“Hata, o sayfa gitmiş”) | Menüden beklenen rota kırık; SEO/bookmark kaybı |
| **Doğru rota gizli** | Çalışan URL: `/tr/pages/promotions` | Tutarsız routing = güven erozyonu |
| **Menü kalabalığı** | Anasayfa + Promosyonlar + Promokod + VIP + Görev + Kasa + TV + News + Bilet + Win-Win | İlk 5 sn’de karar felci |
| **Ana sayfada hero promo yok** | İlk viewport: VIP ilerleme + slot grid; agresif bonus banner yok | Conversion fırsatı kaçıyor |
| **Bildirim şişkinliği** | 10 bildirim + 1 hediye badge, bakiye 0,43₺ | Spam hissi / güvensizlik |
| **VIP ilerleme soğuk** | Bronze’a %0,85 — “uzak hedef” algısı | Retention motivasyonu düşük |
| **Oyun arama readonly** | Snapshot’ta search `readonly` göründü | Keşif sürtünmesi |

### 2.3 UX hükmü

Site **teknik olarak modern bir white-label casino iskeleti**; sorun “çirkinlik” değil. Sorun:

> **Çok ürün, zayıf hiyerarşi, kırık deep-link, ilk yatırım yolculuğu belirsiz.**

Büyüme için UI’yi “yeniden tasarlamak” değil; **yolculuğu sadeleştirmek** gerekir.

---

## 3. Bonus & Etkinlik Envanteri (Canlı Promosyonlar)

### 3.1 Aktif katalog (site)

| Promo | Tip | Stratejik rol |
|-------|-----|---------------|
| %100 Kayıp Bonusu | Retention / risk-hedge | Yüksek maliyet riski |
| %25 Kayıp Bonusu | Recurring retention | Sürekli marj baskısı |
| Gececilere %30 Kayıp | Gece segment | Niş, ölçülmeli |
| Makro Görev | Gamification | İyi yön — güçlendir |
| Arkadaşını Getir | Viral / acquisition | Ölçeklenebilir |
| Kripto yatır → Ultra Kasa 10K | Payment mix | İyi — kripto payını artırır |
| Kripto %5 nakit ilave | Payment mix | İyi |
| 100K Bilet Etkinliği | Engagement | Ödül enflasyonu riski |
| 50K Nakit Rolling | Spor engagement | Niş |
| Temmuz 250K Win-Win | Tournament | Tarihli — bitiş yönetimi |
| Seviye Atlama / Prim / Çevrim | VIP ladder | Retention omurgası |
| %100 Multibet Spor | Spor acquisition | Spor’u büyütür |
| VIP Club Kasa | Loyalty | İyi |
| Pro Club Jackpot | High-roller | Jackpot riski (Eki kanıtladı) |
| Doğum Günü | Soft retention | Düşük maliyet |
| Makro Call Center | FTD IVR | Ölçülebilir kanal |
| Sosyal Medya Etkinlikleri | Community | TG ile bağlanmalı |

### 3.2 Derin inceleme: %100 Kayıp Bonusu (`post=53`)

| Madde | Değer | Analiz |
|-------|-------|--------|
| Geçerlilik | 26.06.2026 13:00 sonrası | Yeni |
| Kullanım | **1 kez / üye** | İyi sınır |
| Min / Max yatırım | 100₺ / 10.000₺ | Alt bariyer düşük → abuse |
| Süre | 3 gün | OK |
| Casino | Sadece **Pragmatic Play slot**, **×3 çevrim**, max çekim **bonus×10** | Dar oyun seti = şikayet riski |
| Spor | ×3 çevrim, min 2’li, oran ≥1.80 | Standart |
| Talep | **Canlı destek manuel** | Ölçek düşmanı; destek yükü |
| Çekim | Bonus varken **tam bakiye çekim zorunlu** | Kullanıcı düşmanı kural |
| Çakışma | Yatırım bonuslu yatırımlarda geçersiz | Karmaşa |

**Getiri / götürü hükmü:**  
Pazarlama dili “sıfır risk” — bu **FTD vaadi gibi satılıyor ama aslında kayıp iadesi**. Üye beklentisi şişiyor → destek çatışması + bonus maliyeti. Ekim tipi W/D krizlerinde bu tip kayıp bonusları **yangına körük** olur.

### 3.3 Bonus mimarisi sorunu

Şu an paralel çalışan **3 kayıp katmanı** var (%100 + %25 + gece %30) + VIP + görev + kasa + turnuva + rolling + jackpot.

Bu yapı:
- **Maliyet öngörülemez**
- **Üye “hangisini alayım?” diye kaybolur**
- **Bonus hunter** çeker, LTV’li oyuncu değil

**Öneri mimari (sade):**

```
1. Hoş geldin (tek net teklif)
2. Kayıp (tek katman: %25 veya %30 — %100’ü VIP’e özel kıl)
3. VIP ladder (seviye/prim/çevrim)
4. Haftalık 1 etkinlik (turnuva VEYA bilet — ikisi birden değil)
5. Referral (arkadaş getir)
```

---

## 4. Telegram Analizi

### 4.1 Kanallar
| Kanal | Abone | Rol |
|-------|------:|-----|
| `@makrobetofficial` | **11.108** | Resmi — düşük ölçek |
| `@makrobet` | (preview aktif) | Operasyonel duyuru / promo push |
| `t.me/makrobetchat` | — | Sohbet |
| Güncel giriş | `b.link/sosyal` | Cloak/rotasyon |

### 4.2 İçerik kalıbı (son postlar — `@makrobet`)

Tekrarlayan şablon:
1. Bonus duyurusu (kayıp / kripto / görev / rolling / bilet)
2. Maç / MakroTV yönlendirme
3. Domain güncelleme
4. Bakım başlangıç / bitiş
5. Alt limit / kripto yöntem duyurusu
6. Her postta aynı footer: Güncel Giriş + VIP Destek + Mobil App

**Etkileşim bandı (görünen reaksiyonlar):** tipik **15–40 reaksiyon / post**.  
11K abonelik için bu **düşük–orta**; viral değil, “duyuru panosu”.

### 4.3 Telegram uyumluluk sorunları

| Sorun | Kanıt | Etki |
|-------|-------|------|
| Emoji / şablon spam | Her postta uzun 〽️ zinciri | Profesyonellik düşüyor |
| Aynı footer her postta | 3 CTA tekrar | CTA yorgunluğu |
| Domain değişim postları | makrobet808 duyurusu | Güven kırığı |
| Bakım duyuruları | Planlı bakım + “tamamlandı” | Kesinti algısı |
| Promo–site senkron | TG’de 250K bilet / sitede 100K bilet | **Mesaj tutarsızlığı** |
| Ölçek | 11K resmi abone | Marketing bütçesine göre çok küçük |

### 4.4 Telegram hükmü

Telegram **satış kanalı değil, bakım/duyuru kanalı** gibi çalışıyor.  
Büyüme için: içerik %70 eğlence/değer (oran, makroTV, kazanan hikaye), %30 soft CTA; emoji şablonunu öldür; abone hedefi 50K+; her kampanyada unique deep-link + FTD ölçümü.

---

## 5. Finansal Gerçeklik — Kanal ve Maliyet

### 5.1 12 aylık reklam harcama (P&L etiket agregasyonu)

| Kanal / kalem | ~12 ay toplam |
|---------------|--------------:|
| Süperbonus (super+süper) | **~4,6M TL** |
| Meta | ~2,3M |
| SEO | ~1,7M |
| Gerilla | ~1,5M |
| Google Ads | ~1,1M |
| Bahisno1 | ~0,86M |
| CanBequit (tek ay!) | **0,83M** |
| Telegram (etiketli) | ~0,56M |
| SMS/Data/Mailing (tüm gider) | **~6,6M** |

### 5.2 Verimsizlik zirvesi
- **Ekim 2025:** Reklam / net depozit = **%19,7** (Haziran’da %1,9 idi)
- Aynı ay W/D %94,7 → **parayı basıp kaybettiniz**

### 5.3 Pronet ürün karması
- Dominant: **Pragmatic Play** (her ay #1)
- Canlı: Evolution / Pragmatic Live
- Jackpot katkıları (Amusnet, EGTD, Pro Club) Eki–Kas’ta marjı ezdi

**Sonuç:** Slot-ağır trafikte bonus + jackpot birleşince W/D patlıyor. Spor payını artırmak (Multibet, Rolling) stratejik olarak doğru ama şu an katalogda boğuluyor.

---

## 6. Üyeyi Kaçıran Aktif Hareketler (Churn Drivers)

Öncelik sırasıyla:

1. **Domain rotasyonu + 404 promo linki** → “site kaçıyor / sahte” algısı  
2. **Manuel bonus talep (canlı destek)** → bekleme + tartışma  
3. **Ağır çekim kuralı** (bonus varken full balance çekim zorunlu)  
4. **Çoklu kayıp bonus + karmaşık şart** → hayal kırıklığı  
5. **Jackpot / yüksek volatility slot baskınlığı** → hızlı kayıp hissi  
6. **Bildirim spam + bakım duyuruları** → yorgunluk  
7. **VIP’in uzak görünmesi** (Bronze %0,85) → “burada ödül yok”  
8. **Ölçülmeyen affiliate/influencer trafiği** → bonus hunter oranı yüksek  

---

## 7. Ne Yaparsak Tekrar Büyürüz? — Yol Haritası

### FAZ 0 — Acil (0–14 gün) “Kanamayı durdur”

| # | Aksiyon | KPI |
|---|---------|-----|
| 1 | `/tr/promotions` 404’ü düzelt → `/pages/promotions` redirect | 0 broken promo link |
| 2 | Ana sayfa hero = **tek teklif** (Hoş geldin VEYA %25 kayıp — ikisi değil) | Hero CTR |
| 3 | %100 kaybı **VIP-only** veya askıya al; varsayılan kayıp = %25 | Bonus cost / deposit ↓ |
| 4 | W/D günlük dashboard; eşik **%85** kırmızı | Erken uyarı |
| 5 | CanBequit / Gerilla tipi tek seferlik harcamaya **FTD zorunlu rapor** | CPA bilinir |
| 6 | TG footer sadeleştir; domain duyurusunu sticky pin | Engagement rate ↑ |
| 7 | Jackpot exposure aylık tavan (ör. 2M TL) | Jackpot/Net ≤ limit |

### FAZ 1 — 30 gün “Funnel onar”

| # | Aksiyon | KPI |
|---|---------|-----|
| 8 | İlk yatırım yolu: kayıt → 1 bonus → 1 oyun → 1 çekim eğitimi (3 adım) | FTD conversion |
| 9 | Bonus taleplerinin %80’ini **otomatikleştir** (Botto denetimli) | Destek ticket ↓ |
| 10 | Smartico haftalık: kayıt / FTD / deposit / bonus by affiliate | Channel ROI |
| 11 | Süperbonus renegotiate: sabit ücret → **CPA / RevShare hibrit** | Cost/FTD ↓ |
| 12 | SMS tavanı: ay max 300K TL + kampanya ROI | SMS ROI > 1 |
| 13 | VIP Bronze’u 7 günde ulaşılabilir yap (mikro ödüller) | D7 retention |

### FAZ 2 — 60–90 gün “Büyüme motoru”

| # | Aksiyon | KPI |
|---|---------|-----|
| 14 | Spor payını artır: Multibet + Rolling + MakroTV paket | Spor GGR % |
| 15 | Referral programını ana büyüme motoru yap (Arkadaş Getir 2.0) | Organic FTD % |
| 16 | Telegram 11K → 50K: günlük değer içeriği + unique aff link | TG FTD |
| 17 | Meta/Google yalnızca **retargeting + lookalike**; cold traffic affiliate’e | Paid CAC |
| 18 | Haftalık 1 büyük etkinlik (turnuva **veya** bilet) | Event → deposit |
| 19 | Pronet provider karlılık: negatif GGR sağlayıcıları kısıtla | Provider ROI |
| 20 | Call Center / IVR FTD’yi Smartico ile bağla | IVR FTD cost |

---

## 8. Hangi Bonuslar / Operasyonlar / Kanallar?

### 8.1 BONUS — Tut / Kes / Dönüştür

| Karar | Bonus | Neden |
|-------|-------|-------|
| **TUT + GÜÇLENDİR** | Makro Görev + VIP ladder + Arkadaş Getir | Retention + viral, maliyet kontrol edilebilir |
| **TUT (sadeleştir)** | %25 Kayıp | Standart retention; tek kayıp katmanı olsun |
| **DÖNÜŞTÜR** | %100 Kayıp | VIP-only veya ayda 1 kampanya; “herkese sıfır risk” mesajını kes |
| **TUT** | Kripto %5 + Ultra Kasa | Ödeme mix; havale baskısını azaltır |
| **TUT (tek sefer/hafta)** | Win-Win / Bilet / Rolling | Aynı anda 3’ü çalışmasın |
| **KISITLA** | Pro Club Jackpot | Eki–Kas kanıtladı: marj katili olabilir |
| **ÖLÇ** | Call Center ilk yatırım | IVR maliyeti yüksek; FTD yoksa kes |

### 8.2 OPERASYON — Zorunlu disiplin

1. Her marketing kalemi >100K TL → **önceden FTD hedefi + post-rapor**  
2. Bonus değişiklikleri → TG + site **aynı gün aynı rakam**  
3. Domain değişimi → 7 gün önceden duyuru + eski domain redirect  
4. Günlük W/D + bonus cost + net dep war-room (15 dk)  
5. Destek: bonus talebi SLA < 5 dk veya otomasyon  

### 8.3 KANAL — Anlaşma matrisi

| Öncelik | Kanal | Model | Not |
|---------|-------|-------|-----|
| **A — Yeniden pazarlık** | Süperbonus | CPA/RevShare hibrit, sabit düşür | 12 ay ~4,6M — en büyük bağımlılık |
| **A — Tut ama ölç** | Bahisno1 | Aylık + FTD KPI | Sabit ödemeyi performansa bağla |
| **A — Tut** | Meta retargeting | Haftalık kredi + ROAS>1.5 | Cold traffic azalt |
| **B — Kes / dondur** | CanBequit tipi tek seferlik | Yok / sadece pilot | 834K tek ay = kabul edilemez |
| **B — Yeniden tasarım** | Gerilla | Şehir aktivasyonu sadece marka haftası | FTD attribution yoksa yapma |
| **B — SEO** | Google SEO anlaşması | Organic ranking KPI | 841K/ay ölçülmeden devam etmesin |
| **C — Büyüt** | Telegram organik + aff | Deep-link FTD | 11K çok küçük |
| **C — Büyüt** | Arkadaş Getir / mailing CRM | Owned media | En ucuz ölçek |
| **C — Tut** | Forumbahis / Pawn / küçük TG | Küçük sabit + aff | Portfolio çeşitliliği |
| **D — Pilot** | Papiboy / Kocaburun tipi publisher | Sabit→performans | Tek seferlik ROI raporu |

**Kural:** Sabit ücretli kanalın devam şartı = **aylık min FTD + min net deposit**. Yoksa kes.

---

## 9. 90 Günlük Hedef Skor Kartı

| Metrik | Bugün (May yakını) | 30 gün | 90 gün |
|--------|-------------------:|-------:|-------:|
| Aylık yatırım | ~105M | 120M | **150M+** |
| W/D | ~82% | ≤80% | **≤78%** |
| Reklam / net depozit | ~5% | ≤4% | **≤3,5%** |
| Asıl net | −3,2M (May) | ≥0 | **+3M+** |
| TG resmi abone | 11K | 20K | **50K** |
| Aktif paralel “büyük” promo | 8+ | 4 | **3** |
| Promo 404 / kırık link | Var | 0 | 0 |

---

## 10. Eksik Veri — Senden İstediğim Dosyalar

Bu rapor **finans + canlı site + TG** ile %85 tamam. Aşağıdakiler gelirse FTD/churn’ü isim bazlı kilitleyebilirim:

1. **Smartico / affiliate aylık export** (Haz 2025–bugün): kayıt, FTD, deposit, withdraw, bonus by affiliate  
2. **Bonus maliyet raporu** (aylık verilen bonus TL + çevrim tamamlanma %)  
3. **Çekim SLA** (ortalama onay süresi, red oranı)  
4. **Canlı destek ticket özeti** (top 20 şikayet kodu)  
5. **Telegram Analytics** (view / join / click — son 90 gün)  
6. **P&L Haziran 2026** (Pronet Haziran var, P&L Mayıs’ta bitiyor)  
7. Aktif affiliate sözleşme listesi (sabit / CPA / RevShare)

Excel veya Google Docs linki yeterli.

---

## 11. Sonuç Hükmü

Makrobet’in sorunu “bonus yok” veya “site çirkin” değil.

Sorun üçlü:

1. **2025 Q3–Q4’te ölçülmeden büyümek** (Ekim katastrofu)  
2. **2026’da ucuz owned growth’a geçememek** (TG 11K, referral zayıf, SMS/SEO pahalı)  
3. **Ürünün fazla vaat / fazla kural** ile üyeyi yorması (%100 kayıp + manuel talep + domain rotasyonu)

**Tekrar büyümek için formül:**

> Daha az kanal × ölçülen FTD × sade bonus × otomatik ops × owned media (TG + referral + mail) × spor/kripto mix

---

*Hazırlayan: Makrobet Operasyon / Finans Analiz AI — Slack hariç tam kapsam*  
*Dosya: `docs/MAKROBET_STRATEJIK_BUYUME_RAPORU_2026-07.md`*
