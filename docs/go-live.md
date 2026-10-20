# Go-live runbook — vaulta.in v1.0

This runbook takes vaulta.in from the old app (on `main`, old Render service, US Neon project) to the rebuild
(phases 1–9 + 6.5 + 8, consolidated on `release/v1`, PR #2). Run the steps **in order**. Every step ends with a
**Check**: don't continue until it passes. Rollback for every step is in §12.

**Facts this runbook assumes**

| Thing | Value |
|---|---|
| Local repo | `~/Desktop/vaulta` |
| GitHub | `KanveerMadan/vaulta.in`, release branch `release/v1`, PR #2 (`release/v1` → `main`, DO NOT MERGE until §9) |
| Domain | `vaulta.in` (Cloudflare, Active). App `https://vaulta.in`, API `https://api.vaulta.in`, inbound mail `in.vaulta.in` |
| Old database | Neon project `steep-smoke-31221922`, branch `production`, AWS US East. **Never migrated** — it stays as the rollback copy |
| New database | New Neon project in **AWS Asia Pacific (Singapore)**, created in §1 |
| Old API | Render service "Vaulta" `srv-d8hh6nt7vvec73acib30` (Oregon, auto-deploy OFF) |
| New API | Render service `vaulta-api`, Python, Singapore, Free, created in §2 |
| Frontend | Vercel project `vaulta` (Hobby), root `frontend`, production builds from `main` |
| Firebase | Project `vaulta-a3d7a`; service account `~/vaulta-secrets/vaulta-a3d7a-firebase-adminsdk-fbsvc-3742773cae.json` |
| Contacts | `privacy@vaulta.in` (grievance + privacy), `security@vaulta.in` — both forward to the owner's Gmail |
| Generated secrets | `~/vaulta-render-secrets.env` (mode 600): `SECRET_KEY`, `INTERNAL_SECRET`, `MASTER_KEY`, `BLIND_INDEX_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `VAULTA_APP_PASSWORD`, `VAULTA_BACKUP_PASSWORD`. Copy each to the password manager before deleting the file (§2.5) |

**What to expect**
- **Downtime:** from §1.2 (old API suspended) until §9 (merge) — plan 30–60 minutes. Pick a quiet hour.
- **Cold starts:** the API runs on Render Free with no keep-awake. After ~15 minutes idle the first request takes
  30–60 s; the app shows "Waking up vaulta.in…" and retries. This is expected.
- **Your machine:** `psql`/`pg_dump`/`pg_restore` **version ≥ the Neon Postgres version** (check in Neon → project →
  Settings; it is **18**; `brew install postgresql@18` if needed), `backend/venv` (Python 3.12), Node 22, `gh`,
  `age`, `npx neonctl@7.0.4` (authenticated), `npx wrangler` (logged in).
- **No secrets on screen:** read values into shell variables with `read -rs` (nothing echoes, nothing goes in shell
  history). Never paste a secret into a chat, a commit or a file inside the repo.

---

## 0. Before you start

```sh
cd ~/Desktop/vaulta
git fetch && git checkout release/v1 && git pull
export DOMAIN=vaulta.in
export OLD_NEON_PROJECT=steep-smoke-31221922
export OLD_NEON_BRANCH=production
gh pr checks 2 --repo KanveerMadan/vaulta.in      # every job green
backend/venv/bin/python -m alembic heads        # prints the head revision (c8d4e6f0a1b3 today)
export HEAD_REV=$(backend/venv/bin/python -m alembic heads | awk '{print $1}')
# a secret from the generated file, without showing it:  secret NAME
secret() { grep "^$1=" ~/vaulta-render-secrets.env | cut -d= -f2-; }
```

**Check:**
- PR #2 checks are all green.
- These are done (prep): Firebase password policy (§3a.3), authorised domains, reCAPTCHA v3 keys, Resend domain
  added, Telegram bot created, Cloudflare Email Routing on with `privacy@` and `security@` rules, Groq key rotated,
  `BACKUP_AGE_RECIPIENT` set in GitHub, Vercel variables set (§3).
- The Groq key in `backend/.env` and in the password manager is the **new** one; the old one is deleted in Groq.

---

## 1. Neon: new Singapore project, copy data, migrate, app role, RLS

The old US project is **copied, never migrated**. That keeps it as an instant rollback.

**1.1 Create the new project.** Neon console → **New project**:
- Name `vaulta`, **Region: AWS Asia Pacific (Singapore)**, **Postgres version 18** (the same as the old project).
- Neon creates a default branch (`main` or `production`) and database `neondb` owned by `neondb_owner`.

Or from the terminal (same result): `npx neonctl@7.0.4 projects create --name vaulta --region-id aws-ap-southeast-1 --pg-version 18`

```sh
npx neonctl@7.0.4 projects list                 # note the new project's id
export NEW_NEON_PROJECT=<new id>
npx neonctl@7.0.4 branches list --project-id $NEW_NEON_PROJECT   # note its default branch name
export NEW_NEON_BRANCH=<that name>
```
If the free plan refuses a second project, stop and report it — the fallback is to keep the US project and accept
the latency.

**Check:** the new project shows region **Singapore** in the console.

**1.2 Stop writes to the old database.** Render → old "Vaulta" service (`srv-d8hh6nt7vvec73acib30`) → **Suspend**.
From here until §9 the app is down.

**Check:** the old API URL no longer answers `/health`.

**1.3 Connection strings** (owner, **direct** host — Neon → Connect → untick "Connection pooling", append
`?sslmode=require`):
```sh
OLD_OWNER_URL=$(npx neonctl@7.0.4 connection-string $OLD_NEON_BRANCH --project-id $OLD_NEON_PROJECT --role-name neondb_owner --ssl require)
NEW_OWNER_URL=$(npx neonctl@7.0.4 connection-string $NEW_NEON_BRANCH --project-id $NEW_NEON_PROJECT --role-name neondb_owner --ssl require)
APP_PASSWORD=$(secret VAULTA_APP_PASSWORD); BACKUP_PASSWORD=$(secret VAULTA_BACKUP_PASSWORD)
export OLD_OWNER_URL NEW_OWNER_URL APP_PASSWORD BACKUP_PASSWORD
```
**Check:** both of these print `neondb_owner`:
```sh
psql "$OLD_OWNER_URL" -Atc "select current_user"
psql "$NEW_OWNER_URL" -Atc "select current_user"
```

**1.4 Copy the data.** The dump is **plaintext financial data** (the old DB is unencrypted) — it lives only in
`/tmp` and is deleted right after.
```sh
psql "$OLD_OWNER_URL" -Atc "select 'users', count(*) from users union all select 'transactions', count(*) from transactions" | tee /tmp/vaulta-counts-before.txt
pg_dump "$OLD_OWNER_URL" --no-owner --no-privileges -Fc -f /tmp/vaulta-old.dump
pg_restore --no-owner --no-privileges -d "$NEW_OWNER_URL" /tmp/vaulta-old.dump
rm -P /tmp/vaulta-old.dump
```
**Check:**
- `psql "$NEW_OWNER_URL" -Atc "select 'users', count(*) from users union all select 'transactions', count(*) from transactions"` matches `/tmp/vaulta-counts-before.txt`.
- `ls /tmp/vaulta-old.dump` → "No such file".
- `pg_restore` printed no errors other than harmless "already exists" notices for extensions.

**1.5 Snapshot the new project before migrating:**
```sh
npx neonctl@7.0.4 branches create --project-id $NEW_NEON_PROJECT --parent $NEW_NEON_BRANCH --name pre-v1-$(date +%Y%m%d-%H%M)
```
**Check:** `npx neonctl@7.0.4 branches list --project-id $NEW_NEON_PROJECT` lists `pre-v1-…`.

**1.6 The app role and the backup role** (SQL only — roles created in the Neon console can bypass RLS). Before
§1.7: the migrations grant the tables to `vaulta_app`, so it must exist first.
```sh
psql "$NEW_OWNER_URL" -v ON_ERROR_STOP=1 -v pw="$APP_PASSWORD" -v bpw="$BACKUP_PASSWORD" <<'SQL'
CREATE ROLE vaulta_app WITH LOGIN PASSWORD :'pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE neondb TO vaulta_app;
CREATE ROLE vaulta_backup WITH LOGIN PASSWORD :'bpw' NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT pg_read_all_data TO vaulta_backup;
SQL
```
**Check:** `psql "$NEW_OWNER_URL" -Atc "select rolname, rolsuper, rolbypassrls from pg_roles where rolname like 'vaulta_%' order by 1"`
prints `vaulta_app|f|f` and `vaulta_backup|f|t` (the backup role reads everything, writes nothing; tested on a Neon
branch 2026-10-19).

**1.7 Migrate** (all migrations: kind backfill, budgets constraint, encryption, RLS, and later ones):
```sh
cd ~/Desktop/vaulta
MASTER_KEY=$(secret MASTER_KEY) BLIND_INDEX_KEY=$(secret BLIND_INDEX_KEY); export MASTER_KEY BLIND_INDEX_KEY   # the values that go on Render
export MIGRATION_DATABASE_URL="$NEW_OWNER_URL" DATABASE_URL="$NEW_OWNER_URL" FIREBASE_SERVICE_ACCOUNT_JSON='{}'
backend/venv/bin/python -m alembic current
backend/venv/bin/python -m alembic upgrade head 2>&1 | grep -E "Running upgrade|Error"   # filtered: never print settings
backend/venv/bin/python -m alembic current
```
If it says forwarding tokens need `ENCRYPTION_KEY`: `read -rs ENCRYPTION_KEY; export ENCRYPTION_KEY` (the old
Fernet key from the old Render service's environment), then run `alembic upgrade head` again. A failed run is one
transaction and leaves nothing behind.

**Checks:**
- `alembic current` prints `$HEAD_REV (head)`.
- Counts still match `/tmp/vaulta-counts-before.txt`.
- `psql "$NEW_OWNER_URL" -Atc "select count(*) from transactions where kind is null"` → `0`.
- `psql "$NEW_OWNER_URL" -Atc "select count(*) from transactions where merchant_raw not like 'e1:%' or (merchant_clean is not null and merchant_clean not like 's1:%')"` → `0` (nothing in plaintext).
- `psql "$NEW_OWNER_URL" -Atc "select count(*) from users where data_key is null"` → `0`.
- `psql "$NEW_OWNER_URL" -Atc "select relname from pg_class where relname in ('transactions','users','activity_log') and relrowsecurity"` lists all three.

**1.8 The API's connection string** — **pooled** host, as `vaulta_app`:
`postgresql://vaulta_app:<password>@<new pooled host>/neondb?sslmode=require` → save it in the password manager as
`vaulta.in – DATABASE_URL (app)`.

**Check:** `psql "postgresql://vaulta_app:$APP_PASSWORD@<new pooled host>/neondb?sslmode=require" -Atc "select count(*) from transactions"` → `0` (no user bound → no rows: RLS works).

**1.9 Backups.** The `vaulta_backup` role exists (§1.6). GitHub → repo → Settings → Secrets and variables → Actions:
- **Secret** `BACKUP_DATABASE_URL` = `postgresql://vaulta_backup:<VAULTA_BACKUP_PASSWORD>@<new direct (not pooled) host>/neondb?sslmode=require`
- **Variable** `BACKUP_AGE_RECIPIENT` (set already).

The backup can't be run yet: GitHub only runs (and offers "Run workflow" for) workflows on the default branch, and
`weekly-backup.yml` reaches `main` in §9. The first run is a §10 clean-up item.

---

## 2. Render: new `vaulta-api` service

Render can't change a service's region or runtime, so a new Python service in Singapore replaces the old one. The old
one stays suspended (rollback) until a week after go-live.

**2.1 Create it.** Render → **+ New → Web Service** → Git provider → `KanveerMadan/vaulta.in` → **Connect**:
- **Name** `vaulta-api` · **Language** `Python 3` · **Branch** `release/v1` (switched to `main` in §9)
- **Region** `Singapore (Southeast Asia)` · **Root Directory** `backend`
- **Build Command** `pip install -r requirements.txt`
- **Start Command** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers ${WEB_CONCURRENCY:-1} --proxy-headers --forwarded-allow-ips='*' --no-access-log`
- **Instance Type** `Free`
- **Advanced → Health Check Path** `/health/ready` · **Auto-Deploy** `No`

**2.2 Environment variables** — add each by hand (**not** "Add from .env"). Copy secrets to the clipboard without
showing them:
```sh
grep '^SECRET_KEY=' ~/vaulta-render-secrets.env | cut -d= -f2- | tr -d '\n' | pbcopy   # repeat per key name
python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))), end="")' \
  ~/vaulta-secrets/vaulta-a3d7a-firebase-adminsdk-fbsvc-3742773cae.json | pbcopy
