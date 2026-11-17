"""Authentication helpers and route decorators."""

from functools import wraps
from typing import Any, Callable
from flask import jsonify, session

from db import get_db


def get_current_user() -> dict[str, Any] | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, display_name, role, active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row or not row["active"]:
            session.clear()
            return None
        return dict(row)
    finally:
        conn.close()


def login_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Autenticação necessária."}), 401
        return fn(user, *args, **kwargs)

    return wrapper


def admin_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Autenticação necessária."}), 401
        if user["role"] != "admin":
            return jsonify({"error": "Acesso restrito ao administrador."}), 403
        return fn(user, *args, **kwargs)

    return wrapper
