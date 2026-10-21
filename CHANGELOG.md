# Changelog

All notable changes to vaulta.in. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **Statement import failed on larger statements** (a 218-row Kotak Mahindra statement, 21 Oct 2026) with only "Import
  failed". Each 200-row batch cost the API about 2,500 database queries, enough on the free instance to run past the
  app's 20-second limit, and a timed-out batch was never sent again. The app now sends 50 rows a request with 90 seconds each, resends a batch that timed out or met a waking
  API (safe: saved rows come back as duplicates), and says what went wrong: the server's reason, the row it refused,
  or how many rows were saved before a failure. The API writes the categorisation counts once per batch instead of
  once per row, and its own 500 and 413 answers now carry CORS headers, so the browser can read them.

### Changed

- **Brand: vaulta.in.** The name people see is now exactly "vaulta.in" (lowercase, with the .in) everywhere: the app,
  page titles and share tags, the installable app's name, emails, the Telegram bot's messages and the docs. "Vaulta"
  alone collides in search with an EOS crypto rebrand and another finance app. Domains, email addresses, code,
  environment variables, database roles and service names are unchanged.
- **New landing page** (`/welcome`): "Kahan gaye paise?", screenshots of the real app (captured from the demo account
  by `scripts/landing-shots/`), Sign in with Google as the main action and the demo as a secondary link.
- The landing page says "Open source" again, now that the repository has a licence.

### Added

- MIT licence.
- Project docs: README, SECURITY, CONTRIBUTING, `docs/ARCHITECTURE.md`, `docs/PRIVACY-MODEL.md`, and
  `docs/MODEL_CARD.md` (moved from `docs/ml/model-card.md`). `docs/deploy.md` and `docs/runbook.md` are now
  `docs/DEPLOY.md` and `docs/RUNBOOK.md`, with the deploy flow, migrations and rollback.

### Removed

- The unused `clsx` dependency and the Vite template's `frontend/README.md`. Phase build logs moved to
  `docs/archive/reports/`.

## [1.0.0] - 2026-10-20

First public release, on https://vaulta.in (git tag `v1.0`).

### Added

- **Statement import, read on your device:** CSV, Excel and PDF statements from HDFC Bank, ICICI Bank, SBI, Axis Bank
  and Kotak Mahindra Bank; credit card statements from HDFC Bank, ICICI Bank, SBI Card and Axis Bank; Google Pay,
  PhonePe and Paytm statements; any other bank's file by matching its columns once; photos of statements by on-device
  text recognition. Account numbers, balances and personal details are stripped before anything is sent. Each import
  can be deleted on its own, or all financial data reset.
- **Forwarded bank alert emails** to a personal address at `in.vaulta.in`, read on arrival and not stored.
- **Telegram bot** (@VaultaAppBot) for quick entries, summaries and alerts.
- **Categories:** your rules, your own past corrections, known merchants, then a small merchant model
  (`docs/MODEL_CARD.md`) that runs in the browser and on the server; anything unsure goes to a review queue.
- **Spending views:** safe to spend today, budgets, goals, recurring payments and price rises, people you pay and
  money lent, a cash wallet, anomalies and a yearly "wrapped".
- **Reports and alerts:** weekly, monthly and annual reports by email, and alerts, sent by an hourly scheduled run.
- **AI chat** that answers from your own computed figures, and can propose changes you confirm.
- **Your data:** export everything as JSON and CSV; delete everything, including the sign-in.
- **Demo account** to look around without signing up.
- **Protection:** per-user envelope encryption of descriptions, merchants, people, notes, chats and reports; Postgres
  row-level security; server-side reCAPTCHA v3 on the demo, sign-up, password reset, import and chat; scrubbed error
  reports; encrypted weekly backups.
- **Hosting:** web app on Vercel, API on Render (Singapore), Postgres on Neon (Singapore).

[Unreleased]: https://github.com/KanveerMadan/Vaulta/compare/v1.0...HEAD
[1.0.0]: https://github.com/KanveerMadan/Vaulta/releases/tag/v1.0