```

| Variable | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `ENVIRONMENT` | `production` |
| `WEB_CONCURRENCY` | `1` |
| `DATABASE_URL` | the `vaulta_app` **pooled** URL from §1.8 |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | the one-line JSON (command above) |
| `SECRET_KEY`, `INTERNAL_SECRET`, `MASTER_KEY`, `BLIND_INDEX_KEY` | from `~/vaulta-render-secrets.env` |
| `ENCRYPTION_KEY` | only if §1.7 needed it; removed after go-live (§10) |
| `BACKEND_CORS_ORIGINS` | `https://vaulta.in` |
| `APP_BASE_URL` | `https://vaulta.in` |
| `API_BASE_URL` | `https://api.vaulta.in` |
| `SECURITY_CONTACT_EMAIL` | `security@vaulta.in` |
| `RECAPTCHA_SECRET_KEY` | the reCAPTCHA v3 **secret** key (only here, never in Vercel or git) |
| `GROQ_API_KEY` | the **new** (rotated) key |
| `SENTRY_DSN` | the **backend** Sentry project DSN |
| `RESEND_API_KEY` | Resend API key (§5) |
| `EMAIL_FROM` | `vaulta.in <noreply@vaulta.in>` |
| `INBOUND_DOMAIN` | `vaulta.in` (the app adds `in.`: addresses are `<token>@in.vaulta.in`) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | §7 |
| `TELEGRAM_WEBHOOK_SECRET` | from `~/vaulta-render-secrets.env` |

