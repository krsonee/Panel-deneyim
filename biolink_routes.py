"""Bio Sayfa — admin API (/api/biolink/*) + herkese açık sayfa/tıklama rotaları (/p/<slug>)."""

from contextlib import closing

from flask import Blueprint, jsonify, redirect, render_template, request, send_file, session

import biolink_api
from database import get_db

MODULE_ACCESS = ("module.biolink", "biolink.pages")

_BIOLINK_DOMAIN_SKIP_PREFIXES = (
    "/admin", "/api/", "/static/", "/demo", "/health", "/login",
    "/uploads/biolink/", "/p/", "/site/", "/robots.txt",
)


def render_public_biolink_page(page, *, preview=False, site_mode=False):
    if preview:
        page = biolink_api.apply_preview_overrides(page, request.args)
        theme = biolink_api.theme_vars(page["theme"], page.get("accent_color") or "")
        return render_template(
            "biolink_page.html", page=page, theme=theme, preview=True,
            click_prefix=f"/p/{page['slug']}",
        )
    biolink_api.send_ga4_event(page, event_name="biolink_page_view")
    theme = biolink_api.theme_vars(page["theme"], page.get("accent_color") or "")
    domain = biolink_api.normalize_custom_domain(request.host.split(":")[0])
    on_custom = bool(page.get("custom_domain")) and domain == page["custom_domain"]
    if site_mode:
        click_prefix = f"/site/{page['slug']}"
    elif on_custom:
        click_prefix = ""
    else:
        click_prefix = f"/p/{page['slug']}"
    return render_template(
        "biolink_page.html", page=page, theme=theme, click_prefix=click_prefix,
    )


def handle_public_biolink_click(page, button_id):
    with closing(get_db()) as conn:
        dest = biolink_api.record_click_and_resolve(
            conn, page["id"], button_id,
            ip=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
            user_agent=request.headers.get("User-Agent", ""),
            referer=request.headers.get("Referer", ""),
        )
    if not dest:
        return ("Bağlantı bulunamadı veya pasif.", 404)
    button_label = next((b["label"] for b in page["buttons"] if b["id"] == button_id), "")
    biolink_api.send_ga4_event(page, event_name="biolink_click", button_label=button_label, destination_url=dest)
    return redirect(dest, code=302)


def handle_custom_domain_biolink():
    """Özel domain (örn. vippmakro.com) kök adresinde bio sayfa göster."""
    path = request.path or "/"
    if any(path.startswith(prefix) for prefix in _BIOLINK_DOMAIN_SKIP_PREFIXES):
        return None
    with closing(get_db()) as conn:
        page = biolink_api.get_public_page_by_domain(conn, request.host)
    if not page:
        return None
    if path == "/favicon.ico":
        return redirect(biolink_api.resolve_favicon_url(page), code=302)
    if path in ("", "/"):
        with closing(get_db()) as conn:
            biolink_api.record_view(conn, page["slug"])
        return render_public_biolink_page(page)
    if path.startswith("/go/"):
        tail = path[4:].strip("/")
        if tail.isdigit() and "/" not in tail:
            return handle_public_biolink_click(page, int(tail))
    return None


