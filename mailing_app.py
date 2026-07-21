"""Mikromail — standalone mailing product (multi-tenant, domain pool).

Run: gunicorn mailing_app:app
Env: DATABASE_URL, SECRET_KEY, MAILING_SECRET_KEY, PUBLIC_BASE_URL,
     MAILING_SUPERADMIN_USER / MAILING_SUPERADMIN_PASSWORD
"""
from __future__ import annotations

import json
import os
from contextlib import closing
from datetime import timedelta
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash

from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    init_mailing_schema,
    iso,
    scalar,
    utcnow,
)
from mail_tenant import (
    allocate_domain,
    create_tenant,
    create_tenant_user,
    current_tenant_id,
    deallocate_domain,
    decrypt_secret,
    encrypt_secret,
    ensure_tenant_schema,
    init_mail_tenant_layer,
    list_allocated_domains,
    normalize_slug,
    require_mail_login,
    require_superadmin,
    tenant_active,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.environ.get("MAILING_SECRET_KEY") or "dev-mikromail"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production" or bool(
    os.environ.get("RENDER")
)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=31)
app.config["SESSION_COOKIE_NAME"] = "mikromail_session"


def _login_rate_ok(username: str) -> bool:
    # Simple in-memory throttle per process
    from time import time

    bucket = getattr(app, "_mail_login_hits", None)
    if bucket is None:
        app._mail_login_hits = {}
        bucket = app._mail_login_hits
    key = (request.remote_addr or "?") + "|" + (username or "")
    now = time()
    hits = [t for t in bucket.get(key, []) if now - t < 300]
    if len(hits) >= 20:
        bucket[key] = hits
        return False
    hits.append(now)
    bucket[key] = hits
    return True


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "mikromail"})


@app.get("/")
def root():
    if session.get("mail_logged_in"):
        return redirect("/app")
    return redirect("/login")


@app.get("/login")
def login_page():
    if session.get("mail_logged_in"):
        return redirect("/app")
    return render_template("mailing_login.html")


@app.post("/api/mail-auth/login")
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Kullanıcı ve şifre gerekli."}), 400
    if not _login_rate_ok(username):
        return jsonify({"error": "Çok fazla deneme. 5 dk bekleyin."}), 429
    with closing(get_db()) as conn:
        ensure_tenant_schema(conn)
        sa = fetchone(
            conn,
            "SELECT * FROM mail_superadmins WHERE LOWER(username) = ? AND active = 1",
            (username,),
        )
        if sa and check_password_hash(sa["password_hash"], password):
            session.clear()
            session.permanent = True
            session["mail_logged_in"] = True
            session["mail_is_superadmin"] = True
            session["mail_username"] = username
            session["mail_display_name"] = sa["display_name"] or username
            session["mail_tenant_id"] = None
            session["mail_permissions"] = ["*"]
            return jsonify({"ok": True, "role": "superadmin", "redirect": "/app"})

        # Tenant user: username may be "slug/user" or plain (search all)
        tenant_id = None
        uname = username
        if "/" in username:
            slug, uname = username.split("/", 1)
            t = fetchone(conn, "SELECT id, status FROM mail_tenants WHERE slug = ?", (normalize_slug(slug),))
            if not t:
                return jsonify({"error": "Firma / kullanıcı bulunamadı."}), 401
            if (t["status"] or "") != "active":
                return jsonify({"error": "Firma askıda."}), 403
            tenant_id = int(t["id"])
            user = fetchone(
                conn,
                "SELECT * FROM mail_tenant_users WHERE tenant_id = ? AND LOWER(username) = ? AND active = 1",
                (tenant_id, uname.strip().lower()),
            )
        else:
            users = fetchall(
                conn,
                "SELECT * FROM mail_tenant_users WHERE LOWER(username) = ? AND active = 1",
                (uname,),
            ) or []
            if len(users) > 1:
                return jsonify({"error": "Birden fazla firma eşleşti. slug/kullanici ile giriş yapın."}), 400
            user = users[0] if users else None
            if user:
                tenant_id = int(user["tenant_id"])

        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Hatalı giriş."}), 401
        if not tenant_active(conn, tenant_id):
            return jsonify({"error": "Firma askıda."}), 403

        try:
            perms = json.loads(user["permissions"] or "[]")
        except Exception:
            perms = ["module.mailing"]

        session.clear()
        session.permanent = True
        session["mail_logged_in"] = True
        session["mail_is_superadmin"] = False
        session["mail_username"] = user["username"]
        session["mail_display_name"] = user["display_name"] or user["username"]
        session["mail_tenant_id"] = tenant_id
        session["mail_user_id"] = int(user["id"])
        session["mail_permissions"] = perms
        session["mail_role"] = user["role"]
    return jsonify({"ok": True, "role": "tenant", "tenant_id": tenant_id, "redirect": "/app"})


