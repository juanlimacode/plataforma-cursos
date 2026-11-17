"""End-to-end tests for authentication, permissions, user isolation, reversible XP/trophies, and Markdown import."""

import os
import sys
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_plataforma.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def logout(client):
    return client.post("/api/auth/logout")


def test_admin_login_and_initial_seed(client):
    # Unauthenticated access is blocked
    assert client.get("/api/courses").status_code == 401

    # Wrong password fails
    assert login(client, "ADMIN", "wrongpass").status_code == 401

    # Initial ADMIN login succeeds
    res = login(client, "ADMIN", "adminppnj")
    assert res.status_code == 200
    assert res.get_json()["user"]["role"] == "admin"

    # Initial Power BI & Power Platform course is seeded
    courses_res = client.get("/api/courses")
    assert courses_res.status_code == 200
    courses = courses_res.get_json()["courses"]
    assert len(courses) == 1
    assert courses[0]["id"] == "power-bi-power-platform"
    assert courses[0]["stats"]["totalModulesCount"] == 18
    assert courses[0]["stats"]["totalTrophiesCount"] == 5


def test_user_permissions_and_deactivation(client):
    login(client, "ADMIN", "adminppnj")

    # Create Alice with access and Bob without access
    r1 = client.post(
        "/api/admin/users",
        json={
            "username": "alice",
            "display_name": "Alice Silva",
            "password": "alice123",
            "role": "user",
            "course_ids": ["power-bi-power-platform"],
        },
    )
    assert r1.status_code == 201
    alice_id = r1.get_json()["id"]

    r2 = client.post(
        "/api/admin/users",
        json={
            "username": "bob",
            "display_name": "Bob Costa",
            "password": "bob123",
            "role": "user",
            "course_ids": [],
        },
    )
    assert r2.status_code == 201
    logout(client)

    # Bob cannot see course or access admin
    assert login(client, "bob", "bob123").status_code == 200
    assert client.get("/api/courses").get_json()["courses"] == []
    assert client.get("/api/courses/power-bi-power-platform").status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    logout(client)

    # Alice sees the course
    assert login(client, "alice", "alice123").status_code == 200
    assert len(client.get("/api/courses").get_json()["courses"]) == 1

    # Admin deactivates Alice and resets her password
    logout(client)
    login(client, "ADMIN", "adminppnj")
    assert client.put(f"/api/admin/users/{alice_id}", json={"active": False, "role": "user"}).status_code == 200
    assert client.post(f"/api/admin/users/{alice_id}/reset-password", json={"password": "newpass99"}).status_code == 200
    logout(client)

    # Deactivated Alice cannot log in
    assert login(client, "alice", "newpass99").status_code == 403


def test_progress_isolation_xp_and_reversible_trophies(client):
    login(client, "ADMIN", "adminppnj")
    client.post(
        "/api/admin/users",
        json={
            "username": "alice",
            "display_name": "Alice",
            "password": "alice123",
            "role": "user",
            "course_ids": ["power-bi-power-platform"],
        },
    )
    client.post(
        "/api/admin/users",
        json={
            "username": "bob",
            "display_name": "Bob",
            "password": "bob123",
            "role": "user",
            "course_ids": ["power-bi-power-platform"],
        },
    )
    logout(client)

    # Alice completes first unit u1-1 (c-1 has 300 XP / 6 units = 50 XP)
    login(client, "alice", "alice123")
    res = client.post("/api/courses/power-bi-power-platform/units/u1-1/toggle")
    assert res.status_code == 200
    prog = res.get_json()["progress"]
    assert prog["totalXp"] == 50
    assert "trophy-1" in prog["unlockedTrophies"]

    # Alice unmarks u1-1 -> XP drops to 0 and trophy-1 is reverted!
    res2 = client.post("/api/courses/power-bi-power-platform/units/u1-1/toggle")
    prog2 = res2.get_json()["progress"]
    assert prog2["totalXp"] == 0
    assert "trophy-1" not in prog2["unlockedTrophies"]

    # Complete all units of c-17 (9 units, 1200 XP) and c-18 (3 units, 800 XP) -> trophy-3 unlocks
    for uid in [f"u17-{i}" for i in range(1, 10)] + [f"u18-{i}" for i in range(1, 4)]:
        r = client.post(f"/api/courses/power-bi-power-platform/units/{uid}/toggle")
    prog3 = r.get_json()["progress"]
    assert prog3["totalXp"] == 2000
    assert prog3["level"] == 4  # floor(2000 / 600) + 1 = 4
    assert prog3["completedModulesCount"] == 2
    assert "trophy-3" in prog3["unlockedTrophies"]

    # Unmark one unit of c-18 -> module c-18 incomplete & trophy-3 reverts
    r_rev = client.post("/api/courses/power-bi-power-platform/units/u18-3/toggle")
    prog4 = r_rev.get_json()["progress"]
    assert prog4["completedModulesCount"] == 1
    assert "trophy-3" not in prog4["unlockedTrophies"]
    logout(client)

    # Bob's progress is completely isolated
    login(client, "bob", "bob123")
    bob_prog = client.get("/api/courses/power-bi-power-platform").get_json()["progress"]
    assert bob_prog["totalXp"] == 0
    assert bob_prog["completedUnitsCount"] == 0


