# Go-live runbook

These steps take Vaulta from the old app on `main` to the rebuild (phases 1–7, plus 6). Run them in this order. Each
step ends with a check: don't go on until it passes. Rollback for every step is at the end.

**What to expect:**
- **Downtime.** The old API on `main` can't read the migrated database. Expect about 15–30 minutes from step 1.4 until
  the new API is live (step 9). Pick a quiet hour.
- **Your machine.** You need `psql`, Python 3.12 with `backend/requirements.txt` installed (the repo's
  `backend/venv` is fine), Node 22 and `gh`. `neonctl` is used with `npx neonctl@7.0.4`.
- **No secrets in commands.** Values are read into shell variables with `read -rs`, so they never appear in your shell
  history or in a file. `docs/deploy.md` says what each variable is and how to generate it.

## 0. Before you start

```sh
cd ~/vaulta && git checkout rebuild/phase6 && git pull
export DOMAIN=vaulta.example                     # your domain: the app at https://$DOMAIN, the API at https://api.$DOMAIN
npx neonctl@7.0.4 auth                        # opens the browser once
npx neonctl@7.0.4 projects list               # note the project id
export NEON_PROJECT=<id from the list>
npx neonctl@7.0.4 branches list --project-id $NEON_PROJECT   # note the production branch's name (usually "main" or "production")
export NEON_PROD_BRANCH=<that name>
```

**Check:** CI on the pull request is green (`gh pr checks`), and the staging rehearsal passes on a fresh copy of
production:
```sh
NEON_PROJECT=$NEON_PROJECT NEON_PROD_BRANCH=$NEON_PROD_BRANCH scripts/staging-rehearsal.sh
```
It must end with `ALL CHECKS PASSED`, `PASS readiness` and the smoke tests passing. Then delete the branch with
`npx neonctl@7.0.4 branches delete staging --project-id $NEON_PROJECT`. It only ever touches the `staging` branch.

Generate the new secrets now, store them in your password manager, and keep them for steps 1–7:
- `SECRET_KEY`, `INTERNAL_SECRET`, `MASTER_KEY`, `BLIND_INDEX_KEY`, `TELEGRAM_WEBHOOK_SECRET`: each one from
  `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`;
- the `vaulta_app` database password: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 1. Neon: snapshot, app role, migrations, encryption, row-level security

**1.1 Snapshot branch.** A copy of production as it is now, to roll back to:
```sh
npx neonctl@7.0.4 branches create --project-id $NEON_PROJECT --parent $NEON_PROD_BRANCH --name pre-phase6-$(date +%Y%m%d-%H%M)
```
**Check:** `npx neonctl@7.0.4 branches list --project-id $NEON_PROJECT` lists `pre-phase6-…`.

**1.2 Connection strings.** Get both into your shell without echoing them:
```sh
read -rs OWNER_URL     # owner (neondb_owner) on the DIRECT host: Neon console → Connect → uncheck "Connection pooling"; add ?sslmode=require
read -rs APP_PASSWORD  # the vaulta_app password you generated
export OWNER_URL APP_PASSWORD
```
**Check:** `psql "$OWNER_URL" -Atc "select current_user"` prints `neondb_owner`.

**1.3 The app role.** Create it with SQL, never in the Neon console: console roles can bypass RLS.
```sh
psql "$OWNER_URL" -v ON_ERROR_STOP=1 -v pw="$APP_PASSWORD" <<'SQL'
CREATE ROLE vaulta_app WITH LOGIN PASSWORD :'pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE neondb TO vaulta_app;
SQL
```
**Check:** `psql "$OWNER_URL" -Atc "select rolsuper, rolbypassrls from pg_roles where rolname='vaulta_app'"` prints `f|f`.

**1.4 Stop the old API.** In the Render dashboard, open the current API service and choose **Suspend**. From here until
step 9, the API is down.

**Check:** the old API's URL no longer answers `/health`.

