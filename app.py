"""Flask application for the Gamified Courses Platform."""

import json
import os
import secrets
from typing import Any
from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from auth import admin_required, get_current_user, login_required
from db import get_db, init_db, now_iso
from md_importer import parse_course_markdown
from progress import compute_course_stats


def _collect_course_unit_ids(course_data: dict[str, Any]) -> set[str]:
    unit_ids: set[str] = set()
    for path in course_data.get("paths", []):
        for module in path.get("courses", []):
            for unit in module.get("units", []):
                unit_ids.add(unit["id"])
    return unit_ids


def _get_user_completed_units(conn, user_id: int, course_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT unit_id FROM user_progress WHERE user_id = ? AND course_id = ? ORDER BY completed_at ASC",
        (user_id, course_id),
    ).fetchall()
    return [r["unit_id"] for r in rows]


def _user_can_access_course(conn, user: dict[str, Any], course_id: str) -> bool:
    if user["role"] == "admin":
        return True
    row = conn.execute(
        "SELECT 1 FROM course_access WHERE user_id = ? AND course_id = ?",
        (user["id"], course_id),
    ).fetchone()
    return row is not None


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    init_db()

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    # ---------------- AUTH ----------------

    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        user = get_current_user()
        if not user:
            return jsonify({"user": None}), 401
        return jsonify({"user": user})

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))

        if not username or not password:
            return jsonify({"error": "Informe usuário e senha."}), 400

        conn = get_db()
        try:
            row = conn.execute(
                "SELECT id, username, display_name, password_hash, role, active, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row or not check_password_hash(row["password_hash"], password):
                return jsonify({"error": "Usuário ou senha inválidos."}), 401
            if not row["active"]:
                return jsonify({"error": "Usuário desativado. Contate o administrador."}), 403

            session.clear()
            session["user_id"] = row["id"]
            user = {
                "id": row["id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
                "active": row["active"],
                "created_at": row["created_at"],
            }
            return jsonify({"user": user})
        finally:
            conn.close()

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        session.clear()
        return jsonify({"ok": True})

    # ---------------- COURSES & PROGRESS ----------------

    @app.route("/api/courses", methods=["GET"])
    @login_required
    def list_courses(user: dict[str, Any]):
        conn = get_db()
        try:
            if user["role"] == "admin":
                rows = conn.execute(
                    "SELECT id, title, description, category, source, version, data_json FROM courses WHERE active = 1 ORDER BY created_at ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT c.id, c.title, c.description, c.category, c.source, c.version, c.data_json
                    FROM courses c
                    INNER JOIN course_access ca ON ca.course_id = c.id
                    WHERE ca.user_id = ? AND c.active = 1
                    ORDER BY c.created_at ASC
                    """,
                    (user["id"],),
                ).fetchall()

            result = []
            for r in rows:
                course_data = json.loads(r["data_json"])
                completed = _get_user_completed_units(conn, user["id"], r["id"])
                stats = compute_course_stats(course_data, completed)
                result.append(
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "description": r["description"],
                        "category": r["category"],
                        "source": r["source"],
                        "version": r["version"],
                        "stats": {
                            "totalXp": stats["totalXp"],
                            "totalPossibleXp": stats["totalPossibleXp"],
                            "level": stats["level"],
                            "percent": stats["percent"],
                            "completedUnitsCount": stats["completedUnitsCount"],
                            "totalUnitsCount": stats["totalUnitsCount"],
                            "completedModulesCount": stats["completedModulesCount"],
                            "totalModulesCount": stats["totalModulesCount"],
                            "unlockedTrophiesCount": len(stats["unlockedTrophies"]),
                            "totalTrophiesCount": len(course_data.get("trophies", [])),
                        },
                    }
                )
            return jsonify({"courses": result})
        finally:
            conn.close()

    @app.route("/api/courses/<course_id>", methods=["GET"])
    @login_required
    def get_course_detail(user: dict[str, Any], course_id: str):
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT id, title, description, category, source, version, data_json, active FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()
            if not row or not row["active"]:
                return jsonify({"error": "Curso não encontrado."}), 404
            if not _user_can_access_course(conn, user, course_id):
                return jsonify({"error": "Você não tem acesso a este curso."}), 403

            course_data = json.loads(row["data_json"])
            completed = _get_user_completed_units(conn, user["id"], course_id)
            progress = compute_course_stats(course_data, completed)
            return jsonify({"course": course_data, "progress": progress})
        finally:
            conn.close()

    @app.route("/api/courses/<course_id>/units/<unit_id>/toggle", methods=["POST"])
    @login_required
    def toggle_unit(user: dict[str, Any], course_id: str, unit_id: str):
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT data_json, active FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            if not row or not row["active"]:
                return jsonify({"error": "Curso não encontrado."}), 404
            if not _user_can_access_course(conn, user, course_id):
                return jsonify({"error": "Você não tem acesso a este curso."}), 403

            course_data = json.loads(row["data_json"])
            valid_units = _collect_course_unit_ids(course_data)
            if unit_id not in valid_units:
                return jsonify({"error": "Unidade não encontrada neste curso."}), 404

            existing = conn.execute(
                "SELECT 1 FROM user_progress WHERE user_id = ? AND course_id = ? AND unit_id = ?",
                (user["id"], course_id, unit_id),
            ).fetchone()

            if existing:
                conn.execute(
                    "DELETE FROM user_progress WHERE user_id = ? AND course_id = ? AND unit_id = ?",
                    (user["id"], course_id, unit_id),
                )
                completed_now = False
            else:
                conn.execute(
                    "INSERT INTO user_progress (user_id, course_id, unit_id, completed_at) VALUES (?, ?, ?, ?)",
                    (user["id"], course_id, unit_id, now_iso()),
                )
                completed_now = True

            conn.commit()
            completed = _get_user_completed_units(conn, user["id"], course_id)
            progress = compute_course_stats(course_data, completed)
            return jsonify({"completed": completed_now, "progress": progress})
        finally:
            conn.close()

    @app.route("/api/courses/<course_id>/import-json", methods=["POST"])
    @login_required
    def import_course_json(user: dict[str, Any], course_id: str):
        data = request.get_json(silent=True) or {}
        units = data.get("completedUnits")
        if not isinstance(units, list):
            return jsonify({"error": "Formato inválido: 'completedUnits' deve ser uma lista."}), 400

        replace = bool(data.get("replace", True))
        conn = get_db()
        try:
            row = conn.execute("SELECT data_json, active FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not row or not row["active"]:
                return jsonify({"error": "Curso não encontrado."}), 404
            if not _user_can_access_course(conn, user, course_id):
                return jsonify({"error": "Você não tem acesso a este curso."}), 403

            course_data = json.loads(row["data_json"])
            valid_units = _collect_course_unit_ids(course_data)
            filtered_units = [str(u) for u in units if str(u) in valid_units]

            if replace:
                conn.execute(
                    "DELETE FROM user_progress WHERE user_id = ? AND course_id = ?",
                    (user["id"], course_id),
                )

            ts = now_iso()
            for uid in filtered_units:
                conn.execute(
                    "INSERT OR IGNORE INTO user_progress (user_id, course_id, unit_id, completed_at) VALUES (?, ?, ?, ?)",
                    (user["id"], course_id, uid, ts),
                )
            conn.commit()
            completed = _get_user_completed_units(conn, user["id"], course_id)
            progress = compute_course_stats(course_data, completed)
            return jsonify({"progress": progress, "importedCount": len(filtered_units)})
        finally:
            conn.close()

    @app.route("/api/courses/<course_id>/migrate-local", methods=["POST"])
    @login_required
    def migrate_local_progress(user: dict[str, Any], course_id: str):
        data = request.get_json(silent=True) or {}
        units = data.get("completedUnits")
        if not isinstance(units, list):
            return jsonify({"error": "Lista 'completedUnits' inválida."}), 400

        conn = get_db()
        try:
            row = conn.execute("SELECT data_json, active FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not row or not row["active"]:
                return jsonify({"error": "Curso não encontrado."}), 404
            if not _user_can_access_course(conn, user, course_id):
                return jsonify({"error": "Você não tem acesso a este curso."}), 403

            course_data = json.loads(row["data_json"])
            valid_units = _collect_course_unit_ids(course_data)
            ts = now_iso()
            added = 0
            for uid in units:
                uid_str = str(uid)
                if uid_str in valid_units:
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO user_progress (user_id, course_id, unit_id, completed_at) VALUES (?, ?, ?, ?)",
                        (user["id"], course_id, uid_str, ts),
                    )
                    added += cur.rowcount
            conn.commit()
            completed = _get_user_completed_units(conn, user["id"], course_id)
            progress = compute_course_stats(course_data, completed)
            return jsonify({"progress": progress, "migratedCount": added})
        finally:
            conn.close()

    @app.route("/api/courses/<course_id>/reset", methods=["POST"])
    @login_required
    def reset_course_progress(user: dict[str, Any], course_id: str):
        conn = get_db()
        try:
            row = conn.execute("SELECT data_json, active FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not row or not row["active"]:
                return jsonify({"error": "Curso não encontrado."}), 404
            if not _user_can_access_course(conn, user, course_id):
                return jsonify({"error": "Você não tem acesso a este curso."}), 403

            conn.execute(
                "DELETE FROM user_progress WHERE user_id = ? AND course_id = ?",
                (user["id"], course_id),
            )
            conn.commit()
            course_data = json.loads(row["data_json"])
            progress = compute_course_stats(course_data, [])
            return jsonify({"progress": progress})
        finally:
            conn.close()

    # ---------------- ADMIN: USERS ----------------

    @app.route("/api/admin/users", methods=["GET"])
    @admin_required
    def admin_list_users(_admin: dict[str, Any]):
        conn = get_db()
        try:
            users_rows = conn.execute(
                "SELECT id, username, display_name, role, active, created_at FROM users ORDER BY id ASC"
            ).fetchall()
            courses_rows = conn.execute("SELECT id, title, data_json FROM courses").fetchall()
            courses_map = {r["id"]: json.loads(r["data_json"]) for r in courses_rows}

            users_list = []
            for u in users_rows:
                access_rows = conn.execute(
                    "SELECT course_id FROM course_access WHERE user_id = ?", (u["id"],)
                ).fetchall()
                course_ids = [a["course_id"] for a in access_rows]

                # Aggregate XP across all courses where user has progress
                prog_rows = conn.execute(
                    "SELECT course_id, unit_id FROM user_progress WHERE user_id = ?", (u["id"],)
                ).fetchall()
                by_course: dict[str, list[str]] = {}
                for p in prog_rows:
                    by_course.setdefault(p["course_id"], []).append(p["unit_id"])

                total_xp = 0
                total_trophies = 0
                for cid, unit_ids in by_course.items():
                    if cid in courses_map:
                        stats = compute_course_stats(courses_map[cid], unit_ids)
                        total_xp += stats["totalXp"]
                        total_trophies += len(stats["unlockedTrophies"])

                users_list.append(
                    {
                        "id": u["id"],
                        "username": u["username"],
                        "display_name": u["display_name"],
                        "role": u["role"],
                        "active": bool(u["active"]),
                        "created_at": u["created_at"],
                        "course_ids": course_ids,
                        "total_xp": total_xp,
                        "level": max(1, (total_xp // 600) + 1),
                        "total_trophies": total_trophies,
                    }
                )
            return jsonify({"users": users_list})
        finally:
            conn.close()

    @app.route("/api/admin/users", methods=["POST"])
    @admin_required
    def admin_create_user(_admin: dict[str, Any]):
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        display_name = str(data.get("display_name", "")).strip() or username
        password = str(data.get("password", ""))
        role = str(data.get("role", "user")).strip()
        course_ids = data.get("course_ids") or []

        if not username or len(username) < 2:
            return jsonify({"error": "Nome de usuário deve ter ao menos 2 caracteres."}), 400
        if not password or len(password) < 4:
            return jsonify({"error": "A senha deve ter ao menos 4 caracteres."}), 400
        if role not in ("admin", "user"):
            return jsonify({"error": "Perfil inválido."}), 400

        conn = get_db()
        try:
            exists = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if exists:
                return jsonify({"error": "Este nome de usuário já está em uso."}), 409

            ts = now_iso()
            cur = conn.execute(
                """
                INSERT INTO users (username, display_name, password_hash, role, active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (username, display_name, generate_password_hash(password), role, ts),
            )
            new_id = cur.lastrowid

            for cid in course_ids:
                c_exists = conn.execute("SELECT id FROM courses WHERE id = ?", (cid,)).fetchone()
                if c_exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO course_access (user_id, course_id, granted_at) VALUES (?, ?, ?)",
                        (new_id, cid, ts),
                    )

            conn.commit()
            return jsonify({"id": new_id, "username": username}), 201
        finally:
            conn.close()

    @app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
    @admin_required
    def admin_update_user(admin_user: dict[str, Any], user_id: int):
        data = request.get_json(silent=True) or {}
        conn = get_db()
        try:
            target = conn.execute("SELECT id, username, role, active FROM users WHERE id = ?", (user_id,)).fetchone()
            if not target:
                return jsonify({"error": "Usuário não encontrado."}), 404

            display_name = str(data.get("display_name", "")).strip()
            role = data.get("role", target["role"])
            active = data.get("active", bool(target["active"]))

            if target["id"] == admin_user["id"] and (not active or role != "admin"):
                return jsonify({"error": "Não é possível desativar ou remover o próprio acesso de administrador."}), 400
            if role not in ("admin", "user"):
                return jsonify({"error": "Perfil inválido."}), 400

            conn.execute(
                """
                UPDATE users
                SET display_name = COALESCE(NULLIF(?, ''), display_name),
                    role = ?,
                    active = ?
                WHERE id = ?
                """,
                (display_name, role, 1 if active else 0, user_id),
            )
            conn.commit()
            return jsonify({"ok": True})
        finally:
            conn.close()

    @app.route("/api/admin/users/<int:user_id>/reset-password", methods=["POST"])
    @admin_required
    def admin_reset_password(_admin: dict[str, Any], user_id: int):
        data = request.get_json(silent=True) or {}
        new_password = str(data.get("password", ""))
        if len(new_password) < 4:
            return jsonify({"error": "A nova senha deve ter ao menos 4 caracteres."}), 400

        conn = get_db()
        try:
            target = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not target:
                return jsonify({"error": "Usuário não encontrado."}), 404

            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_password), user_id),
            )
            conn.commit()
            return jsonify({"ok": True})
        finally:
            conn.close()

    @app.route("/api/admin/users/<int:user_id>/courses", methods=["PUT"])
    @admin_required
    def admin_set_user_courses(_admin: dict[str, Any], user_id: int):
        data = request.get_json(silent=True) or {}
        course_ids = data.get("course_ids")
        if not isinstance(course_ids, list):
            return jsonify({"error": "'course_ids' deve ser uma lista."}), 400

        conn = get_db()
        try:
            target = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not target:
                return jsonify({"error": "Usuário não encontrado."}), 404

            conn.execute("DELETE FROM course_access WHERE user_id = ?", (user_id,))
            ts = now_iso()
            for cid in course_ids:
                c_exists = conn.execute("SELECT id FROM courses WHERE id = ?", (cid,)).fetchone()
                if c_exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO course_access (user_id, course_id, granted_at) VALUES (?, ?, ?)",
                        (user_id, cid, ts),
                    )
            conn.commit()
            return jsonify({"ok": True})
        finally:
            conn.close()

    # ---------------- ADMIN: COURSES & MD IMPORT ----------------

    @app.route("/api/admin/courses", methods=["GET"])
    @admin_required
    def admin_list_courses(_admin: dict[str, Any]):
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT id, title, description, category, source, version, data_json, active, created_at, updated_at FROM courses ORDER BY created_at ASC"
            ).fetchall()
            courses = []
            for r in rows:
                data = json.loads(r["data_json"])
                access_count = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM course_access WHERE course_id = ?", (r["id"],)
                ).fetchone()["cnt"]
                courses.append(
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "description": r["description"],
                        "category": r["category"],
                        "source": r["source"],
                        "version": r["version"],
                        "active": bool(r["active"]),
                        "stats": data.get("stats", {}),
                        "access_count": access_count,
                        "updated_at": r["updated_at"],
                    }
                )
            return jsonify({"courses": courses})
        finally:
            conn.close()

    @app.route("/api/admin/courses/preview-md", methods=["POST"])
    @admin_required
    def admin_preview_md(_admin: dict[str, Any]):
        data = request.get_json(silent=True) or {}
        md_text = str(data.get("markdown", ""))
        parsed = parse_course_markdown(md_text)

        is_update = False
        if parsed["course"] and parsed["course"]["id"]:
            conn = get_db()
            try:
                existing = conn.execute(
                    "SELECT id FROM courses WHERE id = ?", (parsed["course"]["id"],)
                ).fetchone()
                is_update = existing is not None
            finally:
                conn.close()

        return jsonify({**parsed, "isUpdate": is_update})

    @app.route("/api/admin/courses/import-md", methods=["POST"])
    @admin_required
    def admin_import_md(_admin: dict[str, Any]):
        data = request.get_json(silent=True) or {}
        md_text = str(data.get("markdown", ""))
        grant_user_ids = data.get("grant_user_ids") or []

        parsed = parse_course_markdown(md_text)
        if not parsed["valid"]:
            return jsonify({"error": "Markdown inválido.", "errors": parsed["errors"]}), 400

        course = parsed["course"]
        ts = now_iso()
        conn = get_db()
        try:
            existing = conn.execute("SELECT id FROM courses WHERE id = ?", (course["id"],)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE courses
                    SET title = ?, description = ?, category = ?, source = ?, version = ?, data_json = ?, raw_md = ?, active = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        course["title"],
                        course["description"],
                        course["category"],
                        course["source"],
                        course["version"],
                        json.dumps(course, ensure_ascii=False),
                        md_text,
                        ts,
                        course["id"],
                    ),
                )
                updated = True
            else:
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
                        md_text,
                        ts,
                        ts,
                    ),
                )
                updated = False

            for uid in grant_user_ids:
                u_exists = conn.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
                if u_exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO course_access (user_id, course_id, granted_at) VALUES (?, ?, ?)",
                        (uid, course["id"], ts),
                    )

            conn.commit()
            return jsonify({"ok": True, "updated": updated, "course": course}), (200 if updated else 201)
        finally:
            conn.close()

    @app.route("/api/admin/courses/<course_id>", methods=["PATCH"])
    @admin_required
    def admin_toggle_course(_admin: dict[str, Any], course_id: str):
        data = request.get_json(silent=True) or {}
        conn = get_db()
        try:
            row = conn.execute("SELECT id, active FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not row:
                return jsonify({"error": "Curso não encontrado."}), 404
            active = bool(data.get("active", not bool(row["active"])))
            conn.execute(
                "UPDATE courses SET active = ?, updated_at = ? WHERE id = ?",
                (1 if active else 0, now_iso(), course_id),
            )
            conn.commit()
            return jsonify({"ok": True, "active": active})
        finally:
            conn.close()

    @app.route("/api/admin/progress", methods=["GET"])
    @admin_required
    def admin_progress_overview(_admin: dict[str, Any]):
        conn = get_db()
        try:
            users_rows = conn.execute(
                "SELECT id, username, display_name, role, active FROM users ORDER BY id ASC"
            ).fetchall()
            courses_rows = conn.execute(
                "SELECT id, title, data_json FROM courses WHERE active = 1 ORDER BY created_at ASC"
            ).fetchall()
            courses_map = {r["id"]: json.loads(r["data_json"]) for r in courses_rows}

            overview = []
            for u in users_rows:
                if u["role"] == "admin":
                    accessible = list(courses_map.keys())
                else:
                    accessible = [
                        r["course_id"]
                        for r in conn.execute(
                            "SELECT course_id FROM course_access WHERE user_id = ?", (u["id"],)
                        ).fetchall()
                        if r["course_id"] in courses_map
                    ]

                course_entries = []
                for cid in accessible:
                    completed = _get_user_completed_units(conn, u["id"], cid)
                    stats = compute_course_stats(courses_map[cid], completed)
                    course_entries.append(
                        {
                            "course_id": cid,
                            "course_title": courses_map[cid]["title"],
                            "xp": stats["totalXp"],
                            "level": stats["level"],
                            "percent": stats["percent"],
                            "completedModules": stats["completedModulesCount"],
                            "totalModules": stats["totalModulesCount"],
                            "unlockedTrophies": len(stats["unlockedTrophies"]),
                            "totalTrophies": len(courses_map[cid].get("trophies", [])),
                        }
                    )

                overview.append(
                    {
                        "user_id": u["id"],
                        "username": u["username"],
                        "display_name": u["display_name"],
                        "role": u["role"],
                        "active": bool(u["active"]),
                        "courses": course_entries,
                    }
                )
            return jsonify({"overview": overview})
        finally:
            conn.close()

    return app


if __name__ == "__main__":
    application = create_app()
    port = int(os.environ.get("PORT", 5000))
    application.run(host="127.0.0.1", port=port, debug=False)
