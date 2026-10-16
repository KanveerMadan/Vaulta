"""/health (liveness) and /health/ready (database, migrations at head, RLS) for Render's health check."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core import database
from app.core.config import settings
from tests.conftest import owner_engine

REPO = Path(__file__).resolve().parents[2]


def test_migration_head_constant_matches_alembic():
    script = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert script.get_heads() == [database.MIGRATION_HEAD]


def test_ready_when_database_migrations_and_rls_are_right(client):
    assert client.get("/health").json()["status"] == "ok"
    res = client.get("/health/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ready", "database": "ok", "migrations": "at head", "rls": "enforced"}


def test_not_ready_when_migrations_are_behind(client):
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'a5c1e7f9b0d3'"))
    try:
        res = client.get("/health/ready")
        assert res.status_code == 503 and res.json()["migrations"] == f"at a5c1e7f9b0d3, expected {database.MIGRATION_HEAD}"
    finally:
        with owner_engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :v"), {"v": database.MIGRATION_HEAD})


def test_production_is_not_ready_when_rls_is_bypassed(client, monkeypatch):
    monkeypatch.setattr(database, "check_role", lambda conn: "superuser")
    assert client.get("/health/ready").status_code == 200                      # tolerated outside production
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    res = client.get("/health/ready")
    assert res.status_code == 503 and res.json()["rls"] == "bypassed"
