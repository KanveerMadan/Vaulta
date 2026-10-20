# Runbook: when something is wrong

One page per symptom: what to check first, then what to do. Setup lives in `docs/deploy.md`; the first launch in
`docs/go-live.md`. Never paste a secret into a terminal that echoes it, a chat or a ticket (read with `read -rs`).

## How you find out

| Signal | Set up | Tells you |
|---|---|---|
| Sentry (two projects: API and web app) | Sentry → Alerts → **Create alert → Issues**: "a new issue is created" and "an issue changes state from resolved to unresolved" → email. Do it for both projects | A new error, or an old one back. Reports are scrubbed (`/security`, "errors") |
| GitHub | Settings → Notifications → Actions → **Only notify for failed workflows** | Hourly run or weekly backup failed |
| Render | Account → Notifications → **Deploy failed** and **Service unhealthy** → email | A deploy didn't go live, or `/health/ready` failing |
| UptimeRobot (optional) | HTTP monitor `https://api.vaulta.in/health`, every **60 minutes**, timeout at its maximum | The API won't start at all. At 60 minutes it doesn't keep the API awake |
| Users | `privacy@vaulta.in`, `security@vaulta.in` (both to Gmail) | Everything else |

## The app says "vaulta.in is taking longer than usual"

The free API sleeps after 15 idle minutes and takes up to a minute to start; the app waits two.
1. `curl -s -m 90 https://api.vaulta.in/health` (allow for the start). `{"status":"ok"…}` → it was just slow; done.
2. `curl -s https://api.vaulta.in/health/ready`:
   - `"database":"unreachable"` → Neon (next section).
   - `"migrations":"at <x>, expected <y>"` → the code is newer than the database. Run the pending migration
     (`docs/deploy.md`, "Your machine"), after a snapshot branch.
   - `"rls":"bypassed"` → the API is connecting as the wrong role. `DATABASE_URL` must be `vaulta_app`.
3. Render → `vaulta-api` → **Events** and **Logs**. A deploy that just went bad: Events → the previous deploy →
   **Rollback**.
4. Render's own status: status.render.com.

## Database (Neon)

- Neon console → project `vaulta` (Singapore) → **Monitoring** and the usage page: the free plan's storage and compute
  allowances. Over them, Neon suspends compute until the next cycle.
- Restore something deleted by mistake: Neon → Branches → **Restore** to a point in time (the free plan keeps a short
  history), or the weekly encrypted backup (`docs/deploy.md`, "Backups"). Always restore into a **new branch** first,
  check it, then switch.
- Before any migration: a snapshot branch (`npx neonctl@7.0.4 branches create --project-id <id> --name pre-<what>-<date>`).

## Errors in Sentry

1. Open the issue: the error type, the code location and the route are there; personal data isn't (scrubbed).
2. Reproduce locally against a copy (`docs/go-live.md` has the Neon branch commands), fix on a branch, push, CI green,
   merge, Render deploys `main`.
3. If it's breaking sign-ins or imports for everyone: Render → Rollback to the last good deploy first, fix after.

## Hourly run failed (GitHub email)

Actions → **Hourly run** → the failed run's log.
- "didn't wake within 2 minutes" → the API is down (first section). The next hour catches up on its own.
- HTTP 401 → `INTERNAL_SECRET` in GitHub doesn't match Render's. Set both to the same new value.
- Re-running is safe: nothing is built or sent twice. Actions → Hourly run → **Run workflow**.

## Weekly backup failed

Actions → **Weekly backup** → log. "Set the secret…" → `BACKUP_DATABASE_URL` or `BACKUP_AGE_RECIPIENT` missing.
A connection error → the `vaulta_backup` password or host changed (Neon). Run it again by hand once fixed.

## Emails don't arrive (reports, alerts, deletion confirmations)

1. Resend → **Logs**: was it sent, bounced, or never asked for?
2. Never asked → Render: `RESEND_API_KEY` and `EMAIL_FROM=vaulta.in <noreply@vaulta.in>` set; the user's settings allow it.
3. Bounced or in spam → Resend → Domains → `vaulta.in` still **Verified**; `dig +short TXT _dmarc.vaulta.in`.

## Forwarded bank alerts don't arrive

1. The user's Connect page: "Send test". Nothing within two minutes →
2. Cloudflare → Email → Email Routing → **Activity log**: did the message reach `in.vaulta.in`, and the worker?
3. `cd ~/Desktop/vaulta/infra/email-worker && npx wrangler tail`, then send a test: the worker's log, live.
   "No such address" → it wasn't addressed to `in.vaulta.in`. 401 from the API → `INTERNAL_SECRET` mismatch
   (`npx wrangler secret put INTERNAL_SECRET`).
4. Render: `INBOUND_DOMAIN=vaulta.in` (not `in.vaulta.in`).

## Telegram bot doesn't answer

`read -rs TG_TOKEN; curl -s "https://api.telegram.org/bot$TG_TOKEN/getWebhookInfo"`: `last_error_message` says why.
A 401/403 there → `TELEGRAM_WEBHOOK_SECRET` on Render differs from the webhook's: register it again
(`docs/go-live.md` §7). Telegram retries pending updates for a day, so messages sent during an outage still arrive.

## Chat or report summaries fail

Groq's free tier allows about 200k tokens a day per model. Render logs show Groq 429s when it's used up. Short term:
set `GROQ_MODEL=openai/gpt-oss-20b` (a separate allowance) and redeploy; it resets daily. A 401 → the key was revoked:
create a new one in the Groq console, set `GROQ_API_KEY`.

## Bots or abuse

- Render logs, search `recaptcha:` — `missing`, `invalid` and `low` outcomes by action.
- In monitor mode and seeing abuse → `RECAPTCHA_ENFORCE=true`. Too many real people slowed → lower
  `RECAPTCHA_MIN_SCORE` (default 0.5). A low score is never refused outright; it's slowed (`app/core/recaptcha.py`).
- Rate limits answer 429 on their own (`app/core/ratelimit.py`).

## A secret leaked

Rotate first, investigate after. Where each one lives (`docs/deploy.md`, "Every variable"):
- `MASTER_KEY`, `BLIND_INDEX_KEY` → `docs/security/encryption.md` (rotation scripts; not a simple swap).
- `INTERNAL_SECRET` → Render, GitHub secret, email worker (`npx wrangler secret put INTERNAL_SECRET`), all at once.
- `SECRET_KEY` → Render only (demo sessions and unsubscribe links signed with the old one stop working; acceptable).
- Third-party keys (Groq, Resend, Telegram, reCAPTCHA secret, Sentry DSN) → revoke in that service, new one on Render.
- `vaulta_app` / `vaulta_backup` passwords → `ALTER ROLE … PASSWORD …` as the owner, then Render `DATABASE_URL` /
  GitHub `BACKUP_DATABASE_URL`.
- Firebase service account → Google Cloud → IAM → Service accounts → Keys: create a new key, set it on Render, delete
  the old one.
Then: `scripts/secret-check.sh` on every branch, and if it was in git history, treat the old value as public forever.

## Someone asks for their data, or to be deleted

Point them to Settings → **Your data** (export) and **Delete everything**; both work without us. If they can't sign
in, verify they own the address (reply from it), then act on their behalf. Grievances go to `privacy@vaulta.in`
(the contact on `/privacy`).
