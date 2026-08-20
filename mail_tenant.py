"""Mikromail multi-tenant + platform domain pool.

Tenants own contacts/campaigns/templates.
Domains are platform-owned and allocated to tenants (managed send).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from contextlib import closing
from functools import wraps

from flask import g, jsonify, request, session

from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    insert_returning_id,
    iso,
    scalar,
    uses_postgres,
    utcnow,
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

TENANT_TABLES = (
    "mail_contacts",
    "mail_contact_tags",
    "mail_templates",
    "mail_campaigns",
    "mail_sends",
    "mail_import_jobs",
    "mail_ivr_rules",
    "mail_ivr_events",
    "mail_crm_notes",
    "mail_crm_tasks",
    "mail_scrub_jobs",
    "mail_suppressions",
    "mail_audit_log",
)


def _table_columns(conn, table: str) -> set:
    try:
        if uses_postgres():
            rows = fetchall(
                conn,
                """
                SELECT column_name AS name FROM information_schema.columns
                WHERE table_name = ? AND table_schema = 'public'
                """,
                (table,),
            )
        else:
            rows = fetchall(conn, f"PRAGMA table_info({table})")
        out = set()
        for r in rows or []:
            d = dict(r)
            out.add((d.get("name") or d.get("column_name") or "").lower())
        return out
    except Exception:
        return set()


def _add_column(conn, table: str, col_def: str):
    try:
        execute(conn, f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except Exception:
        pass


def mailing_secret_key() -> bytes:
    raw = (os.environ.get("MAILING_SECRET_KEY") or os.environ.get("SECRET_KEY") or "dev-mail-secret").encode()
    return hashlib.sha256(raw).digest()


def encrypt_secret(plain: str) -> str:
    """Lightweight encrypt (HMAC-masked XOR stream). Prefix enc:v1:"""
    if plain is None:
        return ""
    text = str(plain)
    if not text:
        return ""
    if text.startswith("enc:v1:"):
        return text
    key = mailing_secret_key()
    data = text.encode("utf-8")
    out = bytearray()
    for i, b in enumerate(data):
        out.append(b ^ key[i % len(key)] ^ ((i * 17) & 0xFF))
    mac = hmac.new(key, bytes(out), hashlib.sha256).digest()[:16]
    return "enc:v1:" + base64.urlsafe_b64encode(mac + bytes(out)).decode("ascii")


def decrypt_secret(blob: str) -> str:
    if not blob:
        return ""
    text = str(blob)
    if not text.startswith("enc:v1:"):
        return text
    key = mailing_secret_key()
    try:
        raw = base64.urlsafe_b64decode(text[7:].encode("ascii"))
        mac, data = raw[:16], raw[16:]
        expect = hmac.new(key, data, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(mac, expect):
            return ""
        out = bytearray()
        for i, b in enumerate(data):
            out.append(b ^ key[i % len(key)] ^ ((i * 17) & 0xFF))
        return out.decode("utf-8")
    except Exception:
        return ""


def ensure_tenant_schema(conn) -> None:
    """Create tenant/domain-pool tables and add tenant_id columns."""
    now = iso(utcnow())
    if uses_postgres():
        stmts = [
            """
            CREATE TABLE IF NOT EXISTS mail_tenants (
                id SERIAL PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                plan TEXT NOT NULL DEFAULT 'starter',
                max_contacts INTEGER NOT NULL DEFAULT 500000,
                max_sends_day INTEGER NOT NULL DEFAULT 50000,
                max_domains INTEGER NOT NULL DEFAULT 5,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_tenant_users (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES mail_tenants(id) ON DELETE CASCADE,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'operator',
                permissions TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id, username)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_superadmins (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_domain_allocations (
                id SERIAL PRIMARY KEY,
                domain_id INTEGER NOT NULL REFERENCES mail_domains(id) ON DELETE CASCADE,
                tenant_id INTEGER NOT NULL REFERENCES mail_tenants(id) ON DELETE CASCADE,
                exclusive INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(domain_id, tenant_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_usage_daily (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES mail_tenants(id) ON DELETE CASCADE,
                day TEXT NOT NULL,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(tenant_id, day)
            )
            """,
        ]
    else:
        stmts = [
            """
            CREATE TABLE IF NOT EXISTS mail_tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                plan TEXT NOT NULL DEFAULT 'starter',
                max_contacts INTEGER NOT NULL DEFAULT 500000,
                max_sends_day INTEGER NOT NULL DEFAULT 50000,
                max_domains INTEGER NOT NULL DEFAULT 5,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_tenant_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL REFERENCES mail_tenants(id) ON DELETE CASCADE,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'operator',
                permissions TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id, username)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_superadmins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_domain_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_id INTEGER NOT NULL REFERENCES mail_domains(id) ON DELETE CASCADE,
                tenant_id INTEGER NOT NULL REFERENCES mail_tenants(id) ON DELETE CASCADE,
                exclusive INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(domain_id, tenant_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_usage_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL REFERENCES mail_tenants(id) ON DELETE CASCADE,
                day TEXT NOT NULL,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(tenant_id, day)
            )
            """,
        ]
    for sql in stmts:
        try:
            execute(conn, sql)
        except Exception as exc:
            print(f"⚠️  tenant schema: {exc}")

    # Domain pool columns on mail_domains
    dom_cols = _table_columns(conn, "mail_domains")
    for col, typ in (
        ("warm_status", "TEXT NOT NULL DEFAULT 'cold'"),
        ("warm_day", "INTEGER NOT NULL DEFAULT 0"),
        ("daily_cap", "INTEGER NOT NULL DEFAULT 500"),
        ("hourly_cap", "INTEGER NOT NULL DEFAULT 50"),
        ("health_score", "INTEGER NOT NULL DEFAULT 100"),
        ("smtp_password_enc", "TEXT NOT NULL DEFAULT ''"),
        ("platform_owned", "INTEGER NOT NULL DEFAULT 1"),
        # legacy = mevcut ısınmış havuz; new = yeni eklenen ısıtma domainleri
        ("warmup_cohort", "TEXT NOT NULL DEFAULT 'new'"),
        # Otomatik pause'un NEDENİ (bounce_rate=... / fail_rate=... vb.) —
        # önceden sadece server log'una yazılıyordu, panelde hiç görünmüyordu;
        # bir domain paused olduğunda kullanıcı NEDEN olduğunu göremiyordu.
        ("health_note", "TEXT NOT NULL DEFAULT ''"),
    ):
        if col not in dom_cols:
            _add_column(conn, "mail_domains", f"{col} {typ}")
    try:
        _legacy = (
            "vipozelileti.com",
            "vippozelileti.com",
            "vipppozelileti.com",
            "vipileti.com",
            "pronetmail.com",
        )
        ph = ",".join(["?"] * len(_legacy))
        execute(
            conn,
            f"""
            UPDATE mail_domains
            SET warmup_cohort = 'legacy'
            WHERE LOWER(domain) IN ({ph})
              AND COALESCE(NULLIF(warmup_cohort, ''), 'new') = 'new'
            """,
            _legacy,
        )
    except Exception as exc:
        print(f"⚠️  warmup_cohort bootstrap: {exc}")

    # Gecmis veri gizleme kesim noktasi — set edilirse (NULL degilse) o tenant'in
    # NON-superadmin oturumlari SADECE created_at >= data_visible_from olan
    # kampanya/rapor/gonderim/dashboard rakamlarini gorur. Superadmin/impersonation
    # bundan hic etkilenmez, her zaman tam gecmisi gorur. Varsayilan NULL = kisitlama yok.
    tenant_cols = _table_columns(conn, "mail_tenants")
    if "data_visible_from" not in tenant_cols:
        _add_column(conn, "mail_tenants", "data_visible_from TEXT")

    for table in TENANT_TABLES:
        cols = _table_columns(conn, table)
        if not cols:
            continue
        if "tenant_id" not in cols:
            _add_column(conn, table, "tenant_id INTEGER NOT NULL DEFAULT 1")
            try:
                execute(conn, f"UPDATE {table} SET tenant_id = 1 WHERE tenant_id IS NULL OR tenant_id = 0")
            except Exception:
                pass
        try:
            execute(conn, f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(tenant_id)")
        except Exception:
            pass

    # Bootstrap default tenant
    if not fetchone(conn, "SELECT id FROM mail_tenants WHERE slug = ?", ("makro",)):
        insert_returning_id(
            conn,
            """
            INSERT INTO mail_tenants
            (slug, name, status, plan, max_contacts, max_sends_day, max_domains, notes, created_at, updated_at)
            VALUES (?, ?, 'active', 'platform', 5000000, 500000, 50, ?, ?, ?)
            """,
            ("makro", "Makro", "Platform tenant (migrated)", now, now),
        )
    # ESKİ BUG: her ensure’da “makro tahsisi yoksa ekle” → X ile silinen makro geri geliyordu.
    # Artık otomatik tahsis YOK; operatör Domain havuzu’ndan elle bağlar.
    try:
        from database import get_mail_setting, upsert_mail_setting

        boot_flag = "makro_domain_alloc_bootstrap_v2"
        if (get_mail_setting(conn, boot_flag, "") or "").strip() != "1":
            upsert_mail_setting(conn, boot_flag, "1")
    except Exception:
        pass
    try:
        execute(conn, "UPDATE mail_domains SET platform_owned = 1 WHERE platform_owned IS NULL")
        execute(
            conn,
            "UPDATE mail_domains SET warm_status = COALESCE(NULLIF(warm_status, ''), 'cold')",
        )
    except Exception:
        pass
    try:
        heal_ready_domains(conn)
    except Exception as exc:
        print(f"⚠️  heal_ready_domains: {exc}")

    # Bootstrap superadmin from env if empty
    if not scalar(conn, "SELECT COUNT(*) FROM mail_superadmins"):
        from werkzeug.security import generate_password_hash

        user = (os.environ.get("MAILING_SUPERADMIN_USER") or os.environ.get("ADMIN_USERNAME") or "tolgakt").strip()
        pw = (os.environ.get("MAILING_SUPERADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD") or "changeme").strip()
        insert_returning_id(
            conn,
            """
            INSERT INTO mail_superadmins (username, password_hash, display_name, active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (user.lower(), generate_password_hash(pw, method="pbkdf2:sha256"), user, now),
        )
        print(f"✉️  Mikromail superadmin bootstrap: {user}")

    _strip_settings_permission_from_tenant_users(conn)
    _repair_bizzo_template_ownership(conn)


def _strip_settings_permission_from_tenant_users(conn) -> None:
    """"mailing.settings" hiçbir firma kullanıcısında kalmasın — eski satırlar
    (bu izin varsayılan listedeyken oluşturulmuş) burada temizlenir. Backend'de
    ayrıca sert blok var, bu sadece UI/veri hijyeni içindir."""
    import json

    try:
        rows = fetchall(
            conn,
            "SELECT id, permissions FROM mail_tenant_users WHERE permissions LIKE '%mailing.settings%'",
        ) or []
    except Exception:
        return
    for r in rows:
        try:
            perms = json.loads(r["permissions"] or "[]")
        except Exception:
            continue
        if "mailing.settings" not in perms:
            continue
        cleaned = [p for p in perms if p != "mailing.settings"]
        try:
            execute(
                conn,
                "UPDATE mail_tenant_users SET permissions = ? WHERE id = ?",
                (json.dumps(cleaned), int(r["id"])),
            )
        except Exception:
            pass
    try:
        conn.commit()
    except Exception:
        pass


def _repair_bizzo_template_ownership(conn) -> int:
    """Bizzo marka şablonları (seed'de "Bizzo · " önekiyle oluşturulur) tenant_id
    sütununun DEFAULT'u yüzünden yanlış tenant'ta (genelde makro) kalmış olabilir
    — INSERT'lerde tenant_id hiç belirtilmiyordu. 'bizzo' slug'lı bir tenant
    gerçekten varsa bu şablonları ona taşır; yoksa hiçbir şey yapmaz (dokunmadan
    geçer, tek-tenant kurulumları bozmaz)."""
    try:
        bizzo = fetchone(conn, "SELECT id FROM mail_tenants WHERE slug = ?", ("bizzo",))
        if not bizzo:
            return 0
        bizzo_id = int(bizzo["id"])
        cols = _table_columns(conn, "mail_templates")
        if "tenant_id" not in cols:
            return 0
        rows = fetchall(
            conn,
            "SELECT id FROM mail_templates WHERE name LIKE 'Bizzo%' AND (tenant_id IS NULL OR tenant_id != ?)",
            (bizzo_id,),
        ) or []
        if not rows:
            return 0
        for r in rows:
            execute(conn, "UPDATE mail_templates SET tenant_id = ? WHERE id = ?", (bizzo_id, int(r["id"])))
        conn.commit()
        print(f"✉️  Bizzo şablon sahipliği düzeltildi: {len(rows)} şablon → tenant_id={bizzo_id}")
        return len(rows)
    except Exception as exc:
        print(f"⚠️  Bizzo template ownership repair: {exc}")
        return 0


_STALE_DOMAIN_NOTES = (
    "NS henüz yönlendirilmedi",
    "ns henüz yönlendirilmedi",
)


def domain_has_smtp(row) -> bool:
    if not row:
        return False
    d = dict(row) if not isinstance(row, dict) else row
    plain = str(d.get("smtp_password") or "").strip()
    enc = str(d.get("smtp_password_enc") or "").strip()
    if plain and not plain.startswith("enc:v1:"):
        return True
    return bool(enc)


def heal_ready_domains(conn) -> int:
    """SMTP şifresi kayıtlı domainleri pending/unconfigured seed durumundan çıkar.

    Ayrıca info@vipileti.com gibi yanlış yazılmış domain/from_local kayıtlarını düzelt
    (gönderimde info@info@vipileti.com 535 üretmesin).
    """
    from mail_delivery import normalize_from_local, normalize_mail_domain

    rows = fetchall(
        conn,
        """
        SELECT id, domain, from_local, status, dns_status, notes,
               smtp_password, smtp_password_enc
        FROM mail_domains
        """,
    ) or []
    fixed = 0
    for r in rows:
        d = dict(r)
        # Çift @ / info@domain yazımı — SMTP olsun olmasın düzelt
        raw_domain = (d.get("domain") or "").strip()
        raw_local = (d.get("from_local") or "").strip()
        clean_domain = normalize_mail_domain(raw_domain)
        clean_local = normalize_from_local(raw_local or "info")
        if clean_domain and (clean_domain != raw_domain.lower() or "@" in raw_local or raw_local != clean_local):
            execute(
                conn,
                "UPDATE mail_domains SET domain = ?, from_local = ? WHERE id = ?",
                (clean_domain, clean_local, d["id"]),
            )
            fixed += 1
            d["domain"] = clean_domain
            d["from_local"] = clean_local

        if not domain_has_smtp(d):
            continue
        status = (d.get("status") or "").strip().lower()
        dns = (d.get("dns_status") or "").strip().lower()
        notes = (d.get("notes") or "").strip()
        notes_l = notes.lower()
        stale_note = (not notes) or any(s in notes_l for s in _STALE_DOMAIN_NOTES)
        need = status in ("pending", "draft", "") or dns in ("unconfigured", "pending", "") or stale_note
        if not need:
            continue
        new_notes = "" if stale_note else notes
        execute(
            conn,
            """
            UPDATE mail_domains
            SET status = 'active', dns_status = 'ready', notes = ?
            WHERE id = ?
            """,
            (new_notes, d["id"]),
        )
        fixed += 1
    if fixed:
        try:
            conn.commit()
        except Exception:
            pass
    return fixed


def enrich_domain_public(row) -> dict:
    """UI için smtp_password_set + okunabilir durum alanları."""
    d = dict(row) if row else {}
    ready = domain_has_smtp(d)
    d["smtp_password_set"] = ready
    d.pop("smtp_password", None)
    d.pop("smtp_password_enc", None)
    if ready:
        if (d.get("dns_status") or "").lower() in ("unconfigured", "pending", ""):
            d["dns_status"] = "ready"
        if (d.get("status") or "").lower() in ("pending", "draft", ""):
            d["status"] = "active"
        note = (d.get("notes") or "").strip()
        if any(s in note.lower() for s in _STALE_DOMAIN_NOTES):
            d["notes"] = ""
        d["ready"] = True
        d["display_status"] = "ready"
    else:
        d["ready"] = False
        d["display_status"] = (d.get("dns_status") or d.get("status") or "unconfigured")
    return d


def current_tenant_id():
    if getattr(g, "mail_is_superadmin", False):
        # Superadmin may impersonate via header / session
        hdr = (request.headers.get("X-Tenant-Id") or "").strip()
        if hdr.isdigit():
            return int(hdr)
        sid = session.get("mail_tenant_id")
        if sid:
            return int(sid)
        return None
    tid = session.get("mail_tenant_id") or getattr(g, "mail_tenant_id", None)
    return int(tid) if tid else None


def require_mail_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("mail_logged_in"):
            if (request.path or "").startswith("/api/"):
                return jsonify({"error": "Oturum gerekli."}), 401
            from flask import redirect, url_for

            return redirect("/login")
        g.mail_is_superadmin = bool(session.get("mail_is_superadmin"))
        g.mail_tenant_id = session.get("mail_tenant_id")
        g.mail_username = session.get("mail_username")
        return view(*args, **kwargs)

    return wrapped


def require_superadmin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("mail_logged_in") or not session.get("mail_is_superadmin"):
            return jsonify({"error": "Süper admin gerekli."}), 403
        return view(*args, **kwargs)

    return wrapped


def tenant_active(conn, tenant_id: int) -> bool:
    row = fetchone(conn, "SELECT status FROM mail_tenants WHERE id = ?", (tenant_id,))
    return bool(row) and (row["status"] or "") == "active"


def domain_allocated_to_tenant(conn, domain_id: int, tenant_id: int) -> bool:
    n = scalar(
        conn,
        "SELECT COUNT(*) FROM mail_domain_allocations WHERE domain_id = ? AND tenant_id = ?",
        (domain_id, tenant_id),
    )
    return bool(n)


def list_allocated_domains(conn, tenant_id: int):
    return fetchall(
        conn,
        """
        SELECT d.* FROM mail_domains d
        JOIN mail_domain_allocations a ON a.domain_id = d.id
        WHERE a.tenant_id = ?
        ORDER BY d.id ASC
        """,
        (tenant_id,),
    )


def assert_tenant_domain(conn, domain_id: int, tenant_id: int | None):
    """Raise PermissionError if tenant cannot use domain."""
    if tenant_id is None:
        # superadmin without impersonation: allow any platform domain
        row = fetchone(conn, "SELECT id FROM mail_domains WHERE id = ?", (domain_id,))
        if not row:
            raise PermissionError("Domain bulunamadı.")
        return
    if not domain_allocated_to_tenant(conn, domain_id, tenant_id):
        raise PermissionError("Bu domain tenant'a tahsis edilmemiş.")


def bump_usage(conn, tenant_id: int, *, sent: int = 0, failed: int = 0):
    if not tenant_id:
        return
    day = iso(utcnow())[:10]
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO mail_usage_daily (tenant_id, day, sent_count, failed_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (tenant_id, day) DO UPDATE SET
                sent_count = mail_usage_daily.sent_count + EXCLUDED.sent_count,
                failed_count = mail_usage_daily.failed_count + EXCLUDED.failed_count
            """,
            (tenant_id, day, int(sent), int(failed)),
        )
    else:
        row = fetchone(
            conn,
            "SELECT id, sent_count, failed_count FROM mail_usage_daily WHERE tenant_id = ? AND day = ?",
            (tenant_id, day),
        )
        if row:
            execute(
                conn,
                "UPDATE mail_usage_daily SET sent_count = ?, failed_count = ? WHERE id = ?",
                (int(row["sent_count"] or 0) + int(sent), int(row["failed_count"] or 0) + int(failed), row["id"]),
            )
        else:
            insert_returning_id(
                conn,
                "INSERT INTO mail_usage_daily (tenant_id, day, sent_count, failed_count) VALUES (?, ?, ?, ?)",
                (tenant_id, day, int(sent), int(failed)),
            )


def tenant_send_allowed(conn, tenant_id: int) -> tuple[bool, str]:
    row = fetchone(conn, "SELECT * FROM mail_tenants WHERE id = ?", (tenant_id,))
    if not row:
        return False, "Tenant yok."
    if (row["status"] or "") != "active":
        return False, "Tenant askıda."
    day = iso(utcnow())[:10]
    used = int(
        scalar(
            conn,
            "SELECT sent_count FROM mail_usage_daily WHERE tenant_id = ? AND day = ?",
            (tenant_id, day),
        )
        or 0
    )
    cap = int(row["max_sends_day"] or 0)
    if cap and used >= cap:
        return False, f"Günlük gönderim kotası doldu ({cap})."
    try:
        from mail_credit import can_consume
        ok_c, c_err, _ = can_consume(conn, 1, tenant_id=int(tenant_id))
        if not ok_c:
            return False, c_err
    except Exception:
        pass
    return True, ""


def normalize_slug(raw: str) -> str:
    s = (raw or "").strip().lower().replace("_", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def create_tenant(conn, *, slug: str, name: str, plan: str = "starter",
                  max_contacts: int = 500000, max_sends_day: int = 50000,
                  max_domains: int = 3, notes: str = "") -> int:
    slug = normalize_slug(slug)
    if not SLUG_RE.match(slug):
        raise ValueError("Geçersiz slug.")
    now = iso(utcnow())
    return insert_returning_id(
        conn,
        """
        INSERT INTO mail_tenants
        (slug, name, status, plan, max_contacts, max_sends_day, max_domains, notes, created_at, updated_at)
        VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, name.strip(), plan, max_contacts, max_sends_day, max_domains, notes or "", now, now),
    )


DEFAULT_TENANT_PERMISSIONS = [
    "module.mailing",
    "mailing.dashboard", "mailing.crm", "mailing.relations",
    "mailing.templates", "mailing.campaigns", "mailing.ivr",
    "mailing.reports",
]
# NOT: "mailing.settings" bilerek YOK — Sistem Ayarları (SMTP/domain/scrub) SADECE
# süper admin hesabında olur, firma kullanıcısına asla verilmez (backend'de de
# _mail_permission_required ayrıca sert bloklar, bkz mailing_app.py).


def create_tenant_user(conn, tenant_id: int, username: str, password: str, *,
                       role: str = "owner", display_name: str = "",
                       permissions: list | None = None) -> int:
    from werkzeug.security import generate_password_hash
    import json

    now = iso(utcnow())
    perms = json.dumps(permissions if permissions is not None else DEFAULT_TENANT_PERMISSIONS)
    return insert_returning_id(
        conn,
        """
        INSERT INTO mail_tenant_users
        (tenant_id, username, password_hash, display_name, role, permissions, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            tenant_id,
            username.strip().lower(),
            generate_password_hash(password, method="pbkdf2:sha256"),
            display_name or username,
            role,
            perms,
            now,
            now,
        ),
    )


def list_tenant_users(conn, tenant_id: int):
    return fetchall(
        conn,
        "SELECT id, tenant_id, username, display_name, role, permissions, active, "
        "created_at, updated_at FROM mail_tenant_users WHERE tenant_id = ? ORDER BY id ASC",
        (int(tenant_id),),
    )


def update_tenant_user(conn, tenant_id: int, user_id: int, *, username: str | None = None,
                       display_name: str | None = None, active: bool | None = None,
                       permissions: list | None = None) -> None:
    import json

    row = fetchone(
        conn,
        "SELECT * FROM mail_tenant_users WHERE id = ? AND tenant_id = ?",
        (int(user_id), int(tenant_id)),
    )
    if not row:
        raise ValueError("Kullanıcı bulunamadı.")
    new_username = row["username"]
    if username is not None:
        new_username = username.strip().lower()
        if not new_username:
            raise ValueError("Kullanıcı adı boş olamaz.")
        dupe = fetchone(
            conn,
            "SELECT id FROM mail_tenant_users WHERE tenant_id = ? AND LOWER(username) = ? AND id != ?",
            (int(tenant_id), new_username, int(user_id)),
        )
        if dupe:
            raise ValueError("Bu kullanıcı adı bu firmada zaten kayıtlı.")
    new_display = display_name if display_name is not None else row["display_name"]
    new_active = int(bool(active)) if active is not None else row["active"]
    new_perms = json.dumps(permissions) if permissions is not None else row["permissions"]
    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE mail_tenant_users
        SET username = ?, display_name = ?, active = ?, permissions = ?, updated_at = ?
        WHERE id = ? AND tenant_id = ?
        """,
        (new_username, new_display, new_active, new_perms, now, int(user_id), int(tenant_id)),
    )


def set_tenant_user_password(conn, tenant_id: int, user_id: int, new_password: str) -> None:
    from werkzeug.security import generate_password_hash

    if not new_password or len(new_password) < 8:
        raise ValueError("Şifre en az 8 karakter olmalı.")
    row = fetchone(
        conn,
        "SELECT id FROM mail_tenant_users WHERE id = ? AND tenant_id = ?",
        (int(user_id), int(tenant_id)),
    )
    if not row:
        raise ValueError("Kullanıcı bulunamadı.")
    now = iso(utcnow())
    execute(
        conn,
        "UPDATE mail_tenant_users SET password_hash = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
        (generate_password_hash(new_password, method="pbkdf2:sha256"), now, int(user_id), int(tenant_id)),
    )


def delete_tenant_user(conn, tenant_id: int, user_id: int) -> None:
    """Soft-delete: active=0 (denetim icin satir kalir, giris yapamaz)."""
    row = fetchone(
        conn,
        "SELECT id FROM mail_tenant_users WHERE id = ? AND tenant_id = ?",
        (int(user_id), int(tenant_id)),
    )
    if not row:
        raise ValueError("Kullanıcı bulunamadı.")
    now = iso(utcnow())
    execute(
        conn,
        "UPDATE mail_tenant_users SET active = 0, updated_at = ? WHERE id = ? AND tenant_id = ?",
        (now, int(user_id), int(tenant_id)),
    )


def get_data_visible_from(conn, tenant_id: int) -> str | None:
    if not tenant_id:
        return None
    row = fetchone(conn, "SELECT data_visible_from FROM mail_tenants WHERE id = ?", (int(tenant_id),))
    val = (row["data_visible_from"] if row else None) or None
    return val.strip() if isinstance(val, str) and val.strip() else None


def set_data_visible_from(conn, tenant_id: int, value: str | None) -> None:
    now = iso(utcnow())
    execute(
        conn,
        "UPDATE mail_tenants SET data_visible_from = ?, updated_at = ? WHERE id = ?",
        ((value or None), now, int(tenant_id)),
    )


def allocate_domain(conn, domain_id: int, tenant_id: int, *, exclusive: bool = False) -> int:
    now = iso(utcnow())
    existing = fetchone(
        conn,
        "SELECT id FROM mail_domain_allocations WHERE domain_id = ? AND tenant_id = ?",
        (domain_id, tenant_id),
    )
    if existing:
        return int(existing["id"])
    return insert_returning_id(
        conn,
        """
        INSERT INTO mail_domain_allocations (domain_id, tenant_id, exclusive, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (domain_id, tenant_id, 1 if exclusive else 0, now),
    )


def deallocate_domain(conn, domain_id: int, tenant_id: int) -> None:
    execute(
        conn,
        "DELETE FROM mail_domain_allocations WHERE domain_id = ? AND tenant_id = ?",
        (domain_id, tenant_id),
    )


def init_mail_tenant_layer():
    with closing(get_db()) as conn:
        ensure_tenant_schema(conn)
        conn.commit()
