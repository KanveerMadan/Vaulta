# Phase 6 report: security hardening and deployment

Branch `rebuild/phase6` (stacked on `rebuild/phase7`). Pushed. PR #1 description updated, still marked DO NOT MERGE.

## What changed, step by step

1. **Threat model.** `docs/security/threat-model.md` covers:
   - assets, actors and every entry point (including `/internal/*`, inbound email, the Telegram webhook and the demo);
   - a mitigation for each threat, naming the code or test that enforces it;
   - the residual risks.
2. **Field-level encryption** (`docs/security/encryption.md`):
   - `ENCRYPTION_KEY` used to protect only the forwarding-address token. It is now retired; the migration reads it only
     if old tokens exist.
   - Each user has a random AES-256-GCM data key, wrapped by `MASTER_KEY` with the user id as associated data.
   - Encrypted: merchant text and narrations, notes, people, goal names, chat, reports, alerts, Telegram entries and
     source rows.
   - HMAC blind indexes (`BLIND_INDEX_KEY`) are the nonce of "searchable" columns, so grouping, dedup, rules and
     person matching still work in SQL. Text search over encrypted columns moved into the app.
   - Migration `f6a2c8e0b1d3` is batched and idempotent, runs as one transaction and is fully reversible.
   - `scripts/rotate_master_key.py` re-wraps data keys only.
   - Tests: a dump of every table has no plaintext; migrate/reverse/re-run on real rows; rotation; key binding.
3. **Row-level security** (`docs/security/row-level-security.md`):
   - Migration `a7c3e9f1d2b4` adds a policy on every user-owned table, keyed on `app.user_id`. `bind_user` sets it
     per transaction (re-applied after every commit).
   - Users are found before binding through `SECURITY DEFINER` functions that return ids only.
   - The API connects as `vaulta_app`, and production refuses to serve if its role could bypass RLS.
   - Tests: unfiltered queries, unbound sessions, cross-user writes, role checks, delete everything.
