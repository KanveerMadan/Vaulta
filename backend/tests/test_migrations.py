"""Migrations build an empty database, roll back fully, re-apply, and match the models."""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg2
import pytest

from tests.conftest import TEST_DATABASE_URL

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def fresh_db_url():
    parsed = urlparse(TEST_DATABASE_URL)
    name = "vaulta_migration_check"
    admin = psycopg2.connect(urlunparse(parsed._replace(path="/postgres")))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name}")
        cur.execute(f"CREATE DATABASE {name}")
    yield urlunparse(parsed._replace(path=f"/{name}"))
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    admin.close()


def alembic(url, *args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO, env={**os.environ, "DATABASE_URL": url, "MIGRATION_DATABASE_URL": url}, capture_output=True, text=True,
    )


def test_upgrade_downgrade_upgrade_on_empty_database(fresh_db_url):
    for step in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        result = alembic(fresh_db_url, *step)
        assert result.returncode == 0, f"alembic {' '.join(step)} failed:\n{result.stderr[-3000:]}"
    check = alembic(fresh_db_url, "check")
    assert check.returncode == 0, f"schema drift between migrations and models:\n{check.stdout[-2000:]}{check.stderr[-3000:]}"
