#!/usr/bin/env bash
# Phase 6 staging rehearsal: run the go-live database steps on a Neon branch copied from production, then check
# everything. Production itself is never touched: every command runs against the branch "staging".
#
#   npx neonctl@7.0.4 auth                                  # once, in your browser
#   NEON_PROJECT=<id> NEON_PROD_BRANCH=<name> scripts/staging-rehearsal.sh
#
# Local dry run against a disposable local database instead of Neon (what CI-less checking uses):
#   scripts/staging-rehearsal.sh --local postgresql://vaulta@localhost:54329/vaulta_stage
#
# What it does:
#   1. creates the branch "staging" from production (fails if it already exists: delete it first)
#   2. creates the vaulta_app role on that branch, with a random password that lives only in this shell
#   3. records row counts, runs `alembic upgrade head` (encryption + RLS) with keys generated for staging only
#   4. backend/scripts/staging_verify.py: counts preserved, every transaction has a kind, no plaintext left,
#      RLS on, the app role sees nothing unbound, each user's last three months of spending
#   5. starts the API exactly as render.yaml does, as vaulta_app, and checks /health/ready
#   6. runs the browser smoke tests (landing, demo, sign-up, import, chat, settings) against that API
# Secrets and connection strings are kept in shell variables and never printed. Delete the branch afterwards:
#   npx neonctl@7.0.4 branches delete staging --project-id $NEON_PROJECT
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
REPO=$PWD
PY=${PY:-$REPO/backend/venv/bin/python}
NEON="npx --yes neonctl@7.0.4"
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"; [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true' EXIT
rand() { "$PY" -c "import secrets; print(secrets.token_urlsafe(${1:-48}))"; }

if [ "${1:-}" = "--local" ]; then
  OWNER_URL=$2
  APP_URL=$("$PY" -c "import sys; from urllib.parse import urlparse, urlunparse; p = urlparse(sys.argv[1]); print(urlunparse(p._replace(netloc='vaulta_app@' + p.netloc.split('@')[-1])))" "$OWNER_URL")
  psql "$OWNER_URL" -q -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN CREATE ROLE vaulta_app LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END \$\$"
  echo "== local rehearsal"
else
  : "${NEON_PROJECT:?set NEON_PROJECT (npx neonctl@7.0.4 projects list)}"
  : "${NEON_PROD_BRANCH:?set NEON_PROD_BRANCH (npx neonctl@7.0.4 branches list --project-id \$NEON_PROJECT)}"
  echo "== 1. branch staging from $NEON_PROD_BRANCH"
  $NEON branches create --project-id "$NEON_PROJECT" --parent "$NEON_PROD_BRANCH" --name staging --output json >/dev/null
  OWNER_URL=$($NEON connection-string staging --project-id "$NEON_PROJECT" --role-name neondb_owner --ssl require)
  echo "== 2. vaulta_app role on staging"
  APP_PASSWORD=$(rand 32)
  psql "$OWNER_URL" -q -v ON_ERROR_STOP=1 -v pw="$APP_PASSWORD" <<'SQL'
CREATE ROLE vaulta_app WITH LOGIN PASSWORD :'pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE neondb TO vaulta_app;
SQL
  POOLED_URL=$($NEON connection-string staging --project-id "$NEON_PROJECT" --role-name neondb_owner --pooled --ssl require)
  APP_URL=$("$PY" -c "import sys; from urllib.parse import quote, urlparse, urlunparse; p = urlparse(sys.argv[1]); print(urlunparse(p._replace(netloc='vaulta_app:' + quote(sys.argv[2], safe='') + '@' + p.netloc.split('@')[-1])))" "$POOLED_URL" "$APP_PASSWORD")
fi

# Staging-only keys: generated here, used for this branch only, gone when the shell exits
export MASTER_KEY BLIND_INDEX_KEY FIREBASE_SERVICE_ACCOUNT_JSON='{}'
MASTER_KEY=$(rand); BLIND_INDEX_KEY=$(rand)

