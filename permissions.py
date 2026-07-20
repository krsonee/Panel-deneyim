"""Panel yetki tanımları ve yardımcı fonksiyonlar."""

import json

try:
    from panel_config import ENABLED_MODULES, feature_enabled
except ImportError:
    ENABLED_MODULES = ("tracking", "accounting", "biolink")

    def feature_enabled(name):
        return name in ("tracking", "accounting", "biolink", "makrolink")

PERMISSION_CATALOG = [
    {"key": "module.tracking", "label": "Link Takip & Analiz", "group": "Modüller",
     "desc": "Ana takip modülüne erişim"},
    {"key": "module.accounting", "label": "Muhasebe", "group": "Modüller",
     "desc": "Muhasebe modülüne erişim"},
    {"key": "module.mailing", "label": "Mailing", "group": "Modüller",
     "desc": "Kampanya, CRM, şablon ve IVR mailing modülü"},
    {"key": "module.marketing", "label": "Marketing", "group": "Modüller",
     "desc": "Marketing modülüne erişim"},
    {"key": "module.biolink", "label": "Bio Sayfa", "group": "Modüller",
     "desc": "Link-in-bio sayfa oluşturucu modülü"},
    {"key": "module.settings", "label": "Ayarlar", "group": "Modüller",
     "desc": "Panel ayarları ekranı"},
    {"key": "tracking.dashboard", "label": "Dashboard & Grafikler", "group": "Link Takip",
     "desc": "KPI kartları ve grafikler"},
    {"key": "tracking.domains", "label": "Domain Yönetimi", "group": "Link Takip",
     "desc": "Domain ekleme, silme, toplu ekleme"},
    {"key": "tracking.players", "label": "Oyuncu Listeleri", "group": "Link Takip",
     "desc": "Online ve tüm oyuncular tabloları"},
    {"key": "tracking.reports", "label": "Referans Raporu", "group": "Link Takip",
     "desc": "Affiliate / ref performans tablosu"},
    {"key": "tracking.export", "label": "Veri Dışa Aktarma", "group": "Link Takip",
     "desc": "CSV, JSON indirme ve oturum temizleme"},
    {"key": "tracking.smartico", "label": "Smartico Affiliate Raporu", "group": "Link Takip",
     "desc": "Smartico API entegrasyonu, ayarları ve rapor görüntüleme"},
    {"key": "tracking.blink", "label": "bl.ink Link Raporu", "group": "Link Takip",
     "desc": "bl.ink API entegrasyonu, ayarları ve link/online rapor görüntüleme"},
    {"key": "tracking.makrolink", "label": "Kısa Link", "group": "Link Takip",
     "desc": "Kısa link oluşturma, tıklama raporu — hedef eklenen domain/URL üzerinden"},
    {"key": "biolink.pages", "label": "Sayfa Oluşturucu", "group": "Bio Sayfa",
     "desc": "Link-in-bio sayfa oluşturma, tema, buton/promo yönetimi ve tıklama raporu"},
    {"key": "accounting.dashboard", "label": "Muhasebe Özet", "group": "Muhasebe",
     "desc": "Muhasebe dashboard KPI kartları"},
    {"key": "accounting.transactions", "label": "Yatırım / Çekim", "group": "Muhasebe",
     "desc": "Site yatırım ve çekim işlemleri"},
    {"key": "accounting.commissions", "label": "Komisyon Yönetimi", "group": "Muhasebe",
     "desc": "Payment komisyon oranları"},
    {"key": "accounting.expenses", "label": "Cari Gider", "group": "Muhasebe",
     "desc": "Gider kategorileri ve masraf girişi"},
    {"key": "accounting.vault", "label": "Tahsilat & Kasa", "group": "Muhasebe",
     "desc": "Kasa giriş/çıkış takibi"},
    {"key": "accounting.payroll", "label": "Personel Maaş", "group": "Muhasebe",
     "desc": "Personel ve maaş tablosu"},
    {"key": "accounting.payroll.office_salaries", "label": "Ofis Personeli Maaşları", "group": "Muhasebe",
     "desc": "Ofis personeli maaş tutarları, dağılım ve toplamları"},
    {"key": "accounting.invoices", "label": "Proforma Fatura", "group": "Muhasebe",
     "desc": "Aylık resmi fatura şablonu"},
    {"key": "accounting.invoice_debt", "label": "Güncel Fatura Borç", "group": "Muhasebe",
     "desc": "EUR / USDT / TRY fatura borç defteri — borç, ödeme ve anlık bakiye"},
    {"key": "accounting.pl_report", "label": "PL Raporu", "group": "Muhasebe",
     "desc": "Merkeze iletilen aylık kâr/zarar (P&L) raporu"},
    {"key": "accounting.invoice_calc", "label": "Fatura Hesaplama (Günlük)", "group": "Muhasebe",
     "desc": "Sağlayıcı bazında günlük Stake / Winning girişiyle GGR ve komisyon tahmini — Fatura alanından bağımsız"},
    {"key": "accounting.personnel", "label": "Personel (Ofis / Türkiye Listesi)", "group": "Muhasebe",
     "desc": "Ofis ve Türkiye personel listesi — isim, işbaşı tarihi, maaş; Maaş Ödemeleri alanından bağımsız"},
    {"key": "mailing.dashboard", "label": "Mailing Özet", "group": "Mailing",
     "desc": "Mailing dashboard KPI kartları"},
    {"key": "mailing.crm", "label": "CRM Kontaklar", "group": "Mailing",
     "desc": "Kontak listesi, etiket ve CSV import"},
    {"key": "mailing.templates", "label": "Mail Şablonları", "group": "Mailing",
     "desc": "Konu ve gövde şablonları"},
    {"key": "mailing.campaigns", "label": "Kampanyalar", "group": "Mailing",
     "desc": "Toplu kampanya oluşturma ve kuyruğa alma"},
    {"key": "mailing.ivr", "label": "IVR Tetikleme", "group": "Mailing",
     "desc": "IVR cevap sonrası mail kuralları ve olaylar"},
    {"key": "mailing.reports", "label": "Mailing Raporları", "group": "Mailing",
     "desc": "Gönderim logları ve özet raporlar"},
    {"key": "mailing.settings", "label": "Mailing Ayarları", "group": "Mailing",
     "desc": "Domain, SMTP/DirectMail ve webhook ayarları"},
    {"key": "marketing.deals", "label": "Anlaşmalar", "group": "Marketing",
     "desc": "Kanal / affiliate anlaşmaları tablosu — anlaşma tarihi, sabit ücret, komisyon oranı"},
    {"key": "admin.users", "label": "Kullanıcı Yönetimi", "group": "Yönetim",
     "desc": "Admin ekleme, silme ve yetki düzenleme"},
    {"key": "admin.audit", "label": "Aktivite Günlüğü", "group": "Yönetim",
     "desc": "Kim, ne zaman, ne işlem yaptı — tüm panel hareketleri"},
]

