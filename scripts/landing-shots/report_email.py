"""
The weekly report email for the landing page, rendered by the real template (backend/app/services/report_email.py)
from the DEMO account's data, seeded into a LOCAL database. Nothing real is read: throwaway keys, no AI key (the
summary then uses its plain fallback), local database only.

  backend/venv/bin/python scripts/landing-shots/report_email.py postgresql://vaulta@localhost:54329/vaulta_stage out.html
"""
import os
import secrets
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

url, out = sys.argv[1], Path(sys.argv[2])
assert urlparse(url).hostname in ("localhost", "127.0.0.1"), "local databases only"
REPO = Path(__file__).resolve().parents[2]
env = {"DATABASE_URL": url, "MIGRATION_DATABASE_URL": url, "MASTER_KEY": secrets.token_urlsafe(48),
       "BLIND_INDEX_KEY": secrets.token_urlsafe(48), "FIREBASE_SERVICE_ACCOUNT_JSON": "{}", "ENVIRONMENT": "development",
       "APP_BASE_URL": "https://vaulta.in", "API_BASE_URL": "https://api.vaulta.in",
       **{k: "" for k in ("GROQ_API_KEY", "RESEND_API_KEY", "SENTRY_DSN", "TELEGRAM_BOT_TOKEN", "RECAPTCHA_SECRET_KEY")}}
os.environ.update(env)
# throwaway keys every run, so start from an empty schema every run
import psycopg2  # noqa: E402
with psycopg2.connect(url) as conn, conn.cursor() as cur:
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPO, env={**os.environ}, check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

sys.path.insert(0, str(REPO / "backend"))
from app.core.database import SessionLocal  # noqa: E402
from app.services import demo, report_email, reports  # noqa: E402

with SessionLocal() as db:
    user = demo.seed(db)
    report, _ = reports.generate(db, user.id, "weekly", date.today() - timedelta(days=7))   # last full week
    subject, html, _text, _headers = report_email.render(report, user)
    out.write_text(html)
    print("rendered:", subject)
