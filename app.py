import csv
import io
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Flask,
    Response,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from permissions import (
    ALL_PERMISSION_KEYS,
    PERMISSION_CATALOG,
    ROLE_TEMPLATES,
    available_modules,
    default_module_for_user,
    has_any_module_access,
    has_permission,
    normalize_permissions,
    permissions_from_role,
)
import totp
from database import (
    DB_PATH,
    APP_DIR,
    delete_ref_code_label,
    execute,
    fetch_audit_log,
    fetchall,
    fetchone,
    get_db,
    get_ref_code_labels,
    init_db as db_init_schema,
    insert_returning_id,
    integrity_error_type,
    iso,
    log_audit,
    scalar,
    upsert_ref_code_label,
    utcnow,
    uses_postgres,
)

# ── Ortam değişkenleri (Render → Environment) ──
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
# NOT: "makro123" varsayılanı SADECE yerel geliştirme için. Production'da (Render)
# ADMIN_PASSWORD ortam değişkeni MUTLAKA güçlü bir değerle override edilmelidir.
# Bu satır bilerek değiştirilmedi — Render'da zaten farklı bir değer set edilmiş
# olabilir; varsayılanı değiştirmek mevcut admin'i kilitleme riski taşır.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "makro123")
SECRET_KEY = os.environ.get("SECRET_KEY", "makrobet-analytics-gizli-anahtar-degistir")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

ONLINE_THRESHOLD_SECONDS = 90
IntegrityError = integrity_error_type()

app = Flask(__name__)
app.secret_key = SECRET_KEY
_is_prod = bool(os.environ.get("RENDER") or PUBLIC_BASE_URL.startswith("https"))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_is_prod,
    PERMANENT_SESSION_LIFETIME=timedelta(days=31),
)


def init_db():
    db_init_schema()
    migrate_domains()
    ensure_primary_admin()
    seed_admin_users()
    if os.environ.get("RENDER") and not uses_postgres():
        print(
            "\n⚠️  UYARI: Render'da SQLite kullanılıyor — her deploy'da veriler silinir!\n"
            "    Çözüm: PostgreSQL oluşturup DATABASE_URL ortam değişkenini bağlayın.\n"
        )
    elif os.environ.get("RENDER") and uses_postgres():
        print("\n✅ PostgreSQL bağlı — veriler kalıcı.\n")


def ensure_primary_admin():
    """Ana admin hesabını env'deki kullanıcı adı/şifre ile senkron tutar (Render kurtarma)."""
    username = normalize_username(ADMIN_USERNAME)
    if not username or not ADMIN_PASSWORD:
        return
    now = iso(utcnow())
    ph = generate_password_hash(ADMIN_PASSWORD, method="pbkdf2:sha256")
    perms = json.dumps(["*"])
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT id FROM admin_users WHERE LOWER(username) = ?", (username,))
        if row:
            execute(
                conn,
                "UPDATE admin_users SET password_hash = ?, role = ?, permissions = ? WHERE LOWER(username) = ?",
                (ph, "superadmin", perms, username),
            )
        else:
            execute(
                conn,
                "INSERT INTO admin_users (username, password_hash, role, permissions, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, ph, "superadmin", perms, now),
            )
        conn.commit()


def seed_admin_users():
    users = {}
    raw = os.environ.get("ADMIN_USERS", "").strip()
    if raw:
        try:
            users.update(json.loads(raw))
        except json.JSONDecodeError:
            pass
    now = iso(utcnow())
    with closing(get_db()) as conn:
        for username, password in users.items():
            username = normalize_username(username)
            if not username or not password or username == normalize_username(ADMIN_USERNAME):
                continue
            row = fetchone(conn, "SELECT id FROM admin_users WHERE username = ?", (username,))
            if row:
                continue
            execute(
                conn,
                "INSERT INTO admin_users (username, password_hash, role, permissions, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(password, method="pbkdf2:sha256"), "superadmin", json.dumps(["*"]), now),
            )
        conn.commit()


def admin_user_to_dict(row):
    if not row:
        return None
    keys = row.keys()
    role = row["role"] if "role" in keys else "superadmin"
    perms = normalize_permissions(row["permissions"] if "permissions" in keys else '["*"]')
    username = row["username"] if "username" in keys else ""
    if normalize_username(username) == normalize_username(ADMIN_USERNAME):
        role = "superadmin"
        perms = ["*"]
    elif role == "superadmin" or not perms:
        perms = ["*"]
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": (row["display_name"] if "display_name" in keys else "") or "",
        "role": role,
        "permissions": perms,
        "created_at": row["created_at"],
        "two_factor_required": bool(int(row["two_factor_required"] or 0)) if "two_factor_required" in keys else False,
        "two_factor_enabled": bool(int(row["two_factor_enabled"] or 0)) if "two_factor_enabled" in keys else False,
        "must_change_password": bool(int(row["must_change_password"] or 0)) if "must_change_password" in keys else False,
        "is_primary_admin": is_primary_admin(username),
    }


def display_name_for(username):
    username = normalize_username(username)
    if not username:
        return ""
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT display_name FROM admin_users WHERE LOWER(username) = ?", (username,))
    return (row["display_name"] or "").strip() if row and row["display_name"] else ""


def current_display_name():
    dn = (session.get("admin_display_name") or "").strip()
    return dn or session.get("admin_username") or ""


def normalize_username(value):
    return (value or "").strip().lower()


def is_primary_admin(username):
    """Ortam değişkenindeki ana admin hesabı mı? (case-insensitive)"""
    return normalize_username(username) == normalize_username(ADMIN_USERNAME)


def get_admin_user(username, password):
    username = normalize_username(username)
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT * FROM admin_users WHERE LOWER(username) = ?", (username,))
        if row and check_password_hash(row["password_hash"], password):
            return admin_user_to_dict(row)
    if username == normalize_username(ADMIN_USERNAME) and password == ADMIN_PASSWORD:
        return {
            "id": 0, "username": username, "display_name": "", "role": "superadmin",
            "permissions": ["*"], "created_at": "", "two_factor_required": False, "two_factor_enabled": False,
        }
    return None


def get_session_permissions():
    return normalize_permissions(session.get("admin_permissions"))


def login_admin_user(user):
    role = user.get("role", "custom")
    perms = normalize_permissions(user.get("permissions", []))
    if normalize_username(user.get("username")) == normalize_username(ADMIN_USERNAME):
        role = "superadmin"
        perms = ["*"]
    elif role == "superadmin":
        perms = ["*"]
    session["admin_logged_in"] = True
    session["admin_username"] = user["username"]
    session["admin_display_name"] = user.get("display_name") or ""
    session["admin_role"] = role
    session["admin_permissions"] = perms


def verify_admin(username, password):
    return get_admin_user(username, password) is not None


# ── Giriş denemesi kısıtlama (brute-force koruması) ──
# Tek worker/gthread deploy'u için basit bellek-içi çözüm yeterli (Redis/DB gerekmez).
_LOGIN_ATTEMPT_LIMIT = 5
_LOGIN_ATTEMPT_WINDOW = timedelta(minutes=15)
_LOGIN_LOCKOUT_DURATION = timedelta(minutes=15)
_LOGIN_LOCKOUT_MESSAGE = "Çok fazla başarısız giriş denemesi. Lütfen 15 dakika sonra tekrar deneyin."
_login_attempts = {}
_login_attempts_lock = threading.Lock()


def _login_attempt_key(username, ip):
    return f"{normalize_username(username)}|{ip or ''}"


def _cleanup_login_attempts_locked(now):
    """Süresi geçmiş kayıtları temizler. Çağıran, _login_attempts_lock'u tutuyor olmalı."""
    expired = []
    for key, info in _login_attempts.items():
        locked_until = info.get("locked_until")
        if locked_until:
            if now >= locked_until:
                expired.append(key)
        elif now - info.get("first_attempt", now) > _LOGIN_ATTEMPT_WINDOW:
            expired.append(key)
    for key in expired:
        _login_attempts.pop(key, None)


def check_login_rate_limit(username, ip):
    """Kilitliyse Türkçe hata mesajını döner, aksi halde None."""
    now = utcnow()
    key = _login_attempt_key(username, ip)
    with _login_attempts_lock:
        _cleanup_login_attempts_locked(now)
        info = _login_attempts.get(key)
        if info and info.get("locked_until") and now < info["locked_until"]:
            return _LOGIN_LOCKOUT_MESSAGE
    return None


