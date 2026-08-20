"""Alibaba prepaid mail kredisi — panel havuzu + tenant bölüşümü.

Alibaba’da satın alınan paket (örn. 500.000) panelde tutulur; her başarılı
gönderimde global + (varsa) tenant kredisi düşer. Live API sync opsiyonel;
kaynak doğruluk paneldedir.
"""

from __future__ import annotations

from database import execute, fetchall, fetchone, get_mail_setting, scalar, upsert_mail_setting

SETTING_TOTAL = "mail_credit_total"
SETTING_USED = "mail_credit_used"
DEFAULT_TOTAL = 500_000


def _clamp_int(raw, default: int, lo: int = 0, hi: int = 50_000_000) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def get_credit_total(conn) -> int:
    return _clamp_int(get_mail_setting(conn, SETTING_TOTAL, str(DEFAULT_TOTAL)), DEFAULT_TOTAL)


def get_credit_used(conn) -> int:
    return _clamp_int(get_mail_setting(conn, SETTING_USED, "0"), 0)


def set_credit_total(conn, total: int) -> int:
    n = _clamp_int(total, DEFAULT_TOTAL, lo=0)
    used = get_credit_used(conn)
    if used > n:
        # Top-up / azaltmada used > total olmasın
        upsert_mail_setting(conn, SETTING_USED, str(n))
    upsert_mail_setting(conn, SETTING_TOTAL, str(n))
    return n


def set_credit_used(conn, used: int) -> int:
    total = get_credit_total(conn)
    n = _clamp_int(used, 0, lo=0, hi=total)
    upsert_mail_setting(conn, SETTING_USED, str(n))
    return n


def top_up_credits(conn, amount: int) -> dict:
    """Pakete ek kredi ekle (toplam artar, used aynı kalır)."""
    add = max(0, int(amount or 0))
    total = get_credit_total(conn) + add
    upsert_mail_setting(conn, SETTING_TOTAL, str(total))
    return credit_snapshot(conn)