Leave unset: `BACKEND_CORS_ORIGIN_REGEX`, `MASTER_KEY_PREVIOUS`, `RECAPTCHA_ENFORCE` (monitor mode until §3a.5),
`RECAPTCHA_DEBUG_TOKEN`. Production refuses to start with a weak secret, an `http://`/local URL, a reCAPTCHA debug
token, `RECAPTCHA_ENFORCE` without `RECAPTCHA_SECRET_KEY`, or a
vercel.app / onrender.com / firebaseapp.com host in `APP_BASE_URL`, `API_BASE_URL` or `EMAIL_FROM`.

Then **Deploy Web Service**.

**2.3 Custom domain:** `vaulta-api` → **Settings → Custom Domains → + Add** → `api.vaulta.in`. Note the target
hostname Render shows (for §4).

**2.4 GitHub Actions settings** (repo → Settings → Secrets and variables → Actions):
- Variable `API_URL` = `https://api.vaulta.in`
- Secret `INTERNAL_SECRET` = same value as on Render
- Variable `BACKUP_AGE_RECIPIENT` (already set) and the backup secrets from §1.9

**2.5** Once every secret is on Render **and** in the password manager: `rm -P ~/vaulta-render-secrets.env`.

**Check** (after §4 DNS for `api` is in place):
```sh
curl -s https://api.vaulta.in/health/ready
```
→ `{"status":"ready","database":"ok","migrations":"at head","rls":"enforced"}`. The first call may take up to a
minute (cold start).

