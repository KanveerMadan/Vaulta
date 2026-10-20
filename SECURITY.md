# Security policy

## Reporting a vulnerability

Email **security@vaulta.in**. The address is also published at https://vaulta.in/.well-known/security.txt and
https://api.vaulta.in/.well-known/security.txt.

Please include what you found, where (URL, endpoint or file), how to reproduce it, and what an attacker could do with
it. Don't open a public GitHub issue for a vulnerability.

When testing, use only your own account (or the read-only demo), don't access or change anyone else's data, don't run
denial-of-service or high-volume scans, and stop and report as soon as you can show the problem.

> **TODO (owner):** confirm the response times below and whether to offer a safe-harbour statement.

- Acknowledgement: within 3 working days.
- An assessment and a plan (fix, mitigation or why it isn't a vulnerability): within 14 days.
- You'll be told when it's fixed, and credited if you want to be.

There is no bug bounty.

## Scope

In scope:
- https://vaulta.in (the web app) and https://api.vaulta.in (the API)
- inbound alert email at `in.vaulta.in` (the Cloudflare Email Worker in `infra/email-worker/`)
- the Telegram bot @VaultaAppBot
- the code in this repository, including the CI workflows

Out of scope:
- the third-party services vaulta.in uses (Firebase, Google reCAPTCHA, Neon, Render, Vercel, Groq, Resend,
  Cloudflare, Telegram, Sentry): report those to the provider
- denial of service, rate-limit exhaustion and spam
- social engineering, and physical access to someone's device
- missing best-practice headers or settings with no demonstrable impact

## What is in place

How each of these works is in [docs/PRIVACY-MODEL.md](docs/PRIVACY-MODEL.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
and [docs/security/](docs/security/). The app's /security page lists each claim with the test that checks it.

- **Statements stay on the device.** Files are parsed and personal details stripped in the browser; only confirmed
  rows reach the API.
- **Per-user envelope encryption** of descriptions, merchant names, people, notes, chats, reports and alerts
  (AES-256-GCM, a data key per user wrapped by a master key held outside the database; blind indexes with a separate
  key).
- **Postgres row-level security.** The API connects as a role that can't bypass it, and refuses to serve if it could.
- **Sign-in** by Firebase Authentication; the API verifies every ID token, and sensitive actions need a recent sign-in.
- **Server-side reCAPTCHA v3** on the demo, sign-up, password reset, import and chat. A low score slows requests down
  and never locks anyone out.
- **Rate limits** on sign-in-adjacent and expensive routes.
- **Internal endpoints** (hourly run, email worker, Telegram webhook) need a shared secret, compared in constant time.
- **Strict HTTP headers:** CSP without inline scripts, HSTS, `frame-ancestors 'none'`, nosniff, on the app and the API.
- **Secrets** live only in the hosting dashboards (Render, Vercel, GitHub Actions secrets, Cloudflare), never in git.
  CI scans the full git history for secrets and personal data on every push (`scripts/secret-check.sh`, gitleaks).
- **Dependency and code scanning** in CI: pip-audit, npm audit, Bandit, Semgrep and an OWASP ZAP scan of the running
  app and API.
- **Encrypted backups:** a weekly `pg_dump` by a read-only role, encrypted with age on the runner before upload; the
  private key is kept offline.
- **Error reports** (Sentry, EU region) are scrubbed of request contents, identities and financial data before they
  leave the browser or the server.

## Supported versions

Only the version running on vaulta.in (the `main` branch) is supported.