def record_login_failure(username, ip):
    """Başarısız denemeyi kaydeder. Bu deneme kilitlenmeye sebep olduysa True döner."""
    now = utcnow()
    key = _login_attempt_key(username, ip)
    with _login_attempts_lock:
        _cleanup_login_attempts_locked(now)
        info = _login_attempts.get(key)
        if not info or now - info.get("first_attempt", now) > _LOGIN_ATTEMPT_WINDOW:
            info = {"count": 0, "first_attempt": now, "locked_until": None}
        info["count"] += 1
        newly_locked = False
        if info["count"] >= _LOGIN_ATTEMPT_LIMIT and not info["locked_until"]:
            info["locked_until"] = now + _LOGIN_LOCKOUT_DURATION
            newly_locked = True
        _login_attempts[key] = info
    return newly_locked


def record_login_success(username, ip):
    key = _login_attempt_key(username, ip)
    with _login_attempts_lock:
        _login_attempts.pop(key, None)


def audit(action, detail="", status=200):
    """Genel işlem kaydı — süper admin panelinde 'kim ne yaptı' listesi için."""
    try:
        with closing(get_db()) as conn:
            log_audit(
                conn,
                username=session.get("admin_username") or "",
                display_name=current_display_name(),
                action=action,
                method=request.method,
                path=request.path,
                status=status,
                ip=get_client_ip(),
                detail=detail,
            )
        g.audit_logged = True
    except Exception:
        pass


_AUDIT_SKIP_PREFIXES = ("/static/", "/api/audit-log", "/api/admin/audit-log")
_AUDIT_SENSITIVE_KEYS = {
    "password", "current_password", "new_password", "confirm_password", "code",
    "secret", "api_secret", "totp_secret", "smtp_password",
}


def _short_body_summary():
    try:
        data = request.get_json(silent=True)
    except Exception:
        data = None
    if not isinstance(data, dict) or not data:
        return ""
    parts = []
    for key, val in list(data.items())[:8]:
        if key in _AUDIT_SENSITIVE_KEYS:
            continue
        text = str(val)
        if len(text) > 40:
            text = text[:40] + "…"
        parts.append(f"{key}={text}")
    return " ".join(parts)[:400]


@app.after_request
def _auto_audit(response):
    try:
        if (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            and response.status_code < 400
            and session.get("admin_logged_in")
            and not getattr(g, "audit_logged", False)
            and not request.path.startswith(_AUDIT_SKIP_PREFIXES)
        ):
            with closing(get_db()) as conn:
                log_audit(
                    conn,
                    username=session.get("admin_username") or "",
                    display_name=current_display_name(),
                    action=f"{request.method} {request.path}",
                    method=request.method,
                    path=request.path,
                    status=response.status_code,
                    ip=get_client_ip(),
                    detail=_short_body_summary(),
                )
    except Exception:
        pass
    return response


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        urllib.request.urlopen(req, timeout=8)
    except (urllib.error.URLError, TimeoutError, OSError):
        pass


def notify_new_visitor(domain, ref_code, ip_address, device_display):
    ref = ref_code or "Direkt giriş"
    msg = (
        f"🟢 <b>Yeni ziyaretçi</b>\n"
        f"Domain: {domain}\n"
        f"Ref: {ref}\n"
        f"IP: {ip_address or '—'}\n"
        f"Cihaz: {device_display or '—'}"
    )
    threading.Thread(target=send_telegram, args=(msg,), daemon=True).start()


def date_range_from_period(period):
    now = utcnow()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return iso(start), iso(now)
    if period == "yesterday":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = today_start - timedelta(days=1)
        return iso(start), iso(today_start)
    if period == "7days":
        return iso(now - timedelta(days=7)), iso(now)
    if period == "30days":
        return iso(now - timedelta(days=30)), iso(now)
    return None, None


def sessions_date_clause(period):
    start, end = date_range_from_period(period)
    if not start:
        return "", ()
    return " AND vs.started_at >= ? AND vs.started_at < ?", (start, end)


def affiliate_url(domain, ref_code=""):
    base = get_server_base_url()
    d = normalize_domain(domain)
    if ref_code:
        return f"https://{d}?ref={urllib.parse.quote(ref_code)}"
    return f"https://{d}"


