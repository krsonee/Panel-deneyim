import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from permissions import normalize_permissions, ensure_module_parents

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analytics.db"

_pg_pool = None
_pg_pool_lock = threading.Lock()


def get_database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def uses_postgres():
    return get_database_url().startswith("postgres")


def _get_pg_pool():
    """Her request'te yeni TCP/SSL baglantisi acmak yavas oldugu icin (Render'da
    bazen 10-80sn'ye kadar cikabiliyor), kucuk bir havuz tutup baglantilari
    yeniden kullaniyoruz. Ilk baglantilar acilirken bir kerelik gecikme olur,
    sonrasinda getconn() aninda doner."""
    global _pg_pool
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                from psycopg2 import pool as pg_pool

                _pg_pool = pg_pool.ThreadedConnectionPool(
                    1, 8, get_database_url(), connect_timeout=10
                )
    return _pg_pool


class _PooledConnection:
    """psycopg2 baglantisini normal connection gibi kullandirir; close()
    cagrildiginda baglantiyi kapatmaz, havuza geri birakir."""

    __slots__ = ("_conn", "_pool", "_released")

    def __init__(self, conn, pool):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_pool", pool)
        object.__setattr__(self, "_released", False)

    def close(self):
        if self._released:
            return
        object.__setattr__(self, "_released", True)
        try:
            self._conn.rollback()
        except Exception:
            pass
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_db():
    database_url = get_database_url()
    if uses_postgres():
        from psycopg2.extras import RealDictCursor

        pool = _get_pg_pool()
        try:
            conn = pool.getconn()
        except Exception:
            # Havuz tukendi/bozuldu: dogrudan yeni baglanti dene (fallback).
            import psycopg2

            return psycopg2.connect(
                database_url, cursor_factory=RealDictCursor, connect_timeout=10
            )
        conn.cursor_factory = RealDictCursor
        return _PooledConnection(conn, pool)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def q(sql):
    if uses_postgres():
        return sql.replace("?", "%s")
    return sql


