"""Smartico affiliate raporu API rotaları — Link Takip altyapısından bağımsız."""

from contextlib import closing

from flask import Blueprint, jsonify, request

import smartico_api
from database import get_db

MODULE_ACCESS = ("tracking.smartico",)

_VALID_PERIODS = {"all", "today", "yesterday", "7days", "30days"}


def create_smartico_blueprint(permission_required):
    bp = Blueprint("smartico", __name__, url_prefix="/api/smartico")

    def perm(*keys):
        return permission_required(*keys)

    @bp.route("/config", methods=["GET"])
    @perm(*MODULE_ACCESS)
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

    return bp
