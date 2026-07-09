import csv
import io
import json
import os
import re
from functools import wraps
from urllib.parse import urlparse
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analytics.db"

# ── Admin Giriş Ayarları (Render panelinde Environment Variables ile değiştirebilirsin) ──
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "makro123")
SECRET_KEY = os.environ.get("SECRET_KEY", "makrobet-analytics-gizli-anahtar-degistir")

ONLINE_THRESHOLD_SECONDS = 90

app = Flask(__name__)
app.secret_key = SECRET_KEY


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


def parse_iso(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracked_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(domain, ref_code)
            );

            CREATE TABLE IF NOT EXISTS visitor_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                tracked_link_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL,
                started_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                games TEXT NOT NULL DEFAULT '[]',
                game_log TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY (tracked_link_id) REFERENCES tracked_links(id)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_last_seen
                ON visitor_sessions(last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_link
                ON visitor_sessions(tracked_link_id);
            """
        )
        conn.commit()
    migrate_schema()
    migrate_domains()


def migrate_schema():
    """Yeni kolonları mevcut veritabanına ekler."""
    with closing(get_db()) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(visitor_sessions)").fetchall()}
        if "ip_address" not in cols:
            conn.execute(
                "ALTER TABLE visitor_sessions ADD COLUMN ip_address TEXT NOT NULL DEFAULT ''"
            )
        if "user_agent" not in cols:
            conn.execute(
                "ALTER TABLE visitor_sessions ADD COLUMN user_agent TEXT NOT NULL DEFAULT ''"
            )
        conn.commit()


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


def migrate_domains():
    """Eski yanlış kayıtları düzeltir; yerel test için localhost ekler."""
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT id, domain FROM tracked_links").fetchall()
        for row in rows:
            fixed = normalize_domain(row["domain"])
            if fixed and fixed != row["domain"]:
                try:
                    conn.execute(
                        "UPDATE tracked_links SET domain = ? WHERE id = ?",
                        (fixed, row["id"]),
                    )
                except sqlite3.IntegrityError:
                    conn.execute("DELETE FROM tracked_links WHERE id = ?", (row["id"],))

        has_local = conn.execute(
            """
            SELECT 1 FROM tracked_links
            WHERE domain IN ('localhost', '127.0.0.1') LIMIT 1
            """
        ).fetchone()
        if not has_local:
            conn.execute(
                """
                INSERT INTO tracked_links (domain, ref_code, created_at)
                VALUES ('localhost', '', ?)
                """,
                (iso(utcnow()),),
            )
        conn.commit()


def cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.after_request
def after_request(response):
    return cors_headers(response)


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
            row = conn.execute(
                f"SELECT * FROM tracked_links WHERE domain IN ({placeholders}) AND ref_code = ?",
                (*domains, ref_code),
            ).fetchone()
            if row:
                return dict(row)
        row = conn.execute(
            f"SELECT * FROM tracked_links WHERE domain IN ({placeholders}) AND ref_code = ''",
            domains,
        ).fetchone()
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


def session_to_dict(row, now=None):
    now = now or utcnow()
    last_seen = parse_iso(row["last_seen_at"])
    is_online = last_seen and (now - last_seen).total_seconds() <= ONLINE_THRESHOLD_SECONDS
    games = json.loads(row["games"] or "[]")
    game_log = json.loads(row["game_log"] or "[]")
    sid = row["session_id"] or ""
    ua = row["user_agent"] if "user_agent" in row.keys() else ""
    device = parse_user_agent(ua)
    return {
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
        "game_log": game_log,
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


def get_server_base_url():
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


@app.route("/")
def index():
    return redirect(url_for("admin_page"))


@app.route("/admin/login", methods=["GET", "POST"])
def login_page():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_page"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            session.permanent = True
            return redirect(url_for("admin_page"))
        error = "Kullanıcı adı veya şifre hatalı."
    return render_template("login.html", error=error)


@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/admin")
@login_required
def admin_page():
    return render_template("admin.html", server_url=get_server_base_url())


@app.route("/demo")
def demo_page():
    return render_template("demo.html", server_url=get_server_base_url())


# ── Takip Linkleri API ──


@app.route("/api/links", methods=["GET"])
@login_required
def list_links():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM tracked_links ORDER BY created_at DESC"
        ).fetchall()
    links = []
    for row in rows:
        item = dict(row)
        with closing(get_db()) as conn:
            online_count = conn.execute(
                """
                SELECT COUNT(*) FROM visitor_sessions
                WHERE tracked_link_id = ? AND last_seen_at >= ?
                """,
                (item["id"], cutoff),
            ).fetchone()[0]
        item["online_count"] = online_count
        item["tracking_code"] = build_tracking_snippet(item["domain"], item["ref_code"])
        links.append(item)
    return jsonify({"links": links})


@app.route("/api/links", methods=["POST"])
@login_required
def create_link():
    data = request.get_json(silent=True) or {}
    domain = normalize_domain(data.get("domain", ""))
    ref_code = (data.get("ref_code") or "").strip()

    if not domain:
        return jsonify({"error": "Domain zorunludur."}), 400

    created_at = iso(utcnow())
    try:
        with closing(get_db()) as conn:
            cur = conn.execute(
                """
                INSERT INTO tracked_links (domain, ref_code, created_at)
                VALUES (?, ?, ?)
                """,
                (domain, ref_code, created_at),
            )
            conn.commit()
            link_id = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM tracked_links WHERE id = ?", (link_id,)
            ).fetchone()
    except sqlite3.IntegrityError:
        if ref_code:
            return jsonify({"error": "Bu domain + referans kombinasyonu zaten kayıtlı."}), 409
        return jsonify({"error": "Bu domain zaten takip listesinde."}), 409

    item = dict(row)
    item["tracking_code"] = build_tracking_snippet(item["domain"], item["ref_code"])
    return jsonify({"link": item}), 201


@app.route("/api/links/<int:link_id>", methods=["DELETE"])
@login_required
def delete_link(link_id):
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM visitor_sessions WHERE tracked_link_id = ?", (link_id,))
        cur = conn.execute("DELETE FROM tracked_links WHERE id = ?", (link_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Link bulunamadı."}), 404
    return jsonify({"ok": True})


def build_tracking_snippet(domain, ref_code):
    base = get_server_base_url()
    label = f"{domain} / {ref_code}" if ref_code else f"{domain} (tüm site)"
    return (
        f"<!-- Affiliate Takip: {label} -->\n"
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
    with closing(get_db()) as conn:
        existing = conn.execute(
            "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE visitor_sessions
                SET last_seen_at = ?, domain = ?, ref_code = ?, tracked_link_id = ?,
                    ip_address = ?, user_agent = ?
                WHERE session_id = ?
                """,
                (now, domain, ref_code, link["id"], client_ip, user_agent, session_id),
            )
            row = conn.execute(
                "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        else:
            conn.execute(
                """
                INSERT INTO visitor_sessions
                (session_id, tracked_link_id, domain, ref_code, started_at, last_seen_at,
                 ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, link["id"], domain, ref_code, now, now, client_ip, user_agent),
            )
            row = conn.execute(
                "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        conn.commit()

    session = session_to_dict(row)
    return jsonify({
        "tracked": True,
        "session_id": session_id,
        "total_seconds": session["total_seconds"],
        "games": session["games"],
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
        conn.execute(
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
        row = conn.execute(
            "SELECT * FROM visitor_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Oturum bulunamadı"}), 404

        games = json.loads(row["games"] or "[]")
        game_log = json.loads(row["game_log"] or "[]")

        if game not in games:
            games.append(game)
        game_log.append({"game": game, "time": now, "elapsed": elapsed})

        conn.execute(
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
        conn.execute(
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
@login_required
def online_users():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))

    with closing(get_db()) as conn:
        rows = conn.execute(
            """
            SELECT vs.* FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            WHERE vs.last_seen_at >= ?
            ORDER BY vs.last_seen_at DESC
            """,
            (cutoff,),
        ).fetchall()

    users = [session_to_dict(row, now) for row in rows]
    return jsonify({"count": len(users), "users": users})


@app.route("/api/sessions", methods=["GET"])
@login_required
def all_sessions():
    now = utcnow()
    with closing(get_db()) as conn:
        rows = conn.execute(
            """
            SELECT vs.* FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            ORDER BY vs.last_seen_at DESC
            """
        ).fetchall()

    sessions = [session_to_dict(row, now) for row in rows]
    return jsonify({"sessions": sessions})


@app.route("/api/sessions/<session_id>/journey", methods=["GET"])
@login_required
def session_journey(session_id):
    now = utcnow()
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT vs.* FROM visitor_sessions vs WHERE vs.session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return jsonify({"error": "Oturum bulunamadı"}), 404
    data = session_to_dict(row, now)
    return jsonify({"session": data, "timeline": build_journey(data)})


@app.route("/api/charts", methods=["GET"])
@login_required
def chart_data():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))

    with closing(get_db()) as conn:
        domain_rows = conn.execute(
            """
            SELECT
                vs.domain,
                COUNT(*) AS total_players,
                SUM(CASE WHEN vs.last_seen_at >= ? THEN 1 ELSE 0 END) AS online_now,
                SUM(vs.total_seconds) AS total_seconds
            FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            GROUP BY vs.domain
            ORDER BY total_players DESC
            """,
            (cutoff,),
        ).fetchall()

        click_rows = conn.execute(
            "SELECT vs.domain, vs.game_log FROM visitor_sessions vs"
        ).fetchall()

        ref_rows = conn.execute(
            """
            SELECT
                CASE WHEN vs.ref_code = '' OR vs.ref_code IS NULL
                     THEN 'Direkt giriş' ELSE vs.ref_code END AS channel,
                COUNT(*) AS members,
                SUM(CASE WHEN vs.last_seen_at >= ? THEN 1 ELSE 0 END) AS online_now
            FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            GROUP BY channel
            ORDER BY members DESC
            """,
            (cutoff,),
        ).fetchall()

        game_rows = conn.execute(
            """
            SELECT vs.game_log FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            """
        ).fetchall()

    game_counts = {}
    domain_clicks = {}
    for row in game_rows:
        for ev in json.loads(row[0] or "[]"):
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
@login_required
def export_data():
    now = utcnow()
    with closing(get_db()) as conn:
        links = [dict(r) for r in conn.execute("SELECT * FROM tracked_links").fetchall()]
        sessions = [
            session_to_dict(r, now)
            for r in conn.execute(
                """
                SELECT vs.* FROM visitor_sessions vs
                INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
                """
            ).fetchall()
        ]
    return jsonify({"exported_at": iso(now), "links": links, "sessions": sessions})


@app.route("/api/data/export.csv", methods=["GET"])
@login_required
def export_csv():
    now = utcnow()
    with closing(get_db()) as conn:
        rows = conn.execute(
            """
            SELECT vs.* FROM visitor_sessions vs
            INNER JOIN tracked_links tl ON tl.id = vs.tracked_link_id
            ORDER BY vs.last_seen_at DESC
            """
        ).fetchall()
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
@login_required
def clear_sessions():
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM visitor_sessions")
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/stats", methods=["GET"])
@login_required
def stats():
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS))

    with closing(get_db()) as conn:
        online_count = conn.execute(
            "SELECT COUNT(*) FROM visitor_sessions WHERE last_seen_at >= ?",
            (cutoff,),
        ).fetchone()[0]

        total_sessions = conn.execute("SELECT COUNT(*) FROM visitor_sessions").fetchone()[0]
        total_links = conn.execute("SELECT COUNT(*) FROM tracked_links").fetchone()[0]

        log_rows = conn.execute("SELECT game_log FROM visitor_sessions").fetchall()
        total_clicks = sum(len(json.loads(r[0] or "[]")) for r in log_rows)

        top_domain_row = conn.execute(
            """
            SELECT domain, COUNT(*) AS cnt FROM visitor_sessions
            GROUP BY domain ORDER BY cnt DESC LIMIT 1
            """
        ).fetchone()
        top_channel_row = conn.execute(
            """
            SELECT CASE WHEN ref_code = '' OR ref_code IS NULL
                        THEN 'Direkt giriş' ELSE ref_code END AS ch,
                   COUNT(*) AS cnt
            FROM visitor_sessions GROUP BY ch ORDER BY cnt DESC LIMIT 1
            """
        ).fetchone()

    return jsonify({
        "online_count": online_count,
        "total_sessions": total_sessions,
        "total_links": total_links,
        "total_clicks": total_clicks or 0,
        "kpi": {
            "online": online_count,
            "unique_visitors": total_sessions,
            "top_domain": top_domain_row["domain"] if top_domain_row else "—",
            "top_domain_count": top_domain_row["cnt"] if top_domain_row else 0,
            "top_channel": top_channel_row["ch"] if top_channel_row else "—",
            "top_channel_count": top_channel_row["cnt"] if top_channel_row else 0,
        },
    })


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(APP_DIR / "static", filename)


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("\n  Merkezi Analiz Sunucusu")
    print("  ─────────────────────────")
    print(f"  Admin Panel : http://127.0.0.1:{port}/admin")
    print("  Giriş       : admin / makro123")
    print(f"  Demo Site   : http://127.0.0.1:{port}/demo")
    print("  Durdurmak için: Ctrl + C\n")
    app.run(host="0.0.0.0", port=port, debug=True)