def execute(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(q(sql), params)
    return cur


def fetchone(conn, sql, params=()):
    cur = execute(conn, sql, params)
    return cur.fetchone()


def fetchall(conn, sql, params=()):
    cur = execute(conn, sql, params)
    return cur.fetchall()


def scalar(conn, sql, params=()):
    row = fetchone(conn, sql, params)
    if not row:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def insert_returning_id(conn, sql, params=()):
    if uses_postgres():
        sql = q(sql)
        if "RETURNING" not in sql.upper():
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row["id"] if row else None
    cur = execute(conn, sql, params)
    return cur.lastrowid


def integrity_error_type():
    if uses_postgres():
        import psycopg2

        return psycopg2.IntegrityError
    return sqlite3.IntegrityError


def iso(dt):
    return dt.isoformat()


def utcnow():
    return datetime.now(timezone.utc)


def init_schema(conn):
    if uses_postgres():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS tracked_links (
                id SERIAL PRIMARY KEY,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(domain, ref_code)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS visitor_sessions (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                tracked_link_id INTEGER NOT NULL REFERENCES tracked_links(id),
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                games TEXT NOT NULL DEFAULT '[]',
                game_log TEXT NOT NULL DEFAULT '[]',
                ip_address TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_sessions_last_seen ON visitor_sessions(last_seen_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_link ON visitor_sessions(tracked_link_id)",
            """
            CREATE TABLE IF NOT EXISTS smartico_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS smartico_link_bindings (
                id SERIAL PRIMARY KEY,
                affiliate_id TEXT NOT NULL DEFAULT '',
                link_id TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(affiliate_id, link_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS blink_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS blink_link_bindings (
                id SERIAL PRIMARY KEY,
                link_id TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS tracked_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(domain, ref_code)
            )
            """,
            """
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
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_sessions_last_seen ON visitor_sessions(last_seen_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_link ON visitor_sessions(tracked_link_id)",
            """
            CREATE TABLE IF NOT EXISTS smartico_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS smartico_link_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_id TEXT NOT NULL DEFAULT '',
                link_id TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(affiliate_id, link_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS blink_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS blink_link_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        ]
    for sql in statements:
        execute(conn, sql)
    init_accounting_schema(conn)
    conn.commit()


def get_smartico_setting(conn, key, default=None):
    val = scalar(conn, "SELECT value FROM smartico_settings WHERE key = ?", (key,))
    return val if val is not None else default


def upsert_smartico_setting(conn, key, value):
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO smartico_settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, str(value)),
        )
    else:
        execute(conn, "INSERT OR REPLACE INTO smartico_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def migrate_smartico(conn):
    execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS smartico_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
        """,
    )
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS smartico_link_bindings (
                id SERIAL PRIMARY KEY,
                affiliate_id TEXT NOT NULL DEFAULT '',
                link_id TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(affiliate_id, link_id)
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS smartico_link_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_id TEXT NOT NULL DEFAULT '',
                link_id TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(affiliate_id, link_id)
            )
            """,
        )
    conn.commit()


def get_blink_setting(conn, key, default=None):
    val = scalar(conn, "SELECT value FROM blink_settings WHERE key = ?", (key,))
    return val if val is not None else default


def upsert_blink_setting(conn, key, value):
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO blink_settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, str(value)),
        )
    else:
        execute(conn, "INSERT OR REPLACE INTO blink_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def migrate_blink(conn):
    execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS blink_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
        """,
    )
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS blink_link_bindings (
                id SERIAL PRIMARY KEY,
                link_id TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS blink_link_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL,
                ref_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
    conn.commit()


def init_accounting_schema(conn):
    if uses_postgres():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS acc_payment_methods (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                tx_type TEXT NOT NULL DEFAULT 'deposit',
                commission_rate REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, tx_type)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_finance_transactions (
                id SERIAL PRIMARY KEY,
                tx_date TEXT NOT NULL,
                payment_method_id INTEGER NOT NULL REFERENCES acc_payment_methods(id),
                tx_type TEXT NOT NULL,
                amount REAL NOT NULL,
                commission_rate REAL NOT NULL DEFAULT 0,
                commission_amount REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_expense_categories (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_expenses (
                id SERIAL PRIMARY KEY,
                expense_date TEXT NOT NULL,
                category_id INTEGER NOT NULL REFERENCES acc_expense_categories(id),
                description TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_vault_transactions (
                id SERIAL PRIMARY KEY,
                tx_date TEXT NOT NULL,
                vault_name TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_employees (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                start_date TEXT NOT NULL,
                salary REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_acc_fin_tx_date ON acc_finance_transactions(tx_date)",
            "CREATE INDEX IF NOT EXISTS idx_acc_exp_date ON acc_expenses(expense_date)",
            "CREATE INDEX IF NOT EXISTS idx_acc_vault_date ON acc_vault_transactions(tx_date)",
            """
            CREATE TABLE IF NOT EXISTS acc_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS acc_payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tx_type TEXT NOT NULL DEFAULT 'deposit',
                commission_rate REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, tx_type)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_finance_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_date TEXT NOT NULL,
                payment_method_id INTEGER NOT NULL,
                tx_type TEXT NOT NULL,
                amount REAL NOT NULL,
                commission_rate REAL NOT NULL DEFAULT 0,
                commission_amount REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (payment_method_id) REFERENCES acc_payment_methods(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_expense_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_date TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES acc_expense_categories(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_vault_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_date TEXT NOT NULL,
                vault_name TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                start_date TEXT NOT NULL,
                salary REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_acc_fin_tx_date ON acc_finance_transactions(tx_date)",
            "CREATE INDEX IF NOT EXISTS idx_acc_exp_date ON acc_expenses(expense_date)",
            "CREATE INDEX IF NOT EXISTS idx_acc_vault_date ON acc_vault_transactions(tx_date)",
            """
            CREATE TABLE IF NOT EXISTS acc_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
        ]
    for sql in statements:
        execute(conn, sql)
    seed_accounting_defaults(conn)
    conn.commit()


def seed_accounting_defaults(conn):
    defaults = ["Marketing", "Fatura Ödemesi", "Maaş Ödemesi", "Ofis Giderleri"]
    now = iso(utcnow())
    for name in defaults:
        exists = scalar(conn, "SELECT COUNT(*) FROM acc_expense_categories WHERE name = ?", (name,))
        if not exists:
            insert_returning_id(
                conn,
                "INSERT INTO acc_expense_categories (name, created_at) VALUES (?, ?)",
                (name, now),
            )


def seed_employee_departments(conn, now=None):
    now = now or iso(utcnow())
    for name in ("Risk", "Canlı Destek", "Call Center", "Finans", "Pazarlama", "Diğer"):
        exists = scalar(conn, "SELECT COUNT(*) FROM acc_employee_departments WHERE name = ?", (name,))
        if not exists:
            insert_returning_id(
                conn,
                "INSERT INTO acc_employee_departments (name, created_at) VALUES (?, ?)",
                (name, now),
            )


def seed_salary_categories(conn, now=None):
    now = now or iso(utcnow())
    defaults = [
        ("office", "Ofis personeli", 1),
        ("turkey", "Türkiye çalışanlar", 0),
        ("crypto", "Kripto maaş alacaklar", 0),
    ]
    for slug, name, is_office in defaults:
        exists = scalar(conn, "SELECT COUNT(*) FROM acc_salary_categories WHERE slug = ?", (slug,))
        if not exists:
            insert_returning_id(
                conn,
                """
                INSERT INTO acc_salary_categories (slug, name, is_office, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (slug, name, is_office, now),
            )


def migrate_schema(conn):
    if uses_postgres():
        cols = {
            r["column_name"]
            for r in fetchall(
                conn,
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'visitor_sessions'
                """,
            )
        }
    else:
        cols = {r[1] for r in execute(conn, "PRAGMA table_info(visitor_sessions)").fetchall()}

    if "ip_address" not in cols:
        execute(conn, "ALTER TABLE visitor_sessions ADD COLUMN ip_address TEXT NOT NULL DEFAULT ''")
    if "user_agent" not in cols:
        execute(conn, "ALTER TABLE visitor_sessions ADD COLUMN user_agent TEXT NOT NULL DEFAULT ''")
    conn.commit()
    migrate_admin_users(conn)
    migrate_tracked_links(conn)
    migrate_accounting_payment_methods(conn)
    migrate_accounting_currency(conn)
    migrate_accounting_settings(conn)
    migrate_accounting_employees_payroll(conn)
    migrate_accounting_employee_options(conn)
    try:
        migrate_accounting_vaults(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_accounting_vaults hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_smartico(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_smartico hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_blink(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_blink hata (atlanıyor, panel yine açılır): {exc}")


def _table_columns(conn, table_name):
    if uses_postgres():
        return {
            r["column_name"]
            for r in fetchall(
                conn,
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = ?
                """,
                (table_name,),
            )
        }
    exists = scalar(
        conn,
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    if not exists:
        return set()
    return {r[1] for r in execute(conn, f"PRAGMA table_info({table_name})").fetchall()}


def get_setting(conn, key, default=None):
    val = scalar(conn, "SELECT value FROM acc_settings WHERE key = ?", (key,))
    return val if val is not None else default


def upsert_setting(conn, key, value):
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO acc_settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, str(value)),
        )
    else:
        execute(conn, "INSERT OR REPLACE INTO acc_settings (key, value) VALUES (?, ?)", (key, str(value)))


def migrate_accounting_settings(conn):
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
        )
    conn.commit()


