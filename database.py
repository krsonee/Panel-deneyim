import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from permissions import normalize_permissions

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analytics.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def uses_postgres():
    return DATABASE_URL.startswith("postgres")


def get_db():
    if uses_postgres():
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
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
    conn.commit()


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

    rows = fetchall(conn, "SELECT id, role, permissions FROM admin_users")
    for row in rows:
        perms = normalize_permissions(row.get("permissions") if isinstance(row, dict) else row["permissions"])
        if not perms:
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