@app.post("/api/mail-auth/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/mail-auth/me")
@require_mail_login
def api_me():
    tid = current_tenant_id()
    tenant = None
    if tid:
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT id, slug, name, status, plan FROM mail_tenants WHERE id = ?", (tid,))
            if row:
                tenant = dict(row)
    return jsonify({
        "username": session.get("mail_username"),
        "display_name": session.get("mail_display_name"),
        "is_superadmin": bool(session.get("mail_is_superadmin")),
        "tenant_id": tid,
        "tenant": tenant,
        "permissions": session.get("mail_permissions") or [],
    })


@app.post("/api/mail-auth/select-tenant")
@require_superadmin
def select_tenant():
    data = request.get_json(silent=True) or {}
    tid = data.get("tenant_id")
    if tid in (None, "", 0, "0"):
        session["mail_tenant_id"] = None
        return jsonify({"ok": True, "tenant_id": None})
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT id FROM mail_tenants WHERE id = ?", (int(tid),))
        if not row:
            return jsonify({"error": "Tenant yok."}), 404
    session["mail_tenant_id"] = int(tid)
    return jsonify({"ok": True, "tenant_id": int(tid)})


# ── Superadmin platform API ──────────────────────────────────

@app.get("/api/platform/tenants")
@require_superadmin
def platform_list_tenants():
    with closing(get_db()) as conn:
        rows = fetchall(conn, "SELECT * FROM mail_tenants ORDER BY id ASC") or []
        out = []
        for r in rows:
            d = dict(r)
            d["user_count"] = int(scalar(
                conn, "SELECT COUNT(*) FROM mail_tenant_users WHERE tenant_id = ?", (d["id"],)
            ) or 0)
            d["domain_count"] = int(scalar(
                conn, "SELECT COUNT(*) FROM mail_domain_allocations WHERE tenant_id = ?", (d["id"],)
            ) or 0)
            out.append(d)
    return jsonify({"tenants": out})


@app.post("/api/platform/tenants")
@require_superadmin
def platform_create_tenant():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    slug = normalize_slug(data.get("slug") or name)
    owner_user = (data.get("owner_username") or "admin").strip().lower()
    owner_pass = data.get("owner_password") or ""
    if not name or not slug:
        return jsonify({"error": "name/slug gerekli."}), 400
    if not owner_pass or len(owner_pass) < 8:
        return jsonify({"error": "Owner şifresi en az 8 karakter."}), 400
    try:
        with closing(get_db()) as conn:
            tid = create_tenant(
                conn,
                slug=slug,
                name=name,
                plan=(data.get("plan") or "starter").strip(),
                max_contacts=int(data.get("max_contacts") or 500000),
                max_sends_day=int(data.get("max_sends_day") or 50000),
                max_domains=int(data.get("max_domains") or 3),
                notes=(data.get("notes") or "").strip(),
            )
            create_tenant_user(conn, tid, owner_user, owner_pass, role="owner", display_name=name)
            conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Oluşturulamadı: {exc}"}), 400
    return jsonify({"ok": True, "tenant_id": tid, "login_hint": f"{slug}/{owner_user}"}), 201


