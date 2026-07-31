# MAKROBET — Neden Küçüldü, Neden Büyümüyor, Ne Lazım?

**Tarih:** 31 Temmuz 2026  
**Kapsam:** MakroPanel P&L + Pronet + Dagur + CT + Bonus sheet + site UX + Telegram  
**Haziran 2026 altın veri seti** (paneller çapraz doğrulanmış)

---

## 0. Tek cümle teşhis

Site küçüldü çünkü **2025 sonbaharında pahalı trafikle hacim şişirildi, Ekim’de W/D patladı, kalitesiz üye eridi**; bugün büyüyemiyor çünkü **casino GGR’nin ~%60’ı bonus/indirime gidiyor** (özellikle VIP Anlık Kayıp) ve **ölçülü acquisition + sade ürün motoru yok**.

---

## 1. Panel üçgeni — Haziran 2026 gerçekleri

| Kaynak | Ne söylüyor | Rakam |
|--------|-------------|------:|
| **Dagur** Aktivite | Yatırım / Çekim | **108,25M / 93,84M** |
| **Dagur** | Toplam İndirim | **23,22M** |
| **Bonus Sheet** | Toplam bonus (May≈Haz) | **~23,5M** |
| **Bonus Sheet** | VIP Anlık Kayıp (Haz) | **15,70M** |
| **CT** Vendor Günlük | Casino GGR (gerçek bakiye) | **35,94M** |
| **CT** Gelir Raporu | Bakiyeden bahis / kazanılan | **1,043B / 1,004B** |
| **CT** Promosyon Gelir | Jackpot+FS+turnuva+cashdrop → reel | **4,75M** |
| **Dagur** | Spor GGR / spor stake | **~3,13M / 24,3M** |
| **P&L Excel** | Reklam (Haz) | **~544K** |
| **P&L Excel** | Pronet fatura | **~8,85M** |
| **P&L Excel** | Asıl net | **≈ −9,4M** |
| Site / TG | Promo URL / resmi TG | `/promotions` 404; TG ~11K |

### Kritik çapraz doğrulama

```
Dagur Casino GGR ≈ 36,0M
CT Vendor GGR     = 36,00M  ✓
CT Gelir (stake−win) ≈ 39,0M (iptal/timezone farkı, aynı hikâye)

Dagur İndirim 23,22M ≈ Sheet TOTAL 23,55M  ✓
CT Bonus cüzdan stake sadece ~1,0M
→ 23M’lik “bonus” CT bonus wallet değil; Makroz/indirim ile REEL bakiyeye basılıyor.
```

---

## 2. Neden küçüldü? (tarihsel)

| Dönem | Ne oldu | Sonuç |
|-------|---------|-------|
| Ağu–Eyl 2025 | Gerilla + SEO + Süperbonus + SMS saldırısı | Hacim şişti |
| **Eki 2025** | Yatırım **205,8M**, W/D **%94,7**, jackpot şoku, reklam/netdep **%19,7** | Asıl net **−20,4M** |
| Kas–Şub | Kalitesiz cohort churn | Dip **~102M** (−%50 zirveden) |
| Mar–May | Dalgalı toparlanma, sürdürülebilir motor yok | May 105M |
| **Haz 2026** | Yatırım **~109M** (hafif +), reklam kesildi, **bonus hâlâ 23,5M** | Asıl net **−9,4M** |

**Sonuç:** Küçülme “site kötü” değil; **büyüme tuzağı + marj çöküşü + cohort erimesi**.

---

## 3. Neden büyümüyor? (bugünün motor arızası)

### 3.1 Birim ekonomisi kırık (Haziran)

| Metrik | Değer | Yorum |
|--------|------:|-------|
| Net depozit | ~14,4M | Brüt hacim yanıltıcı |
| Casino GGR | ~36M | Ürün casino-dominant |
| Spor GGR | ~3,1M | Spor payı zayıf (~%8 GGR) |
| Bonus / yatırım | **%21,8** | Endüstri üstü yakma |
| VIP Anlık Kayıp / yatırım | **%14,5** | Tek kalem siteyi yer |
| Bonus / Casino GGR | **~%60** | GGR’nin çoğu iade |
| Bonus+CT promo / GGR | **~%72** | Jackpot/FS dahil |
| Bonus / net depozit | **~%163** | Net’in 1,6×’i hediye |
| GGR − bonus − promo − Pronet | **~1,9M** | Personel/OpEx öncesi neredeyse sıfır |