---

## 3. Vercel

`frontend/vercel.json` already allows `https://api.vaulta.in` in `connect-src`, proxies `https://vaulta.in/__/auth/*`
to Firebase, and 308-redirects `vaulta-henna.vercel.app` and `www.vaulta.in` to `https://vaulta.in` (same path).

**3.1 Environment variables** (Settings → Environment Variables). Type **Config**. Edit the existing June values
(hidden) or add new ones. **Production and Preview** unless stated:

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://api.vaulta.in` |
| `VITE_FIREBASE_API_KEY` | `apiKey` from Firebase → Project settings → Your apps → web app (set) |
| `VITE_FIREBASE_AUTH_DOMAIN` | `vaulta.in` (**not** the firebaseapp.com domain) |
| `VITE_FIREBASE_PROJECT_ID` | `vaulta-a3d7a` |
| `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID` | from the same Firebase config (set) |
| `VITE_RECAPTCHA_SITE_KEY` | reCAPTCHA v3 **site** key |
| `VITE_SENTRY_DSN` | frontend Sentry DSN — **Production only** |
| `VITE_PRIVACY_CONTACT` | `privacy@vaulta.in` (set) |
| `VITE_SECURITY_CONTACT` | `security@vaulta.in` (set) |

Never add `measurementId` (no analytics) or `VITE_RECAPTCHA_DEBUG_TOKEN`. (Verified 2026-10-19 with `vercel env pull`:
Preview has the right API, auth domain and contacts.)