@app.patch("/api/platform/tenants/<int:tenant_id>")
@require_superadmin
def platform_patch_tenant(tenant_id):
    data = request.get_json(silent=True) or {}
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT * FROM mail_tenants WHERE id = ?", (tenant_id,))
        if not row:
            return jsonify({"error": "Yok."}), 404
        now = iso(utcnow())
        execute(
            conn,
            """
            UPDATE mail_tenants SET
                name = ?, status = ?, plan = ?,
                max_contacts = ?, max_sends_day = ?, max_domains = ?,
                notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                (data.get("name") if "name" in data else row["name"]),
                (data.get("status") if "status" in data else row["status"]),
                (data.get("plan") if "plan" in data else row["plan"]),
                int(data["max_contacts"]) if "max_contacts" in data else row["max_contacts"],
                int(data["max_sends_day"]) if "max_sends_day" in data else row["max_sends_day"],
                int(data["max_domains"]) if "max_domains" in data else row["max_domains"],
                (data.get("notes") if "notes" in data else row["notes"]),
                now,
                tenant_id,
            ),
        )
        conn.commit()
        row = fetchone(conn, "SELECT * FROM mail_tenants WHERE id = ?", (tenant_id,))
    return jsonify({"tenant": dict(row)})


@app.get("/api/platform/domains")
@require_superadmin
def platform_list_domains():
    with closing(get_db()) as conn:
        rows = fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC") or []
        out = []
        for r in rows:
            d = dict(r)
            pw = d.get("smtp_password_enc") or d.get("smtp_password") or ""
            d["smtp_password_set"] = bool(pw)
            d.pop("smtp_password", None)
            d.pop("smtp_password_enc", None)
            allocs = fetchall(
                conn,
                """
                SELECT a.tenant_id, a.exclusive, t.slug, t.name
                FROM mail_domain_allocations a
                JOIN mail_tenants t ON t.id = a.tenant_id
                WHERE a.domain_id = ?
                """,
                (d["id"],),
            ) or []
            d["allocations"] = [dict(a) for a in allocs]
            out.append(d)
    return jsonify({"domains": out})


@app.post("/api/platform/domains")
@require_superadmin
def platform_create_domain():
    data = request.get_json(silent=True) or {}
    domain = (data.get("domain") or "").strip().lower()
    if not domain or "." not in domain:
        return jsonify({"error": "Geçerli domain gerekli."}), 400
    now = iso(utcnow())
    with closing(get_db()) as conn:
        if fetchone(conn, "SELECT id FROM mail_domains WHERE domain = ?", (domain,)):
            return jsonify({"error": "Domain zaten var."}), 400
        smtp_pw = (data.get("smtp_password") or "").strip()
        enc = encrypt_secret(smtp_pw) if smtp_pw else ""
        from database import insert_returning_id

        did = insert_returning_id(
            conn,
            """
            INSERT INTO mail_domains
            (domain, status, from_name, from_local, dns_status, notes, created_at,
             warm_status, warm_day, daily_cap, hourly_cap, health_score, smtp_password_enc, platform_owned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 100, ?, 1)
            """,
            (
                domain,
                (data.get("status") or "pending").strip(),
                (data.get("from_name") or "VIP").strip(),
                (data.get("from_local") or "noreply").strip(),
                (data.get("dns_status") or "unconfigured").strip(),
                (data.get("notes") or "").strip(),
                now,
                (data.get("warm_status") or "cold").strip(),
                int(data.get("daily_cap") or 500),
                int(data.get("hourly_cap") or 50),
                enc,
            ),
        )
        # Also store legacy smtp_password encrypted if column exists
        try:
            execute(conn, "UPDATE mail_domains SET smtp_password = ? WHERE id = ?", (enc, did))
        except Exception:
            pass
        conn.commit()
    return jsonify({"ok": True, "domain_id": did}), 201


@app.patch("/api/platform/domains/<int:domain_id>")
@require_superadmin
def platform_patch_domain(domain_id):
    data = request.get_json(silent=True) or {}
    with closing(get_db()) as conn:
        row = fetchone(conn, "SELECT * FROM mail_domains WHERE id = ?", (domain_id,))
        if not row:
            return jsonify({"error": "Yok."}), 404
        row = dict(row)
        fields = {
            "from_name": data.get("from_name", row.get("from_name")),
            "from_local": data.get("from_local", row.get("from_local")),
            "status": data.get("status", row.get("status")),
            "dns_status": data.get("dns_status", row.get("dns_status")),
            "notes": data.get("notes", row.get("notes")),
            "warm_status": data.get("warm_status", row.get("warm_status") or "cold"),
            "warm_day": int(data["warm_day"]) if "warm_day" in data else int(row.get("warm_day") or 0),
            "daily_cap": int(data["daily_cap"]) if "daily_cap" in data else int(row.get("daily_cap") or 500),
            "hourly_cap": int(data["hourly_cap"]) if "hourly_cap" in data else int(row.get("hourly_cap") or 50),
            "health_score": int(data["health_score"]) if "health_score" in data else int(row.get("health_score") or 100),
        }
        enc = row.get("smtp_password_enc") or row.get("smtp_password") or ""
        if data.get("smtp_password"):
            enc = encrypt_secret(str(data["smtp_password"]).strip())
        execute(
            conn,
            """
            UPDATE mail_domains SET
                from_name=?, from_local=?, status=?, dns_status=?, notes=?,
                warm_status=?, warm_day=?, daily_cap=?, hourly_cap=?, health_score=?,
                smtp_password_enc=?
            WHERE id=?
            """,
            (
                fields["from_name"], fields["from_local"], fields["status"], fields["dns_status"], fields["notes"],
                fields["warm_status"], fields["warm_day"], fields["daily_cap"], fields["hourly_cap"],
                fields["health_score"], enc, domain_id,
            ),
        )
        try:
            execute(conn, "UPDATE mail_domains SET smtp_password = ? WHERE id = ?", (enc, domain_id))
        except Exception:
            pass
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/platform/domains/<int:domain_id>/allocate")
@require_superadmin
def platform_allocate(domain_id):
    data = request.get_json(silent=True) or {}
    tid = int(data.get("tenant_id") or 0)
    if not tid:
        return jsonify({"error": "tenant_id gerekli."}), 400
    with closing(get_db()) as conn:
        if not fetchone(conn, "SELECT id FROM mail_domains WHERE id = ?", (domain_id,)):
            return jsonify({"error": "Domain yok."}), 404
        if not fetchone(conn, "SELECT id FROM mail_tenants WHERE id = ?", (tid,)):
            return jsonify({"error": "Tenant yok."}), 404
        aid = allocate_domain(conn, domain_id, tid, exclusive=bool(data.get("exclusive")))
        conn.commit()
    return jsonify({"ok": True, "allocation_id": aid})


@app.post("/api/platform/domains/<int:domain_id>/deallocate")
@require_superadmin
def platform_deallocate(domain_id):
    data = request.get_json(silent=True) or {}
    tid = int(data.get("tenant_id") or 0)
    with closing(get_db()) as conn:
        deallocate_domain(conn, domain_id, tid)
        conn.commit()
    return jsonify({"ok": True})


@app.get("/app")
@require_mail_login
def mail_app():
    return render_template(
        "mailing_admin.html",
        is_superadmin=bool(session.get("mail_is_superadmin")),
        display_name=session.get("mail_display_name") or session.get("mail_username"),
        tenant_id=session.get("mail_tenant_id"),
    )


def _mail_permission_required(*required_perms):
    """Adaptor: tenant session permissions (or superadmin *)."""

    def decorator(view):
        @wraps(view)
        @require_mail_login
        def wrapped(*args, **kwargs):
            if session.get("mail_is_superadmin"):
                tid = current_tenant_id()
                if tid is None and request.method not in ("GET", "HEAD", "OPTIONS"):
                    # Mutations need a selected tenant except platform APIs (already separate)
                    if (request.path or "").startswith("/api/mailing"):
                        return jsonify({"error": "Süper admin: önce tenant seçin (X-Tenant-Id veya select-tenant)."}), 400
                g.mail_tenant_id = tid
                return view(*args, **kwargs)
            perms = session.get("mail_permissions") or []
            if "*" in perms:
                return view(*args, **kwargs)
            from permissions import has_permission

            if not has_permission(perms, required_perms):
                return jsonify({"error": "Yetki yok."}), 403
            # Suspended tenant hard-stop
            tid = current_tenant_id()
            if tid:
                with closing(get_db()) as conn:
                    if not tenant_active(conn, tid):
                        return jsonify({"error": "Firma askıda."}), 403
            g.mail_tenant_id = tid
            return view(*args, **kwargs)

        return wrapped

    return decorator


def _register_mailing():
    from mailing_routes import create_mailing_blueprint, create_mailing_click_blueprint

    # External worker: do not start in-process scheduler
    os.environ.setdefault("MAILING_WORKER_EXTERNAL", "1")
    app.register_blueprint(create_mailing_blueprint(_mail_permission_required))
    app.register_blueprint(create_mailing_click_blueprint())


def _startup():
    with closing(get_db()) as conn:
        init_mailing_schema(conn)
        ensure_tenant_schema(conn)
        conn.commit()
    init_mail_tenant_layer()
    _register_mailing()
    print("✉️  Mikromail app ready (standalone)")


_startup()


# Decrypt helper for delivery layer
def get_domain_smtp_password(conn, domain_id: int) -> str:
    row = fetchone(conn, "SELECT smtp_password_enc, smtp_password FROM mail_domains WHERE id = ?", (domain_id,))
    if not row:
        return ""
    blob = (row.get("smtp_password_enc") if hasattr(row, "get") else None) or ""
    if not blob:
        blob = dict(row).get("smtp_password_enc") or dict(row).get("smtp_password") or ""
    return decrypt_secret(blob) if blob else ""
