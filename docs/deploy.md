# Deploying Vaulta

| Piece | Where it runs | Config |
|---|---|---|
| API (FastAPI) | Render web service `vaulta-api`, free plan, Singapore | `render.yaml` and the settings below |
| Hourly run | GitHub Actions schedule (Render's cron jobs aren't free) | `.github/workflows/hourly-run.yml` |
| Keeping the API awake | UptimeRobot, `GET /health` every 5 minutes | UptimeRobot dashboard |
| Web app (React, PWA) | Vercel, root directory `frontend` | `frontend/vercel.json` |
| Database | Neon Postgres | roles: `docs/security/row-level-security.md` |
| Inbound alert email | Cloudflare Email Routing + Worker `vaulta-inbound-email` | `infra/email-worker/` |
| Sign-in | Firebase Authentication (project `vaulta-a3d7a`) | Firebase console |
| Email out | Resend | Resend dashboard |
| AI | Groq | Groq console |
| Bot | Telegram (@BotFather) | `setWebhook` |

The step-by-step first launch is `docs/go-live.md`.

## Generating secrets

Every random secret below is made the same way, with a fresh value for each variable and each environment:

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

This gives 64 URL-safe characters (288 bits). The API refuses to start in production if any of `SECRET_KEY`,
`INTERNAL_SECRET`, `MASTER_KEY` or `BLIND_INDEX_KEY` is missing, shorter than 32 characters or a placeholder.
`MASTER_KEY` and `BLIND_INDEX_KEY` must also differ from each other.

Keep a copy of `MASTER_KEY` and `BLIND_INDEX_KEY` **outside Render** (a password manager). Without them, the encrypted
data can't be read back, and a database backup can't replace them.

## Render settings (`vaulta-api`)

The service was created in the dashboard, so these are entered there (`render.yaml` holds the same values):

| Setting | Value |
|---|---|
| Instance type | Free (512 MB; it sleeps after 15 idle minutes, which UptimeRobot prevents) |
| Region | Singapore |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers ${WEB_CONCURRENCY:-1} --proxy-headers --forwarded-allow-ips='*' --no-access-log` |
| Health check path | `/health/ready` (database up, migrations at head, row-level security enforced) |
| Python | `PYTHON_VERSION=3.12.7` |
| Auto-deploy | **off** until cutover (go-live stage 11); then on, from `main` |
| Workers | `WEB_CONCURRENCY=1`: a 12-month import peaks near 390 MB in one process (`docs/ml/evaluation.md`, an upper bound), so two could pass 512 MB |

## Every variable

### Render: API web service (`vaulta-api`)

| Variable | Required | What / how to get it |
|---|---|---|
| `ENVIRONMENT` | yes | `production` (set by `render.yaml`) |
| `PYTHON_VERSION`, `WEB_CONCURRENCY` | yes | `3.12.7`, `1` |
| `DATABASE_URL` | yes | Neon connection string for the **`vaulta_app`** role on the **pooled** host, with `?sslmode=require`. Never the owner. |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | yes | Firebase console → Project settings → Service accounts → Generate new private key; paste the JSON on one line |
| `SECRET_KEY` | yes | random (above). Signs demo sessions and unsubscribe links. |
| `INTERNAL_SECRET` | yes | random. Shared with the hourly run (a GitHub secret) and the email worker. |
| `MASTER_KEY` | yes | random. Wraps each user's data key (`docs/security/encryption.md`). |
| `BLIND_INDEX_KEY` | yes | random, different from `MASTER_KEY`. Keys the blind indexes. |
| `MASTER_KEY_PREVIOUS` | only during a rotation | the old `MASTER_KEY` while `scripts/rotate_master_key.py` runs |
| `BACKEND_CORS_ORIGINS` | yes | `https://vaulta.in,https://www.vaulta.in,https://vaulta-henna.vercel.app` (comma-separated https origins of the web app; production refuses `http://`, `localhost` and `*`; `http://localhost:5173` is only the local default) |
| `BACKEND_CORS_ORIGIN_REGEX` | **leave unset in production** | it would let Vercel preview builds (any pushed branch) call the production API. Previews use their own Preview variables and a non-production API, or none |
| `APP_BASE_URL` | yes | the web app's https URL (links in emails) |
| `API_BASE_URL` | yes | the API's https URL (unsubscribe links) |
| `SECURITY_CONTACT_EMAIL` | yes | the address published at the API's `/.well-known/security.txt` |
| `DEMO_SESSIONS_PER_IP` | optional | default 30 per 10 minutes |
| `RECENT_LOGIN_SECONDS` | optional | how recent a sign-in sensitive actions need; default 300, production accepts 60–600 |
| `APP_CHECK_ENFORCE` | after go-live step 3a | `true` refuses requests without a valid App Check token; unset = monitor mode (logs only) |
| `APP_CHECK_DEBUG_TOKEN` | never in production | local runs and browser tests only; production refuses to start with it |
| `GROQ_API_KEY` | for chat and report summaries | console.groq.com → API keys |
| `GROQ_MODEL` | optional | default `openai/gpt-oss-120b` (Groq retired `llama-3.3-70b-versatile`; unset it if it is still set to that) |
| `MERCHANT_MODEL_ENABLED` | optional | default `true`: the merchant model categorises (docs/ml/model-card.md); `false` returns to the rule-based categories |
| `RESEND_API_KEY` | for emails | resend.com → API keys (sending access, one domain) |
| `EMAIL_FROM` | for emails | e.g. `Vaulta <reports@mail.vaulta.example>` on a domain verified in Resend |
| `INBOUND_DOMAIN` | for alert forwarding | your domain; addresses become `<token>@in.<domain>` |
| `TELEGRAM_BOT_TOKEN` | for the bot | from @BotFather |
| `TELEGRAM_BOT_USERNAME` | for the bot | the bot's username, without @ |
| `TELEGRAM_WEBHOOK_SECRET` | for the bot | random, at least 32 characters (allowed: letters, digits, `_`, `-`) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_PLAN_ID` | for subscriptions | Razorpay dashboard |
| `ENCRYPTION_KEY` | no | Phase 4's Fernet key, read only by the encryption migration if old forwarding tokens exist; remove after go-live |

### GitHub Actions: hourly run (`.github/workflows/hourly-run.yml`)

Repository → Settings → Secrets and variables → Actions:

| Name | Kind | What |
|---|---|---|
| `API_URL` | variable | the API's public base URL, e.g. `https://vaulta-f6t8.onrender.com` (later `https://api.vaulta.in`) |
| `INTERNAL_SECRET` | secret | the same value as the API's |