**3.2** Settings → General → **Root Directory** = `frontend`.

**3.3** Settings → Deployment Protection → Vercel Authentication **on, Standard Protection** (previews need a Vercel
login; production stays public). Already done.

**3.4 Domains are added at cutover (§9), not now** — adding `vaulta.in` earlier would point it at the old `main`.

**Check:** the latest `release/v1` preview build succeeds (it fails on purpose while any required variable is missing).

---

## 3a. Firebase and Google Cloud

**3a.1 Email enumeration protection: on.** Authentication → Settings → User actions.
Check (prints `INVALID_LOGIN_CREDENTIALS`, not `EMAIL_NOT_FOUND`):
```sh
read -r FIREBASE_WEB_API_KEY      # the public web apiKey (Firebase config)
curl -s "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FIREBASE_WEB_API_KEY" \
  -H 'content-type: application/json' -d '{"email":"nobody-'$RANDOM'@example.com","password":"x","returnSecureToken":true}' | grep -o '"message": "[A-Z_]*'
```

**3a.2 One account per email: on.** Authentication → Settings → User account linking → link accounts with the same
email (default).

**3a.3 Password policy: minimum 10, enforced.** Authentication → Settings → Password policy. Set (done). This
setting is part of Firebase Authentication with Identity Platform; **if enabling it would require a billing
account, leave it** — the app enforces 10 on sign-up and the API on every password change. Document whichever
applies in `/security`.

**3a.4 Google sign-in on vaulta.in.**
- Authorized domains: `vaulta.in`, `www.vaulta.in` (done).
- Google Cloud console (project `vaulta-a3d7a`) → APIs & Services → Credentials → OAuth 2.0 Client IDs → **Web
  client (auto created by Google Service)**:
  - Authorized JavaScript origins: add `https://vaulta.in`
  - Authorized redirect URIs: add `https://vaulta.in/__/auth/handler`
  - Keep the existing firebaseapp.com entries. Save.

**3a.5 Bot checks: reCAPTCHA v3 verified by the API** (no Firebase App Check: its reCAPTCHA v3 provider is
deprecated and the replacement needs billing). Nothing to do in the Firebase console.
1. Keys (done): reCAPTCHA admin console, v3, domains `vaulta.in`, `www.vaulta.in`, `vaulta-henna.vercel.app`, `localhost`.
2. Site key on Vercel as `VITE_RECAPTCHA_SITE_KEY` (§3.1); secret key on Render as `RECAPTCHA_SECRET_KEY` (§2.2).
3. **Monitor first:** leave `RECAPTCHA_ENFORCE` unset for about a day. Render → `vaulta-api` → Logs, search
   `recaptcha:`: lines like `recaptcha: low (score 0.3) on demo (monitor mode)`. Real use should show few of them.
   Optional: `RECAPTCHA_MIN_SCORE` (default `0.5`).