Bu tablo büyümeyi kilitleyen asıl sebeptir: **daha çok yatırım = daha çok VIP kayıp + aynı oranda indirim**. Hacim artsa bile net artmıyor.

### 3.2 Ürün / bonus mimarisi

1. **Üç kayıp katmanı** (%100 + %25 + gece %30) + VIP anlık + call kayıp + yatırım bonusları  
2. **Makroz VIP Anlık Kayıp 15,7M** — Haziran’da Mayıs’tan **+1,95M** arttı  
3. Yatırım bonusları May→Haz **2,99M → 1,14M** düştü; yani acquisition bonusları kesildi ama **retention kayıp makinesi büyüdü**  
4. CT’de bonus wallet neredeyse boş → maliyet görünmez “indirim” olarak geliyor  
5. Site kataloğu kalabalık; `/tr/promotions` **404**; talep çoğu manuel livechat

### 3.3 Funnel / kanal

| Katman | Durum |
|--------|-------|
| Acquisition | Ölçülmeyen affiliate/influencer geçmişi; Haziran’da reklam kesildi ama **FTD motoru kurulmadı** |
| Activation | VIP uzak, onboarding zayıf, promo karmaşık |
| Retention | Nakit kayıp iadesi = pahalı bağımlılık |
| Referral / owned | TG ~11K; duyuru panosu, büyüme kanalı değil |
| Mix | Casino %90+; spor/crypto ölçeklenmiyor |

### 3.4 Ops / güven

- Domain rotasyonu + bakım duyuruları → bookmark/güven kaybı  
- TG ↔ site rakam tutarsızlığı  
- Destek üzerinden bonus = ölçek düşmanı  

---

## 4. “Büyümek için ne lazım?” — Proje planı

Hedef formül:

> **Daha az kanal × ölçülü FTD × sade bonus × otomasyon × owned media × spor/crypto mix**  
> Hacim değil: **kaliteli net depozit + pozitif asıl net**.

### FAZ 0 — 0–14 gün (kanamayı durdur)

| # | Proje | Sahip | KPI |
|---|-------|-------|-----|
| P0.1 | VIP Anlık Kayıp tavanı / oran kesimi (hedef: yatırımın ≤%8) | Bonus + Makroz | VIP kayıp ≤ 8,5M |
| P0.2 | %100 kayıp → VIP-only veya askı; tek kayıp katmanı = %25 | CRM | Call+%100 kayıp ↓ |
| P0.3 | `/tr/promotions` → redirect; TG–site rakam senkron | Site | 0 broken promo |
| P0.4 | Günlük war-room: W/D, indirim, net dep, casino GGR | Ops | W/D alarm ≥%85 |
| P0.5 | Jackpot/FS promosyon tavanı (aylık) | CT | Promo reel ≤ 3M |
| P0.6 | Reklamsız ayda bile FTD tracking aç (Smartico) | Growth | FTD by source |

**Beklenen etki (30 gün):** Bonus/yatırım %22 → ≤%14; asıl net −9M → −3M bandı (henüz kâr şart değil).

### FAZ 1 — 15–45 gün (funnel onar)

| # | Proje | KPI |
|---|-------|-----|
| P1.1 | Bonus otomasyonu: kayıp/yatırım talebinin %80’i botsuz | Ticket ↓, SLA &lt;5 dk |
| P1.2 | Tek hoş geldin + tek kayıp + VIP ladder (katalog sade) | Promo claim confusion ↓ |
| P1.3 | Affiliate/CPA renegotiate (Süperbonus hibrit) | Cost/FTD |
| P1.4 | VIP Bronze 7 günde ulaşılır mikro ödül | D7 retention |
| P1.5 | SMS/mailing tavan + kampanya ROI | SMS ROI &gt;1 |
| P1.6 | CT churn skoru + Dagur inaktif → Smartico winback | Reactivation FTD |

