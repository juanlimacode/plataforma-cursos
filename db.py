"""SQLite database setup, connection management, and initial seeding."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from md_importer import parse_course_markdown

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "plataforma.db"))


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS courses (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                source TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                data_json TEXT NOT NULL,
                raw_md TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS course_access (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                granted_at TEXT NOT NULL,
                PRIMARY KEY (user_id, course_id)
            );

            CREATE TABLE IF NOT EXISTS user_progress (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                unit_id TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, course_id, unit_id)
            );
            """
        )

        # Seed initial ADMIN user (development credentials protected with PBKDF2 hash)
        admin_exists = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("ADMIN",)
        ).fetchone()
        if not admin_exists:
            conn.execute(
                """
                INSERT INTO users (username, display_name, password_hash, role, active, created_at)
                VALUES (?, ?, ?, 'admin', 1, ?)
                """,
                ("ADMIN", "Administrador", generate_password_hash("adminppnj"), now_iso()),
            )

        # Seed initial Power BI & Power Platform course from seed_power_bi.md
        seed_exists = conn.execute(
            "SELECT id FROM courses WHERE id = ?", ("power-bi-power-platform",)
        ).fetchone()
        if not seed_exists:
            seed_md_path = os.path.join(BASE_DIR, "seed_power_bi.md")
            with open(seed_md_path, "r", encoding="utf-8") as f:
                raw_md = f.read()
            parsed = parse_course_markdown(raw_md)
            if not parsed["valid"]:
                raise RuntimeError(f"Erro no seed_power_bi.md: {parsed['errors']}")
            course = parsed["course"]
            ts = now_iso()
            conn.execute(
                """
                INSERT INTO courses (id, title, description, category, source, version, data_json, raw_md, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    course["id"],
                    course["title"],
                    course["description"],
                    course["category"],
                    course["source"],
                    course["version"],
                    json.dumps(course, ensure_ascii=False),
                    raw_md,
                    ts,
                    ts,
                ),
            )

        conn.commit()
    finally:
        conn.close()