def parse_iso(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_domain(domain):
    """Kullanıcı tam URL yapıştırsa bile sadece domain adını alır."""
    raw = (domain or "").strip().lower()
    if not raw:
        return ""

    if "://" in raw or raw.startswith("//"):
        if not raw.startswith(("http://", "https://", "//")):
            raw = "https://" + raw.lstrip("/")
        parsed = urlparse(raw)
        d = (parsed.hostname or "").strip().lower()
    else:
        d = raw.split("/")[0].split("?")[0].split("#")[0].strip().lower()

    d = d.removeprefix("www.")
    if d == "127.0.0.1":
        return "localhost"
    return d


MAX_BULK_RANGE = 500


def expand_domain_line(line):
    """Tek satırdan domain listesi üretir. Aralık: makrobet804-1084 veya makrobet 804 - 1084"""
    raw = (line or "").strip()
    if not raw:
        return []

    compact = re.sub(r"\s+", "", raw)
    range_match = re.match(r"^([a-zA-Z][a-zA-Z0-9]*?)(\d+)-(\d+)$", compact, re.I)
    if range_match:
        prefix = range_match.group(1).lower()
        start = int(range_match.group(2))
        end = int(range_match.group(3))
        if start > end:
            start, end = end, start
        count = end - start + 1
        if count > MAX_BULK_RANGE:
            raise ValueError(f"Tek aralıkta en fazla {MAX_BULK_RANGE} domain eklenebilir ({count} istendi).")
        return [f"{prefix}{num}.com" for num in range(start, end + 1)]

    domain = normalize_domain(raw)
    return [domain] if domain else []


def expand_domain_input(text):
    """Metin kutusundaki satırları ve aralıkları domain listesine çevirir."""
    if isinstance(text, list):
        lines = text
    else:
        lines = str(text or "").replace(",", "\n").split("\n")

    domains = []
    seen = set()
    for line in lines:
        for domain in expand_domain_line(line):
            if domain and domain not in seen:
                seen.add(domain)
                domains.append(domain)
    return domains


def migrate_domains():
    """Eski yanlış kayıtları düzeltir; yerel test için localhost ekler."""
    with closing(get_db()) as conn:
        rows = fetchall(conn, "SELECT id, domain FROM tracked_links")
        for row in rows:
            fixed = normalize_domain(row["domain"])
            if fixed and fixed != row["domain"]:
                try:
                    execute(conn, "UPDATE tracked_links SET domain = ? WHERE id = ?", (fixed, row["id"]))
                except IntegrityError:
                    execute(conn, "DELETE FROM tracked_links WHERE id = ?", (row["id"],))

        has_local = fetchone(
            conn,
            "SELECT 1 FROM tracked_links WHERE domain IN ('localhost', '127.0.0.1') LIMIT 1",
        )
        if not has_local:
            execute(
                conn,
                "INSERT INTO tracked_links (domain, ref_code, label, created_at) VALUES ('localhost', '', '', ?)",
                (iso(utcnow()),),
            )
        conn.commit()


# Bu rotalar 3. parti (casino/bahis) sitelerine gömülü tracker.js tarafından
# çapraz-origin çağrılır — bunlar için CORS her zaman açık kalmalı.
_PUBLIC_CORS_PREFIXES = ("/api/track/",)


def _is_public_cors_path(path):
    return path.startswith(_PUBLIC_CORS_PREFIXES)


def cors_headers(response):
    path = request.path
    if _is_public_cors_path(path):
        # Genel takip uç noktaları: 3. parti sitelere gömülü, herkese açık kalmalı.
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif _is_prod:
        # Panel/iç API'ler: sadece kendi origin'imizden gelen isteklere izin ver.
        origin = request.headers.get("Origin", "")
        if origin and PUBLIC_BASE_URL and origin.rstrip("/") == PUBLIC_BASE_URL:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        # Origin eşleşmiyorsa veya yoksa header eklenmez (çapraz-origin erişim reddedilir).
    else:
        # Yerel geliştirme kolaylığı için (prod değilken) serbest bırak.
        response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if _is_prod:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.after_request
def after_request(response):
    return security_headers(cors_headers(response))


@app.route("/api/<path:_path>", methods=["OPTIONS"])
def api_options(_path):
    return cors_headers(jsonify({"ok": True}))


def domain_lookup_values(domain):
    """localhost ile 127.0.0.1 aynı kabul edilir."""
    d = normalize_domain(domain)
    if d == "localhost":
        return ["localhost", "127.0.0.1"]
    return [d]


def find_tracked_link(domain, ref_code):
    """Önce domain+ref eşleşmesi, yoksa sadece domain kaydı (ref boş) kullanılır."""
    ref_code = (ref_code or "").strip()
    domains = domain_lookup_values(domain)
    if not domains or not domains[0]:
        return None
    placeholders = ",".join("?" * len(domains))
    with closing(get_db()) as conn:
        if ref_code:
            row = fetchone(
                conn,
                f"SELECT * FROM tracked_links WHERE domain IN ({placeholders}) AND ref_code = ?",
                (*domains, ref_code),
            )
            if row:
                return dict(row)
        row = fetchone(
            conn,
            f"SELECT * FROM tracked_links WHERE domain IN ({placeholders}) AND ref_code = ''",
            domains,
        )
        return dict(row) if row else None


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def get_user_agent():
    return (request.headers.get("User-Agent") or "")[:512]


def parse_user_agent(ua):
    """User-Agent stringinden cihaz, işletim sistemi, marka ve tarayıcı çıkarır."""
    raw = ua or ""
    low = raw.lower()

    if not raw.strip():
        return {
            "device_category": "unknown",
            "device_label": "Bilinmiyor",
            "os": "—",
            "brand": "—",
            "browser": "—",
            "device_display": "Bilinmiyor",
        }

    # ── Cihaz kategorisi & işletim sistemi ──
    is_ipad = "ipad" in low
    is_iphone = "iphone" in low or "ipod" in low
    is_android = "android" in low
    is_mobile_flag = "mobile" in low

    if is_ipad:
        category = "tablet"
        os_name = "iPadOS"
        brand = "Apple iPad"
    elif is_iphone:
        category = "mobile"
        os_name = "iOS"
        brand = "Apple iPhone"
    elif is_android:
        category = "tablet" if "tablet" in low and not is_mobile_flag else "mobile"
        os_name = "Android"
        brand = _detect_android_brand(raw, low)
    elif any(x in low for x in ("windows", "macintosh", "mac os", "linux", "cros")):
        category = "desktop"
        if "windows" in low:
            os_name = "Windows"
        elif "macintosh" in low or "mac os" in low:
            os_name = "macOS"
        elif "cros" in low:
            os_name = "Chrome OS"
        else:
            os_name = "Linux"
        brand = "Bilgisayar"
    else:
        category = "unknown"
        os_name = "—"
        brand = "—"

    browser = _detect_browser(raw, low, is_iphone or is_ipad, is_android)

    # ── Görüntü metni ──
    if category == "mobile":
        device_label = f"Mobil · {os_name}"
        if brand and brand not in ("—", "Android"):
            device_label += f" · {brand}"
        if browser != "—":
            device_label += f" · {browser}"
    elif category == "tablet":
        device_label = f"Tablet · {brand or os_name}"
        if browser != "—":
            device_label += f" · {browser}"
    elif category == "desktop":
        device_label = f"Bilgisayar · {browser}" if browser != "—" else f"Bilgisayar · {os_name}"
    else:
        device_label = browser if browser != "—" else "Bilinmiyor"

    return {
        "device_category": category,
        "device_label": device_label,
        "os": os_name,
        "brand": brand,
        "browser": browser,
        "device_display": device_label,
    }


def _detect_browser(ua, low, is_ios, is_android):
    if "edg/" in low or "edga/" in low or "edgios/" in low:
        return "Microsoft Edge"
    if "opr/" in low or "opera" in low:
        return "Opera"
    if "samsungbrowser" in low:
        return "Samsung Internet"
    if "crios/" in low:
        return "Chrome (iOS)"
    if "fxios/" in low:
        return "Firefox (iOS)"
    if "chrome/" in low or "chromium" in low:
        return "Chrome"
    if "firefox/" in low:
        return "Firefox"
    if "safari/" in low and "chrome" not in low and "chromium" not in low:
        return "Safari"
    if is_ios:
        return "Safari"
    if is_android:
        return "Android WebView"
    return "—"


def _detect_android_brand(ua, low):
    """Android User-Agent içinden telefon markasını tahmin eder."""
    model = ""
    match = re.search(r"android[^;)]*;\s*([^;)]+)", ua, re.I)
    if match:
        model = match.group(1).strip()

    checks = [
        (lambda m, l: "samsung" in l or m.upper().startswith("SM-"), "Samsung"),
        (lambda m, l: "pixel" in l, "Google Pixel"),
        (lambda m, l: any(x in l for x in ("redmi", "poco", " mi ", "m210", "m200", "220")), "Xiaomi"),
        (lambda m, l: "huawei" in l or m.upper().startswith("HW-") or "honor" in l, "Huawei"),
        (lambda m, l: "oneplus" in l, "OnePlus"),
        (lambda m, l: "oppo" in l, "OPPO"),
        (lambda m, l: "vivo" in l, "vivo"),
        (lambda m, l: "realme" in l, "Realme"),
        (lambda m, l: "nokia" in l, "Nokia"),
        (lambda m, l: "motorola" in l or "moto " in l, "Motorola"),
        (lambda m, l: m.upper().startswith("LG-") or "lg-" in l, "LG"),
        (lambda m, l: "sony" in l, "Sony"),
        (lambda m, l: "htc" in l, "HTC"),
        (lambda m, l: "lenovo" in l, "Lenovo"),
        (lambda m, l: "zte" in l, "ZTE"),
        (lambda m, l: "meizu" in l, "Meizu"),
        (lambda m, l: "infinix" in l, "Infinix"),
        (lambda m, l: "tecno" in l, "Tecno"),
    ]
    for fn, name in checks:
        if fn(model, low):
            return name

    if model and model.lower() not in ("k", "linux", "android", "mobile", "wv"):
        if len(model) <= 24:
            return model
    return "Android"


def session_to_dict(row, now=None, *, light=False):
    now = now or utcnow()
    last_seen = parse_iso(row["last_seen_at"])
    is_online = last_seen and (now - last_seen).total_seconds() <= ONLINE_THRESHOLD_SECONDS
    games = json.loads(row["games"] or "[]")
    sid = row["session_id"] or ""
    ua = row["user_agent"] if "user_agent" in row.keys() else ""
    device = parse_user_agent(ua)
    data = {
        "id": row["id"],
        "session_id": sid,
        "session_short": sid[:8] + "…" if len(sid) > 8 else sid,
        "tracked_link_id": row["tracked_link_id"],
        "domain": row["domain"],
        "ref_code": row["ref_code"] or "Direkt giriş",
        "started_at": row["started_at"],
        "last_seen_at": row["last_seen_at"],
        "total_seconds": row["total_seconds"],
        "games": games,
        "is_online": bool(is_online),
        "ip_address": row["ip_address"] if "ip_address" in row.keys() else "",
        "user_agent": ua,
        "device_category": device["device_category"],
        "device_label": device["device_label"],
        "device_display": device["device_display"],
        "device_os": device["os"],
        "device_brand": device["brand"],
        "device_browser": device["browser"],
    }
    if not light:
        data["game_log"] = json.loads(row["game_log"] or "[]")
    return data


def get_server_base_url():
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return request.host_url.rstrip("/")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("admin_logged_in"):
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Giriş gerekli"}), 401
        return redirect(url_for("login_page"))
    return wrapped


def permission_required(*required_perms):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            needed = list(required_perms)
            if not has_permission(get_session_permissions(), needed):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Bu işlem için yetkiniz yok."}), 403
                return render_template("login.html", error="Bu sayfa için yetkiniz yok."), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def admin_only_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if (session.get("admin_username") or "").strip().lower() != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Bu işlem sadece admin hesabı içindir."}), 403
            return render_template("login.html", error="Bu sayfa için yetkiniz yok."), 403
        return view(*args, **kwargs)
    return wrapped


def superadmin_required(view):
    """Süper admin katmanı: yetki listesinde "*" olan HERKES (ana admin + superadmin rolündeki diğer hesaplar).
    admin_only_required'tan farklı — o SADECE ana admin hesabına (literal ADMIN_USERNAME) izin verir."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if "*" not in get_session_permissions():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Bu işlem için süper admin yetkisi gerekir."}), 403
            return render_template("login.html", error="Bu sayfa için süper admin yetkisi gerekir."), 403
        return view(*args, **kwargs)
    return wrapped


def build_journey(session_data):
    """Kullanıcının kronolojik zaman tüneli."""
    ref = session_data["ref_code"] or "Direkt giriş"
    timeline = [{
        "time": session_data["started_at"],
        "type": "entry",
        "icon": "🌐",
        "text": f"{session_data['domain']} sitesinden girdi",
        "detail": (
            f"Referans: {ref} · IP: {session_data.get('ip_address') or '—'}"
            f" · Cihaz: {session_data.get('device_display') or '—'}"
        ),
    }]
    for ev in session_data.get("game_log") or []:
        timeline.append({
            "time": ev.get("time"),
            "type": "game",
            "icon": "🎮",
            "text": f"{ev.get('game', 'Oyun')} tıkladı",
            "detail": f"Oturum süresi: {ev.get('elapsed', 0)} sn",
        })
    timeline.sort(key=lambda x: x.get("time") or "")
    if session_data.get("last_seen_at"):
        timeline.append({
            "time": session_data["last_seen_at"],
            "type": "activity",
            "icon": "⏱",
            "text": "Son aktivite",
            "detail": f"Toplam süre: {session_data.get('total_seconds', 0)} sn",
        })
    return timeline


# ── Sayfalar ──


@app.route("/health")
def health():
    db_type = "postgresql" if uses_postgres() else "sqlite"
    link_count = 0
    try:
        with closing(get_db()) as conn:
            link_count = scalar(conn, "SELECT COUNT(*) FROM tracked_links") or 0
    except Exception:
        pass
    return jsonify({
        "ok": True,
        "service": "makropanel",
        "database": db_type,
        "persistent": db_type == "postgresql",
        "tracked_domains": link_count,
    })


@app.route("/")
def index():
    return redirect(url_for("admin_page"))


def _proceed_after_password_ok(user):
    """Şifre (varsa zorunlu şifre değişikliği dahil) onaylandıktan sonraki adım:
    2FA gerekiyorsa doğrulamaya yönlendir, yoksa oturumu tamamen aç.
    Hem /admin/login hem /admin/force-password-change buradan devam eder."""
    if user.get("two_factor_required"):
        session["pending_2fa_username"] = user["username"]
        session["pending_2fa_display_name"] = user.get("display_name") or ""
        audit("login_password_ok_pending_2fa", detail=f"username={user['username']}")
        return redirect(url_for("verify_2fa_page"))
    login_admin_user(user)
    session.permanent = True
    if not has_any_module_access(get_session_permissions()):
        session.clear()
        return redirect(url_for("login_page", error="Hesabınızda panel erişim yetkisi yok. Yöneticinize başvurun."))
    audit("login_success")
    return redirect(url_for("admin_page"))


@app.route("/admin/login", methods=["GET", "POST"])
def login_page():
    if session.get("admin_logged_in"):
        if has_any_module_access(get_session_permissions()):
            return redirect(url_for("admin_page"))
        session.clear()
    error = request.args.get("error")
    if request.method == "POST":
        username = normalize_username(request.form.get("username", ""))
        password = request.form.get("password", "")
        client_ip = get_client_ip()
        lockout_message = check_login_rate_limit(username, client_ip)
        if lockout_message:
            audit("login_rate_limited", detail=f"username={username}", status=429)
            error = lockout_message
        else:
            user = get_admin_user(username, password)
            if user:
                record_login_success(username, client_ip)
                if user.get("must_change_password"):
                    session["pending_pwchange_username"] = user["username"]
                    audit("login_password_ok_pending_pwchange", detail=f"username={user['username']}")
                    return redirect(url_for("force_password_change_page"))
                return _proceed_after_password_ok(user)
            else:
                just_locked = record_login_failure(username, client_ip)
                audit("login_failed", detail=f"username={username}", status=401)
                if just_locked:
                    audit(
                        "login_locked_out",
                        detail=f"username={username} ip={client_ip}",
                        status=429,
                    )
                    error = _LOGIN_LOCKOUT_MESSAGE
                else:
                    error = "Kullanıcı adı veya şifre hatalı."
    return render_template("login.html", error=error)


@app.route("/admin/verify-2fa", methods=["GET", "POST"])
def verify_2fa_page():
    username = normalize_username(session.get("pending_2fa_username") or "")
    if not username:
        return redirect(url_for("login_page"))
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT * FROM admin_users WHERE LOWER(username) = ?", (username,))
    if not row:
        session.pop("pending_2fa_username", None)
        return redirect(url_for("login_page"))

    is_setup = not bool(int(row["two_factor_enabled"] or 0))
    secret = (row["totp_secret"] or "").strip()
    if is_setup and not secret:
        secret = totp.generate_secret()
        with closing(get_db()) as conn:
            execute(conn, "UPDATE admin_users SET totp_secret = ? WHERE id = ?", (secret, row["id"]))
            conn.commit()

    error = None
    if request.method == "POST":
        code = request.form.get("code", "")
        if totp.verify_code(secret, code):
            user = admin_user_to_dict(row)
            if is_setup:
                with closing(get_db()) as conn:
                    execute(conn, "UPDATE admin_users SET two_factor_enabled = 1 WHERE id = ?", (row["id"],))
                    conn.commit()
            session.pop("pending_2fa_username", None)
            session.pop("pending_2fa_display_name", None)
            login_admin_user(user)
            session.permanent = True
            if not has_any_module_access(get_session_permissions()):
                session.clear()
                return redirect(url_for("login_page", error="Hesabınızda panel erişim yetkisi yok."))
            audit("login_success_2fa")
            return redirect(url_for("admin_page"))
        audit("login_2fa_failed", detail=f"username={username}", status=401)
        error = "Kod hatalı veya süresi geçmiş, tekrar dene."

    qr_svg = None
    if is_setup:
        uri = totp.build_otpauth_uri(secret, username)
        qr_svg = totp.qr_svg_data_uri(uri)
    return render_template(
        "login_2fa.html",
        error=error,
        setup=is_setup,
        secret=secret if is_setup else "",
        qr_svg=qr_svg,
    )


@app.route("/admin/force-password-change", methods=["GET", "POST"])
def force_password_change_page():
    """Admin tarafından atanan ilk/geçici şifre değiştirilmeden panele girilemez.
    /admin/verify-2fa gibi pre-login bir adım — @login_required kullanmaz, kendi pending session anahtarını kontrol eder."""
    username = normalize_username(session.get("pending_pwchange_username") or "")
    if not username:
        return redirect(url_for("login_page"))
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT * FROM admin_users WHERE LOWER(username) = ?", (username,))
    if not row:
        session.pop("pending_pwchange_username", None)
        return redirect(url_for("login_page"))

    error = None
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not new_password or not confirm_password:
            error = "Yeni şifre ve tekrarı gerekli."
        elif new_password != confirm_password:
            error = "Şifreler eşleşmiyor."
        elif len(new_password) < 6:
            error = "Şifre en az 6 karakter olmalı."
        else:
            with closing(get_db()) as conn:
                execute(
                    conn,
                    "UPDATE admin_users SET password_hash = ?, must_change_password = 0 WHERE LOWER(username) = ?",
                    (generate_password_hash(new_password, method="pbkdf2:sha256"), username),
                )
                conn.commit()
                updated = fetchone(conn, "SELECT * FROM admin_users WHERE LOWER(username) = ?", (username,))
            session.pop("pending_pwchange_username", None)
            audit("forced_password_change", detail=f"username={username}")
            return _proceed_after_password_ok(admin_user_to_dict(updated))

    return render_template("force_password.html", error=error)


@app.route("/admin/logout")
def logout():
    if session.get("admin_username"):
        audit("logout")
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/admin")
@login_required
def admin_page():
    perms = get_session_permissions()
    if not has_any_module_access(perms):
        session.clear()
        return redirect(url_for("login_page", error="Panele erişim yetkiniz yok. Yöneticinize başvurun."))
    return render_template(
        "admin.html",
        server_url=get_server_base_url(),
        default_module=default_module_for_user(perms),
    )


@app.route("/api/me", methods=["GET"])
@login_required
def api_me():
    perms = get_session_permissions()
    with closing(get_db()) as conn:
        row = fetchone(
            conn,
            "SELECT two_factor_required, two_factor_enabled, display_name FROM admin_users WHERE LOWER(username) = ?",
            (normalize_username(session.get("admin_username")),),
        )
    two_factor_required = bool(int(row["two_factor_required"] or 0)) if row else False
    two_factor_enabled = bool(int(row["two_factor_enabled"] or 0)) if row else False
    return jsonify({
        "username": session.get("admin_username"),
        "display_name": (row["display_name"] if row else "") or session.get("admin_username"),
        "role": session.get("admin_role"),
        "permissions": perms,
        "two_factor_required": two_factor_required,
        "two_factor_enabled": two_factor_enabled,
        "role_templates": ROLE_TEMPLATES,
        "permission_catalog": PERMISSION_CATALOG,
        "available_modules": available_modules(perms),
        "default_module": default_module_for_user(perms),
    })


@app.route("/api/permissions/catalog", methods=["GET"])
@login_required
def permissions_catalog():
    return jsonify({
        "catalog": PERMISSION_CATALOG,
        "role_templates": ROLE_TEMPLATES,
    })


@app.route("/demo")
def demo_page():
    return render_template("demo.html", server_url=get_server_base_url())


# ── Takip Linkleri API ──


@app.route("/api/links", methods=["GET"])
@superadmin_required
def list_links():
    cutoff = iso(utcnow() - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))
    with closing(get_db()) as conn:
        rows = fetchall(conn, "SELECT * FROM tracked_links ORDER BY created_at DESC")
        online_rows = fetchall(
            conn,
            """
            SELECT tracked_link_id, COUNT(*) AS cnt
            FROM visitor_sessions
            WHERE last_seen_at >= ?
            GROUP BY tracked_link_id
            """,
            (cutoff,),
        )
    online_map = {row["tracked_link_id"]: row["cnt"] for row in online_rows}
    links = []
    for row in rows:
        item = dict(row)
        item["online_count"] = online_map.get(item["id"], 0)
        item["affiliate_url"] = affiliate_url(item["domain"], item["ref_code"])
        links.append(item)
    return jsonify({"links": links, "tracking_snippet": build_tracking_snippet()})


@app.route("/api/links", methods=["POST"])
@superadmin_required
def create_link():
    data = request.get_json(silent=True) or {}
    domain = normalize_domain(data.get("domain", ""))
    ref_code = (data.get("ref_code") or "").strip()
    label = (data.get("label") or data.get("name") or "").strip()

    if not domain:
        return jsonify({"error": "Domain zorunludur."}), 400

    created_at = iso(utcnow())
    created_by = current_display_name()
    try:
        with closing(get_db()) as conn:
            link_id = insert_returning_id(
                conn,
                "INSERT INTO tracked_links (domain, ref_code, label, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
                (domain, ref_code, label, created_at, created_by),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM tracked_links WHERE id = ?", (link_id,))
    except IntegrityError:
        if ref_code:
            return jsonify({"error": "Bu domain + referans kombinasyonu zaten kayıtlı."}), 409
        return jsonify({"error": "Bu domain zaten takip listesinde."}), 409

    item = dict(row)
    item["affiliate_url"] = affiliate_url(item["domain"], item["ref_code"])
    return jsonify({"link": item, "tracking_snippet": build_tracking_snippet()}), 201


@app.route("/api/links/bulk", methods=["POST"])
@superadmin_required
def create_links_bulk():
    data = request.get_json(silent=True) or {}
    raw_domains = data.get("domains") or data.get("text") or ""
    ref_code = (data.get("ref_code") or "").strip()

    try:
        domain_list = expand_domain_input(raw_domains)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not domain_list:
        return jsonify({"error": "Geçerli domain bulunamadı."}), 400

    added, skipped, errors = [], [], []
    created_at = iso(utcnow())
    created_by = current_display_name()
    for domain in domain_list:
        try:
            with closing(get_db()) as conn:
                insert_returning_id(
                    conn,
                    "INSERT INTO tracked_links (domain, ref_code, label, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
                    (domain, ref_code, "", created_at, created_by),
                )
                conn.commit()
            added.append(domain)
        except IntegrityError:
            skipped.append(domain)
        except Exception as exc:
            errors.append({"domain": domain, "error": str(exc)})

    return jsonify({
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "count_added": len(added),
        "count_skipped": len(skipped),
        "count_expanded": len(domain_list),
    })


@app.route("/api/links/bulk/preview", methods=["POST"])
@superadmin_required
def preview_links_bulk():
    data = request.get_json(silent=True) or {}
    raw = data.get("text") or data.get("domains") or ""
    try:
        domains = expand_domain_input(raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    preview = domains[:8]
    return jsonify({
        "count": len(domains),
        "preview": preview,
        "first": domains[0] if domains else None,
        "last": domains[-1] if domains else None,
    })


@app.route("/api/links/<int:link_id>", methods=["DELETE"])
@superadmin_required
def delete_link(link_id):
    with closing(get_db()) as conn:
        execute(conn, "DELETE FROM visitor_sessions WHERE tracked_link_id = ?", (link_id,))
        cur = execute(conn, "DELETE FROM tracked_links WHERE id = ?", (link_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Link bulunamadı."}), 404
    return jsonify({"ok": True})


def build_tracking_snippet(domain=None, ref_code=None):
    base = get_server_base_url()
    return (
        "<!-- MakroPanel — tüm kayıtlı domainler için ortak takip kodu -->\n"
        f'<script src="{base}/static/tracker.js" '
        f'data-api="{base}" async></script>'
    )


# ── Tracker API ──


@app.route("/api/track/init", methods=["POST"])
def track_init():
    data = request.get_json(silent=True) or {}
    domain = normalize_domain(data.get("domain", ""))
    ref_code = (data.get("ref_code") or "").strip()
    session_id = (data.get("session_id") or "").strip() or str(uuid.uuid4())
    client_ip = get_client_ip()
    user_agent = get_user_agent()

    link = find_tracked_link(domain, ref_code)
    if not link:
        return jsonify({"tracked": False, "reason": "Bu domain/referans kayıtlı değil."})

    now = iso(utcnow())
    is_new = False
    with closing(get_db()) as conn:
        existing = fetchone(conn, "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,))

        if existing:
            execute(
                conn,
                """
                UPDATE visitor_sessions
                SET last_seen_at = ?, domain = ?, ref_code = ?, tracked_link_id = ?,
                    ip_address = ?, user_agent = ?
                WHERE session_id = ?
                """,
                (now, domain, ref_code, link["id"], client_ip, user_agent, session_id),
            )
            row = fetchone(conn, "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,))
        else:
            is_new = True
            execute(
                conn,
                """
                INSERT INTO visitor_sessions
                (session_id, tracked_link_id, domain, ref_code, started_at, last_seen_at,
                 ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, link["id"], domain, ref_code, now, now, client_ip, user_agent),
            )
            row = fetchone(conn, "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,))
        conn.commit()

    session_data = session_to_dict(row)
    if is_new:
        notify_new_visitor(domain, ref_code, client_ip, session_data.get("device_display"))
    return jsonify({
        "tracked": True,
        "session_id": session_id,
        "total_seconds": session_data["total_seconds"],
        "games": session_data["games"],
    })


@app.route("/api/track/heartbeat", methods=["POST"])
def track_heartbeat():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    domain = normalize_domain(data.get("domain", ""))
    ref_code = (data.get("ref_code") or "").strip()
    total_seconds = int(data.get("total_seconds") or 0)
    games = data.get("games") or []

    if not session_id:
        return jsonify({"error": "session_id gerekli"}), 400

    link = find_tracked_link(domain, ref_code)
    if not link:
        return jsonify({"tracked": False}), 403

    now = iso(utcnow())
    with closing(get_db()) as conn:
        execute(
            conn,
            """
            UPDATE visitor_sessions
            SET last_seen_at = ?, total_seconds = ?, games = ?,
                ip_address = ?, user_agent = ?
            WHERE session_id = ?
            """,
            (
                now,
                total_seconds,
                json.dumps(games, ensure_ascii=False),
                get_client_ip(),
                get_user_agent(),
                session_id,
            ),
        )
        conn.commit()

    return jsonify({"ok": True, "total_seconds": total_seconds})


@app.route("/api/track/event", methods=["POST"])
def track_event():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    domain = normalize_domain(data.get("domain", ""))
    ref_code = (data.get("ref_code") or "").strip()
    game = (data.get("game") or "").strip()
    elapsed = int(data.get("elapsed") or 0)

    if not session_id or not game:
        return jsonify({"error": "session_id ve game gerekli"}), 400

    link = find_tracked_link(domain, ref_code)
    if not link:
        return jsonify({"tracked": False}), 403

    now = iso(utcnow())
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,))
        if not row:
            return jsonify({"error": "Oturum bulunamadı"}), 404

        games = json.loads(row["games"] or "[]")
        game_log = json.loads(row["game_log"] or "[]")

        if game not in games:
            games.append(game)
        game_log.append({"game": game, "time": now, "elapsed": elapsed})

        if uses_postgres():
            execute(
                conn,
                """
                UPDATE visitor_sessions
                SET last_seen_at = ?, games = ?, game_log = ?,
                    total_seconds = GREATEST(total_seconds, ?)
                WHERE session_id = ?
                """,
                (
                    now,
                    json.dumps(games, ensure_ascii=False),
                    json.dumps(game_log, ensure_ascii=False),
                    elapsed,
                    session_id,
                ),
            )
        else:
            execute(
                conn,
                """
                UPDATE visitor_sessions
                SET last_seen_at = ?, games = ?, game_log = ?, total_seconds = MAX(total_seconds, ?)
                WHERE session_id = ?
                """,
                (
                    now,
                    json.dumps(games, ensure_ascii=False),
                    json.dumps(game_log, ensure_ascii=False),
                    elapsed,
                    session_id,
                ),
            )
        conn.commit()

    return jsonify({"ok": True})


