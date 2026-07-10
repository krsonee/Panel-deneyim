import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from permissions import normalize_permissions

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analytics.db"


def get_database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def uses_postgres():
    return get_database_url().startswith("postgres")


def get_db():
    database_url = get_database_url()
    if uses_postgres():
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        return conn
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
        ]
    for sql in statements:
        execute(conn, sql)
    init_accounting_schema(conn)
    conn.commit()


def init_accounting_schema(conn):
    if uses_postgres():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS acc_payment_methods (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                commission_rate REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS acc_payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                commission_rate REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
        perms = normalize_permissions(row.get("permissions") if isinstance(row, dict) else row["permissions"])
        if not perms or (role == "superadmin" and "*" not in perms):
            execute(
                conn,
                "UPDATE admin_users SET role = ?, permissions = ? WHERE id = ?",
                ("superadmin", json.dumps(["*"]), row["id"]),
            )
    conn.commit()


def init_db():
    with closing(get_db()) as conn:
        init_schema(conn)
        migrate_schema(conn)