def create_biolink_blueprint(permission_required):
    bp = Blueprint("biolink", __name__)

    # Banner GIF'ler kaldırıldı — mevcut sayfalardaki banner referanslarını temizle (bir kez)
    try:
        biolink_api.clear_all_page_banners_once()
    except Exception as exc:
        print(f"⚠️  biolink banner clear: {exc}")

    def perm(*keys):
        return permission_required(*keys)

    # ── Admin API ──────────────────────────────────────────────
    api = Blueprint("biolink_api_bp", __name__, url_prefix="/api/biolink")

    @api.route("/button-types", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def button_types():
        return jsonify({"types": biolink_api.button_type_catalog()})

    @api.route("/themes", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def themes():
        from biolink_themes import brand_default_theme
        try:
            from panel_config import BRAND
            casino = BRAND.get("casino_name") or ""
        except Exception:
            casino = ""
        return jsonify({
            "themes": biolink_api.theme_list(),
            "heading_styles": biolink_api.heading_style_list(),
            "popup_shapes": biolink_api.popup_shape_catalog(),
            "default_theme": brand_default_theme(),
            "casino_name": casino,
        })

    @api.route("/assets", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def assets():
        with closing(get_db()) as conn:
            return jsonify(biolink_api.list_brand_assets(conn))

    @api.route("/assets/upload", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def upload_asset():
        kind = (request.form.get("kind") or "").strip().lower()
        label = (request.form.get("label") or "").strip()
        upload = request.files.get("file")
        username = (session.get("admin_username") or "").strip()
        try:
            with closing(get_db()) as conn:
                asset = biolink_api.upload_asset(
                    conn, kind, upload, label=label, created_by=username,
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"asset": asset}), 201

    @api.route("/assets/<int:asset_id>", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    def delete_asset(asset_id):
        with closing(get_db()) as conn:
            ok = biolink_api.delete_asset(conn, asset_id)
        if not ok:
            return jsonify({"error": "Dosya bulunamadı."}), 404
        return jsonify({"ok": True})

    @api.route("/assets/hide-brand", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def hide_brand_asset():
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                biolink_api.hide_brand_asset(
                    conn, data.get("key") or "", kind=data.get("kind") or "",
                )
                assets = biolink_api.list_brand_assets(conn)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "assets": assets})

    @api.route("/assets/restore-brand", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def restore_brand_assets():
        with closing(get_db()) as conn:
            biolink_api.unhide_all_brand_assets(conn)
            assets = biolink_api.list_brand_assets(conn)
        return jsonify({"ok": True, "assets": assets})

    @api.route("/pages", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def list_pages():
        with closing(get_db()) as conn:
            pages = biolink_api.list_pages(conn)
        return jsonify({"pages": pages})

    @api.route("/pages", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def create_page():
        data = request.get_json(silent=True) or {}
        username = (session.get("admin_username") or "").strip()
        try:
            with closing(get_db()) as conn:
                page = biolink_api.create_page(
                    conn,
                    title=data.get("title") or "",
                    subtitle=data.get("subtitle") or "",
                    slug=data.get("slug") or None,
                    theme=data.get("theme"),
                    accent_color=data.get("accent_color") or "",
                    avatar_url=data.get("avatar_url") or "",
                    banner_url=data.get("banner_url") or "",
                    button_shape=data.get("button_shape") or "pill",
                    ga4_measurement_id=data.get("ga4_measurement_id") or "",
                    ga4_api_secret=data.get("ga4_api_secret") or "",
                    custom_domain=data.get("custom_domain") or "",
                    favicon_url=data.get("favicon_url") or "",
                    created_by=username,
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"page": page}), 201

    @api.route("/pages/<int:page_id>", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def get_page(page_id):
        with closing(get_db()) as conn:
            page = biolink_api.get_page(conn, page_id)
        if not page:
            return jsonify({"error": "Sayfa bulunamadı."}), 404
        return jsonify({"page": page})

    @api.route("/pages/<int:page_id>", methods=["PUT"])
    @perm(*MODULE_ACCESS)
    def update_page(page_id):
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                page = biolink_api.update_page(conn, page_id, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"page": page})

    @api.route("/pages/<int:page_id>", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    def delete_page(page_id):
        with closing(get_db()) as conn:
            ok = biolink_api.delete_page(conn, page_id)
        if not ok:
            return jsonify({"error": "Sayfa bulunamadı."}), 404
        return jsonify({"ok": True})

    @api.route("/pages/<int:page_id>/duplicate", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def duplicate_page(page_id):
        username = (session.get("admin_username") or "").strip()
        try:
            with closing(get_db()) as conn:
                page = biolink_api.duplicate_page(conn, page_id, created_by=username)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"page": page}), 201

    @api.route("/pages/<int:page_id>/stats", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def page_stats(page_id):
        with closing(get_db()) as conn:
            stats = biolink_api.get_stats(conn, page_id)
        if stats is None:
            return jsonify({"error": "Sayfa bulunamadı."}), 404
        return jsonify(stats)

    @api.route("/pages/<int:page_id>/buttons", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def add_button(page_id):
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                if not biolink_api.get_page(conn, page_id, with_buttons=False):
                    return jsonify({"error": "Sayfa bulunamadı."}), 404
                btn = biolink_api.add_button(
                    conn, page_id,
                    button_type=data.get("button_type") or "link",
                    label=data.get("label") or "",
                    url=data.get("url") or "",
                    icon=data.get("icon") or "",
                    highlight=bool(data.get("highlight")),
                    badge_text=data.get("badge_text") or "",
                    is_active=data.get("is_active", True),
                    heading_style=data.get("heading_style") or "",
                    layout_col=data.get("layout_col") or "full",
                    text_align=data.get("text_align") or "left",
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"button": btn}), 201

    @api.route("/buttons/<int:button_id>", methods=["PUT"])
    @perm(*MODULE_ACCESS)
    def update_button(button_id):
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                btn = biolink_api.update_button(conn, button_id, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"button": btn})

    @api.route("/buttons/<int:button_id>", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    def delete_button(button_id):
        with closing(get_db()) as conn:
            ok = biolink_api.delete_button(conn, button_id)
        if not ok:
            return jsonify({"error": "Buton bulunamadı."}), 404
        return jsonify({"ok": True})

    @api.route("/pages/<int:page_id>/buttons/reorder", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def reorder_buttons(page_id):
        data = request.get_json(silent=True) or {}
        ids = data.get("order") or []
        with closing(get_db()) as conn:
            biolink_api.reorder_buttons(conn, page_id, ids)
        return jsonify({"ok": True})

    # ── Public sayfa + tıklama ─────────────────────────────────
    @bp.route("/uploads/biolink/<path:filename>")
    def biolink_upload_file(filename):
        path = biolink_api.biolink_upload_path(filename)
        if not path:
            return ("Dosya bulunamadı.", 404)
        return send_file(path)

    @bp.route("/p/<slug>")
    def public_page(slug):
        preview = request.args.get("preview") == "1"
        is_admin = bool(session.get("admin_logged_in"))
        with closing(get_db()) as conn:
            if preview and is_admin:
                page = biolink_api.get_page_by_slug(
                    conn, slug, active_only=False, buttons_active_only=True,
                )
            else:
                page = biolink_api.get_public_page(conn, slug)
            if not page:
                return render_template("biolink_404.html"), 404
            if not (preview and is_admin):
                biolink_api.record_view(conn, slug)
        if preview and is_admin:
            return render_public_biolink_page(page, preview=True)
        return render_public_biolink_page(page)

    @bp.route("/p/<slug>/go/<int:button_id>")
    def public_click(slug, button_id):
        with closing(get_db()) as conn:
            page = biolink_api.get_public_page(conn, slug)
        if not page:
            return ("Sayfa bulunamadı.", 404)
        return handle_public_biolink_click(page, button_id)

    @bp.route("/site/<slug>")
    def site_page(slug):
        """DNS oturana kadar gerçek site gibi test adresi: /site/vipmakro"""
        with closing(get_db()) as conn:
            page = biolink_api.get_public_page(conn, slug)
            if not page:
                return render_template("biolink_404.html"), 404
            biolink_api.record_view(conn, slug)
        return render_public_biolink_page(page, site_mode=True)

    @bp.route("/site/<slug>/go/<int:button_id>")
    def site_click(slug, button_id):
        with closing(get_db()) as conn:
            page = biolink_api.get_public_page(conn, slug)
        if not page:
            return ("Sayfa bulunamadı.", 404)
        return handle_public_biolink_click(page, button_id)

    @bp.route("/site/<slug>/favicon.ico")
    def site_favicon(slug):
        with closing(get_db()) as conn:
            page = biolink_api.get_public_page(conn, slug)
        if not page:
            return ("", 404)
        return redirect(biolink_api.resolve_favicon_url(page), code=302)

    bp.register_blueprint(api)
    return bp