def ensure_credit_defaults(conn) -> None:
    raw_t = (get_mail_setting(conn, SETTING_TOTAL, "") or "").strip()
    if not raw_t:
        upsert_mail_setting(conn, SETTING_TOTAL, str(DEFAULT_TOTAL))
    raw_u = (get_mail_setting(conn, SETTING_USED, "") or "").strip()
    if not raw_u:
        upsert_mail_setting(conn, SETTING_USED, "0")
    # Tenant kolonları
    try:
        from mail_tenant import _add_column, _table_columns
        cols = _table_columns(conn, "mail_tenants")
        if cols:
            if "credit_allocated" not in cols:
                _add_column(conn, "mail_tenants", "credit_allocated INTEGER NOT NULL DEFAULT 0")
            if "credit_used" not in cols:
                _add_column(conn, "mail_tenants", "credit_used INTEGER NOT NULL DEFAULT 0")
    except Exception as exc:
        print(f"⚠️  mail credit tenant cols: {exc}")
    # Performans indeksleri (~50 domain + yüksek hacim)
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_mail_sends_domain_created ON mail_sends(domain_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_mail_sends_status_created ON mail_sends(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_mail_campaign_recip_camp_status ON mail_campaign_recipients(campaign_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_mail_domains_cohort ON mail_domains(warmup_cohort)",
    ):
        try:
            execute(conn, stmt)
        except Exception:
            pass


def sum_tenant_allocated(conn, *, exclude_tenant_id: int | None = None) -> int:
    sql = """
        SELECT COALESCE(SUM(credit_allocated), 0) FROM mail_tenants
        WHERE COALESCE(status, '') != 'deleted'
    """
    params: tuple = ()
    if exclude_tenant_id:
        sql += " AND id != ?"
        params = (int(exclude_tenant_id),)
    try:
        return int(scalar(conn, sql, params) or 0)
    except Exception:
        return 0


def credit_snapshot(conn) -> dict:
    total = get_credit_total(conn)
    used = get_credit_used(conn)
    remaining = max(0, total - used)
    allocated = sum_tenant_allocated(conn)
    unallocated = max(0, total - allocated)
    pct = round(100.0 * used / total, 1) if total else 0.0
    return {
        "total": total,
        "used": used,
        "remaining": remaining,
        "pct_used": pct,
        "exhausted": remaining <= 0,
        "allocated_to_tenants": allocated,
        "unallocated": unallocated,
        "source": "panel_prepaid_credit",
        "note": "Alibaba paket kredisi — panel sayacı; her başarılı gönderimde düşer.",
    }


def tenant_credit_snapshot(conn, tenant_id: int) -> dict:
    row = fetchone(conn, "SELECT * FROM mail_tenants WHERE id = ?", (int(tenant_id),))
    if not row:
        return {
            "tenant_id": tenant_id,
            "allocated": 0,
            "used": 0,
            "remaining": 0,
            "exhausted": True,
            "error": "Tenant yok",
        }
    allocated = int(row.get("credit_allocated") or 0)
    used = int(row.get("credit_used") or 0)
    remaining = max(0, allocated - used)
    # allocated=0 → sınırsız tenant payı yok; global havuzdan düşer ama tenant bloklanmaz
    # Kullanıcı firmalara bölüşüm istedi — 0 = henüz pay yok → gönderemez (strict)
    unlimited = allocated <= 0
    return {
        "tenant_id": int(tenant_id),
        "allocated": allocated,
        "used": used,
        "remaining": remaining if not unlimited else None,
        "exhausted": (not unlimited) and remaining <= 0,
        "requires_allocation": unlimited,
        "slug": row.get("slug") or "",
        "name": row.get("name") or "",
    }


def set_tenant_credit_allocated(conn, tenant_id: int, allocated: int) -> dict:
    from database import iso, utcnow

    n = _clamp_int(allocated, 0, lo=0)
    row = fetchone(conn, "SELECT credit_used FROM mail_tenants WHERE id = ?", (int(tenant_id),))
    if not row:
        raise ValueError("Tenant yok.")
    used = int(row.get("credit_used") or 0)
    if n < used:
        raise ValueError(f"Tahsis ({n}) kullanılan krediden ({used}) küçük olamaz.")
    other = sum_tenant_allocated(conn, exclude_tenant_id=int(tenant_id))
    total = get_credit_total(conn)
    if other + n > total:
        raise ValueError(
            f"Toplam tahsis paketi aşıyor: diğer firmalar {other} + bu {n} > paket {total}. "
            f"Önce paketi büyüt veya diğer tahsisleri düşür."
        )
    execute(
        conn,
        "UPDATE mail_tenants SET credit_allocated = ?, updated_at = ? WHERE id = ?",
        (n, iso(utcnow()), int(tenant_id)),
    )
    return tenant_credit_snapshot(conn, tenant_id)


def can_consume(conn, count: int = 1, *, tenant_id: int | None = None) -> tuple[bool, str, dict]:
    """Kampanya kuyruğu / gönderim öncesi kredi yeterliliği."""
    need = max(0, int(count or 0))
    snap = credit_snapshot(conn)
    tenant_snap = tenant_credit_snapshot(conn, tenant_id) if tenant_id else None
    if need <= 0:
        return True, "", {"global": snap, "tenant": tenant_snap}
    if snap["remaining"] <= 0:
        return (
            False,
            f"Mail kredisi bitti ({snap['used']}/{snap['total']}). Paketi yenile / top-up yap.",
            {"global": snap, "tenant": tenant_snap},
        )
    if need > snap["remaining"]:
        return (
            False,
            f"Mail kredisi yetersiz: kalan {snap['remaining']}, ihtiyaç {need} (paket {snap['total']}).",
            {"global": snap, "tenant": tenant_snap},
        )
    if tenant_id and tenant_snap:
        if tenant_snap.get("requires_allocation"):
            return (
                False,
                "Bu firmaya henüz mail kredisi tahsis edilmedi. Platform → Tenant’tan kredi bölüştür.",
                {"global": snap, "tenant": tenant_snap},
            )
        rem = int(tenant_snap.get("remaining") or 0)
        if rem <= 0:
            return (
                False,
                f"Firma kredisi bitti ({tenant_snap['used']}/{tenant_snap['allocated']}).",
                {"global": snap, "tenant": tenant_snap},
            )
        if need > rem:
            return (
                False,
                f"Firma kredisi yetersiz: kalan {rem}, ihtiyaç {need}.",
                {"global": snap, "tenant": tenant_snap},
            )
    return True, "", {"global": snap, "tenant": tenant_snap}


def credit_blocks_send(conn, *, tenant_id: int | None = None) -> tuple[bool, str]:
    ok, err, _ = can_consume(conn, 1, tenant_id=tenant_id)
    return (not ok), err


def consume_credit(conn, *, tenant_id: int | None = None, n: int = 1) -> bool:
    """Başarılı gönderim sonrası kredi düş. False = kredi yoktu (yine de düşmeye çalışmaz)."""
    need = max(1, int(n or 1))
    ok, _, _ = can_consume(conn, need, tenant_id=tenant_id)
    if not ok:
        return False
    used = get_credit_used(conn) + need
    total = get_credit_total(conn)
    upsert_mail_setting(conn, SETTING_USED, str(min(used, total)))
    if tenant_id:
        row = fetchone(
            conn,
            "SELECT credit_allocated, credit_used FROM mail_tenants WHERE id = ?",
            (int(tenant_id),),
        )
        if row and int(row.get("credit_allocated") or 0) > 0:
            tu = int(row.get("credit_used") or 0) + need
            ta = int(row.get("credit_allocated") or 0)
            execute(
                conn,
                "UPDATE mail_tenants SET credit_used = ? WHERE id = ?",
                (min(tu, ta), int(tenant_id)),
            )
    return True


def list_tenant_credits(conn) -> list[dict]:
    rows = fetchall(
        conn,
        """
        SELECT id, slug, name, status, credit_allocated, credit_used, max_sends_day
        FROM mail_tenants
        WHERE COALESCE(status, '') != 'deleted'
        ORDER BY id ASC
        """,
    ) or []
    out = []
    for r in rows:
        d = dict(r)
        allocated = int(d.get("credit_allocated") or 0)
        used = int(d.get("credit_used") or 0)
        d["credit_remaining"] = max(0, allocated - used) if allocated > 0 else None
        out.append(d)
    return out
