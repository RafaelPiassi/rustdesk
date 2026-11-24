import sqlite3
import time

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS brands (
    id INTEGER PRIMARY KEY,
    app_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    company TEXT NOT NULL,
    color_dark TEXT NOT NULL DEFAULT '#304929',
    logo_light BLOB, logo_light_type TEXT,
    logo_dark BLOB, logo_dark_type TEXT,
    emblem BLOB, emblem_type TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    document TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    brand_id INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY,
    serial TEXT NOT NULL UNIQUE,
    serial_key TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    validity_days INTEGER NOT NULL,
    machine TEXT,
    peer_id TEXT NOT NULL DEFAULT '',
    hostname TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    app TEXT NOT NULL DEFAULT '',
    last_ip TEXT NOT NULL DEFAULT '',
    activated_at INTEGER,
    expires_at INTEGER,
    last_seen_at INTEGER,
    revoked_at INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS licenses_customer ON licenses(customer_id);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    license_id INTEGER REFERENCES licenses(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_at ON events(at);

CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    release_tag TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested',
    run_url TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);
"""


def now() -> int:
    return int(time.time())


def get() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"], timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def log_event(kind, detail="", license_id=None, actor="", ip=""):
    get().execute(
        "INSERT INTO events (at, license_id, kind, detail, actor, ip) VALUES (?, ?, ?, ?, ?, ?)",
        (now(), license_id, kind, detail, actor, ip),
    )


def init_app(app):
    app.teardown_appcontext(close)
    with app.app_context():
        conn = get()
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _bootstrap_admin(app, conn)
        conn.commit()


def _bootstrap_admin(app, conn):
    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return
    password = app.config["ADMIN_PASSWORD"]
    if not password:
        raise RuntimeError(
            "No user exists yet: set PANEL_ADMIN_PASSWORD for the first start."
        )
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (app.config["ADMIN_USER"], generate_password_hash(password), now()),
    )