if [ "$(psql "$OWNER_URL" -Atc "select to_regclass('public.rate_limits') is not null")" = "t" ]; then
  echo "This database is already migrated (keys from that run are gone). Start from a fresh copy of production:"
  echo "  npx neonctl@7.0.4 branches delete staging --project-id \$NEON_PROJECT   and run this again."
  exit 1
fi

echo "== 3. row counts, then migrations as the owner"
(cd backend && DATABASE_URL="$OWNER_URL" "$PY" scripts/staging_verify.py before "$OWNER_URL" "$STATE/counts.json")
DATABASE_URL="$OWNER_URL" MIGRATION_DATABASE_URL="$OWNER_URL" "$PY" -m alembic current 2>/dev/null | tail -1
DATABASE_URL="$OWNER_URL" MIGRATION_DATABASE_URL="$OWNER_URL" "$PY" -m alembic upgrade head 2>&1 | grep -E "Running upgrade" | sed 's/^INFO  \[alembic.runtime.migration\] //' || true
DATABASE_URL="$OWNER_URL" MIGRATION_DATABASE_URL="$OWNER_URL" "$PY" -m alembic current 2>/dev/null | tail -1

echo "== 4. checks"
(cd backend && DATABASE_URL="$APP_URL" "$PY" scripts/staging_verify.py after "$OWNER_URL" "$APP_URL" "$STATE/counts.json")

echo "== 5. the API as render.yaml starts it, as vaulta_app"
PEM=$("$PY" -c "
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
print(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())")
FIREBASE_SERVICE_ACCOUNT_JSON=$("$PY" -c "import json, sys; print(json.dumps({'type': 'service_account', 'project_id': 'demo-vaulta', 'private_key_id': 's', 'private_key': sys.argv[1], 'client_email': 's@demo-vaulta.iam.gserviceaccount.com', 'client_id': '0', 'token_uri': 'https://oauth2.googleapis.com/token'}))" "$PEM")
(
  cd backend
  export DATABASE_URL="$APP_URL" ENVIRONMENT=staging FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099
  export SECRET_KEY INTERNAL_SECRET; SECRET_KEY=$(rand); INTERNAL_SECRET=$(rand)
  export BACKEND_CORS_ORIGINS=http://localhost:4173 GROQ_API_KEY=fake GROQ_API_URL=http://127.0.0.1:8002/v1/chat/completions
  export INBOUND_DOMAIN=vaulta.test TELEGRAM_BOT_TOKEN=0:e2e TELEGRAM_BOT_USERNAME=VaultaTestBot TELEGRAM_WEBHOOK_SECRET=e2e
  export DEMO_SESSIONS_PER_IP=100000 RESEND_API_KEY= EMAIL_FROM= PORT=8001 WEB_CONCURRENCY=2
  exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --workers "$WEB_CONCURRENCY" \
    --proxy-headers --forwarded-allow-ips='*' --no-access-log
) > "$STATE/api.log" 2>&1 &
API_PID=$!
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8001/health >/dev/null && break; sleep 1; done
READY=$(curl -s http://127.0.0.1:8001/health/ready)
echo "/health/ready: $READY"
case "$READY" in *'"status":"ready"'*'"rls":"enforced"'*) echo "PASS readiness";; *) echo "FAIL readiness"; exit 1;; esac

echo "== 6. browser smoke tests against this API (Firebase emulator, fake LLM)"
cd frontend
E2E_REUSE=1 npx playwright test e2e/public.spec.js e2e/app.spec.js --project=desktop --reporter=line \
  --grep "landing|demo|import|chat|settings|your data|security|privacy" > "$STATE/smoke.log" 2>&1 || true
sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$STATE/smoke.log" | grep -vE "WebServer" \
  | grep -E "^\s+[0-9]+ (passed|failed|skipped)|^\s+\[desktop\] ›|Expected|Received|Error:" | head -20
echo "== done. Delete the branch when finished: npx neonctl@7.0.4 branches delete staging --project-id \$NEON_PROJECT"
