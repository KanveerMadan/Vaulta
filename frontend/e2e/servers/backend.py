"""
Start the API for browser tests: a fresh local database, migrations applied
from empty (alembic upgrade head) as the owner, the API as the vaulta_app role, Firebase tokens checked against the local
Auth emulator, the LLM pointed at servers/fake_llm.py. Refuses non-local DBs.

  E2E_DATABASE_URL   default postgresql://vaulta@localhost:54329/vaulta_e2e
  E2E_PYTHON         interpreter with backend requirements (default backend/venv/bin/python)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

REPO = Path(__file__).resolve().parents[3]
URL = os.environ.get("E2E_DATABASE_URL", "postgresql://vaulta@localhost:54329/vaulta_e2e")
PY = os.environ.get("E2E_PYTHON", str(REPO / "backend/venv/bin/python"))
parsed = urlparse(URL)
assert parsed.hostname in ("localhost", "127.0.0.1"), "browser tests only run against a local database"

# Fresh database
name = parsed.path.lstrip("/")
admin = urlunparse(parsed._replace(path="/postgres"))
# browser-test launcher: runs the developer's own interpreter on a local database
# nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
subprocess.run([PY, "-c", f"""
import psycopg2
c = psycopg2.connect({admin!r}); c.autocommit = True
cur = c.cursor()
cur.execute('DROP DATABASE IF EXISTS {name} WITH (FORCE)')
cur.execute('CREATE DATABASE {name}')
cur.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN "
            "CREATE ROLE vaulta_app LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$")
"""], check=True)
# The API connects as vaulta_app (row-level security applies); migrations run as the database owner, as in production
APP_URL = urlunparse(parsed._replace(netloc=f"vaulta_app@{parsed.netloc.split('@')[-1]}"))

import secrets  # noqa: E402
# browser-test launcher: runs the developer's own interpreter on a local database
# nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
pem = subprocess.run([PY, "-c", """
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
print(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
"""], capture_output=True, text=True, check=True).stdout

env = {
    **os.environ,
    "DATABASE_URL": APP_URL,
    "MIGRATION_DATABASE_URL": URL,
    "MASTER_KEY": secrets.token_urlsafe(48),
    "BLIND_INDEX_KEY": secrets.token_urlsafe(48),
    "FIREBASE_SERVICE_ACCOUNT_JSON": json.dumps({
        "type": "service_account", "project_id": "demo-vaulta", "private_key_id": "e2e", "private_key": pem,
        "client_email": "e2e@demo-vaulta.iam.gserviceaccount.com", "client_id": "0", "token_uri": "https://oauth2.googleapis.com/token"}),
    "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
    "ENVIRONMENT": "test",
    "SECRET_KEY": "e2e-secret-key-not-for-production-use-0123456789",
    "INTERNAL_SECRET": "e2e-internal-secret-not-for-production-0123456789",
    "BACKEND_CORS_ORIGINS": "http://localhost:4173",
    "GROQ_API_KEY": "fake", "GROQ_API_URL": "http://127.0.0.1:8002/v1/chat/completions",
    "INBOUND_DOMAIN": "vaulta.test",
    "DEMO_SESSIONS_PER_IP": "100000",   # every browser test starts its demo from 127.0.0.1
    "TELEGRAM_BOT_TOKEN": "0:e2e", "TELEGRAM_BOT_USERNAME": "VaultaTestBot", "TELEGRAM_WEBHOOK_SECRET": "e2e",
    "RESEND_API_KEY": "", "EMAIL_FROM": "", "RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "",
}
# browser-test launcher: runs the developer's own interpreter on a local database
# nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
subprocess.run([PY, "-m", "alembic", "upgrade", "head"], cwd=REPO, env=env, check=True)
# browser-test launcher: runs the developer's own interpreter on a local database
# nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
subprocess.run([PY, "-m", "app.services.demo"], cwd=REPO / "backend", env=env, check=True)   # as a deploy would
os.chdir(REPO / "backend")
# browser-test launcher: runs the developer's own interpreter on a local database
# nosemgrep: python.lang.security.audit.dangerous-os-exec-tainted-env-args.dangerous-os-exec-tainted-env-args
os.execve(PY, [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"], env)
