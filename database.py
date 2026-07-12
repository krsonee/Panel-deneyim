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
    init_mailing_schema(conn)
    init_audit_log_schema(conn)
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


def migrate_ref_labels(conn):
    execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS ref_code_labels (
            ref_code TEXT PRIMARY KEY,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """,
    )
    conn.commit()


# Postgres'in "real" (float4) tipi ~7 anlamli basamaktan sonra kusur veriyor.
# Milyonlarca TL'lik tutarlarda kurus hanesi sessizce siliniyordu (ör. 14.557.838,34 -> 14.557.838,00).
# SQLite icin bu sorun yok (REAL orada zaten 8 byte double), migration sadece Postgres'te calisir.
FLOAT_PRECISION_COLUMNS = {
    "acc_payment_methods": ["commission_rate"],
    "acc_finance_transactions": [
        "amount", "commission_rate", "commission_amount",
        "amount_try", "amount_usd", "amount_eur",
        "commission_amount_try", "commission_amount_usd", "commission_amount_eur",
        "rate_usd_try", "rate_eur_try",
    ],
    "acc_expenses": ["amount", "amount_try", "amount_usd", "amount_eur", "rate_usd_try", "rate_eur_try"],
    "acc_vault_transactions": [
        "amount", "usdt_in", "usdt_out", "fee_usdt",
        "amount_try", "amount_usd", "amount_eur", "rate_usd_try", "rate_eur_try",
    ],
    "acc_employees": [
        "salary", "bank_salary", "crypto_salary", "advance_amount", "bonus_amount",
        "salary_try", "salary_usd", "salary_eur", "rate_usd_try", "rate_eur_try",
    ],
    "acc_vaults": ["opening_usdt", "opening_try"],
}


def migrate_float_precision(conn):
    if not uses_postgres():
        return
    for table, columns in FLOAT_PRECISION_COLUMNS.items():
        existing = _table_columns(conn, table)
        if not existing:
            continue
        for col in columns:
            if col not in existing:
                continue
            try:
                execute(conn, f"ALTER TABLE {table} ALTER COLUMN {col} TYPE DOUBLE PRECISION")
                conn.commit()
            except Exception:
                conn.rollback()


def get_ref_code_labels(conn):
    rows = fetchall(conn, "SELECT ref_code, label FROM ref_code_labels")
    return {(r["ref_code"] or "").strip().lower(): r["label"] for r in rows if r["label"]}


def upsert_ref_code_label(conn, ref_code, label):
    ref_code = (ref_code or "").strip().lower()
    label = (label or "").strip()
    if not ref_code:
        return
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO ref_code_labels (ref_code, label, created_at) VALUES (?, ?, ?)
            ON CONFLICT (ref_code) DO UPDATE SET label = EXCLUDED.label
            """,
            (ref_code, label, iso(utcnow())),
        )
    else:
        execute(
            conn,
            "INSERT OR REPLACE INTO ref_code_labels (ref_code, label, created_at) VALUES (?, ?, ?)",
            (ref_code, label, iso(utcnow())),
        )
    conn.commit()


def delete_ref_code_label(conn, ref_code):
    ref_code = (ref_code or "").strip().lower()
    execute(conn, "DELETE FROM ref_code_labels WHERE ref_code = ?", (ref_code,))
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


