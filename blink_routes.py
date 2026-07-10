"""bl.ink link raporu API rotaları — Smartico entegrasyonundan bağımsız."""

from contextlib import closing

from flask import Blueprint, jsonify, request

import blink_api
from database import get_db

MODULE_ACCESS = ("tracking.blink",)


def create_blink_blueprint(permission_required, admin_only_required=None):
    bp = Blueprint("blink", __name__, url_prefix="/api/blink")

    def perm(*keys):
        return permission_required(*keys)

    def admin_only(view):
        return admin_only_required(view) if admin_only_required else view

    @bp.route("/config", methods=["GET"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def get_config():
        with closing(get_db()) as conn:
            cfg = blink_api.get_config(conn)
        return jsonify({
            "configured": bool(cfg["email"] and cfg["password"]),
            "email_masked": blink_api.mask_email(cfg["email"]) if cfg["email"] else "",
        })

    @bp.route("/config", methods=["POST"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def save_config():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip()
        password = (data.get("password") or "").strip()
        if not email or not password:
            return jsonify({"error": "Email ve şifre boş olamaz."}), 400
        with closing(get_db()) as conn:
            cfg = blink_api.save_config(conn, email, password)
            try:
                blink_api._get_access_token(conn, force=True)
            except blink_api.BlinkError as exc:
                blink_api.clear_config(conn)
                return jsonify({"error": str(exc)}), 400
        return jsonify({"configured": True, "email_masked": blink_api.mask_email(cfg["email"])})

    @bp.route("/config", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def delete_config():
        with closing(get_db()) as conn:
            blink_api.clear_config(conn)
        return jsonify({"ok": True})

    @bp.route("/links", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def links():
        force = request.args.get("force") == "1"
        with closing(get_db()) as conn:
            result = blink_api.fetch_links_with_online(conn, force=force)
        return jsonify(result)

    @bp.route("/bindings", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def list_bindings():
        with closing(get_db()) as conn:
            bindings = blink_api.get_link_bindings(conn)
        return jsonify({"bindings": bindings})

    @bp.route("/bindings", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def save_binding():
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                blink_api.save_link_binding(conn, data.get("link_id"), data.get("domain"), data.get("ref_code"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True})

    @bp.route("/bindings", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    def remove_binding():
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            blink_api.delete_link_binding(conn, data.get("link_id"))
        return jsonify({"ok": True})

    return bp