4. **Enforce:** set `RECAPTCHA_ENFORCE=true` on Render → Manual Deploy. Missing or forged tokens are then refused
   (401 `recaptcha_failed`); a low score is only slowed (5 an hour per IP and action), never refused, and writes
   already need a verified email.

Never set `RECAPTCHA_DEBUG_TOKEN` on Render: production refuses to start with it.

**Check (after §9, enforcing):** `curl -s -X POST https://api.vaulta.in/auth/demo` (no token) answers `401` with
`"code":"recaptcha_failed"`; the demo button on `https://vaulta.in` still works.

**3a.6 Email templates:** Authentication → Templates → sender name "vaulta.in" for verification and password reset (and the subject lines, which say "%APP_NAME%": set the public-facing project name to "vaulta.in" in Project settings → General).

**Check (after §9):** Google sign-in works on `https://vaulta.in` and the popup shows `vaulta.in`.

---

## 4. Cloudflare DNS

Cloudflare → `vaulta.in` → DNS → Records → **Add record**. All **DNS only** (grey cloud) — Vercel and Render issue
their own certificates. SSL/TLS mode **Full (strict)**.

**Now (before §9):**

| Name | Type | Target | Proxy |
|---|---|---|---|
| `api` | CNAME | the `vaulta-api` hostname from §2.3 (`vaulta-api-….onrender.com`) | DNS only |

**At cutover (§9), after adding the domains in Vercel:**

| Name | Type | Target | Proxy |
|---|---|---|---|
| `@` | A | the address Vercel shows for `vaulta.in` (usually `76.76.21.21`) | DNS only |
| `www` | CNAME | the target Vercel shows for `www.vaulta.in` (usually `cname.vercel-dns.com`) | DNS only |

Email Routing's MX/SPF records on `@` stay untouched.

**Inbound alerts:** Email → Email Routing → Settings → **Subdomains → Add** `in` (Cloudflare adds MX + SPF for
`in.vaulta.in`).

**Google Search Console:** add the `google-site-verification=…` TXT record on `@` (Search Console → Add property →
Domain → `vaulta.in`) → Verify.

**Checks:**
- `dig +short api.vaulta.in` ends with `onrender.com`; Render shows the certificate issued.
- `dig +short MX in.vaulta.in` lists `route*.mx.cloudflare.net`.
- After §9: `dig +short vaulta.in` prints Vercel's address; Vercel shows both domains verified.

---

## 5. Resend (SPF, DKIM, DMARC)

Done: `vaulta.in` added in Resend (region Tokyo), records added by Resend's Cloudflare connection (DKIM
`resend._domainkey`, the `send` records for SPF/bounces), receiving off. DMARC added by hand:

| Name | Type | Value |
|---|---|---|
| `_dmarc` | TXT | `v=DMARC1; p=none; rua=mailto:privacy@vaulta.in` |

`p=none` only reports. **Tighten after two weeks** of aggregate reports (they arrive at privacy@) showing only Resend
and Google passing: change it to `v=DMARC1; p=quarantine; rua=mailto:privacy@vaulta.in`.

On Render: `RESEND_API_KEY`, `EMAIL_FROM=vaulta.in <noreply@vaulta.in>` (§2.2).

**Checks:**
- Resend shows `vaulta.in` **Verified**; `dig +short TXT _dmarc.vaulta.in` prints the policy.
- After §9: Render → `vaulta-api` → Shell →
  `python -c "from app.services import email; email.send('<your Gmail>', 'vaulta.in test', '<p>Test</p>', 'Test')"` →
  arrives from `noreply@vaulta.in`; Gmail → Show original: SPF, DKIM, DMARC all PASS.

---

## 6. Inbound email worker