4. **App security:**
   - one request middleware: request ids, security headers on every response, a 1 MB body limit, generic 500s;
   - JSON logs with a keyed user hash and no personal or financial data (tested over a full account's activity);
   - Firebase revocation checks on delete, export, Telegram link/unlink, address regeneration and settings;
   - Postgres-backed rate limits replacing the per-process ones (demo, demo chat, Telegram per chat, imports,
     sensitive routes, unsubscribe, bad tokens);
   - Settings → Activity, and Export my data (a zip of JSON and CSV, decrypted, built per request, CSV-injection-safe);
   - CORS from env with an optional preview regex;
   - `vercel.json` with a strict CSP (no inline scripts or styles), HSTS, caching and SPA routing. `vite preview`
     serves the same headers, so every browser test runs under the production CSP;
   - TOTP MFA not enabled: `docs/security/mfa.md` explains why.
5. **CI** (`.github/workflows/ci.yml`, actions pinned by SHA, no production secrets):
   - jobs: backend (with migrations up/down/up), frontend lint/unit/build, email worker, Playwright with the emulator
     and fake LLM;
   - security: secret check over the full history, pip-audit, an npm audit gate, Bandit, Semgrep, ZAP baseline on the
     app and API scan on the API;
   - Dependabot for pip, npm and Actions, with a 14-day cooldown;
   - Linux visual baselines rendered in Playwright's Linux image.
6. **/security, /privacy, security.txt:**
   - `/security` has ten claims, each linked to how it works and how it's checked. It names Groq, and says that report
     summaries go to Groq even with chat off.
   - The landing page lists seven claims, each linking to its place on `/security`.
   - `/privacy` is DPDP-aligned and **marked as a draft for your review**.
   - `/.well-known/security.txt` is served by the app (built from `VITE_SECURITY_CONTACT`; the build fails without it)
     and by the API.
7. **Deploy config:**
   - `render.yaml`: the API in Singapore (Starter, 2 workers, proxy headers, readiness health check, variables by name
     only) and the cron.
   - `/health/ready` checks the database, migrations at head and RLS enforced.
   - Production startup checks: https non-local URLs and origins, the contact address, the Telegram secret, the
     rotation key.
   - `docs/deploy.md` lists every variable.
8. **Staging:** `scripts/staging-rehearsal.sh` does the whole rehearsal on a Neon branch `staging`. **It was not run
   against Neon**, because there are no neonctl credentials on this machine.
   - It was run end to end with `--local`, on a database at production's revision with old-shape plaintext rows: all
     checks pass, readiness is ready with RLS enforced, and the browser smoke tests pass 13/13.
   - That rehearsal found a demo race (fixed below).
9. **Go-live runbook:** `docs/go-live.md` has ordered copy-paste steps, a check after each, and a rollback for every
   step.

## Results

| Check | Result |
|---|---|
| Backend tests (local; also with UTC database sessions like Neon) | 342 passed |
| Frontend unit / lint / build | 215 passed / 0 problems / OK |
| Email worker | 2 passed |
| Playwright (desktop, 360 px, reduced motion; production CSP) | 112 passed, 2 skipped |
| pip-audit | no known vulnerabilities |
| npm audit gate | 0 unaccepted; 1 accepted (braces GHSA-vfj7-8cjw-p6xm: no fix exists, build tooling only) |
| Bandit / Semgrep / actionlint | clean (each suppression has a reason inline) |
| OWASP ZAP | app baseline 0 fail, 66 pass; API scan 0 fail, 116 pass (accepted warnings listed in `.zap/rules.tsv`) |
| Secret check (all `rebuild/phase*` history) | clean |
| GitHub Actions on `rebuild/phase6` | see the PR description (updated with the final run) |

## Security findings and what was done

- **Dependency advisories** in starlette, pydantic-settings, cryptography, setuptools (through razorpay 1.x), axios,
  react-router, firebase, vite, postcss, firebase-tools, wrangler and transitive npm packages: all upgraded to fixed
  releases at least two weeks old (razorpay 2.0.1 no longer needs the setuptools pin). One advisory is accepted
  because no fix exists (braces).
- **Bandit:** `assert` used as a guard replaced by exceptions. SQL built from constant identifiers is justified inline.
- **Semgrep:** 23 findings, all reviewed. They are migration DDL with constant names, the test launcher, and regexes
  built from escaped or letter-only input. Each is justified inline.
- **ZAP:**
  - The CSP's `style-src 'unsafe-inline'` was removed.
  - Accepted, with reasons in `.zap/rules.tsv`: no COEP (it would break the Google sign-in popup), informational
    comments in third-party code, timestamps in the demo token, 503 while payments aren't configured, and plain http
    in the CI scan only.
- **Found while building:**
  - The forwarding-address hash was an unkeyed SHA-256; it is now an HMAC.
  - The unsubscribe test's tampering was a no-op 1 time in 16.
  - Alert-time tests depended on the database's time zone. Stored times were right.
  - A visitor arriving while the demo was still being built got a half-built demo. Fixed and tested.
  - The `/security` anchor links didn't scroll on phones after the lazy load. Fixed.

## Not verified

- The staging rehearsal against Neon (needs your `neonctl auth`).
- Real Google sign-in under the new CSP.
- Razorpay checkout under the CSP: its telemetry beacons from the page are blocked by design.
- Resend, Groq, Telegram and Cloudflare in production.
- Real bank alert formats.
- Real phones and non-Chromium browsers.
- TOTP MFA.

## Your manual steps, in order

1. `npx neonctl@7.0.4 auth`, then
   `NEON_PROJECT=… NEON_PROD_BRANCH=… scripts/staging-rehearsal.sh`, then delete the `staging` branch.
2. Review `/privacy` (and the contact addresses it shows), then remove its draft notice.
3. Follow `docs/go-live.md` steps 0–11:
   - the Neon snapshot, the `vaulta_app` role and the production migrations;
   - Render, Vercel (including the `connect-src` edit for `api.<domain>`), DNS, Resend SPF/DKIM/DMARC, the email
     worker and the Telegram webhook;
   - seeding the demo, the merge, the smoke test.
4. Turn on branch protection for `main` requiring the CI checks. Only then is "every change is tested before it ships"
   enforced: `/security` currently says only "tested and security-scanned".
5. After go-live: remove `ENCRYPTION_KEY` from Render, and keep `MASTER_KEY`/`BLIND_INDEX_KEY` in your password
   manager.
