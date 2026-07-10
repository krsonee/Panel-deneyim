"""Panel yetki tanımları ve yardımcı fonksiyonlar."""

import json

PERMISSION_CATALOG = [
    {"key": "module.tracking", "label": "Link Takip & Analiz", "group": "Modüller",
     "desc": "Ana takip modülüne erişim"},
    {"key": "module.accounting", "label": "Muhasebe", "group": "Modüller",
     "desc": "Muhasebe modülüne erişim"},
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
    {"key": "accounting.invoices", "label": "Fatura Hesaplama", "group": "Muhasebe",
     "desc": "Fatura şablonu alanı (yakında)"},
    {"key": "admin.users", "label": "Kullanıcı Yönetimi", "group": "Yönetim",
     "desc": "Admin ekleme, silme ve yetki düzenleme"},
]

ALL_PERMISSION_KEYS = [p["key"] for p in PERMISSION_CATALOG]

MODULE_KEYS = ("module.tracking", "module.accounting", "module.settings")

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
            "tracking.players", "tracking.reports", "tracking.export", "tracking.smartico",
            "tracking.blink",
        ],
    },
    "accountant": {
        "label": "Muhasebeci",
        "desc": "Muhasebe modülünde tam yetki",
        "permissions": [
            "module.accounting", "accounting.dashboard", "accounting.transactions",
            "accounting.commissions", "accounting.expenses", "accounting.vault",
            "accounting.payroll", "accounting.payroll.office_salaries", "accounting.invoices",
        ],
    },
    "viewer": {
        "label": "İzleyici",
        "desc": "Sadece görüntüleme, düzenleme yok",
        "permissions": [
            "module.tracking", "tracking.dashboard", "tracking.players", "tracking.reports", "tracking.smartico",
            "tracking.blink",
        ],
    },
    "affiliate_manager": {
        "label": "Affiliate Yöneticisi",
        "desc": "Raporlar ve dashboard",
        "permissions": [
            "module.tracking", "tracking.dashboard", "tracking.reports", "tracking.smartico",
            "tracking.blink",
        ],
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
    cleaned = []
    for item in raw:
        key = str(item).strip()
        if key == "*" or key in ALL_PERMISSION_KEYS:
            if key not in cleaned:
                cleaned.append(key)
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
    if "admin.users" in perms and "module.settings" not in perms:
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


def has_any_module_access(user_permissions):
    perms = normalize_permissions(user_permissions)
    if "*" in perms:
        return True
    if any(m in perms for m in MODULE_KEYS):
        return True
    if any(p.startswith("tracking.") for p in perms):
        return True
    if any(p.startswith("accounting.") for p in perms):
        return True
    if "admin.users" in perms:
        return True
    return False


def available_modules(user_permissions):
    perms = normalize_permissions(user_permissions)
    if "*" in perms:
        return ["tracking", "accounting", "settings"]
    mods = []
    if "module.tracking" in perms or any(p.startswith("tracking.") for p in perms):
        mods.append("tracking")
    if "module.accounting" in perms or any(p.startswith("accounting.") for p in perms):
        mods.append("accounting")
    if "module.settings" in perms or "admin.users" in perms:
        mods.append("settings")
    return mods


def default_module_for_user(user_permissions):
    mods = available_modules(user_permissions)
    if "tracking" in mods:
        return "tracking"
    if "accounting" in mods:
        return "accounting"
    return mods[0] if mods else None