It runs at minute 7 of every hour and can be started by hand (Actions → Hourly run → Run workflow). It waits for a
sleeping free instance to wake, then calls `POST /internal/run-reports`, which is safe to repeat. **GitHub may delay a
scheduled run** (often 5–30 minutes when busy) or skip one; the next run catches up, because each job does whatever
is due and not yet done. GitHub also disables schedules in a public repository after 60 days without commits: if
that happens, re-enable the workflow in the Actions tab.

### Vercel: web app (Production and Preview)

All `VITE_*` values are compiled into the public JavaScript, so none of them is a secret. `backend/.env.example` and
`frontend/.env.example` list every name for local development.

- **Production** (builds of `main`): every variable below, with `VITE_API_BASE_URL` set to the production API.
- **Preview** (every other pushed branch): only `VITE_SECURITY_CONTACT`, `VITE_PRIVACY_CONTACT` and the Firebase web
  config, so previews build. **Leave `VITE_API_BASE_URL` unset for Preview**: previews then have no API to call, and
  with `BACKEND_CORS_ORIGIN_REGEX` unset on Render the production API refuses their origin anyway. Previews sit
  behind Vercel's login (Deployment Protection), which should stay on.
- SPA routing: `frontend/vercel.json` serves `index.html` for every path that isn't a file; `src/vercelConfig.test.js`
  checks the file with Vercel's own parser.

| Variable | What |
|---|---|
| `VITE_API_BASE_URL` | the API's https URL. **Its origin must be in `connect-src` in `frontend/vercel.json`**: the build fails otherwise. |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID` | Firebase console → Project settings → Your apps → Web app config. If `VITE_FIREBASE_AUTH_DOMAIN` changes, update `frame-src` in `vercel.json`. |
| `VITE_SECURITY_CONTACT` | security contact email; becomes `/.well-known/security.txt` and is shown on `/security`. Required: the build fails without it. |
| `VITE_PRIVACY_CONTACT` | privacy and grievance contact email shown on `/privacy`. Required. |
| `VITE_RECAPTCHA_ENTERPRISE_SITE_KEY` | the reCAPTCHA Enterprise key id for App Check (go-live step 3a). Without it the app sends no App Check token, so leave `APP_CHECK_ENFORCE` off. |

### Cloudflare: email worker (`infra/email-worker`)

| Name | Kind | What |
|---|---|---|
| `API_URL` | var in `wrangler.toml` | the API's https URL |
| `INTERNAL_SECRET` | `wrangler secret put INTERNAL_SECRET` | the same value as the API's |

### Your machine: migrations and key rotation (never on Render or Vercel)

| Variable | What |
|---|---|
| `MIGRATION_DATABASE_URL` | Neon owner role (`neondb_owner`) on the **direct** (non-pooler) host, `?sslmode=require` |
| `DATABASE_URL` | the same value (the config requires one) |
| `MASTER_KEY`, `BLIND_INDEX_KEY` | the same values as the API's (the encryption migration uses them) |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | any value, e.g. `{}` (migrations don't sign anyone in) |
| `ENCRYPTION_KEY` | only if the database holds Phase 4 forwarding tokens |

After a deploy that ships a new merchant model or taxonomy, re-check existing users' categories from the same machine
(the API role is enough, as `DATABASE_URL`). It is a dry run unless `--apply`, prints counts only, never touches rows a
user corrected, and each user's run can be undone in Settings or with `--undo-latest`:

```
cd backend && python scripts/recategorise.py            # dry run: how many would change
cd backend && python scripts/recategorise.py --apply
```

## Security headers and caching

- **API** (`backend/app/core/logs.py`): CSP `default-src 'none'`, `frame-ancestors 'none'`, nosniff, `X-Frame-Options`,
  Referrer-Policy, Permissions-Policy, COOP/CORP, and HSTS in production, on every response.
- **Web app** (`frontend/vercel.json`): a strict CSP with no inline scripts, `connect-src` limited to the app, the API
  and Firebase Auth, plus HSTS (preload-ready), nosniff, `frame-ancestors 'none'`, Referrer-Policy and
  Permissions-Policy.
- **Caching:**
  - hashed `/assets/*`: one year, immutable;
  - `index.html`, the service worker, `registerSW.js`, the manifest and HTML navigations: `no-cache`.
- **Routing:** unknown paths without a file extension fall back to `index.html` (SPA). A missing asset is a real 404.

## Health

| Path | Meaning |
|---|---|
| `GET /health` | The process is up. |
| `GET /health/ready` | The database answers, `alembic_version` equals the code's `MIGRATION_HEAD`, and the API's role can't bypass RLS. Returns 503 with the failing check otherwise. Render's health check uses it, so a deploy whose migrations haven't run never takes traffic. |
