"""Smartico affiliate raporu API rotaları — Link Takip altyapısından bağımsız."""

from contextlib import closing

from flask import Blueprint, jsonify, request

import smartico_api
from database import get_db

MODULE_ACCESS = ("tracking.smartico",)

_VALID_PERIODS = {"all", "today", "yesterday", "7days", "30days"}


def create_smartico_blueprint(permission_required, admin_only_required=None):
    bp = Blueprint("smartico", __name__, url_prefix="/api/smartico")

    def perm(*keys):
        return permission_required(*keys)

    def admin_only(view):
        return admin_only_required(view) if admin_only_required else view

    @bp.route("/config", methods=["GET"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def get_config():
        with closing(get_db()) as conn:
            cfg = smartico_api.get_config(conn)
        return jsonify({
            "configured": bool(cfg["api_key"]),
            "api_host": cfg["api_host"],
            "api_key_masked": smartico_api.mask_key(cfg["api_key"]) if cfg["api_key"] else "",
        })

    @bp.route("/config", methods=["POST"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def save_config():
        data = request.get_json(silent=True) or {}
        api_key = (data.get("api_key") or "").strip()
        api_host = (data.get("api_host") or "").strip()
        if not api_key:
            return jsonify({"error": "API anahtarı boş olamaz."}), 400
        with closing(get_db()) as conn:
            cfg = smartico_api.save_config(conn, api_key, api_host)
        return jsonify({
            "configured": True,
            "api_host": cfg["api_host"],
            "api_key_masked": smartico_api.mask_key(cfg["api_key"]),
        })

    @bp.route("/config", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def delete_config():
        with closing(get_db()) as conn:
            smartico_api.clear_config(conn)
        return jsonify({"ok": True})

    @bp.route("/report", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def report():
        period = (request.args.get("period") or "all").strip()
        if period not in _VALID_PERIODS:
            period = "all"
        force = request.args.get("force") == "1"
        with closing(get_db()) as conn:
            result = smartico_api.fetch_media_report(conn, period=period, force=force)
        return jsonify(result)

    @bp.route("/affiliates", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def list_affiliates():
        """?status=approved -> sadece Approved (2). ?status=all -> hepsi.
        Varsayılan: approved (Suspended/Blocked hariç partner listesi için).
        """
        status = (request.args.get("status") or "approved").strip().lower()
        force = request.args.get("force") == "1"
        with closing(get_db()) as conn:
            if status == "all":
                rows_raw = smartico_api.fetch_affiliates_raw(conn, status_ids=None, force=force)
            elif status == "approved":
                rows_raw = smartico_api.fetch_affiliates_raw(
                    conn, status_ids=[smartico_api.AFF_STATUS_APPROVED], force=force
                )
            else:
                return jsonify({"error": "status=approved|all"}), 400
        rows = []
        for row in rows_raw:
            aid = row.get("affiliate_id") or row.get("id")
            if aid is None:
                continue
            rows.append({
                "affiliate_id": str(aid),
                "affiliate_name": row.get("affiliate_name") or row.get("username") or f"Affiliate #{aid}",
                "aff_status_id": row.get("aff_status_id"),
                "email": row.get("email") or row.get("bo_user_email"),
                "telegram": row.get("contact_telegram") or row.get("telegram") or row.get("skype"),
                "company": row.get("company"),
                "web_site_url": row.get("web_site_url"),
                "manager_id": row.get("manager_id"),
                "create_date": row.get("create_date") or row.get("created"),
            })
        rows.sort(key=lambda r: (r["affiliate_name"] or "").lower())
        return jsonify({"rows": rows, "count": len(rows), "status_filter": status})

    @bp.route("/bindings", methods=["GET"])
    @perm(*MODULE_ACCESS)
    def list_bindings():
        with closing(get_db()) as conn:
            bindings = smartico_api.get_link_bindings(conn)
        return jsonify({"bindings": bindings})

    @bp.route("/bindings", methods=["POST"])
    @perm(*MODULE_ACCESS)
    def save_binding():
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                smartico_api.save_link_binding(
                    conn,
                    data.get("affiliate_id"),
                    data.get("link_id"),
                    data.get("domain"),
                    data.get("ref_code"),
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True})

    @bp.route("/bindings", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    def remove_binding():
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            smartico_api.delete_link_binding(conn, data.get("affiliate_id"), data.get("link_id"))
        return jsonify({"ok": True})

    return bp