@app.route("/api/track/leave", methods=["POST"])
def track_leave():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    total_seconds = int(data.get("total_seconds") or 0)

    if not session_id:
        return jsonify({"ok": True})

    past = iso(utcnow() - timedelta(seconds=ONLINE_THRESHOLD_SECONDS + 5))
    with closing(get_db()) as conn:
        if uses_postgres():
            execute(
                conn,
                """
                UPDATE visitor_sessions
                SET last_seen_at = ?, total_seconds = GREATEST(total_seconds, ?)
                WHERE session_id = ?
                """,
                (past, total_seconds, session_id),
            )
        else:
            execute(
                conn,
                """
                UPDATE visitor_sessions
                SET last_seen_at = ?, total_seconds = MAX(total_seconds, ?)
                WHERE session_id = ?
                """,
                (past, total_seconds, session_id),
            )
        conn.commit()

    return jsonify({"ok": True})


# ── Admin veri API ──


@app.route("/api/online", methods=["GET"])
@permission_required("tracking.players")
def online_users():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))

    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            """
            SELECT vs.* FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE vs.last_seen_at >= ?
            ORDER BY vs.last_seen_at DESC
            """,
            (cutoff,),
        )

    users = [session_to_dict(row, now, light=True) for row in rows]
    return jsonify({"count": len(users), "users": users})