def migrate_accounting_employees_payroll(conn):
    cols = _table_columns(conn, "acc_employees")
    if not cols:
        return
    new_cols = [
        ("salary_category", "TEXT NOT NULL DEFAULT 'turkey'"),
        ("end_date", "TEXT"),
        ("bank_salary", "REAL NOT NULL DEFAULT 0"),
        ("crypto_salary", "REAL NOT NULL DEFAULT 0"),
        ("advance_amount", "REAL NOT NULL DEFAULT 0"),
        ("bonus_amount", "REAL NOT NULL DEFAULT 0"),
        ("crypto_wallet", "TEXT NOT NULL DEFAULT ''"),
        ("bank_iban", "TEXT NOT NULL DEFAULT ''"),
        ("bank_account_name", "TEXT NOT NULL DEFAULT ''"),
        ("location", "TEXT NOT NULL DEFAULT ''"),
        ("notes", "TEXT NOT NULL DEFAULT ''"),
    ]
    for name, typedef in new_cols:
        if name not in cols:
            execute(conn, f"ALTER TABLE acc_employees ADD COLUMN {name} {typedef}")
    conn.commit()


def migrate_accounting_employee_options(conn):
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_employee_departments (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_salary_categories (
                id SERIAL PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL UNIQUE,
                is_office INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_employee_departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_salary_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL UNIQUE,
                is_office INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
        )
    now = iso(utcnow())
    seed_employee_departments(conn, now)
    seed_salary_categories(conn, now)
    conn.commit()


def migrate_accounting_vaults(conn):
    from accounting_vault import (
        DEFAULT_VAULT_METHODS,
        DEFAULT_VAULT_OPERATION_TYPES,
        VAULT_ICONS,
        VAULT_PALETTE,
    )

    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_vaults (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '#6366f1',
                icon TEXT NOT NULL DEFAULT '💰',
                opening_usdt REAL NOT NULL DEFAULT 0,
                opening_try REAL NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_vault_methods (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_vault_operation_types (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_vaults (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '#6366f1',
                icon TEXT NOT NULL DEFAULT '💰',
                opening_usdt REAL NOT NULL DEFAULT 0,
                opening_try REAL NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_vault_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_vault_operation_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
        )

    tx_cols = _table_columns(conn, "acc_vault_transactions")
    if tx_cols:
        for name, typedef in (
            ("vault_id", "INTEGER"),
            ("method_name", "TEXT NOT NULL DEFAULT ''"),
            ("operation_type", "TEXT NOT NULL DEFAULT ''"),
            ("usdt_in", "REAL NOT NULL DEFAULT 0"),
            ("usdt_out", "REAL NOT NULL DEFAULT 0"),
            ("fee_usdt", "REAL NOT NULL DEFAULT 0"),
        ):
            if name not in tx_cols:
                execute(conn, f"ALTER TABLE acc_vault_transactions ADD COLUMN {name} {typedef}")

    now = iso(utcnow())
    for idx, method in enumerate(DEFAULT_VAULT_METHODS):
        if uses_postgres():
            execute(
                conn,
                """
                INSERT INTO acc_vault_methods (name, sort_order, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (name) DO NOTHING
                """,
                (method, idx, now),
            )
        else:
            execute(
                conn,
                """
                INSERT OR IGNORE INTO acc_vault_methods (name, sort_order, created_at)
                VALUES (?, ?, ?)
                """,
                (method, idx, now),
            )
    for idx, optype in enumerate(DEFAULT_VAULT_OPERATION_TYPES):
        if uses_postgres():
            execute(
                conn,
                """
                INSERT INTO acc_vault_operation_types (name, sort_order, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (name) DO NOTHING
                """,
                (optype, idx, now),
            )
        else:
            execute(
                conn,
                """
                INSERT OR IGNORE INTO acc_vault_operation_types (name, sort_order, created_at)
                VALUES (?, ?, ?)
                """,
                (optype, idx, now),
            )

    if tx_cols:
        # Eski kayıtlarda "Yöntem" alanına yazılmış işlem başlıklarını
        # (Devir/Masraf/Virman/Kasa Aktarım) yeni operation_type alanına taşı.
        legacy_rows = fetchall(
            conn,
            "SELECT id, method_name FROM acc_vault_transactions WHERE COALESCE(operation_type, '') = ''",
        )
        optype_lookup = {o.lower(): o for o in DEFAULT_VAULT_OPERATION_TYPES}
        for row in legacy_rows:
            method = (row["method_name"] or "").strip()
            match = optype_lookup.get(method.lower())
            if match:
                execute(
                    conn,
                    "UPDATE acc_vault_transactions SET operation_type = ?, method_name = '' WHERE id = ?",
                    (match, row["id"]),
                )

    # Önceki sürümlerde acc_vault_methods içine karışmış işlem başlıklarını temizle
    # (artık acc_vault_operation_types tablosunda ayrı yönetiliyorlar).
    stale_optype_names = fetchall(
        conn,
        "SELECT name FROM acc_vault_methods WHERE LOWER(name) IN ({})".format(
            ", ".join("?" for _ in DEFAULT_VAULT_OPERATION_TYPES)
        ),
        [o.lower() for o in DEFAULT_VAULT_OPERATION_TYPES],
    )
    for row in stale_optype_names:
        still_used = scalar(
            conn,
            "SELECT COUNT(*) FROM acc_vault_transactions WHERE method_name = ?",
            (row["name"],),
        )
        if not still_used:
            execute(conn, "DELETE FROM acc_vault_methods WHERE name = ?", (row["name"],))

    vault_count = scalar(conn, "SELECT COUNT(*) FROM acc_vaults") or 0
    if vault_count == 0:
        execute(
            conn,
            """
            INSERT INTO acc_vaults
            (name, description, color, icon, opening_usdt, opening_try, sort_order, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Ana Kasa", "Varsayılan USDT kasası", VAULT_PALETTE[0], VAULT_ICONS[0], 0, 0, 0, 1, now),
        )

    vault_rows = fetchall(conn, "SELECT id, name FROM acc_vaults")
    name_to_id = {r["name"]: r["id"] for r in vault_rows}

    if tx_cols:
        unnamed = fetchall(
            conn,
            """
            SELECT DISTINCT vault_name FROM acc_vault_transactions
            WHERE vault_name IS NOT NULL AND TRIM(vault_name) != ''
            """,
        )
        sort_order = len(vault_rows)
        for row in unnamed:
            vname = (row["vault_name"] or "").strip()
            if not vname or vname in name_to_id:
                continue
            color = VAULT_PALETTE[sort_order % len(VAULT_PALETTE)]
            icon = VAULT_ICONS[sort_order % len(VAULT_ICONS)]
            vid = insert_returning_id(
                conn,
                """
                INSERT INTO acc_vaults
                (name, description, color, icon, opening_usdt, opening_try, sort_order, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (vname, "", color, icon, 0, 0, sort_order, 1, now),
            )
            name_to_id[vname] = vid
            sort_order += 1

        if "vault_id" in (_table_columns(conn, "acc_vault_transactions") or set()):
            for vname, vid in name_to_id.items():
                execute(
                    conn,
                    """
                    UPDATE acc_vault_transactions
                    SET vault_id = ?
                    WHERE vault_id IS NULL AND vault_name = ?
                    """,
                    (vid, vname),
                )

            legacy = fetchall(
                conn,
                """
                SELECT id, tx_type, amount_usd, amount, usdt_in, usdt_out
                FROM acc_vault_transactions
                WHERE (usdt_in = 0 AND usdt_out = 0) AND (amount_usd > 0 OR amount > 0)
                """,
            )
            for row in legacy:
                amt = row["amount_usd"] or row["amount"] or 0
                if (row["tx_type"] or "") == "in":
                    execute(
                        conn,
                        "UPDATE acc_vault_transactions SET usdt_in = ?, usdt_out = 0 WHERE id = ?",
                        (amt, row["id"]),
                    )
                elif (row["tx_type"] or "") == "out":
                    execute(
                        conn,
                        "UPDATE acc_vault_transactions SET usdt_out = ?, usdt_in = 0 WHERE id = ?",
                        (amt, row["id"]),
                    )

    conn.commit()


def migrate_accounting_currency(conn):
    from accounting_fx import convert_to_all, fetch_exchange_rates

    rates = fetch_exchange_rates()
    usd_try = rates["usd_try"]
    eur_try = rates["eur_try"]

    finance_cols = [
        ("currency", "TEXT NOT NULL DEFAULT 'USD'"),
        ("amount_try", "REAL NOT NULL DEFAULT 0"),
        ("amount_usd", "REAL NOT NULL DEFAULT 0"),
        ("amount_eur", "REAL NOT NULL DEFAULT 0"),
        ("commission_amount_try", "REAL NOT NULL DEFAULT 0"),
        ("commission_amount_usd", "REAL NOT NULL DEFAULT 0"),
        ("commission_amount_eur", "REAL NOT NULL DEFAULT 0"),
        ("rate_usd_try", "REAL NOT NULL DEFAULT 0"),
        ("rate_eur_try", "REAL NOT NULL DEFAULT 0"),
    ]
    money_cols = [
        ("currency", "TEXT NOT NULL DEFAULT 'USD'"),
        ("amount_try", "REAL NOT NULL DEFAULT 0"),
        ("amount_usd", "REAL NOT NULL DEFAULT 0"),
        ("amount_eur", "REAL NOT NULL DEFAULT 0"),
        ("rate_usd_try", "REAL NOT NULL DEFAULT 0"),
        ("rate_eur_try", "REAL NOT NULL DEFAULT 0"),
    ]
    salary_cols = [
        ("currency", "TEXT NOT NULL DEFAULT 'TRY'"),
        ("salary_try", "REAL NOT NULL DEFAULT 0"),
        ("salary_usd", "REAL NOT NULL DEFAULT 0"),
        ("salary_eur", "REAL NOT NULL DEFAULT 0"),
        ("rate_usd_try", "REAL NOT NULL DEFAULT 0"),
        ("rate_eur_try", "REAL NOT NULL DEFAULT 0"),
    ]

    tables = [
        ("acc_finance_transactions", finance_cols),
        ("acc_expenses", money_cols),
        ("acc_vault_transactions", money_cols),
        ("acc_employees", salary_cols),
    ]

    for table, cols in tables:
        existing = _table_columns(conn, table)
        if not existing or "currency" in existing:
            continue
        for name, typedef in cols:
            execute(conn, f"ALTER TABLE {table} ADD COLUMN {name} {typedef}")

    fin_cols = _table_columns(conn, "acc_finance_transactions")
    if fin_cols and "amount_try" in fin_cols:
        rows = fetchall(conn, "SELECT id, amount, commission_amount FROM acc_finance_transactions WHERE amount_try = 0 AND amount > 0")
        for row in rows:
            fx = convert_to_all(row["amount"], "USD", rates)
            comm = convert_to_all(row["commission_amount"] or 0, "USD", rates)
            execute(
                conn,
                """
                UPDATE acc_finance_transactions
                SET currency = 'USD', amount_try = ?, amount_usd = ?, amount_eur = ?,
                    commission_amount_try = ?, commission_amount_usd = ?, commission_amount_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?
                WHERE id = ?
                """,
                (
                    fx["TRY"], fx["USD"], fx["EUR"],
                    comm["TRY"], comm["USD"], comm["EUR"],
                    fx["rate_usd_try"], fx["rate_eur_try"],
                    row["id"],
                ),
            )

    for table, amount_col in (("acc_expenses", "amount"), ("acc_vault_transactions", "amount")):
        cols = _table_columns(conn, table)
        if not cols or "amount_try" not in cols:
            continue
        rows = fetchall(conn, f"SELECT id, {amount_col} AS amt FROM {table} WHERE amount_try = 0 AND {amount_col} > 0")
        for row in rows:
            fx = convert_to_all(row["amt"], "USD", rates)
            execute(
                conn,
                f"""
                UPDATE {table}
                SET currency = 'USD', amount_try = ?, amount_usd = ?, amount_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?
                WHERE id = ?
                """,
                (fx["TRY"], fx["USD"], fx["EUR"], fx["rate_usd_try"], fx["rate_eur_try"], row["id"]),
            )

    emp_cols = _table_columns(conn, "acc_employees")
    if emp_cols and "salary_try" in emp_cols:
        rows = fetchall(conn, "SELECT id, salary FROM acc_employees WHERE salary_try = 0 AND salary > 0")
        for row in rows:
            fx = convert_to_all(row["salary"], "TRY", rates)
            execute(
                conn,
                """
                UPDATE acc_employees
                SET currency = 'TRY', salary_try = ?, salary_usd = ?, salary_eur = ?,
                    rate_usd_try = ?, rate_eur_try = ?
                WHERE id = ?
                """,
                (fx["TRY"], fx["USD"], fx["EUR"], fx["rate_usd_try"], fx["rate_eur_try"], row["id"]),
            )
    conn.commit()


def migrate_accounting_payment_methods(conn):
    if uses_postgres():
        cols = {
            r["column_name"]
            for r in fetchall(
                conn,
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'acc_payment_methods'
                """,
            )
        }
    else:
        table_exists = scalar(
            conn,
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='acc_payment_methods'",
        )
        if not table_exists:
            return
        cols = {r[1] for r in execute(conn, "PRAGMA table_info(acc_payment_methods)").fetchall()}

    if "tx_type" in cols:
        return

    if uses_postgres():
        execute(conn, "ALTER TABLE acc_payment_methods ADD COLUMN tx_type TEXT NOT NULL DEFAULT 'deposit'")
        execute(conn, "ALTER TABLE acc_payment_methods DROP CONSTRAINT IF EXISTS acc_payment_methods_name_key")
        execute(
            conn,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_acc_pm_name_tx_type
            ON acc_payment_methods(name, tx_type)
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE acc_payment_methods_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tx_type TEXT NOT NULL DEFAULT 'deposit',
                commission_rate REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, tx_type)
            )
            """,
        )
        execute(
            conn,
            """
            INSERT INTO acc_payment_methods_new (id, name, tx_type, commission_rate, created_at, updated_at)
            SELECT id, name, 'deposit', commission_rate, created_at, updated_at
            FROM acc_payment_methods
            """,
        )
        execute(conn, "DROP TABLE acc_payment_methods")
        execute(conn, "ALTER TABLE acc_payment_methods_new RENAME TO acc_payment_methods")
    conn.commit()


def migrate_tracked_links(conn):
    if uses_postgres():
        cols = {
            r["column_name"]
            for r in fetchall(
                conn,
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'tracked_links'
                """,
            )
        }
    else:
        cols = {r[1] for r in execute(conn, "PRAGMA table_info(tracked_links)").fetchall()}

    if "label" not in cols:
        execute(conn, "ALTER TABLE tracked_links ADD COLUMN label TEXT NOT NULL DEFAULT ''")
    conn.commit()


def migrate_admin_users(conn):
    if uses_postgres():
        cols = {
            r["column_name"]
            for r in fetchall(
                conn,
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'admin_users'
                """,
            )
        }
    else:
        cols = {r[1] for r in execute(conn, "PRAGMA table_info(admin_users)").fetchall()}

    if "role" not in cols:
        execute(conn, "ALTER TABLE admin_users ADD COLUMN role TEXT NOT NULL DEFAULT 'superadmin'")
    if "permissions" not in cols:
        execute(conn, "ALTER TABLE admin_users ADD COLUMN permissions TEXT NOT NULL DEFAULT '[\"*\"]'")
    conn.commit()

    rows = fetchall(conn, "SELECT id, username, role, permissions FROM admin_users")
    for row in rows:
        role = row.get("role") if isinstance(row, dict) else row["role"]
        raw_perms = row.get("permissions") if isinstance(row, dict) else row["permissions"]
        perms = ensure_module_parents(normalize_permissions(raw_perms))
        if not perms or (role == "superadmin" and "*" not in perms):
            execute(
                conn,
                "UPDATE admin_users SET role = ?, permissions = ? WHERE id = ?",
                ("superadmin", json.dumps(["*"]), row["id"]),
            )
        elif json.dumps(perms) != json.dumps(normalize_permissions(raw_perms)):
            execute(
                conn,
                "UPDATE admin_users SET permissions = ? WHERE id = ?",
                (json.dumps(perms), row["id"]),
            )
    conn.commit()


def init_db():
    with closing(get_db()) as conn:
        init_schema(conn)
        migrate_schema(conn)