```sh
cd ~/Desktop/vaulta/infra/email-worker
npm ci
npx wrangler secret put INTERNAL_SECRET      # same value as on Render
npx wrangler deploy
```
Cloudflare → Email Routing → Routing rules → **Catch-all → Edit → Send to a Worker → `vaulta-inbound-email`** →
Save → enable. Explicit rules (`privacy@`, `security@`) keep going to Gmail. The worker only accepts
`in.vaulta.in` addresses and retries with backoff for up to 2 minutes while the API wakes up.

**Check (after §9):**
1. Settings → Run setup again → forwarding step → **Send test** → "✓ Your forwarding address works" within ~2 minutes.
2. A real forwarded bank alert appears as a transaction.
3. Mail to `nobody@vaulta.in` bounces.
4. With the API asleep (20 minutes idle), a test still arrives.

---

## 7. Telegram

Bot already created with @BotFather. On Render set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`,
`TELEGRAM_WEBHOOK_SECRET`, redeploy, then:
```sh
read -rs TG_TOKEN; read -rs TG_SECRET
curl -s "https://api.telegram.org/bot$TG_TOKEN/setWebhook" \
  --data-urlencode "url=https://api.$DOMAIN/internal/telegram" \
  --data-urlencode "secret_token=$TG_SECRET" \
  --data-urlencode 'allowed_updates=["message","callback_query"]' \
  -d drop_pending_updates=true
```
**Checks:**
- `curl -s "https://api.telegram.org/bot$TG_TOKEN/getWebhookInfo"` shows the URL, `"pending_update_count":0`.
- After §9: Settings → Link Telegram → send the code → bot replies "Linked to vaulta.in".

---

## 8. Seed the demo

After `vaulta-api` is live: Render → `vaulta-api` → **Shell**:
```sh
python -m app.services.demo
```
**Check:** prints `demo user … seeded`. (The hourly job rebuilds it daily.)

---

## 9. Cutover — only on the owner's explicit "go"

1. **Merge PR #2:**
   ```sh
   gh pr checks 2 --repo KanveerMadan/vaulta.in --watch     # all green
   gh pr merge 2 --repo KanveerMadan/vaulta.in --merge
   ```
   Vercel starts building production from `main`.
2. **Render:** `vaulta-api` → Settings → Branch **`main`**, Auto-Deploy **On Commit** → Manual Deploy → latest
   commit.
3. **Vercel domains:** Settings → Domains → add `vaulta.in` (primary) and `www.vaulta.in` → add the `@` and `www`
   records from §4 in Cloudflare → wait for "Valid Configuration".
4. Run the §2, §3a.4, §5, §6, §7 "after §9" checks.
5. `git tag v1.0 && git push origin v1.0`.

---

## 10. Smoke test (private window, phone and laptop)

- [ ] `https://vaulta.in/welcome` loads; no CSP errors in the console; the cold-start screen appears and recovers if the API was asleep.
- [ ] Try the demo: home, transactions, budgets, chat answer; a change shows the read-only message.
- [ ] Google sign-in → new account → onboarding → guided tour → checklist.
- [ ] Import a real statement: preview shows removed fields and balance check; import lands; totals look right.
- [ ] Delete this import → preview count → gone; totals recompute.
- [ ] Chat: "how much did I spend this month?" answers with figures; AI chat off → refused.
- [ ] Email/password sign-up → "Check your inbox" → import refused until verified → works after.
- [ ] Forgot password: same message for a real and a made-up address; reset works.
- [ ] Sign out of all devices signs out a second browser.
- [ ] 5 minutes after sign-in, Export asks to sign in again; the zip downloads; Activity lists it.
- [ ] Reset my data (type RESET) clears data, keeps the login.
- [ ] Forwarding address test (§6) and Telegram `150 auto cash` → ✓ Save → `/undo`.
- [ ] `curl -s https://api.vaulta.in/health/ready` → ready, at head, RLS enforced.
- [ ] `/security`, `/privacy`, `/terms` show the right contacts; `/.well-known/security.txt` answers on both domains.
- [ ] After the next hour: Actions → Hourly run is green (and tolerated the cold start).
- [ ] Delete everything with a throwaway account: data and login gone.