def migrate_makrolink(conn):
    execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS makrolink_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
        """,
    )
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS makrolink_links (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                destination_url TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                affiliate_id TEXT NOT NULL DEFAULT '',
                smartico_link_id TEXT NOT NULL DEFAULT '',
                ref_code TEXT NOT NULL DEFAULT '',
                click_count INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS makrolink_clicks (
                id SERIAL PRIMARY KEY,
                link_id INTEGER NOT NULL REFERENCES makrolink_links(id),
                code TEXT NOT NULL,
                clicked_at TEXT NOT NULL,
                ip_hash TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                referer TEXT NOT NULL DEFAULT ''
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS makrolink_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                destination_url TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                affiliate_id TEXT NOT NULL DEFAULT '',
                smartico_link_id TEXT NOT NULL DEFAULT '',
                ref_code TEXT NOT NULL DEFAULT '',
                click_count INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS makrolink_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                clicked_at TEXT NOT NULL,
                ip_hash TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                referer TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (link_id) REFERENCES makrolink_links(id)
            )
            """,
        )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_makrolink_clicks_link ON makrolink_clicks(link_id)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_makrolink_clicks_at ON makrolink_clicks(clicked_at)")
    # Default public host
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO makrolink_settings (key, value) VALUES ('public_host', 'makrovip.com')
            ON CONFLICT (key) DO NOTHING
            """,
        )
        execute(
            conn,
            """
            INSERT INTO makrolink_settings (key, value) VALUES ('public_scheme', 'https')
            ON CONFLICT (key) DO NOTHING
            """,
        )
        execute(
            conn,
            """
            INSERT INTO makrolink_settings (key, value) VALUES ('aff_base', 'https://go.aff.makroaffi.com')
            ON CONFLICT (key) DO NOTHING
            """,
        )
        execute(
            conn,
            """
            INSERT INTO makrolink_settings (key, value) VALUES ('short_hosts', 'makrovip.com')
            ON CONFLICT (key) DO NOTHING
            """,
        )
    else:
        execute(
            conn,
            """
            INSERT OR IGNORE INTO makrolink_settings (key, value) VALUES ('public_host', 'makrovip.com')
            """,
        )
        execute(
            conn,
            """
            INSERT OR IGNORE INTO makrolink_settings (key, value) VALUES ('public_scheme', 'https')
            """,
        )
        execute(
            conn,
            """
            INSERT OR IGNORE INTO makrolink_settings (key, value) VALUES ('aff_base', 'https://go.aff.makroaffi.com')
            """,
        )
        execute(
            conn,
            """
            INSERT OR IGNORE INTO makrolink_settings (key, value) VALUES ('short_hosts', 'makrovip.com')
            """,
        )
    cols = _table_columns(conn, "makrolink_links")
    if cols and "target_domain" not in cols:
        execute(conn, "ALTER TABLE makrolink_links ADD COLUMN target_domain TEXT NOT NULL DEFAULT ''")
    conn.commit()


def init_accounting_schema(conn):
    if uses_postgres():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS acc_payment_methods (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                tx_type TEXT NOT NULL DEFAULT 'deposit',
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
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
                amount DOUBLE PRECISION NOT NULL,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                commission_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
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
                amount DOUBLE PRECISION NOT NULL,
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
                amount DOUBLE PRECISION NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_employees (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                start_date TEXT NOT NULL,
                salary DOUBLE PRECISION NOT NULL,
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
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
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
                amount DOUBLE PRECISION NOT NULL,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                commission_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
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
                amount DOUBLE PRECISION NOT NULL,
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
                amount DOUBLE PRECISION NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS acc_employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                start_date TEXT NOT NULL,
                salary DOUBLE PRECISION NOT NULL,
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
    migrate_accounting_period_rates(conn)
    migrate_accounting_payment_method_status(conn)
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
    try:
        migrate_makrolink(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_makrolink hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_ref_labels(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_ref_labels hata (atlanıyor, panel yine açılır): {exc}")
    try:
        init_mailing_schema(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  init_mailing_schema hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_float_precision(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_float_precision hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_accounting_pronet(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_accounting_pronet hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_invoice_calc(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_invoice_calc hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_staff_roster(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_staff_roster hata (atlanıyor, panel yine açılır): {exc}")
    try:
        migrate_accounting_pl(conn)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  migrate_accounting_pl hata (atlanıyor, panel yine açılır): {exc}")


def migrate_accounting_pronet(conn):
    from accounting_pronet import seed_pronet_templates

    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_providers (
                id SERIAL PRIMARY KEY,
                section TEXT NOT NULL DEFAULT 'casino',
                name TEXT NOT NULL UNIQUE,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_fixed_fees (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                amount_eur DOUBLE PRECISION NOT NULL DEFAULT 0,
                billing_cycle TEXT NOT NULL DEFAULT 'monthly',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_period_meta (
                period TEXT PRIMARY KEY,
                gross_revenue_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                eur_try_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                sms_fee_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_period_lines (
                id SERIAL PRIMARY KEY,
                period TEXT NOT NULL,
                line_kind TEXT NOT NULL DEFAULT 'provider',
                provider_id INTEGER REFERENCES acc_pronet_providers(id),
                fixed_fee_id INTEGER REFERENCES acc_pronet_fixed_fees(id),
                custom_label TEXT,
                volume_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                jackpot_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                tips_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                commission_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                manual_commission DOUBLE PRECISION,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section TEXT NOT NULL DEFAULT 'casino',
                name TEXT NOT NULL UNIQUE,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_fixed_fees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                amount_eur DOUBLE PRECISION NOT NULL DEFAULT 0,
                billing_cycle TEXT NOT NULL DEFAULT 'monthly',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_period_meta (
                period TEXT PRIMARY KEY,
                gross_revenue_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                eur_try_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                sms_fee_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pronet_period_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL,
                line_kind TEXT NOT NULL DEFAULT 'provider',
                provider_id INTEGER,
                fixed_fee_id INTEGER,
                custom_label TEXT,
                volume_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                jackpot_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                tips_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                commission_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                manual_commission DOUBLE PRECISION,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (provider_id) REFERENCES acc_pronet_providers(id),
                FOREIGN KEY (fixed_fee_id) REFERENCES acc_pronet_fixed_fees(id)
            )
            """,
        )
    execute(
        conn,
        "CREATE INDEX IF NOT EXISTS idx_acc_pronet_lines_period ON acc_pronet_period_lines(period)",
    )
    seed_pronet_templates(conn)
    exists = scalar(conn, "SELECT COUNT(*) FROM acc_pronet_providers WHERE name = ?", ("Klas Poker",))
    if not exists:
        now = iso(utcnow())
        insert_returning_id(
            conn,
            """
            INSERT INTO acc_pronet_providers
            (section, name, commission_rate, sort_order, active, created_at)
            VALUES ('casino', 'Klas Poker', 25, 125, 1, ?)
            """,
            (now,),
        )
    conn.commit()