### FAZ 2 — 45–90 gün (büyüme motoru)

| # | Proje | KPI |
|---|-------|-----|
| P2.1 | Spor paketi: Multibet + Rolling + MakroTV (tek funnel) | Spor GGR payı %8→%15 |
| P2.2 | Referral 2.0 = ana organic motor | Organic FTD % |
| P2.3 | Telegram 11K→50K: değer içeriği, unique deep-link | TG FTD |
| P2.4 | Meta/Google sadece retarget + lookalike | Paid CAC |
| P2.5 | Provider karlılık: negatif GGR oyun/sağlayıcı kısıt | Provider ROI |
| P2.6 | Kripto payı + Ultra Kasa (ödeme mix) | Crypto deposit % |

### FAZ 3 — 90–180 gün (ölçek)

- Segmentli CRM (VIP / churn / sportsbook / slot whale)  
- Aylık bonus budget = **Casino GGR × %35 tavan** (şu an ~%60)  
- Acquisition sadece pozitif LTV kanallar  
- Hedef: yatırım 140–160M bandı **ve** asıl net ≥ 0  

---

## 5. Tut / Kes / Dönüştür matrisi

| Karar | Kalem | Neden |
|-------|-------|-------|
| **KES / TAVAN** | VIP Anlık Kayıp (15,7M) | Büyümenin #1 freni |
| **DÖNÜŞTÜR** | %100 Call/Kayıp | VIP veya kampanya; herkese değil |
| **TUT + SADE** | %25 kayıp (tek katman) | Öngörülebilir retention |
| **TUT** | Görev + VIP ladder + Referral | Kontrollü LTV |
| **TUT** | Kripto %5 / Ultra Kasa | Ödeme diversifikasyonu |
| **KISITLA** | Jackpot + sınırsız FS win (4,75M) | Marj sızıntısı |
| **ÖLÇ VEYA KES** | Influencer / tek seferlik deal | FTD yoksa para yok |
| **YENİDEN YAP** | Süperbonus | CPA/RevShare |

---

## 6. 90 günlük sayısal hedef kartı

| KPI | Haz 2026 (bugün) | 90 gün hedef |
|-----|-----------------:|-------------:|
| Yatırım | ~109M | 130–145M |
| W/D | ~%87 | ≤%82 |
| Bonus / yatırım | %21,8 | ≤%14 |
| VIP Anlık / yatırım | %14,5 | ≤%8 |
| Casino GGR | ~36M | ≥40M |
| Spor GGR payı | ~%8 | ≥%15 |
| Asıl net | −9,4M | ≥ 0 |
| TG resmi | ~11K | ≥30K |
| FTD by source | eksik | %100 kapsama |

---

## 7. Panellerden çıkan operasyonel gerçek (sistem haritası)

```
Üye parası / spor     → Dagur (ps.pgbo.io)
Casino oyun / GGR     → CT (ct.pgbo.io)
Casino VIP / indirim  → Makroz Bonus Bot  ← asıl maliyet burada
P&L / Pronet / muhasebe → MakroPanel
CRM / FTD / segment   → Smartico (canlı API şart)
Owned media           → Telegram + mail
```

**Analiz boşluğu (bilinçli):** Smartico canlı FTD zaman serisi bu oturumda çekilmedi (local boş). Büyüme motorunu kilitlemek için **haftalık FTD by affiliate** Smartico’dan bağlanmalı — teşhis için zorunlu değildi; icra için zorunlu.

---

## 8. Yönetici kararları (bu hafta)

1. **VIP Anlık Kayıp oranını hemen düşür** (en yüksek ROI’li tek hareket).  
2. **%100 kayıp + çift kayıp katmanlarını kapat / VIP’e al.**  
3. **Bonus budget = GGR’nin max %35’i** kuralını yaz ve Makroz’a uygula.  
4. **FTD dashboard** (Smartico) açmadan yeni marketing harcama yok.  
5. **Promo URL + TG senkron + domain sticky** — güven sızıntısını durdur.  

Bunlar yapılmadan “daha çok reklam / daha çok affiliate” sadece **daha hızlı zarar** üretir.
