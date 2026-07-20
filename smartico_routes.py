"""Smartico affiliate raporu API rotaları — Link Takip altyapısından bağımsız."""

import re
from contextlib import closing

from flask import Blueprint, jsonify, request

import smartico_api
from database import get_db

MODULE_ACCESS = ("tracking.smartico",)

_VALID_PERIODS = {"all", "today", "yesterday", "7days", "30days"}
_CUSTOM_PERIOD_RE = re.compile(r"^custom:\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$")


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
        if period not in _VALID_PERIODS and not _CUSTOM_PERIOD_RE.match(period):
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

    # --- TAP int-api: Üye Taşıma (AFF_MOVE_AFFILIATE cid 30062) ---

    @bp.route("/int-config", methods=["GET"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def get_int_config():
        with closing(get_db()) as conn:
            cfg = smartico_api.ensure_makro_int_defaults(conn)
            configured = smartico_api.is_int_configured(conn)
        return jsonify({
            "configured": configured,
            "int_api_base": cfg["int_api_base"],
            "authorization_token_masked": (
                smartico_api.mask_key(cfg["authorization_token"]) if cfg["authorization_token"] else ""
            ),
            "label_id": cfg["label_id"],
            "brand_id": cfg["brand_id"],
            "default_affiliate_id": cfg.get("default_affiliate_id"),
        })

    @bp.route("/int-config", methods=["POST"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def save_int_config():
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                # Token boşsa mevcut token korunur (sadece label/brand güncelleme)
                existing = smartico_api.get_int_config(conn)
                token = (data.get("authorization_token") or "").strip() or existing["authorization_token"]
                # default_affiliate_id gönderilmezse mevcut korunur
                default_aff = data.get("default_affiliate_id", existing.get("default_affiliate_id"))
                cfg = smartico_api.save_int_config(
                    conn,
                    authorization_token=token,
                    label_id=data.get("label_id"),
                    brand_id=data.get("brand_id"),
                    int_api_base=data.get("int_api_base"),
                    default_affiliate_id=default_aff,
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({
            "configured": True,
            "int_api_base": cfg["int_api_base"],
            "authorization_token_masked": smartico_api.mask_key(cfg["authorization_token"]),
            "label_id": cfg["label_id"],
            "brand_id": cfg["brand_id"],
            "default_affiliate_id": cfg.get("default_affiliate_id"),
        })

    @bp.route("/int-config", methods=["DELETE"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def delete_int_config():
        with closing(get_db()) as conn:
            smartico_api.clear_int_config(conn)
        return jsonify({"ok": True})

    @bp.route("/lookup-player", methods=["GET"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def lookup_player():
        """Oyuncu ID / registration_id / username ile mevcut kanal kayıtlarını getir."""
        ext_id = (
            (request.args.get("ext_customer_id") or "").strip()
            or (request.args.get("q") or "").strip()
        )
        if not ext_id:
            return jsonify({"error": "Oyuncu ID / registration ID / username gerekli."}), 400
        try:
            with closing(get_db()) as conn:
                result = smartico_api.lookup_player_by_ext_id(conn, ext_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except smartico_api.SmarticoError as exc:
            return jsonify({"error": str(exc)}), 502
        return jsonify(result)

    @bp.route("/move-affiliate", methods=["POST"])
    @perm(*MODULE_ACCESS)
    @admin_only
    def move_affiliate():
        """Oyuncuyu yeni affiliate/deal altına taşı (TAP cid 30062).

        affiliate_id + deal_id boşsa default_affiliate_id (normal link / kanal yok) kullanılır.
        """
        data = request.get_json(silent=True) or {}
        try:
            with closing(get_db()) as conn:
                if not smartico_api.is_int_configured(conn):
                    return jsonify({
                        "error": "not_configured",
                        "message": "Önce Üye Taşıma ayarlarını kaydet (token, label_id, brand_id).",
                    }), 400
                use_default = bool(
                    data.get("use_default")
                    or data.get("to_default")
                    or data.get("default")
                )
                result = smartico_api.move_affiliate(
                    conn,
                    ext_customer_id=data.get("ext_customer_id"),
                    affiliate_id=None if use_default else data.get("affiliate_id"),
                    deal_id=None if use_default else data.get("deal_id"),
                    utm_source=data.get("utm_source"),
                    utm_medium=data.get("utm_medium"),
                    use_default=use_default,
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except smartico_api.SmarticoError as exc:
            return jsonify({"error": str(exc)}), 502
        return jsonify(result)

    return bp