@app.route("/api/sessions", methods=["GET"])
@permission_required("tracking.players")
def all_sessions():
    now = utcnow()
    period = request.args.get("period", "all")
    date_sql, date_params = sessions_date_clause(period)
    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            f"""
            SELECT vs.* FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            ORDER BY vs.last_seen_at DESC
            """,
            date_params,
        )

    sessions = [session_to_dict(row, now, light=True) for row in rows]
    return jsonify({"sessions": sessions, "period": period})


@app.route("/api/reports/referrals", methods=["GET"])
@permission_required("tracking.reports")
def referral_report():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))
    period = request.args.get("period", "all")
    date_sql, date_params = sessions_date_clause(period)

    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            f"""
            SELECT
                vs.domain,
                CASE WHEN vs.ref_code = '' OR vs.ref_code IS NULL
                     THEN 'Direkt giriş' ELSE vs.ref_code END AS ref_label,
                vs.ref_code,
                COUNT(*) AS total_visitors,
                SUM(CASE WHEN vs.last_seen_at >= ? THEN 1 ELSE 0 END) AS online_now,
                SUM(vs.total_seconds) AS total_seconds,
                MAX(vs.last_seen_at) AS last_seen_at,
                COUNT(DISTINCT vs.ip_address) AS unique_ips
            FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            GROUP BY vs.domain, vs.ref_code
            ORDER BY total_visitors DESC
            """,
            (cutoff, *date_params),
        )
        labels = get_ref_code_labels(conn)

    report = []
    for row in rows:
        item = dict(row)
        ref = item.get("ref_code") or ""
        item["affiliate_url"] = affiliate_url(item["domain"], ref)
        item["total_minutes"] = round((item.get("total_seconds") or 0) / 60, 1)
        custom_label = labels.get(ref.strip().lower()) if ref else None
        item["ref_name"] = custom_label
        if custom_label:
            item["ref_label"] = custom_label
        report.append(item)
    return jsonify({"report": report, "period": period})