def test_markdown_import_validation_and_progress_preservation(client):
    login(client, "ADMIN", "adminppnj")
    u_res = client.post(
        "/api/admin/users",
        json={"username": "carlos", "password": "carlos123", "role": "user", "course_ids": []},
    )
    carlos_id = u_res.get_json()["id"]

    # Invalid MD with unsafe link
    bad_md = """---
id: curso-ruim
titulo: "Curso Ruim"
---
## Trilha: T1
- id: t1
### Módulo: M1
- id: m1
- link: javascript:alert(1)
- xp: 100
#### Unidade: U1
- id: u1
"""
    prev_bad = client.post("/api/admin/courses/preview-md", json={"markdown": bad_md}).get_json()
    assert prev_bad["valid"] is False
    assert any("link inválido" in e for e in prev_bad["errors"])

    # Valid MD v1
    good_md_v1 = """---
id: sql-essencial
versao: 1
titulo: "SQL Essencial"
descricao: "Consultas SQL."
categoria: "Dados"
fonte: "Interno"
---
## Trilha: Fundamentos
- id: t1
- descricao: Base SQL
### Módulo: SELECT
- id: m1
- link: https://learn.microsoft.com/pt-br/sql/
- etiqueta: Iniciante
- xp: 200
#### Unidade: SELECT básico
- id: sql-u1
- duracao: 10 min
#### Unidade: WHERE
- id: sql-u2
- duracao: 10 min
## Conquistas
### Conquista: Primeiro SQL
- id: sql-ach1
- descricao: Complete 1 unidade
- tipo: unidades_concluidas
- operador: ">="
- meta: 1
"""
    imp = client.post(
        "/api/admin/courses/import-md",
        json={"markdown": good_md_v1, "grant_user_ids": [carlos_id]},
    )
    assert imp.status_code == 201
    logout(client)

    # Carlos completes sql-u1
    login(client, "carlos", "carlos123")
    t_res = client.post("/api/courses/sql-essencial/units/sql-u1/toggle")
    assert t_res.status_code == 200
    assert t_res.get_json()["progress"]["totalXp"] == 100
    logout(client)

    # Admin updates sql-essencial adding sql-u3 (stable IDs sql-u1, sql-u2 preserved)
    login(client, "ADMIN", "adminppnj")
    good_md_v2 = good_md_v1.replace(
        "#### Unidade: WHERE\n- id: sql-u2\n- duracao: 10 min",
        "#### Unidade: WHERE\n- id: sql-u2\n- duracao: 10 min\n#### Unidade: ORDER BY\n- id: sql-u3\n- duracao: 10 min",
    ).replace("xp: 200", "xp: 300")
    upd = client.post("/api/admin/courses/import-md", json={"markdown": good_md_v2})
    assert upd.status_code == 200
    assert upd.get_json()["updated"] is True
    logout(client)

    # Carlos still has sql-u1 completed (now 300/3 = 100 XP)
    login(client, "carlos", "carlos123")
    c_prog = client.get("/api/courses/sql-essencial").get_json()["progress"]
    assert c_prog["completedUnits"] == ["sql-u1"]
    assert c_prog["totalUnitsCount"] == 3
    assert c_prog["totalXp"] == 100


def test_localstorage_migration_and_json_backup(client):
    login(client, "ADMIN", "adminppnj")
    mig = client.post(
        "/api/courses/power-bi-power-platform/migrate-local",
        json={"completedUnits": ["u1-1", "u1-2", "non-existent-id"]},
    )
    assert mig.status_code == 200
    data = mig.get_json()
    assert data["migratedCount"] == 2
    assert data["progress"]["completedUnitsCount"] == 2

    # Reset and restore via JSON backup
    client.post("/api/courses/power-bi-power-platform/reset")
    imp = client.post(
        "/api/courses/power-bi-power-platform/import-json",
        json={"completedUnits": ["u1-1", "u1-2", "u1-3"]},
    )
    assert imp.status_code == 200
    assert imp.get_json()["progress"]["completedUnitsCount"] == 3
