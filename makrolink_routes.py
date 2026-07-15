"""MakroLink API + public redirect rotaları."""

from contextlib import closing

from flask import Blueprint, jsonify, redirect, request

import makrolink_api
from database import get_db

MODULE_ACCESS = ("tracking.makrolink",)


def create_makrolink_blueprint(permission_required, admin_only_required=None):
    bp = Blueprint("makrolink", __name__)

    def perm(*keys):
        return permission_required(*keys)

    def admin_only(view):
        return admin_only_required(view) if admin_only_required else view

    # ── Admin API ──────────────────────────────────────────────
    api = Blueprint("makrolink_api", __name__, url_prefix="/api/makrolink")

    @api.route("/config", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def get_config():
        with closing(get_db()) as conn:
            cfg = makrolink_api.get_config(conn)
        return jsonify(cfg)

    @api.route("/config", methods=["POST"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def save_config():
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                cfg = makrolink_api.save_config(
                    conn,
                    public_host=data.get("public_host"),
                    short_hosts=data.get("short_hosts"),
                    public_scheme=data.get("public_scheme"),
                    aff_base=data.get("aff_base"),
                    ga4_measurement_id=data.get("ga4_measurement_id"),
                    ga4_api_secret=(
                        data.get("ga4_api_secret")
                        if ("ga4_api_secret" in data and str(data.get("ga4_api_secret") or "").strip())
                        else None
                    ),
                    online_domain_group=data.get("online_domain_group")
                    if "online_domain_group" in data
                    else None,
                )
            return jsonify(cfg)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @api.route("/ga4/test", methods=["POST"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def ga4_test():
        with closing(get_db()) as conn:
            result = makrolink_api.test_ga4(conn)
        status = 200 if result.get("ok") else 400
        return jsonify(result), status

    @api.route("/resync-tracking", methods=["POST"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def resync_tracking():
        """Mevcut MakroLink'leri tracked_links ile yeniden eşle (online için)."""
        with closing(get_db()) as conn:
            result = makrolink_api.resync_all_tracking(conn)
        return jsonify(result)

    @api.route("/categories", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def get_categories():
        return jsonify({"categories": makrolink_api.list_categories()})

    @api.route("/links", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def list_links():
        q = request.args.get("q") or ""
        with closing(get_db()) as conn:
            items = makrolink_api.list_links(conn, q_text=q)
        return jsonify({"links": items, "categories": makrolink_api.list_categories()})

    @api.route("/target-domains", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def target_domains():
        """Canlı casino domain grubu (Ayarlar). Eski dropdown yerine bu liste kullanılır."""
        with closing(get_db()) as conn:
            cfg = makrolink_api.get_config(conn)
        return jsonify({
            "domains": cfg.get("online_domains") or [],
            "online_domain_group": cfg.get("online_domain_group") or "",
            "count": cfg.get("online_domain_count") or 0,
            "error": cfg.get("online_group_error") or "",
        })

    @api.route("/links", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def create_link():
        from flask import session as flask_session

        data = request.get_json(silent=True) or {}
        username = (flask_session.get("admin_username") or "").strip()
        try:
            with closing(get_db()) as conn:
                item = makrolink_api.create_link(
                    conn,
                    destination_url=data.get("destination_url"),
                    label=data.get("label") or "",
                    code=data.get("code") or None,
                    affiliate_id=data.get("affiliate_id") or "",
                    smartico_link_id=data.get("smartico_link_id") or "",
                    ref_code=data.get("ref_code") or "",
                    created_by=username,
                    target_domain=data.get("target_domain") or None,
                    category=data.get("category") or "",
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"link": item}), 201

    @api.route("/links/<int:link_id>", methods=["PATCH"])
    @perm(*MODULE_ACCESS)
    def patch_link(link_id):
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                item = makrolink_api.update_link(
                    conn,
                    link_id,
                    destination_url=data.get("destination_url") if "destination_url" in data else None,
                    label=data.get("label") if "label" in data else None,
                    code=data.get("code") if "code" in data else None,
                    affiliate_id=data.get("affiliate_id") if "affiliate_id" in data else None,
                    ref_code=data.get("ref_code") if "ref_code" in data else None,
                    target_domain=data.get("target_domain") if "target_domain" in data else None,
                    category=data.get("category") if "category" in data else None,
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"link": item})

    @api.route("/links/<int:link_id>", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    def delete_link(link_id):
        with closing(get_db()) as conn:
            ok = makrolink_api.deactivate_link(conn, link_id)
        if not ok:
            return jsonify({"error": "Link bulunamadı."}), 404
        return jsonify({"ok": True})

    # ── Public redirect ────────────────────────────────────────
    @bp.route("/r/<code>")
    def redirect_short(code):
        host = (request.host or "").split(":")[0]
        with closing(get_db()) as conn:
            dest = makrolink_api.record_click_and_resolve(
                conn,
                code,
                ip=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
                user_agent=request.headers.get("User-Agent", ""),
                referer=request.headers.get("Referer", ""),
                short_host=host,
            )
        if not dest:
            return ("Link bulunamadı veya pasif.", 404)
        return redirect(dest, code=302)

    bp.register_blueprint(api)
    return bp