@app.route("/api/reports/referral-labels", methods=["GET"])
@permission_required("tracking.reports")
def list_referral_labels():
    with closing(get_db()) as conn:
        labels = get_ref_code_labels(conn)
    return jsonify({"labels": labels})


@app.route("/api/reports/referral-labels", methods=["POST"])
@permission_required("tracking.reports")
def save_referral_label():
    data = request.get_json(silent=True) or {}
    ref_code = (data.get("ref_code") or "").strip()
    label = (data.get("label") or "").strip()
    if not ref_code:
        return jsonify({"error": "ref_code gerekli."}), 400
    with closing(get_db()) as conn:
        if label:
            upsert_ref_code_label(conn, ref_code, label)
        else:
            delete_ref_code_label(conn, ref_code)
    return jsonify({"ok": True})


@app.route("/api/reports/referral-labels", methods=["DELETE"])
@permission_required("tracking.reports")
def delete_referral_label():
    data = request.get_json(silent=True) or {}
    ref_code = (data.get("ref_code") or "").strip()
    if not ref_code:
        return jsonify({"error": "ref_code gerekli."}), 400
    with closing(get_db()) as conn:
        delete_ref_code_label(conn, ref_code)
    return jsonify({"ok": True})


@app.route("/api/sessions/<session_id>/journey", methods=["GET"])
@permission_required("tracking.players")
def session_journey(session_id):
    now = utcnow()
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT vs.* FROM visitor_sessions vs WHERE vs.session_id = ?", (session_id,))
    if not row:
        return jsonify({"error": "Oturum bulunamadı"}), 404
    data = session_to_dict(row, now)
    return jsonify({"session": data, "timeline": build_journey(data)})


@app.route("/api/charts", methods=["GET"])
@permission_required("tracking.dashboard")
def chart_data():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))
    period = request.args.get("period", "all")
    date_sql, date_params = sessions_date_clause(period)

    with closing(get_db()) as conn:
        domain_rows = fetchall(
            conn,
            f"""
            SELECT
                vs.domain,
                COUNT(*) AS total_players,
                SUM(CASE WHEN vs.last_seen_at >= ? THEN 1 ELSE 0 END) AS online_now,
                SUM(vs.total_seconds) AS total_seconds
            FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            GROUP BY vs.domain
            ORDER BY total_players DESC
            """,
            (cutoff, *date_params),
        )

        click_rows = fetchall(
            conn,
            f"""
            SELECT vs.domain, vs.game_log FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            """,
            date_params,
        )

        ref_rows = fetchall(
            conn,
            f"""
            SELECT
                CASE WHEN vs.ref_code = '' OR vs.ref_code IS NULL
                     THEN 'Direkt giriş' ELSE vs.ref_code END AS channel,
                COUNT(*) AS members,
                SUM(CASE WHEN vs.last_seen_at >= ? THEN 1 ELSE 0 END) AS online_now
            FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            GROUP BY channel
            ORDER BY members DESC
            """,
            (cutoff, *date_params),
        )

        game_rows = fetchall(
            conn,
            f"""
            SELECT vs.game_log FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            """,
            date_params,
        )

    game_counts = {}
    domain_clicks = {}
    for row in game_rows:
        for ev in json.loads(row["game_log"] or "[]"):
            name = ev.get("game", "Bilinmeyen")
            game_counts[name] = game_counts.get(name, 0) + 1
    for row in click_rows:
        d = row["domain"]
        domain_clicks[d] = domain_clicks.get(d, 0) + len(json.loads(row["game_log"] or "[]"))

    game_stats = sorted(
        [{"game": k, "clicks": v} for k, v in game_counts.items()],
        key=lambda x: x["clicks"],
        reverse=True,
    )

    return jsonify({
        "domain_traffic": [
            {
                "domain": r["domain"],
                "total_players": r["total_players"],
                "online_now": r["online_now"],
                "total_minutes": round((r["total_seconds"] or 0) / 60, 1),
                "total_clicks": domain_clicks.get(r["domain"], 0),
            }
            for r in domain_rows
        ],
        "affiliate_channels": [
            {
                "channel": r["channel"],
                "members": r["members"],
                "online_now": r["online_now"],
            }
            for r in ref_rows
        ],
        "game_clicks": game_stats,
    })


@app.route("/api/data/export", methods=["GET"])
@permission_required("tracking.export")
def export_data():
    now = utcnow()
    with closing(get_db()) as conn:
        links = [dict(r) for r in fetchall(conn, "SELECT * FROM tracked_links")]
        sessions = [
            session_to_dict(r, now)
            for r in fetchall(
                conn,
                """
                SELECT vs.* FROM visitor_sessions vs
                INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
                """,
            )
        ]
    return jsonify({"exported_at": iso(now), "links": links, "sessions": sessions})


