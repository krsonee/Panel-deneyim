# 🎰 Casino & Spor Bahis Medya Üretim Botu

Bu proje, **Telegram** üzerinden çalışan, Pragmatic Play tarzı (Sweet Bonanza, Gates of
Olympus benzeri) premium casino görselleri ve spor bahis görselleri/animasyonları/sticker'ları
üreten bir bot **iskeletidir (scaffold)**.

Bu README, hiç Python/terminal deneyimi olmayan biri için **tıklama tıklama, komut komut**
yazılmıştır. Aşağıdaki adımları sırasıyla takip edersen bot bilgisayarında çalışır hale gelir.

> ⚠️ **Önemli:** Bu iskelet, görsel/video üretimi için OpenAI (DALL·E 3) ve
> Luma/Runway gibi ücretli servisleri kullanır. Gerçek API key'leri girmeden bot
> çalışır, menülerde gezersin, ama "Üret" dediğin anda "Bu servis henüz
> yapılandırılmadı" mesajı görürsün — bu normaldir, key'leri ekleyince otomatik
> düzelir (aşağıda "5. Adım"da anlatılıyor).

---

## İçindekiler

1. [Gereken programlar](#1-gereken-programlar)
2. [Proje klasörünü bilgisayarına alma](#2-proje-klasörünü-bilgisayarına-alma)
3. [Sanal ortam (venv) kurulumu](#3-sanal-ortam-venv-kurulumu)
4. [Gerekli paketlerin kurulumu](#4-gerekli-paketlerin-kurulumu)
5. [.env dosyasını doldurma](#5-env-dosyasını-doldurma)
6. [Botu çalıştırma](#6-botu-çalıştırma)
7. [Botu Telegram'da kullanma](#7-botu-telegramda-kullanma)
8. [Kota (günlük kullanım limiti) sistemi](#8-kota-günlük-kullanım-limiti-sistemi)
9. [Proje klasör yapısı](#9-proje-klasör-yapısı)
10. [Sık karşılaşılan hatalar](#10-sık-karşılaşılan-hatalar)
11. [Testleri çalıştırma (isteğe bağlı)](#11-testleri-çalıştırma-isteğe-bağlı)

---

## 1. Gereken programlar

Başlamadan önce bilgisayarında şunların kurulu olması gerekiyor:

- **Python 3.11 veya üzeri** — [python.org/downloads](https://www.python.org/downloads/)
  adresinden indirip kurabilirsin. Kurulum ekranında **"Add Python to PATH"**
  kutucuğunu işaretlemeyi unutma (Windows'ta).
- **FFmpeg** — video/sticker dönüştürme işlemleri için gerekli.
  - **Windows:** [ffmpeg.org/download.html](https://ffmpeg.org/download.html) adresinden
    "Windows builds" bağlantısına tıkla, zip'i indir, bir klasöre çıkart (örn.
    `C:\ffmpeg`), sonra `C:\ffmpeg\bin` klasörünü Windows'ta PATH ortam değişkenine
    ekle (Denetim Masası → Sistem → Gelişmiş sistem ayarları → Ortam Değişkenleri).
  - **Mac:** Terminal'i aç, [Homebrew](https://brew.sh) kuruluysa şu komutu çalıştır:
    ```
    brew install ffmpeg
    ```
  - **Linux (Ubuntu/Debian):**
    ```
    sudo apt update && sudo apt install ffmpeg
    ```
- **Bir Telegram bot tokeni** — Telegram'da [@BotFather](https://t.me/BotFather) ile
  konuş, `/newbot` yaz, botuna bir isim ve kullanıcı adı ver. Sana
  `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` gibi bir token verecek. Bu tokeni
  bir kenara not et, 5. adımda kullanacaksın.
- **Kendi Telegram user_id'n** — Telegram'da [@userinfobot](https://t.me/userinfobot)
  ile konuş, sana kendi sayısal ID'ni gösterecek (örn. `123456789`). Bu ID'yi de not
  et, 5. adımda kullanacaksın (whitelist için gerekli).

---

## 2. Proje klasörünü bilgisayarına alma

Bu proje zaten bir Git deposunun (`telegram_media_bot/` klasörü) içinde. Eğer bu
depoyu henüz bilgisayarına klonlamadıysan, bir terminal aç ve:

```
git clone <REPO_URL>
cd <REPO_KLASÖRÜ>/telegram_media_bot
```

Eğer proje zaten bilgisayarında bir klasördeyse, terminalde o klasöre gitmen yeterli:

```
cd yolu/telegram_media_bot
```

> 💡 **Terminal nasıl açılır?**
> - **Windows:** Başlat menüsüne "PowerShell" yaz, aç.
> - **Mac:** `Cmd + Boşluk` tuşuna bas, "Terminal" yaz, Enter'a bas.
> - **Linux:** `Ctrl + Alt + T` genelde terminali açar.

Terminalin şu an `telegram_media_bot` klasöründe olduğundan eminsen bir sonraki adıma geç.

---

## 3. Sanal ortam (venv) kurulumu

Sanal ortam (virtual environment / venv), bu projenin Python paketlerini
bilgisayarındaki diğer projelerden ayrı tutar. Böylece paket çakışması olmaz.

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> Eğer "çalıştırma politikası" hatası alırsan (PowerShell script çalıştırmayı
> engelliyor), önce şunu çalıştır, sonra tekrar dene:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### Mac / Linux (Terminal)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Aktivasyon başarılıysa, terminal satırının başında `(.venv)` yazısını görürsün.
Bundan sonraki tüm komutları **bu aktif haldeyken** çalıştır.

> 💡 Terminali kapatıp yeniden açtığında (`(.venv)` yazısı kaybolduğunda) yukarıdaki
> aktivasyon komutunu tekrar çalıştırman gerekir. Venv'i yeniden oluşturmana gerek yok,
> sadece aktive et.

---

## 4. Gerekli paketlerin kurulumu

Venv aktifken (satır başında `(.venv)` görüyorken), şu komutu çalıştır:

```bash
pip install -r requirements.txt
```

Bu komut birkaç dakika sürebilir (özellikle `rembg` — arka plan kaldırma paketi —
biraz büyük). Kurulum bitince terminalde hata görmemen gerekiyor.

> ⚠️ **rembg ile ilgili not:** `requirements.txt` içinde `rembg[cpu]` yazıyor —
> köşeli parantezdeki `[cpu]` kısmı önemli, arka plan kaldırma motorunu (ONNX Runtime)
> de kurar. Eğer elle `pip install rembg` yazarsan (köşeli parantezsiz), sticker
> üretimi "No onnxruntime backend found" hatası verir. `requirements.txt`'teki
> komutu olduğu gibi kullandığın sürece bu sorun yaşanmaz.

---

## 5. .env dosyasını doldurma

Proje klasöründe `.env.example` adlı bir dosya var. Bu dosyayı kopyalayıp `.env`
adında yeni bir dosya oluşturman gerekiyor (gerçek şifrelerin/key'lerin bu `.env`
dosyasında duracak — bu dosya asla Git'e/GitHub'a yüklenmez, güvenlidir).

### Windows (PowerShell)

```powershell
Copy-Item .env.example .env
```

### Mac / Linux

```bash
cp .env.example .env
```

Şimdi `.env` dosyasını bir metin editörüyle aç (Not Defteri, VS Code, TextEdit —
hangisi elindeyse) ve şu satırları doldur:

```env
# 1. adımda BotFather'dan aldığın token
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 1. adımda @userinfobot'tan aldığın kendi user_id'n.
# Birden fazla kişiye izin vermek istersen virgülle ayır: 111111111,222222222
WHITELISTED_USER_IDS=123456789
```

Diğer satırları (`OPENAI_API_KEY`, `LUMA_API_KEY`, `RUNWAY_API_KEY` gibi) **şimdilik
boş bırakabilirsin** — gerçek API key'lerin yoksa bot yine çalışır, sadece "Üret"
adımında ilgili servis için "henüz yapılandırılmadı" mesajı görürsün. Key'lerin
olduğunda ilgili satıra key'i yapıştırman yeterli, kod tarafında başka bir şey
değiştirmene gerek yok.

- **OPENAI_API_KEY:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
  adresinden alınır (DALL·E 3 görsel üretimi için).
- **LUMA_API_KEY:** [lumalabs.ai/dream-machine/api](https://lumalabs.ai/dream-machine/api)
  adresinden alınır (video/animasyon üretimi için, `VIDEO_PROVIDER=luma` iken).
- **RUNWAY_API_KEY:** [dev.runwayml.com](https://dev.runwayml.com/) adresinden alınır
  (video/animasyon üretimi için, `VIDEO_PROVIDER=runway` iken).

`.env` dosyasını kaydet ve editörü kapat.

---

## 6. Botu çalıştırma

Terminalde (venv aktifken, `telegram_media_bot` klasöründeyken):

```bash
python main.py
```

Her şey doğruysa terminalde şuna benzer satırlar görürsün:

```
2026-09-22 21:04:23 | INFO | __main__ | Bot başlatılıyor...
2026-09-22 21:04:23 | INFO | bot.services.database | Veritabanı hazır: data/bot.db
2026-09-22 21:04:23 | INFO | bot.loader | Uygulama hazır: 1 beyaz listede kullanıcı, ...
2026-09-22 21:04:23 | INFO | aiogram.dispatcher | Start polling
```

Bu satırı gördüysen bot çalışıyor demektir! Botu durdurmak için terminalde
`Ctrl + C` tuşlarına bas.

---

## 7. Botu Telegram'da kullanma

1. Telegram'ı aç, botunu bul (BotFather'da verdiğin kullanıcı adıyla ara).
2. `/start` yaz.
3. Karşına gelen menüden **🎰 Casino** veya **⚽ Spor Bahis** seç.
4. Bir görsel teması seç (örn. **🎡 Slot Ana Görseli**, **🌟 Freespin Yağmuru**,
   **🐯 3D Parlak Maskot**, **🏟️ Maç Günü Banner**, vb.).
5. Hangi oyun/takım/maç için üretmek istediğini yaz (örn. "Aztec Gold Deluxe" veya
   "Galatasaray - Fenerbahçe derbisi").
6. İstersen ek bir sanat detayı yaz (renk, sahne, maskot türü...), istemezsen
   "➡️ Detaysız geç" butonuna bas.
7. Çıktı türünü seç: **🖼️ Görsel**, **🎬 Video/Animasyon** veya **✨ Şeffaf Sticker**.
8. Botun hazırladığı prompt'u (üretim talimatını) gör, **✅ Üret** butonuna bas.
9. API key'lerin doluysa görsel/video birkaç saniye/dakika içinde gelir. Key'lerin
   boşsa "⚠️ Bu servis henüz yapılandırılmadı" mesajını görürsün — bu, henüz gerçek
   key eklenmediği için beklenen bir durumdur.

`/kota` yazarak günlük kullanım hakkını (kaç görsel/video/sticker hakkın kaldığını)
görebilirsin.

---

## 8. Kota (günlük kullanım limiti) sistemi

API çağrıları ücretli olduğu için bot, her whitelist'teki kullanıcı için **günlük**
üretim limiti tutar (varsayılan: 20 görsel, 5 video, 15 sticker — `.env` dosyasındaki
`DAILY_IMAGE_QUOTA`, `DAILY_VIDEO_QUOTA`, `DAILY_STICKER_QUOTA` değerlerinden
değiştirilebilir). Limit her gün gece yarısı (UTC saatine göre) otomatik sıfırlanır,
elle bir şey yapmana gerek yoktur.

Whitelist'te olmayan (yani `.env`'deki `WHITELISTED_USER_IDS` listesinde bulunmayan)
kullanıcılar botu **hiç kullanamaz** — bu, API kredinin başka biri tarafından
tüketilmesini önler.

---

## 9. Proje klasör yapısı

```
telegram_media_bot/
├── main.py                     # Botu başlatan giriş dosyası (python main.py)
├── requirements.txt             # Gerekli Python paketleri
├── .env.example                 # Örnek ortam değişkenleri (bunu .env'e kopyala)
├── bot/
│   ├── config.py                 # .env okuma ve doğrulama
│   ├── loader.py                  # Bot/Dispatcher/servisleri birbirine bağlar
│   ├── logging_config.py           # Loglama ayarları
│   ├── handlers/                    # Telegram komut/mesaj/buton işleyicileri
│   │   ├── start.py                    # /start, /help
│   │   ├── menu.py                      # Ana menü butonları
│   │   ├── casino.py                     # Casino tema seçimi
│   │   ├── sports.py                      # Spor bahis tema seçimi
│   │   ├── generation.py                   # Üretim akışının kalbi
│   │   ├── quota.py                         # /kota komutu
│   │   └── fallback.py                       # Eşleşmeyen her şeyi yakalar
│   ├── keyboards/                    # Inline klavyeler (butonlar)
│   ├── states/                       # FSM (adım adım akış) durumları
│   ├── services/                     # Dış servis entegrasyonları
│   │   ├── openai_image_service.py       # DALL·E 3 görsel üretimi
│   │   ├── video_generation_service.py    # Luma / Runway video üretimi
│   │   ├── media_processing_service.py     # ffmpeg + rembg (sticker/.webm)
│   │   ├── database.py                      # aiosqlite bağlantısı
│   │   └── quota_service.py                  # Günlük kota takibi
│   ├── middlewares/
│   │   └── whitelist.py               # Yetkisiz kullanıcıları engeller
│   └── utils/
│       ├── prompt_builder.py           # Casino/spor prompt motoru (en önemli dosya!)
│       ├── labels.py                    # Türkçe menü metinleri
│       ├── constants.py                  # Sabitler (temalar, Telegram limitleri)
│       └── exceptions.py                  # Özel hata sınıfları
├── data/                          # Çalışırken oluşan sqlite veritabanı + geçici dosyalar
└── tests/                         # Otomatik testler (bkz. 11. adım)
```

En çok "kişiselleştirmek" isteyeceğin dosya **`bot/utils/prompt_builder.py`** —
casino/spor bahis görsellerinin nasıl tarif edildiği (renkler, stil, sahne) burada.

---

## 10. Sık karşılaşılan hatalar

| Hata mesajı | Ne anlama gelir | Çözüm |
|---|---|---|
| `BOT_TOKEN tanımlı değil` | `.env` dosyası yok veya `BOT_TOKEN` boş | 5. adımı tekrar yap, `.env` dosyasını kontrol et |
| `WHITELISTED_USER_IDS boş bırakıldı` uyarısı | Kimseye izin verilmemiş | `.env`'de kendi user_id'ni `WHITELISTED_USER_IDS` satırına ekle |
| `🚫 Bu bot sadece yetkilendirilmiş kullanıcılara açıktır` | Telegram'daki user_id'n whitelist'te değil | @userinfobot ile ID'ni kontrol et, `.env`'e doğru ekle, botu yeniden başlat |
| `No onnxruntime backend found` | `rembg[cpu]` yerine sade `rembg` kurulmuş | `pip install -r requirements.txt` komutunu tekrar çalıştır |
| `ffmpeg başarısız oldu` | FFmpeg kurulu değil veya PATH'te değil | 1. adımdaki FFmpeg kurulum talimatlarını tekrar kontrol et |
| `Servis henüz yapılandırılmadı` | İlgili API key `.env`'de boş | O servisin key'ini `.env`'e ekle (5. adım) |

---

## 11. Testleri çalıştırma (isteğe bağlı)

Bu proje otomatik testler içerir (prompt üretimi, kota sistemi, whitelist, klavyeler,
genel bağlantı testi). Çalıştırmak için:

```bash
pip install -r requirements-dev.txt
pytest
```

Hepsi yeşil (PASSED) görünüyorsa kodun temel iskeleti sağlam demektir.