**Clean-up right after go-live:**
- [ ] Remove `ENCRYPTION_KEY` from Render (migration only).
- [ ] Google Cloud → IAM & Admin → Service accounts → `firebase-adminsdk-fbsvc@…` → Keys → delete the old key `6105c18b88…` (and its JSON file, if you still have a copy anywhere).
- [ ] reCAPTCHA admin → v3 site → Domains → remove `vaulta-henna.vercel.app`.
- [ ] `scripts/check-default-domains.sh --live https://vaulta.in` prints CLEAN; `curl -sI https://vaulta-henna.vercel.app/security` → `308` to `https://vaulta.in/security`.
- [ ] Google sign-in popup shows `vaulta.in`.
- [ ] Search Console → Sitemaps → `sitemap.xml` → Submit; URL inspection → `https://vaulta.in/welcome` → Request indexing.
- [ ] Review `/privacy` and `/terms`, remove the draft notice.
- [ ] After ~1 day of `recaptcha:` monitor logs: enforce (§3a.5 step 4).
- [ ] Two weeks after go-live: DMARC `p=none` → `p=quarantine` (§5).
- [ ] Backups: Actions → **Weekly backup** → **Run workflow** → green; download the artifact
      (`gh run download <run-id> -n vaulta-<date>.dump.age`) and check it decrypts:
      `age -d -i ~/vaulta-backup-key.txt vaulta-<date>.dump.age | pg_restore --list | head`; then delete the download.
- [ ] Actions → **Hourly run** → Run workflow once by hand → green (it waits out a cold start).
- [ ] UptimeRobot (optional): HTTP monitor `https://api.vaulta.in/health`, 60-minute interval — outage alert only.

**One week after a stable go-live:**
- [ ] Render: delete the old "Vaulta" service (`srv-d8hh6nt7vvec73acib30`).
- [ ] Neon: delete the old US project `steep-smoke-31221922` and the `pre-v1-…` snapshot branch.

---

## 11. Not part of go-live

Phase 10 (repo cleanup, README and docs, LinkedIn post) starts after v1.0 on the owner's approval.

---

## 12. Rollback

Because the old US database is never migrated, rolling back is fast until the old project is deleted.

| Step | How to undo |
|---|---|
| 1.1–1.8 new Neon project | Nothing touches the old project. Resume the old Render service (§1.2) and the old app works as before. Delete the new project if abandoning. |
| 1.2 old API suspended | Render → old "Vaulta" service → **Resume**. |
| 1.6 app role | `psql "$NEW_OWNER_URL" -c "DROP OWNED BY vaulta_app; DROP ROLE vaulta_app;"` |
| 1.7 migrations | Restore the new project's branch from `pre-v1-…`: `npx neonctl@7.0.4 branches restore $NEW_NEON_BRANCH pre-v1-… --project-id $NEW_NEON_PROJECT`, then rerun §1.7. |
| 2 Render | Suspend or delete `vaulta-api`; disable the Hourly run workflow; resume the old service. |
| 3 Vercel | Deployments → last old production deployment → **Promote to Production**; revert env vars. |
| 3a Bot checks | Unset `RECAPTCHA_ENFORCE` (back to monitor mode) and redeploy. |
| 4 DNS | Delete the added records; remove the domains from Vercel; disable Email Routing for `in.vaulta.in`. |
| 5 Resend | Remove the domain and records; the app works without email. |
| 6 Worker | `npx wrangler delete`; disable the catch-all rule. |
| 7 Telegram | `curl -s "https://api.telegram.org/bot$TG_TOKEN/deleteWebhook"`; remove the three variables. |
| 8 Demo | `psql "$NEW_OWNER_URL" -c "delete from users where firebase_uid='vaulta-demo'"` |
| 9 Merge | `git revert -m 1 <merge commit> && git push`; promote the old Vercel deployment; Render `vaulta-api` back to `release/v1` or suspended; resume the old service. Data written to the new database after go-live stays there (not in the old one). |