@app.route("/api/data/export.csv", methods=["GET"])
@permission_required("tracking.export")
def export_csv():
    now = utcnow()
    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            """
            SELECT vs.* FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            ORDER BY vs.last_seen_at DESC
            """,
        )
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Oturum ID", "Durum", "Domain", "Referans", "IP Adresi",
        "Cihaz Türü", "İşletim Sistemi", "Marka / Model", "Tarayıcı", "Cihaz Özeti",
        "Toplam Süre (sn)", "Oyunlar", "Başlangıç", "Son Görülme",
    ])
    for row in rows:
        s = session_to_dict(row, now)
        writer.writerow([
            s["session_id"],
            "Online" if s["is_online"] else "Offline",
            s["domain"],
            s["ref_code"],
            s["ip_address"],
            s["device_category"],
            s["device_os"],
            s["device_brand"],
            s["device_browser"],
            s["device_display"],
            s["total_seconds"],
            ", ".join(s["games"]),
            s["started_at"],
            s["last_seen_at"],
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=link-takip-verileri.csv"},
    )


@app.route("/api/data/clear-sessions", methods=["POST"])
@permission_required("tracking.export")
def clear_sessions():
    with closing(get_db()) as conn:
        execute(conn, "DELETE FROM visitor_sessions")
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/users", methods=["GET"])
@superadmin_required
def list_admin_users():
    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            """
            SELECT id, username, display_name, role, permissions, created_at,
                   two_factor_required, two_factor_enabled
            FROM admin_users ORDER BY username
            """,
        )
    users = []
    for row in rows:
        item = admin_user_to_dict(row)
        item["role_label"] = ROLE_TEMPLATES.get(item["role"], {}).get("label", item["role"])
        users.append(item)
    return jsonify({"users": users, "role_templates": ROLE_TEMPLATES, "permission_catalog": PERMISSION_CATALOG})