**1.5 Record row counts, then migrate.** This runs every migration, including the encryption (`f6a2c8e0b1d3`) and RLS
(`a7c3e9f1d2b4`) ones.
```sh
psql "$OWNER_URL" -Atc "select 'users', count(*) from users union all select 'transactions', count(*) from transactions" | tee /tmp/vaulta-counts-before.txt
cd ~/vaulta
read -rs MASTER_KEY; read -rs BLIND_INDEX_KEY; export MASTER_KEY BLIND_INDEX_KEY   # the values you'll put on Render
export MIGRATION_DATABASE_URL="$OWNER_URL" DATABASE_URL="$OWNER_URL" FIREBASE_SERVICE_ACCOUNT_JSON='{}'
backend/venv/bin/python -m alembic current
backend/venv/bin/python -m alembic upgrade head
backend/venv/bin/python -m alembic current
```
**Checks:**
- `alembic current` prints `b9e5f1a3c4d6 (head)`.
- `psql "$OWNER_URL" -Atc "select 'users', count(*) from users union all select 'transactions', count(*) from transactions"`
  matches `/tmp/vaulta-counts-before.txt`.
- `psql "$OWNER_URL" -Atc "select count(*) from transactions where kind is null"` prints `0`.
- `psql "$OWNER_URL" -Atc "select count(*) from transactions where merchant_raw not like 'e1:%' or (merchant_clean is not null and merchant_clean not like 's1:%')"` prints `0` (nothing left in plaintext).
- `psql "$OWNER_URL" -Atc "select count(*) from users where data_key is null"` prints `0`.
- `psql "$OWNER_URL" -Atc "select relname from pg_class where relname in ('transactions','users','activity_log') and relrowsecurity"` lists all three.

If the migration says forwarding tokens need `ENCRYPTION_KEY`, run `read -rs ENCRYPTION_KEY; export ENCRYPTION_KEY`
with the old Fernet key from Render, then run `alembic upgrade head` again. It is one transaction, so a failed run
leaves nothing behind.

**1.6 The API's connection string.** Use the pooled host, as `vaulta_app`:
`postgresql://vaulta_app:<password>@<pooled host>/neondb?sslmode=require`.

**Check:** `psql "postgresql://vaulta_app:$APP_PASSWORD@<pooled host>/neondb?sslmode=require" -Atc "select count(*) from transactions"` prints `0` (no user bound means no rows: RLS works).

## 2. Render

1. Render dashboard → **New → Blueprint** → this repository, branch `main`. It creates `vaulta-api` and
   `vaulta-report-run` in Singapore from `render.yaml`. The old service was created in another region, and a region
   can't be changed.
2. When asked for values, fill in every `sync: false` variable from `docs/deploy.md`:
   - `DATABASE_URL`: from step 1.6.
   - `BACKEND_CORS_ORIGINS`: `https://$DOMAIN`.
   - `APP_BASE_URL`: `https://$DOMAIN`.
   - `API_BASE_URL`: `https://api.$DOMAIN`.
   - Leave `MASTER_KEY_PREVIOUS` empty.
3. On the cron, set:
   - `API_URL`: `https://api.$DOMAIN`;
   - `INTERNAL_SECRET`: the same value as the API's.
4. Under `vaulta-api` → **Settings → Custom domains**, add `api.$DOMAIN`. Render shows the target hostname for step 4.

Blueprints deploy the branch they're connected to. Until the PR is merged (step 9), `main` holds the old code: let the
first deploy fail its health check, or click **Suspend** on `vaulta-api` until step 9.

**Check (after step 9):**
```sh
curl -s https://api.$DOMAIN/health/ready
```
It must print `{"status":"ready","database":"ok","migrations":"at head","rls":"enforced"}`.

## 3. Vercel

1. If the API's address changes (it does: `https://api.$DOMAIN`), edit `frontend/vercel.json`: in `connect-src`,
   replace `https://vaulta-f6t8.onrender.com` with `https://api.$DOMAIN`. Commit it on `rebuild/phase6` and push. A
   build whose `VITE_API_BASE_URL` isn't in `connect-src` fails on purpose.
2. Vercel → Project → Settings → Environment Variables, for Production and Preview:
   - `VITE_API_BASE_URL=https://api.$DOMAIN`;
   - the six `VITE_FIREBASE_*` values (unchanged);
   - `VITE_SECURITY_CONTACT`;
   - `VITE_PRIVACY_CONTACT`.
3. Confirm that Settings → General → Root Directory is `frontend`.
4. Settings → Domains: add `$DOMAIN` (and `www.$DOMAIN`, redirecting to it).

**Check (after step 9):**
```sh
curl -sI https://$DOMAIN/ | grep -iE "content-security-policy|strict-transport|x-frame"
```
It must show the CSP, HSTS and `DENY`, and `curl -s https://$DOMAIN/.well-known/security.txt` must start with `Contact:`.