def migrate_accounting_pl(conn):
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pl_meta (
                period TEXT PRIMARY KEY,
                notes TEXT NOT NULL DEFAULT '',
                pronet_fatura_label TEXT NOT NULL DEFAULT '',
                pronet_fatura_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                pronet_odenen_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                asil_net_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pl_lines (
                id SERIAL PRIMARY KEY,
                period TEXT NOT NULL,
                section_key TEXT NOT NULL,
                label TEXT NOT NULL,
                amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pl_meta (
                period TEXT PRIMARY KEY,
                notes TEXT NOT NULL DEFAULT '',
                pronet_fatura_label TEXT NOT NULL DEFAULT '',
                pronet_fatura_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                pronet_odenen_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                asil_net_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_pl_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL,
                section_key TEXT NOT NULL,
                label TEXT NOT NULL,
                amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    execute(
        conn,
        "CREATE INDEX IF NOT EXISTS idx_acc_pl_lines_period ON acc_pl_lines(period)",
    )
    conn.commit()

    # Mayıs 2026'dan itibaren Excel'e eklenen "Kâr Payı Dağılımı" bloğu (Yönetim Payı / Kalan / Ortak A / Ortak B).
    pl_meta_cols = _table_columns(conn, "acc_pl_meta")
    if pl_meta_cols and "yonetim_payi_label" not in pl_meta_cols:
        new_cols = [
            ("yonetim_payi_label", "TEXT NOT NULL DEFAULT ''"),
            ("yonetim_payi_amount", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("kalan_amount", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("ortak_a_label", "TEXT NOT NULL DEFAULT ''"),
            ("ortak_a_amount", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("ortak_b_label", "TEXT NOT NULL DEFAULT ''"),
            ("ortak_b_amount", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ]
        for name, typedef in new_cols:
            execute(conn, f"ALTER TABLE acc_pl_meta ADD COLUMN {name} {typedef}")
        conn.commit()


def migrate_invoice_calc(conn):
    """Fatura Hesaplama (günlük GGR takip) — Pronet Fatura alanından tamamen bağımsız."""
    from accounting_pronet import SEED_PROVIDERS

    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_invoice_calc_providers (
                id SERIAL PRIMARY KEY,
                section TEXT NOT NULL DEFAULT 'casino',
                name TEXT NOT NULL UNIQUE,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_invoice_calc_daily (
                id SERIAL PRIMARY KEY,
                period TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                provider_id INTEGER NOT NULL REFERENCES acc_invoice_calc_providers(id),
                stake_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                winning_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(entry_date, provider_id)
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_invoice_calc_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section TEXT NOT NULL DEFAULT 'casino',
                name TEXT NOT NULL UNIQUE,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_invoice_calc_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                provider_id INTEGER NOT NULL,
                stake_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                winning_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(entry_date, provider_id),
                FOREIGN KEY (provider_id) REFERENCES acc_invoice_calc_providers(id)
            )
            """,
        )
    execute(
        conn,
        "CREATE INDEX IF NOT EXISTS idx_acc_invoice_calc_daily_period ON acc_invoice_calc_daily(period)",
    )

    now = iso(utcnow())
    for section, name, rate, sort_order in SEED_PROVIDERS:
        exists = scalar(
            conn,
            "SELECT COUNT(*) FROM acc_invoice_calc_providers WHERE name = ?",
            (name,),
        )
        if not exists:
            insert_returning_id(
                conn,
                """
                INSERT INTO acc_invoice_calc_providers
                (section, name, commission_rate, sort_order, active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (section, name, rate, sort_order, now),
            )
    conn.commit()


def migrate_staff_roster(conn):
    """Personel sekmesi — sade Ofis/Türkiye listesi. Maaş Ödemeleri (acc_employees) alanından bağımsız."""
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_staff (
                id SERIAL PRIMARY KEY,
                category TEXT NOT NULL DEFAULT 'turkey',
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                salary_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL DEFAULT 'turkey',
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                salary_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_acc_staff_category ON acc_staff(category)")
    conn.commit()

    cols = _table_columns(conn, "acc_staff")
    if cols and "currency" not in cols:
        extra_cols = [
            ("currency", "TEXT NOT NULL DEFAULT 'TRY'"),
            ("salary_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("salary_usd", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("salary_eur", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("rate_usd_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("rate_eur_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("department", "TEXT NOT NULL DEFAULT ''"),
            ("location", "TEXT NOT NULL DEFAULT ''"),
        ]
        for name, typedef in extra_cols:
            execute(conn, f"ALTER TABLE acc_staff ADD COLUMN {name} {typedef}")
        conn.commit()
        # Var olan (salary_amount ile eklenmiş) kayıtları TRY olarak geri doldur.
        execute(
            conn,
            "UPDATE acc_staff SET salary_try = salary_amount, currency = 'TRY' "
            "WHERE salary_try = 0 AND salary_amount > 0",
        )
        conn.commit()


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
        ("bank_salary", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("crypto_salary", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("advance_amount", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("bonus_amount", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
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
                opening_usdt DOUBLE PRECISION NOT NULL DEFAULT 0,
                opening_try DOUBLE PRECISION NOT NULL DEFAULT 0,
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
                opening_usdt DOUBLE PRECISION NOT NULL DEFAULT 0,
                opening_try DOUBLE PRECISION NOT NULL DEFAULT 0,
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
            ("usdt_in", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("usdt_out", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("fee_usdt", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
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
        ("amount_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("amount_usd", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("amount_eur", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("commission_amount_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("commission_amount_usd", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("commission_amount_eur", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("rate_usd_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("rate_eur_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
    ]
    money_cols = [
        ("currency", "TEXT NOT NULL DEFAULT 'USD'"),
        ("amount_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("amount_usd", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("amount_eur", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("rate_usd_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("rate_eur_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
    ]
    salary_cols = [
        ("currency", "TEXT NOT NULL DEFAULT 'TRY'"),
        ("salary_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("salary_usd", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("salary_eur", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("rate_usd_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("rate_eur_try", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
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
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
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


def migrate_accounting_period_rates(conn):
    """Payment komisyon oranları — ay bazlı (YYYY-MM)."""
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS acc_payment_method_rates (
                id SERIAL PRIMARY KEY,
                payment_method_id INTEGER NOT NULL REFERENCES acc_payment_methods(id) ON DELETE CASCADE,
                period TEXT NOT NULL,
                commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(payment_method_id, period)
            )
            """,
        )
    else:
        table_exists = scalar(
            conn,
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='acc_payment_method_rates'",
        )
        if not table_exists:
            execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS acc_payment_method_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_method_id INTEGER NOT NULL,
                    period TEXT NOT NULL,
                    commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(payment_method_id, period),
                    FOREIGN KEY (payment_method_id) REFERENCES acc_payment_methods(id)
                )
                """,
            )
    execute(
        conn,
        "CREATE INDEX IF NOT EXISTS idx_acc_pm_rates_period ON acc_payment_method_rates(period)",
    )
    conn.commit()


def migrate_accounting_payment_method_status(conn):
    """Manuel aktif/pasif override — NULL ise işlem sayısına göre otomatik hesaplanır."""
    cols = _table_columns(conn, "acc_payment_methods")
    if not cols or "manual_active" in cols:
        return
    execute(conn, "ALTER TABLE acc_payment_methods ADD COLUMN manual_active INTEGER")
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
    if "created_by" not in cols:
        execute(conn, "ALTER TABLE tracked_links ADD COLUMN created_by TEXT NOT NULL DEFAULT ''")
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
    if "totp_secret" not in cols:
        execute(conn, "ALTER TABLE admin_users ADD COLUMN totp_secret TEXT NOT NULL DEFAULT ''")
    if "two_factor_required" not in cols:
        execute(conn, "ALTER TABLE admin_users ADD COLUMN two_factor_required INTEGER NOT NULL DEFAULT 0")
    if "two_factor_enabled" not in cols:
        execute(conn, "ALTER TABLE admin_users ADD COLUMN two_factor_enabled INTEGER NOT NULL DEFAULT 0")
    if "display_name" not in cols:
        execute(conn, "ALTER TABLE admin_users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
    if "must_change_password" not in cols:
        execute(conn, "ALTER TABLE admin_users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
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


def init_audit_log_schema(conn):
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                method TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                status INTEGER NOT NULL DEFAULT 0,
                ip TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                method TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                status INTEGER NOT NULL DEFAULT 0,
                ip TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(username)")
    conn.commit()


def log_audit(conn, username="", display_name="", action="", method="", path="", status=0, ip="", detail=""):
    try:
        execute(
            conn,
            """
            INSERT INTO audit_log (username, display_name, action, method, path, status, ip, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (username or "")[:64],
                (display_name or "")[:100],
                (action or "")[:200],
                (method or "")[:10],
                (path or "")[:300],
                int(status or 0),
                (ip or "")[:64],
                (detail or "")[:500],
                iso(utcnow()),
            ),
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def fetch_audit_log(conn, limit=300, username=None):
    if username:
        return fetchall(
            conn,
            "SELECT * FROM audit_log WHERE username = ? ORDER BY id DESC LIMIT ?",
            (username, int(limit)),
        )
    return fetchall(conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),))


MAILING_SEED_DOMAINS = (
    "vipozelileti.com",
    "vippozelileti.com",
    "vipppozelileti.com",
)


def get_mail_setting(conn, key, default=None):
    val = scalar(conn, "SELECT value FROM mail_settings WHERE key = ?", (key,))
    return val if val is not None else default


def upsert_mail_setting(conn, key, value):
    if uses_postgres():
        execute(
            conn,
            """
            INSERT INTO mail_settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, str(value)),
        )
    else:
        execute(conn, "INSERT OR REPLACE INTO mail_settings (key, value) VALUES (?, ?)", (key, str(value)))


def seed_mailing_defaults(conn):
    import secrets

    now = iso(utcnow())
    for domain in MAILING_SEED_DOMAINS:
        exists = scalar(conn, "SELECT COUNT(*) FROM mail_domains WHERE domain = ?", (domain,))
        if not exists:
            insert_returning_id(
                conn,
                """
                INSERT INTO mail_domains (domain, status, from_name, from_local, dns_status, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (domain, "pending", "VIP Özel İleti", "noreply", "unconfigured", "NS henüz yönlendirilmedi", now),
            )
    if not get_mail_setting(conn, "webhook_secret"):
        upsert_mail_setting(conn, "webhook_secret", secrets.token_hex(24))
    if get_mail_setting(conn, "provider_mode") is None:
        upsert_mail_setting(conn, "provider_mode", "stub")
    if get_mail_setting(conn, "smtp_host") is None:
        upsert_mail_setting(conn, "smtp_host", "")
    if get_mail_setting(conn, "smtp_port") is None:
        upsert_mail_setting(conn, "smtp_port", "465")
    if get_mail_setting(conn, "smtp_user") is None:
        upsert_mail_setting(conn, "smtp_user", "")
    if get_mail_setting(conn, "smtp_password") is None:
        upsert_mail_setting(conn, "smtp_password", "")
    if get_mail_setting(conn, "default_domain_id") is None:
        first = fetchone(conn, "SELECT id FROM mail_domains ORDER BY id ASC LIMIT 1")
        upsert_mail_setting(conn, "default_domain_id", str(first["id"]) if first else "")
    if get_mail_setting(conn, "smartico_affiliate_id") is None:
        upsert_mail_setting(conn, "smartico_affiliate_id", "")
    if get_mail_setting(conn, "smartico_subid_param") is None:
        upsert_mail_setting(conn, "smartico_subid_param", "afp1")
    # Default IVR rule if none
    rule_count = scalar(conn, "SELECT COUNT(*) FROM mail_ivr_rules") or 0
    if not rule_count:
        insert_returning_id(
            conn,
            """
            INSERT INTO mail_ivr_rules (name, active, template_id, domain_id, delay_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("IVR cevap sonrası mail", 0, None, None, 0, now),
        )


def init_mailing_schema(conn):
    if uses_postgres():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS mail_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_domains (
                id SERIAL PRIMARY KEY,
                domain TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                from_name TEXT NOT NULL DEFAULT '',
                from_local TEXT NOT NULL DEFAULT 'noreply',
                dns_status TEXT NOT NULL DEFAULT 'unconfigured',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_contact_tags (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_contacts (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'manual',
                unsubscribed INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_templates (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                html_body TEXT NOT NULL DEFAULT '',
                text_body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_campaigns (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                campaign_type TEXT NOT NULL DEFAULT 'bulk',
                template_id INTEGER REFERENCES mail_templates(id),
                domain_id INTEGER REFERENCES mail_domains(id),
                status TEXT NOT NULL DEFAULT 'draft',
                tag_filter TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                queued_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_campaign_recipients (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER NOT NULL REFERENCES mail_campaigns(id),
                contact_id INTEGER NOT NULL REFERENCES mail_contacts(id),
                status TEXT NOT NULL DEFAULT 'pending',
                send_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(campaign_id, contact_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_sends (
                id SERIAL PRIMARY KEY,
                channel TEXT NOT NULL DEFAULT 'bulk',
                campaign_id INTEGER REFERENCES mail_campaigns(id),
                contact_id INTEGER REFERENCES mail_contacts(id),
                template_id INTEGER REFERENCES mail_templates(id),
                domain_id INTEGER REFERENCES mail_domains(id),
                to_email TEXT NOT NULL,
                to_phone TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                provider_msg_id TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                opened_at TEXT,
                clicked_at TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_ivr_rules (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL DEFAULT 'IVR kuralı',
                active INTEGER NOT NULL DEFAULT 0,
                template_id INTEGER REFERENCES mail_templates(id),
                domain_id INTEGER REFERENCES mail_domains(id),
                delay_seconds INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_ivr_events (
                id SERIAL PRIMARY KEY,
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                answered_at TEXT,
                contact_id INTEGER REFERENCES mail_contacts(id),
                send_id INTEGER REFERENCES mail_sends(id),
                status TEXT NOT NULL DEFAULT 'received',
                payload TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_mail_contacts_email ON mail_contacts(email)",
            "CREATE INDEX IF NOT EXISTS idx_mail_contacts_phone ON mail_contacts(phone)",
            "CREATE INDEX IF NOT EXISTS idx_mail_sends_created ON mail_sends(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_mail_sends_status ON mail_sends(status)",
            "CREATE INDEX IF NOT EXISTS idx_mail_sends_contact ON mail_sends(contact_id)",
            "CREATE INDEX IF NOT EXISTS idx_mail_ivr_events_created ON mail_ivr_events(created_at)",
            """
            CREATE TABLE IF NOT EXISTS mail_click_links (
                id SERIAL PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                send_id INTEGER REFERENCES mail_sends(id),
                contact_id INTEGER REFERENCES mail_contacts(id),
                campaign_id INTEGER REFERENCES mail_campaigns(id),
                dest_url TEXT NOT NULL,
                is_smartico INTEGER NOT NULL DEFAULT 0,
                click_count INTEGER NOT NULL DEFAULT 0,
                first_clicked_at TEXT,
                last_clicked_at TEXT,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_mail_click_token ON mail_click_links(token)",
            """
            CREATE TABLE IF NOT EXISTS mail_import_jobs (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                total_rows INTEGER NOT NULL DEFAULT 0,
                processed_rows INTEGER NOT NULL DEFAULT 0,
                upserted_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS mail_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                from_name TEXT NOT NULL DEFAULT '',
                from_local TEXT NOT NULL DEFAULT 'noreply',
                dns_status TEXT NOT NULL DEFAULT 'unconfigured',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_contact_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'manual',
                unsubscribed INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                html_body TEXT NOT NULL DEFAULT '',
                text_body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                campaign_type TEXT NOT NULL DEFAULT 'bulk',
                template_id INTEGER,
                domain_id INTEGER,
                status TEXT NOT NULL DEFAULT 'draft',
                tag_filter TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                queued_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (template_id) REFERENCES mail_templates(id),
                FOREIGN KEY (domain_id) REFERENCES mail_domains(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_campaign_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                send_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(campaign_id, contact_id),
                FOREIGN KEY (campaign_id) REFERENCES mail_campaigns(id),
                FOREIGN KEY (contact_id) REFERENCES mail_contacts(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL DEFAULT 'bulk',
                campaign_id INTEGER,
                contact_id INTEGER,
                template_id INTEGER,
                domain_id INTEGER,
                to_email TEXT NOT NULL,
                to_phone TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                provider_msg_id TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                opened_at TEXT,
                clicked_at TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES mail_campaigns(id),
                FOREIGN KEY (contact_id) REFERENCES mail_contacts(id),
                FOREIGN KEY (template_id) REFERENCES mail_templates(id),
                FOREIGN KEY (domain_id) REFERENCES mail_domains(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_ivr_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT 'IVR kuralı',
                active INTEGER NOT NULL DEFAULT 0,
                template_id INTEGER,
                domain_id INTEGER,
                delay_seconds INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (template_id) REFERENCES mail_templates(id),
                FOREIGN KEY (domain_id) REFERENCES mail_domains(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mail_ivr_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                answered_at TEXT,
                contact_id INTEGER,
                send_id INTEGER,
                status TEXT NOT NULL DEFAULT 'received',
                payload TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (contact_id) REFERENCES mail_contacts(id),
                FOREIGN KEY (send_id) REFERENCES mail_sends(id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_mail_contacts_email ON mail_contacts(email)",
            "CREATE INDEX IF NOT EXISTS idx_mail_contacts_phone ON mail_contacts(phone)",
            "CREATE INDEX IF NOT EXISTS idx_mail_sends_created ON mail_sends(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_mail_sends_status ON mail_sends(status)",
            "CREATE INDEX IF NOT EXISTS idx_mail_sends_contact ON mail_sends(contact_id)",
            "CREATE INDEX IF NOT EXISTS idx_mail_ivr_events_created ON mail_ivr_events(created_at)",
            """
            CREATE TABLE IF NOT EXISTS mail_click_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                send_id INTEGER,
                contact_id INTEGER,
                campaign_id INTEGER,
                dest_url TEXT NOT NULL,
                is_smartico INTEGER NOT NULL DEFAULT 0,
                click_count INTEGER NOT NULL DEFAULT 0,
                first_clicked_at TEXT,
                last_clicked_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (send_id) REFERENCES mail_sends(id),
                FOREIGN KEY (contact_id) REFERENCES mail_contacts(id),
                FOREIGN KEY (campaign_id) REFERENCES mail_campaigns(id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_mail_click_token ON mail_click_links(token)",
            """
            CREATE TABLE IF NOT EXISTS mail_import_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                total_rows INTEGER NOT NULL DEFAULT 0,
                processed_rows INTEGER NOT NULL DEFAULT 0,
                upserted_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        ]
    for sql in statements:
        execute(conn, sql)
    seed_mailing_defaults(conn)
    conn.commit()


def ensure_mail_click_links_table(conn):
    """Mevcut DB'lerde click tracking tablosu yoksa ekle."""
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_click_links (
                id SERIAL PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                send_id INTEGER REFERENCES mail_sends(id),
                contact_id INTEGER REFERENCES mail_contacts(id),
                campaign_id INTEGER REFERENCES mail_campaigns(id),
                dest_url TEXT NOT NULL,
                click_count INTEGER NOT NULL DEFAULT 0,
                first_clicked_at TEXT,
                last_clicked_at TEXT,
                created_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_click_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                send_id INTEGER,
                contact_id INTEGER,
                campaign_id INTEGER,
                dest_url TEXT NOT NULL,
                click_count INTEGER NOT NULL DEFAULT 0,
                first_clicked_at TEXT,
                last_clicked_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (send_id) REFERENCES mail_sends(id),
                FOREIGN KEY (contact_id) REFERENCES mail_contacts(id),
                FOREIGN KEY (campaign_id) REFERENCES mail_campaigns(id)
            )
            """,
        )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_mail_click_token ON mail_click_links(token)")
    cols = _table_columns(conn, "mail_click_links")
    if cols and "is_smartico" not in cols:
        execute(conn, "ALTER TABLE mail_click_links ADD COLUMN is_smartico INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def ensure_mail_import_jobs_table(conn):
    """Mevcut DB'lerde büyük liste import job tablosu yoksa ekle."""
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_import_jobs (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                total_rows INTEGER NOT NULL DEFAULT 0,
                processed_rows INTEGER NOT NULL DEFAULT 0,
                upserted_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_import_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                total_rows INTEGER NOT NULL DEFAULT 0,
                processed_rows INTEGER NOT NULL DEFAULT 0,
                upserted_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    conn.commit()


def _dedupe_mail_contacts_by_email(conn):
    """Büyük ölçekli bulk upsert (ON CONFLICT) için email üzerinde UNIQUE
    index gerekiyor — önce olası (nadir) mükerrer kayıtları birleştirir."""
    dups = fetchall(conn, "SELECT email FROM mail_contacts GROUP BY email HAVING COUNT(*) > 1")
    for d in dups:
        email = d["email"] if isinstance(d, dict) else d[0]
        try:
            rows = fetchall(conn, "SELECT id, name, tags FROM mail_contacts WHERE email = ? ORDER BY id ASC", (email,))
            if len(rows) < 2:
                continue
            keep_id = rows[0]["id"]
            all_tags = []
            best_name = ""
            for r in rows:
                try:
                    parsed = json.loads(r["tags"] or "[]")
                    if isinstance(parsed, list):
                        all_tags += [str(x) for x in parsed]
                except Exception:
                    pass
                if not best_name and (r["name"] or "").strip():
                    best_name = (r["name"] or "").strip()
            merged = json.dumps(sorted(set(all_tags)), ensure_ascii=False)
            execute(conn, "UPDATE mail_contacts SET tags = ?, name = ? WHERE id = ?", (merged, best_name, keep_id))
            for r in rows[1:]:
                dup_id = r["id"]
                for tbl, col in (
                    ("mail_campaign_recipients", "contact_id"),
                    ("mail_sends", "contact_id"),
                    ("mail_click_links", "contact_id"),
                    ("mail_ivr_events", "contact_id"),
                ):
                    execute(conn, f"UPDATE {tbl} SET {col} = ? WHERE {col} = ?", (keep_id, dup_id))
                execute(conn, "DELETE FROM mail_contacts WHERE id = ?", (dup_id,))
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass


def ensure_mail_contacts_unique_email(conn):
    """Toplu import (ON CONFLICT (email) DO UPDATE) için gerekli unique index."""
    try:
        execute(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_mail_contacts_email_unique ON mail_contacts(email)")
        conn.commit()
        return
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    _dedupe_mail_contacts_by_email(conn)
    try:
        execute(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_mail_contacts_email_unique ON mail_contacts(email)")
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"⚠️  ensure_mail_contacts_unique_email hata: {exc}")


def init_db():
    with closing(get_db()) as conn:
        init_schema(conn)
        migrate_schema(conn)
        try:
            ensure_mail_click_links_table(conn)
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"⚠️  ensure_mail_click_links_table hata: {exc}")
        try:
            ensure_mail_import_jobs_table(conn)
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"⚠️  ensure_mail_import_jobs_table hata: {exc}")
        try:
            ensure_mail_contacts_unique_email(conn)
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"⚠️  ensure_mail_contacts_unique_email hata: {exc}")
