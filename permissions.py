"""Panel yetki tanımları ve yardımcı fonksiyonlar."""

import json

PERMISSION_CATALOG = [
    {"key": "module.tracking", "label": "Link Takip & Analiz", "group": "Modüller",
     "desc": "Ana takip modülüne erişim"},
    {"key": "module.accounting", "label": "Muhasebe", "group": "Modüller",
     "desc": "Muhasebe modülü (yakında)"},
    {"key": "module.crm", "label": "CRM", "group": "Modüller",
     "desc": "CRM modülü (yakında)"},
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
    {"key": "admin.users", "label": "Kullanıcı Yönetimi", "group": "Yönetim",
     "desc": "Admin ekleme, silme ve yetki düzenleme"},
]

ALL_PERMISSION_KEYS = [p["key"] for p in PERMISSION_CATALOG]

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
        ],
    },
    "viewer": {
        "label": "İzleyici",
        "desc": "Sadece görüntüleme, düzenleme yok",
        "permissions": [
            "module.tracking", "tracking.dashboard", "tracking.players", "tracking.reports",
        ],
    },
    "affiliate_manager": {
        "label": "Affiliate Yöneticisi",
        "desc": "Raporlar ve dashboard",
        "permissions": [
            "module.tracking", "tracking.dashboard", "tracking.reports",
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


def permissions_from_role(role, custom_permissions=None):
    role = (role or "custom").strip().lower()
    if role == "superadmin":
        return ["*"]
    if role in ROLE_TEMPLATES and role != "custom":
        return list(ROLE_TEMPLATES[role]["permissions"])
    return normalize_permissions(custom_permissions)


def has_permission(user_permissions, required):
    perms = normalize_permissions(user_permissions)
    if "*" in perms:
        return True
    if not required:
        return True
    if isinstance(required, (list, tuple, set)):
        return any(p in perms for p in required)
    return required in perms