## 4. Domain and DNS (Cloudflare)

In Cloudflare → `$DOMAIN` → DNS:

| Name | Type | Target | Proxy |
|---|---|---|---|
| `@` | A | `76.76.21.21` (Vercel) | DNS only |
| `www` | CNAME | `cname.vercel-dns.com` | DNS only |
| `api` | CNAME | the hostname Render showed in step 2 (`vaulta-api.onrender.com`) | DNS only |

Leave all three on **DNS only**, because Vercel and Render issue their own certificates.

Then **Email → Email Routing → Settings → add subdomain `in.$DOMAIN`**. Cloudflare adds the MX and SPF records for it.

**Checks:**
- `dig +short $DOMAIN` prints `76.76.21.21`.
- `dig +short api.$DOMAIN` ends with the Render hostname.
- `dig +short MX in.$DOMAIN` prints Cloudflare's `route*.mx.cloudflare.net` hosts.
- Vercel and Render show the domains as verified, with certificates issued.

## 5. Resend: SPF, DKIM, DMARC

1. Resend → Domains → **Add domain** `mail.$DOMAIN`, region closest to India.
2. Add the records Resend shows to Cloudflare DNS, all DNS only:
   - the `MX` and `TXT` (SPF) records on `send.mail.$DOMAIN`;
   - the `TXT` DKIM record `resend._domainkey.mail.$DOMAIN`.
3. Add DMARC:

   | Name | Type | Value |
   |---|---|---|
   | `_dmarc` | TXT | `v=DMARC1; p=quarantine; adkim=s; aspf=s; rua=mailto:<your address>` |

4. On Render, set `EMAIL_FROM=Vaulta <reports@mail.$DOMAIN>`.

**Checks:**
- Resend shows the domain **Verified**.
- `dig +short TXT _dmarc.$DOMAIN` prints the policy.
- After step 9: in Render → `vaulta-api` → Shell, run
  `python -c "from app.services import email; email.send('<your address>', 'Vaulta test', '<p>Test</p>', 'Test')"`.
  The email arrives, and Gmail's "Show original" shows `SPF: PASS`, `DKIM: PASS` and `DMARC: PASS`.

## 6. Cloudflare email worker and routing

```sh
cd ~/vaulta/infra/email-worker
sed -i '' "s#^API_URL = .*#API_URL = \"https://api.$DOMAIN\"#" wrangler.toml
npm ci
npx wrangler login
npx wrangler secret put INTERNAL_SECRET        # paste the API's INTERNAL_SECRET
npx wrangler deploy
```
Then go to Cloudflare → Email Routing → `in.$DOMAIN` → **Routing rules → Catch-all → Send to Worker
`vaulta-inbound-email`**, and enable it. Commit the `wrangler.toml` change.

**Check (after step 9):**
1. Sign in → Settings → **Run setup again** → the alert forwarding step → **Send test**.
2. Send any email to the address shown. Within a minute it says "✓ Your forwarding address works": the email went
   through Cloudflare and the worker and reached the API.
3. A real bank alert forwarded from Gmail appears as a transaction.

## 7. Telegram

1. In Telegram, @BotFather → `/newbot` (or `/token` for the existing bot). Set `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_BOT_USERNAME` on Render, plus `TELEGRAM_WEBHOOK_SECRET` from step 0.
2. Register the webhook. The values are read without echoing:
   ```sh
   read -rs TG_TOKEN; read -rs TG_SECRET
   curl -s "https://api.telegram.org/bot$TG_TOKEN/setWebhook" \
     --data-urlencode "url=https://api.$DOMAIN/internal/telegram" \
     --data-urlencode "secret_token=$TG_SECRET" \
     --data-urlencode 'allowed_updates=["message","callback_query"]' \
     -d drop_pending_updates=true
   ```

**Checks:**
- `curl -s "https://api.telegram.org/bot$TG_TOKEN/getWebhookInfo"` shows the URL and `"pending_update_count":0`.
- After step 9: Settings → Link Telegram → send the code → the bot replies "Linked to Vaulta".

## 8. Seed the demo on production

The demo is built on the first visit to "Try the demo", and the hourly run rebuilds it daily. To build it ahead of
time, after step 9 open Render → `vaulta-api` → **Shell** and run:
```sh
python -m app.services.demo
```
**Check:** it prints `demo user … seeded`, and `https://$DOMAIN/welcome` → "Try the demo" shows the home screen with
four months of data.