ALL_PERMISSION_KEYS = [p["key"] for p in PERMISSION_CATALOG]

MODULE_KEYS = ("module.tracking", "module.accounting", "module.mailing", "module.marketing", "module.biolink", "module.settings")

BIOLINK_PERMS = (
    "module.biolink",
    "biolink.pages",
)

MAILING_PERMS = (
    "module.mailing",
    "mailing.dashboard",
    "mailing.crm",
    "mailing.templates",
    "mailing.campaigns",
    "mailing.ivr",
    "mailing.reports",
    "mailing.settings",
)

MARKETING_PERMS = (
    "module.marketing",
    "marketing.deals",
)

ROLE_TEMPLATES = {
    "superadmin": {
        "label": "Süper Admin",
        "desc": "Tüm modüller ve işlemler",
        "permissions": ["*"],
    },
    "operator": {
        "label": "Operatör",
        "desc": "Takip modülünde tam yetki, kullanıcı yönetimi yok",
        "permissions": [
            "module.tracking", "tracking.dashboard", "tracking.domains",
            "tracking.players", "tracking.reports", "tracking.export",
            "tracking.makrolink",
            "module.biolink", "biolink.pages",
        ],
    },
    "accountant": {
        "label": "Muhasebeci",
        "desc": "Muhasebe modülünde tam yetki",
        "permissions": [
            "module.accounting", "accounting.dashboard", "accounting.transactions",
            "accounting.commissions", "accounting.expenses", "accounting.vault",
            "accounting.payroll", "accounting.payroll.office_salaries", "accounting.invoices",
            "accounting.invoice_debt",
            "accounting.pl_report",
            "accounting.invoice_calc", "accounting.personnel",
        ],
    },
    "viewer": {
        "label": "İzleyici",
        "desc": "Sadece görüntüleme, düzenleme yok",
        "permissions": [
            "module.tracking", "tracking.dashboard", "tracking.players", "tracking.reports",
            "tracking.makrolink",
            "module.biolink", "biolink.pages",
        ],
    },
    "affiliate_manager": {
        "label": "Affiliate Yöneticisi",
        "desc": "Raporlar ve dashboard",
        "permissions": [
            "module.tracking", "tracking.dashboard", "tracking.reports",
            "tracking.makrolink",
            "module.biolink", "biolink.pages",
        ],
    },
    "biolink_editor": {
        "label": "Bio Sayfa Editörü",
        "desc": "Link-in-bio sayfa oluşturucu modülünde tam yetki",
        "permissions": list(BIOLINK_PERMS),
    },
    "custom": {
        "label": "Özel Yetki",
        "desc": "Manuel seçim",
        "permissions": [],
    },
}


