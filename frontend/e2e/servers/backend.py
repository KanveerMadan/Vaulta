"""
Start the API for browser tests: a fresh local database, migrations applied
from empty (alembic upgrade head), Firebase tokens checked against the local
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
subprocess.run([PY, "-c", f"""
import psycopg2
c = psycopg2.connect({admin!r}); c.autocommit = True
cur = c.cursor()
cur.execute('DROP DATABASE IF EXISTS {name} WITH (FORCE)')
cur.execute('CREATE DATABASE {name}')
"""], check=True)

key = subprocess.run([PY, "-c", "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"],
                     capture_output=True, text=True, check=True).stdout.strip()
pem = subprocess.run([PY, "-c", """
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
print(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
"""], capture_output=True, text=True, check=True).stdout

env = {
    **os.environ,
    "DATABASE_URL": URL,
    "ENCRYPTION_KEY": key,
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
    "TELEGRAM_BOT_TOKEN": "0:e2e", "TELEGRAM_BOT_USERNAME": "VaultaTestBot", "TELEGRAM_WEBHOOK_SECRET": "e2e",
    "RESEND_API_KEY": "", "EMAIL_FROM": "", "RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "",
}
subprocess.run([PY, "-m", "alembic", "upgrade", "head"], cwd=REPO, env=env, check=True)
subprocess.run([PY, "-m", "app.services.demo"], cwd=REPO / "backend", env=env, check=True)   # as a deploy would
os.chdir(REPO / "backend")
os.execve(PY, [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"], env)