## 9. Merge

The open PR #1 points at `rebuild/phase5`. Phase 6 (which contains phases 1–7) goes in from `rebuild/phase6`:
```sh
gh pr create --repo KanveerMadan/Vaulta --base main --head rebuild/phase6 --title "Vaulta rebuild: phases 1–7 and 6" \
  --body "Supersedes #1. See #1 for the full description."
gh pr checks rebuild/phase6 --repo KanveerMadan/Vaulta --watch   # every CI job green
gh pr merge rebuild/phase6 --repo KanveerMadan/Vaulta --merge
gh pr close 1 --repo KanveerMadan/Vaulta --comment "Merged via rebuild/phase6"
```
Merging deploys:
- Vercel builds production from `main`;
- the Render Blueprint deploys `vaulta-api` (resume it if you suspended it).

**Check:** steps 2, 3, 6 and 7's "after step 9" checks all pass.

## 10. Smoke test after deploying

Do this in a private window, on your phone and on a laptop.

- [ ] `https://$DOMAIN/welcome` loads. The browser console shows no CSP errors.
- [ ] "Try the demo": home, transactions, budgets and chat answer. A change shows the read-only message.
- [ ] Sign in with Google: a new account goes through onboarding.
- [ ] Import `fixtures/statements/hdfc.csv`: the preview shows what was removed; the import lands; home totals look
  right.
- [ ] Chat: "how much did I spend this month?" gets an answer with figures. Settings → turn AI chat off → chat
  refuses.
- [ ] Settings → Activity lists your sign-in.
- [ ] Settings → Export my data downloads a zip with `data.json`; Activity lists the export.
- [ ] Connect: the forwarding address works (step 6 check).
- [ ] Telegram: link, send `150 auto cash`, tap ✓ Save; `/undo` removes it.
- [ ] `curl -s https://api.$DOMAIN/health/ready` reports ready, migrations at head, RLS enforced.
- [ ] `/security` and `/privacy` show the right contact addresses; `/.well-known/security.txt` on both domains
  answers.
- [ ] After the next hour: the cron's log in Render shows `200` and a JSON summary.
- [ ] Delete everything with a throwaway account: it ends on the welcome page and can't sign back in to its data.
- [ ] Remove `ENCRYPTION_KEY` from Render (it was only for the migration).
- [ ] Update `/privacy` after your review, and remove its draft notice.

## 11. Rollback

| Step | How to undo |
|---|---|
| 1.1 snapshot | Nothing to undo. Delete the branch after a week of stable running: `npx neonctl@7.0.4 branches delete pre-phase6-… --project-id $NEON_PROJECT`. |
| 1.3 app role | `psql "$OWNER_URL" -c "DROP OWNED BY vaulta_app; DROP ROLE vaulta_app;"` |
| 1.4 old API suspended | Render → old service → **Resume**. Only valid while the database is not yet migrated, or after restoring it (next row). |
| 1.5 migrations | Fastest and complete: Neon → restore `$NEON_PROD_BRANCH` from `pre-phase6-…` (`npx neonctl@7.0.4 branches restore $NEON_PROD_BRANCH pre-phase6-… --project-id $NEON_PROJECT`), then resume the old API. Data written after the migration is lost. To keep the data: `alembic downgrade a5c1e7f9b0d3` (decrypts, drops RLS) with the same keys in the environment. |
| 2 Render | Suspend or delete `vaulta-api` and `vaulta-report-run`. Resume the old service only after restoring the database. |
| 3 Vercel | Vercel → Deployments → the last old production deployment → **Promote to Production**. Revert the env vars. |
| 4 DNS | Delete the records added. Point `$DOMAIN` back where it was, and disable Email Routing for `in.$DOMAIN`. |
| 5 Resend | Remove the domain and its records. Emails then stop (the app keeps working: email is optional). |
| 6 Worker | `npx wrangler delete` and remove the routing rule. Alert forwarding stops; nothing else is affected. |
| 7 Telegram | `curl -s "https://api.telegram.org/bot$TG_TOKEN/deleteWebhook"` and remove the three variables. |
| 8 Demo | Nothing to undo. Delete it with `psql "$OWNER_URL" -c "delete from users where firebase_uid='vaulta-demo'"`. |
| 9 Merge | `git revert -m 1 <merge commit> && git push` (Vercel and Render redeploy the old code). The database must then be restored as in 1.5, because the old code can't read it. |