@app.route("/api/admin/users", methods=["POST"])
@superadmin_required
def create_admin_user():
    data = request.get_json(silent=True) or {}
    username = normalize_username(data.get("username"))
    password = (data.get("password") or "").strip()
    display_name = (data.get("display_name") or "").strip()[:100]
    role = (data.get("role") or "custom").strip().lower()
    permissions = permissions_from_role(role, data.get("permissions"))
    two_factor_required = 1 if data.get("two_factor_required") else 0
    if not username or not password:
        return jsonify({"error": "Kullanıcı adı ve şifre gerekli."}), 400
    if len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalı."}), 400
    if role == "custom" and not permissions:
        return jsonify({"error": "Özel rol için en az bir yetki seçin."}), 400
    try:
        with closing(get_db()) as conn:
            insert_returning_id(
                conn,
                """
                INSERT INTO admin_users
                  (username, password_hash, role, permissions, created_at, display_name, two_factor_required, must_change_password)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    username,
                    generate_password_hash(password, method="pbkdf2:sha256"),
                    role,
                    json.dumps(permissions),
                    iso(utcnow()),
                    display_name,
                    two_factor_required,
                ),
            )
            conn.commit()
    except IntegrityError:
        return jsonify({"error": "Bu kullanıcı adı zaten var."}), 409
    audit("user_created", detail=f"target={username} role={role}")
    return jsonify({"ok": True, "username": username, "role": role, "permissions": permissions}), 201


@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@superadmin_required
def update_admin_user(user_id):
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "custom").strip().lower()
    permissions = permissions_from_role(role, data.get("permissions"))
    password = (data.get("password") or "").strip()
    if role == "custom" and not permissions:
        return jsonify({"error": "Özel rol için en az bir yetki seçin."}), 400
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT * FROM admin_users WHERE id = ?", (user_id,))
        if not row:
            return jsonify({"error": "Kullanıcı bulunamadı."}), 404

        target_is_primary = is_primary_admin(row["username"])

        if target_is_primary and password:
            audit("primary_admin_update_restricted", detail=f"attempted_by={session.get('admin_username')}")
            return jsonify({
                "error": "Ana admin hesabının şifresi panelden değiştirilemez. Sadece sunucudaki ADMIN_PASSWORD ortam değişkeninden güncellenebilir.",
            }), 403

        set_clauses = []
        params = []
        if not target_is_primary:
            # Ana admin hesabı için rol/yetki her zaman zorla superadmin/["*"] olduğundan
            # bu alanlar sessizce değiştirilmeden bırakılır (read-time zaten override ediyor).
            set_clauses.extend(["role = ?", "permissions = ?"])
            params.extend([role, json.dumps(permissions)])

        if "display_name" in data:
            set_clauses.append("display_name = ?")
            params.append((data.get("display_name") or "").strip()[:100])

        if "two_factor_required" in data:
            two_factor_required = 1 if data.get("two_factor_required") else 0
            set_clauses.append("two_factor_required = ?")
            params.append(two_factor_required)
            if not two_factor_required:
                # Kapatınca eski secret'ı da temizle — tekrar açılırsa sıfırdan kurulum ister.
                set_clauses.append("totp_secret = ''")
                set_clauses.append("two_factor_enabled = 0")

        if password:
            if len(password) < 6:
                return jsonify({"error": "Şifre en az 6 karakter olmalı."}), 400
            set_clauses.append("password_hash = ?")
            params.append(generate_password_hash(password, method="pbkdf2:sha256"))
            # Admin başka birinin şifresini atadığında, o kullanıcı bir dahaki girişte değiştirmeye zorlanır.
            set_clauses.append("must_change_password = 1")

        if set_clauses:
            params.append(user_id)
            execute(conn, f"UPDATE admin_users SET {', '.join(set_clauses)} WHERE id = ?", tuple(params))
            conn.commit()
        updated = fetchone(conn, "SELECT * FROM admin_users WHERE id = ?", (user_id,))
    item = admin_user_to_dict(updated)
    if session.get("admin_username") == item["username"]:
        session["admin_role"] = item["role"]
        session["admin_permissions"] = item["permissions"]
    audit("user_updated", detail=f"target={item['username']} role={item['role']}")
    return jsonify({"ok": True, "user": item})


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@superadmin_required
def delete_admin_user(user_id):
    current = session.get("admin_username")
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT username FROM admin_users WHERE id = ?", (user_id,))
        if not row:
            return jsonify({"error": "Kullanıcı bulunamadı."}), 404
        if is_primary_admin(row["username"]):
            return jsonify({"error": "Ana admin hesabı silinemez."}), 403
        if row["username"] == current:
            return jsonify({"error": "Kendi hesabını silemezsin."}), 400
        total = scalar(conn, "SELECT COUNT(*) FROM admin_users")
        if total <= 1:
            return jsonify({"error": "Son admin kullanıcı silinemez."}), 400
        execute(conn, "DELETE FROM admin_users WHERE id = ?", (user_id,))
        conn.commit()
    audit("user_deleted", detail=f"target={row['username']}")
    return jsonify({"ok": True})


@app.route("/api/admin/users/<int:user_id>/unlock", methods=["POST"])
@superadmin_required
def unlock_admin_user(user_id):
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT username FROM admin_users WHERE id = ?", (user_id,))
        if not row:
            return jsonify({"error": "Kullanıcı bulunamadı."}), 404
    target_username = normalize_username(row["username"])
    prefix = f"{target_username}|"
    with _login_attempts_lock:
        matching_keys = [key for key in _login_attempts if key.startswith(prefix)]
        for key in matching_keys:
            _login_attempts.pop(key, None)
    audit("login_unlock", detail=f"target_username={target_username}")
    return jsonify({"ok": True})


@app.route("/api/admin/users/<int:user_id>/2fa/reset", methods=["POST"])
@superadmin_required
def admin_reset_user_2fa(user_id):
    """Süper admin, başka bir kullanıcının 2FA'sını sıfırlar (telefon değişti/kayboldu vb.) — hedefin şifresi istenmez."""
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT username FROM admin_users WHERE id = ?", (user_id,))
        if not row:
            return jsonify({"error": "Kullanıcı bulunamadı."}), 404
        target_username = normalize_username(row["username"])
        execute(
            conn,
            "UPDATE admin_users SET totp_secret = '', two_factor_enabled = 0 WHERE id = ?",
            (user_id,),
        )
        conn.commit()
    audit("2fa_admin_reset", detail=f"target_username={target_username}")
    return jsonify({"ok": True})


@app.route("/api/me/password", methods=["POST"])
@login_required
def change_own_password():
    data = request.get_json(silent=True) or {}
    current_password = (data.get("current_password") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    username = session.get("admin_username")
    if is_primary_admin(username):
        return jsonify({
            "error": "Ana admin hesabının şifresi panelden değiştirilemez. Sadece sunucudaki ADMIN_PASSWORD ortam değişkeninden güncellenebilir.",
        }), 403
    if not current_password or not new_password:
        return jsonify({"error": "Mevcut ve yeni şifre gerekli."}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Yeni şifre en az 6 karakter olmalı."}), 400
    if not verify_admin(username, current_password):
        audit("password_change_failed", status=401)
        return jsonify({"error": "Mevcut şifre hatalı."}), 401
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT id FROM admin_users WHERE LOWER(username) = ?", (normalize_username(username),))
        if not row:
            # Sadece env tabanlı ana admin hesabı DB'de yoksa burada oluşturulmaz — güvenlik için reddet.
            return jsonify({"error": "Bu hesap ortam değişkeninden geliyor, panelden şifre değiştirilemez."}), 400
        execute(
            conn,
            "UPDATE admin_users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password, method="pbkdf2:sha256"), row["id"]),
        )
        conn.commit()
    audit("password_changed")
    return jsonify({"ok": True})


@app.route("/api/me/2fa/reset", methods=["POST"])
@login_required
def reset_own_2fa():
    """Telefon değişti / authenticator kayboldu — kendi secret'ını sıfırla, sonraki girişte yeniden kurulum ister."""
    data = request.get_json(silent=True) or {}
    current_password = (data.get("current_password") or "").strip()
    username = session.get("admin_username")
    if not current_password:
        return jsonify({"error": "Onay için mevcut şifreni gir."}), 400
    if not verify_admin(username, current_password):
        return jsonify({"error": "Şifre hatalı."}), 401
    with closing(get_db()) as conn:
        execute(
            conn,
            "UPDATE admin_users SET totp_secret = '', two_factor_enabled = 0 WHERE LOWER(username) = ?",
            (normalize_username(username),),
        )
        conn.commit()
    audit("2fa_self_reset")
    return jsonify({"ok": True})


@app.route("/api/admin/audit-log", methods=["GET"])
@admin_only_required
def get_audit_log():
    limit = min(int(request.args.get("limit", 300) or 300), 1000)
    username_filter = (request.args.get("username") or "").strip() or None
    with closing(get_db()) as conn:
        rows = fetch_audit_log(conn, limit=limit, username=username_filter)
    return jsonify({"entries": [dict(r) for r in rows]})


@app.route("/api/settings", methods=["GET"])
@admin_only_required
def get_settings():
    return jsonify({
        "public_base_url": get_server_base_url(),
        "database": "postgresql" if uses_postgres() else "sqlite",
        "database_persistent": uses_postgres(),
        "database_warning": (
            None if uses_postgres() else
            "SQLite kullanılıyor — Render'da her deploy verileri siler. PostgreSQL bağlayın."
        ),
        "telegram_enabled": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "current_user": session.get("admin_username"),
        "current_role": session.get("admin_role"),
        "permissions": get_session_permissions(),
        "custom_domain_hint": (
            "Render → Settings → Custom Domain ekleyin, "
            "sonra PUBLIC_BASE_URL ortam değişkenini ayarlayın."
        ),
    })


@app.route("/api/stats", methods=["GET"])
@permission_required("tracking.dashboard")
def stats():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))
    period = request.args.get("period", "all")
    date_sql, date_params = sessions_date_clause(period)

    with closing(get_db()) as conn:
        online_count = scalar(
            conn,
            "SELECT COUNT(*) FROM visitor_sessions WHERE last_seen_at >= ?",
            (cutoff,),
        )
        total_sessions = scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            """,
            date_params,
        )
        total_links = scalar(conn, "SELECT COUNT(*) FROM tracked_links")

        if uses_postgres():
            total_clicks = scalar(
                conn,
                f"""
                SELECT COALESCE(SUM(
                    jsonb_array_length(COALESCE(NULLIF(vs.game_log, '')::jsonb, '[]'::jsonb))
                ), 0)
                FROM visitor_sessions vs
                INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
                WHERE 1=1{date_sql}
                """,
                date_params,
            )
        else:
            total_clicks = scalar(
                conn,
                f"""
                SELECT COALESCE(SUM(json_array_length(COALESCE(vs.game_log, '[]'))), 0)
                FROM visitor_sessions vs
                INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
                WHERE 1=1{date_sql}
                """,
                date_params,
            )

        top_domain_row = fetchone(
            conn,
            f"""
            SELECT vs.domain, COUNT(*) AS cnt FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            GROUP BY vs.domain ORDER BY cnt DESC LIMIT 1
            """,
            date_params,
        )
        top_channel_row = fetchone(
            conn,
            f"""
            SELECT CASE WHEN vs.ref_code = '' OR vs.ref_code IS NULL
                        THEN 'Direkt giriş' ELSE vs.ref_code END AS ch,
                   COUNT(*) AS cnt
            FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE 1=1{date_sql}
            GROUP BY ch ORDER BY cnt DESC LIMIT 1
            """,
            date_params,
        )

    return jsonify({
        "online_count": online_count or 0,
        "total_sessions": total_sessions or 0,
        "total_links": total_links or 0,
        "total_clicks": total_clicks or 0,
        "period": period,
        "kpi": {
            "online": online_count or 0,
            "unique_visitors": total_sessions or 0,
            "top_domain": top_domain_row["domain"] if top_domain_row else "—",
            "top_domain_count": top_domain_row["cnt"] if top_domain_row else 0,
            "top_channel": top_channel_row["ch"] if top_channel_row else "—",
            "top_channel_count": top_channel_row["cnt"] if top_channel_row else 0,
        },
    })


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(APP_DIR / "static", filename)


from accounting_routes import create_accounting_blueprint
from smartico_routes import create_smartico_blueprint
from blink_routes import create_blink_blueprint
from makrolink_routes import create_makrolink_blueprint
from mailing_routes import create_mailing_blueprint, create_mailing_click_blueprint
import makrolink_api

app.register_blueprint(create_accounting_blueprint(permission_required))
app.register_blueprint(create_smartico_blueprint(permission_required, superadmin_required))
app.register_blueprint(create_blink_blueprint(permission_required, superadmin_required))
app.register_blueprint(create_makrolink_blueprint(permission_required, admin_only_required))
app.register_blueprint(create_mailing_blueprint(permission_required))
app.register_blueprint(create_mailing_click_blueprint())


@app.before_request
def makrolink_host_short_codes():
    """makrovip.com/AbC123 → redirect (panel host'taki /admin vs. dokunulmaz)."""
    host = (request.host or "").split(":")[0].strip().lower()
    path = (request.path or "/").strip("/")
    if not path or "/" in path:
        return None
    if path.lower() in makrolink_api.RESERVED_PATHS:
        return None
    # Only short-code paths on the configured public host (or www)
    try:
        with closing(get_db()) as conn:
            if not makrolink_api.is_makrolink_host(host, conn):
                return None
            dest = makrolink_api.record_click_and_resolve(
                conn,
                path,
                ip=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
                user_agent=request.headers.get("User-Agent", ""),
                referer=request.headers.get("Referer", ""),
                short_host=host,
            )
    except Exception:
        return None
    if not dest:
        return ("Link bulunamadı veya pasif.", 404)
    return redirect(dest, code=302)


def _run_startup():
    init_db()


# Werkzeug reloader açıkken parent process'te init atlanır (çift migration / kilit riski)
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or os.environ.get("FLASK_RELOAD", "0") not in ("1", "true", "yes"):
    _run_startup()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # debug=True iken use_reloader varsayılan açık kalır; dosya kaydı sırasında
    # yarım kalan kod import hatasıyla sunucuyu düşürür. Reload varsayılan kapalı.
    debug = os.environ.get("FLASK_DEBUG", "1").strip().lower() in ("1", "true", "yes")
    use_reloader = os.environ.get("FLASK_RELOAD", "0").strip().lower() in ("1", "true", "yes")
    print("\n  Merkezi Analiz Sunucusu")
    print("  ─────────────────────────")
    print(f"  Admin Panel : http://127.0.0.1:{port}/admin")
    if not _is_prod:
        print("  Giriş       : admin / makro123 (varsayılan, yerel geliştirme)")
    print(f"  Demo Site   : http://127.0.0.1:{port}/demo")
    if debug and not use_reloader:
        print("  Mod         : debug açık, otomatik reload kapalı (stabil)")
    elif use_reloader:
        print("  Mod         : otomatik reload açık (FLASK_RELOAD=1)")
    print("  Durdurmak için: Ctrl + C\n")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=use_reloader)