def normalize_permissions(raw):
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, list):
        return []
    legacy_biolink = any(str(item).strip() == "tracking.biolink" for item in raw)
    cleaned = []
    for item in raw:
        key = str(item).strip()
        if key == "tracking.biolink":
            continue
        if key == "*" or key in ALL_PERMISSION_KEYS:
            if key not in cleaned:
                cleaned.append(key)
    if legacy_biolink and "biolink.pages" not in cleaned:
        cleaned.append("biolink.pages")
    return cleaned


def ensure_module_parents(permissions):
    """Alt yetki verildiyse ilgili modül anahtarını otomatik ekle (giriş engelini önler)."""
    perms = normalize_permissions(permissions)
    if "*" in perms:
        return perms
    if any(p.startswith("tracking.") for p in perms) and "module.tracking" not in perms:
        perms.append("module.tracking")
    if any(p.startswith("accounting.") for p in perms) and "module.accounting" not in perms:
        perms.append("module.accounting")
    if any(p.startswith("mailing.") for p in perms) and "module.mailing" not in perms:
        perms.append("module.mailing")
    if any(p.startswith("marketing.") for p in perms) and "module.marketing" not in perms:
        perms.append("module.marketing")
    if any(p.startswith("biolink.") for p in perms) and "module.biolink" not in perms:
        perms.append("module.biolink")
    if "admin.users" in perms and "module.settings" not in perms:
        perms.append("module.settings")
    if "admin.audit" in perms and "module.settings" not in perms:
        perms.append("module.settings")
    return perms


def permissions_from_role(role, custom_permissions=None):
    role = (role or "custom").strip().lower()
    if role == "superadmin":
        return ["*"]
    if role in ROLE_TEMPLATES and role != "custom":
        return ensure_module_parents(list(ROLE_TEMPLATES[role]["permissions"]))
    return ensure_module_parents(custom_permissions)


def has_permission(user_permissions, required):
    perms = normalize_permissions(user_permissions)
    if "*" in perms:
        return True
    if not required:
        return True
    if isinstance(required, (list, tuple, set)):
        return any(p in perms for p in required)
    return required in perms


def _module_enabled(name: str) -> bool:
    return name in ENABLED_MODULES or name == "settings"


def active_permission_catalog():
    """Kapalı özelliklerin yetki anahtarlarını katalogdan çıkarır."""
    hidden_prefixes = []
    if not feature_enabled("mailing"):
        hidden_prefixes.extend(("module.mailing", "mailing."))
    if not feature_enabled("marketing"):
        hidden_prefixes.extend(("module.marketing", "marketing."))
    if not feature_enabled("smartico"):
        hidden_prefixes.append("tracking.smartico")
    if not feature_enabled("blink"):
        hidden_prefixes.append("tracking.blink")
    out = []
    for item in PERMISSION_CATALOG:
        key = item["key"]
        if any(key == p or key.startswith(p) for p in hidden_prefixes if p.endswith(".")) or key in hidden_prefixes:
            continue
        if key.startswith("module.") and key not in (
            "module.tracking", "module.accounting", "module.mailing",
            "module.biolink", "module.settings",
        ):
            mod = key.split(".", 1)[1]
            if mod not in ENABLED_MODULES and mod != "settings":
                continue
        row = dict(item)
        if key == "accounting.invoices":
            try:
                from panel_config import BRAND
                vendor = BRAND.get("invoice_vendor") or "Pronet"
            except Exception:
                vendor = "Pronet"
            row["label"] = f"{vendor} Proforma Fatura"
            row["desc"] = f"Aylık resmi fatura şablonu ({vendor})"
        out.append(row)
    return out


def has_any_module_access(user_permissions):
    perms = normalize_permissions(user_permissions)
    if "*" in perms:
        return True
    for m in ENABLED_MODULES:
        if f"module.{m}" in perms:
            return True
        if any(p.startswith(f"{m}.") for p in perms):
            return True
    if "admin.users" in perms or "admin.audit" in perms:
        return True
    return False


def available_modules(user_permissions):
    perms = normalize_permissions(user_permissions)
    order = [m for m in ("tracking", "accounting", "mailing", "biolink") if m in ENABLED_MODULES]
    if "*" in perms:
        mods = list(order)
        mods.append("settings")
        return mods
    mods = []
    for m in order:
        if f"module.{m}" in perms or any(p.startswith(f"{m}.") for p in perms):
            mods.append(m)
    if "module.settings" in perms or "admin.users" in perms or "admin.audit" in perms:
        mods.append("settings")
    return mods


def default_module_for_user(user_permissions):
    mods = available_modules(user_permissions)
    if "tracking" in mods:
        return "tracking"
    if "accounting" in mods:
        return "accounting"
    if "mailing" in mods:
        return "mailing"
    if "biolink" in mods:
        return "biolink"
    return mods[0] if mods else None
