# Vaulta threat model

Scope: the API (`backend/`), the web app (`frontend/`), the Cloudflare email worker (`infra/email-worker/`), the
Render cron job, and the Postgres database on Neon. Written for Phase 6; every mitigation names the code or test that
implements it. When you change one of those, update this file in the same commit.

## Assets

| Asset | Where it lives | Sensitivity |
|---|---|---|
| Transactions (date, amount, description, merchant, notes, category, kind) | `transactions`, `transaction_sources` | High: a person's whole financial life |
| People (who the user pays and is paid by, masked UPI IDs) | `people`, `transactions.person_id` | High: third parties' names |
| Rules, recurring series, budgets, goals, cash wallet | `rules`, `recurring_series`, `budgets`, `goals`, `goal_entries`, `cash_declarations` | Medium to high: habits, income, plans |
| Chat history and proposed actions | `chat_messages`, `chat_actions` | High: free text the user typed |
| Reports, anomalies, alerts | `reports`, `anomalies`, `alerts` | High: merchant names, amounts, narratives |
| Tokens and secrets | Firebase ID tokens (browser), demo tokens, chat confirm tokens, Telegram link codes, unsubscribe links, `SECRET_KEY`, `INTERNAL_SECRET`, `MASTER_KEY`, `BLIND_INDEX_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `DATABASE_URL` | Critical: each one opens a door |
| Forwarding addresses (`<token>@in.<domain>`) | `users.inbound_token_hash`, `users.inbound_token_encrypted` | High: anyone with it can inject transactions |
| Telegram links | `users.telegram_chat_id`, `telegram_link_codes`, `telegram_entries` | High: the bot answers money questions in that chat |
| Account identity | `users.email`, `users.full_name`, `users.firebase_uid` | Medium |
| Activity log | `activity_log` | Medium: when and how the account was used |

## Actors

| Actor | Can | Wants |
|---|---|---|
| Outside attacker | Reach every public URL, send any request, run scripts | Other people's data, account takeover, abuse (spam, LLM spend), defacement |
| Another Vaulta user | Everything an outsider can, plus a valid session | Read or change someone else's data through the API |
| Compromised dependency (npm, PyPI, GitHub Action) | Run code in the browser, the API or CI | Exfiltrate tokens, data or secrets |
| Malicious email sender | Send any email to a forwarding address | Inject fake transactions, phish through the Gmail confirmation, exploit the parser |
| Holder of a leaked database dump (backup, Neon branch, stolen credentials) | Read every row of every table | Read users' financial data |
| LLM provider (Groq) | Sees every prompt sent to it | (Honest but curious) retain or leak what it receives |

## Entry points

| Entry point | Auth | Notes |
|---|---|---|
| `GET /health`, `GET /health/ready` | none | Status only, no data |
| `POST /auth/demo` | none | Issues a read-only demo token; rate limited per IP |
| `GET/PATCH/DELETE /auth/me` | Firebase ID token | `DELETE` is a sensitive route |
| `GET /api/export` | Firebase ID token | Sensitive route |
| `GET /api/activity` | Firebase ID token | |
| `/api/transactions*`, `/api/import/*`, `/api/recurring*`, `/api/people*`, `/api/rules*`, `/api/review*`, `/api/budgets*`, `/api/goals*`, `/api/cash*`, `/api/home`, `/api/anomalies*`, `/api/reports*`, `/api/alerts*`, `/api/onboarding*` | Firebase ID token or demo token (reads only) | User data; every query is scoped by user and by RLS |
| `/api/chat*` | Firebase ID token or demo token | Sends data to the LLM provider |
| `/api/settings`, `/api/inbound*`, `/api/telegram*` | Firebase ID token | Settings changes, address regeneration and Telegram unlink are sensitive routes |
| `/api/payments/create-subscription`, `/api/payments/status` | Firebase ID token | |
| `POST /api/payments/webhook` | Razorpay HMAC signature | |
| `GET/POST /unsubscribe?token=` | HMAC token (`SECRET_KEY`) | Turns one email type off, nothing else |
| `POST /internal/run-reports` | `X-Internal-Secret` | Render cron |
| `POST /internal/inbound-email` | `X-Internal-Secret` | Cloudflare email worker; one email ≤ 256 KB |
| `POST /internal/telegram` | `X-Telegram-Bot-Api-Secret-Token` | Telegram webhook |
| Inbound email (`*@in.<domain>`) | sender allowlist + DKIM/SPF verdict | Through the worker |
| Telegram chat with the bot | linked chat id; link codes are one-time, 10 minutes | |
| Web app (Vercel) | Firebase Auth in the browser | Static files, statement parsing on the device |
| Demo session | `demo.<sid>.<exp>.<sig>` HMAC token, 2 hours | Read-only except chat |

## Threats and mitigations

Each row: the threat, then what stops it and where that is enforced or tested.

### Outside attacker

| Threat | Mitigation |
|---|---|
| Calling user routes without a session | Every `/api/*` route depends on `get_current_user` (`app/core/auth.py`); Firebase ID tokens are verified with the Admin SDK. `tests/test_ownership.py::test_every_route_is_covered` fails when a route is added without an isolation case. |
| A stolen but revoked token (user signed out everywhere, password changed, account disabled) | Sensitive routes (delete, export, unlink, address regeneration, settings) verify with `check_revoked=True` (`app/core/auth.py::get_sensitive_user`). Other routes accept the token until it expires (at most 1 hour). |
| Brute force or flooding: demo sessions, chat (LLM spend), imports, Telegram, auth-sensitive routes | Postgres-backed fixed-window limits (`app/core/ratelimit.py`, table `rate_limits`), shared by every API worker. `tests/test_ratelimit.py`. |
| Oversized bodies, huge imports, long strings | Request body cap in middleware (`MAX_BODY_BYTES`), per-field Pydantic limits, at most 500 rows per import batch, 256 KB per inbound email. |
| Learning internals from errors | Production returns a generic `{"detail": "Something went wrong.", "request_id": …}` for unhandled errors, no stack traces; `/docs` and `/redoc` are off. `tests/test_app_security.py`. |
| XSS in the web app | React escapes output; a strict CSP (`frontend/vercel.json`) with no `unsafe-inline` scripts and `connect-src` limited to the API and Firebase; emails escape every user value (`services/report_email.py`, `services/email_alerts.py`). |
| Clickjacking | `frame-ancestors 'none'` and `X-Frame-Options: DENY` on the app and the API. |
| Downgrade, sniffing, referrer leaks | HSTS, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`. Headers tested on the API (`tests/test_app_security.py`) and checked in CI by OWASP ZAP. |
| Cross-origin calls from other sites | CORS allows only `BACKEND_CORS_ORIGINS` and, when set, `BACKEND_CORS_ORIGIN_REGEX` (Vercel previews). Auth is a bearer header, never cookies, so there is no CSRF surface. |
| Forging internal calls | `/internal/*` requires `X-Internal-Secret` (≥ 32 random characters in production) compared in constant time; refuses everything when unset. The Telegram webhook requires its own secret. |
| Forging demo, unsubscribe or confirm tokens | HMAC-SHA256 with `SECRET_KEY` (demo, unsubscribe); chat confirm tokens are 256-bit random and stored as SHA-256 only, bound to user and session, single use, 10 minutes. |
| Guessing a forwarding address | 10 random characters from a 36-character alphabet (about 52 bits), looked up by a keyed HMAC (a dump can't be brute-forced back to addresses); the internal endpoint itself needs `X-Internal-Secret`, so guesses have to arrive as real email through Cloudflare; unknown recipients are dropped without a reply. |

### Another Vaulta user

| Threat | Mitigation |
|---|---|
| Reading or changing another user's rows by id (IDOR) | Every query filters by `user_id`; `tests/test_ownership.py` walks every route as a second user. |
| A query that forgets the `user_id` filter | Postgres row-level security on every user-owned table (`alembic/versions/*_row_level_security.py`): policies compare `user_id` with `app.user_id`, set per transaction by `bind_user` (`app/core/scope.py`). The API connects as `vaulta_app`, which doesn't own the tables and has no `BYPASSRLS`. `tests/test_rls.py` runs unfiltered queries and gets nothing back for other users. |
| Writing into the demo account | The demo token is read-only except chat; `tests/test_demo.py` walks every write route and expects 403. |
| Reusing someone else's chat confirm token or Telegram code | Tokens are bound to their user; `tests/test_chat.py`, `tests/test_telegram.py`. |

### Compromised dependency

| Threat | Mitigation |
|---|---|
| A malicious npm package in the browser | Strict CSP limits where scripts load from and where data can be sent (`connect-src`: the API and Firebase only); Playwright fails any request to another origin (`frontend/e2e/fixtures.js`). Lockfiles are committed; `npm audit` runs in CI. |
| A malicious PyPI package in the API | Pinned `requirements.txt`; `pip-audit` and Bandit in CI; the API's database role can't change the schema or bypass RLS. Secrets come from the environment, never the repo (`scripts/secret-check.sh`). |
| A compromised GitHub Action | Actions are pinned to full commit SHAs; the workflow token is read-only (`permissions: contents: read`); CI gets no production secrets. Dependabot proposes updates. |

### Malicious email sender

| Threat | Mitigation |
|---|---|
| Fake bank alerts injecting transactions | Sender must be on the bank's allowlist (`app/core/alert_senders.py`) and the message must pass DKIM or SPF for that domain in Cloudflare's `Authentication-Results`; otherwise only an `untrusted_sender`/`auth_failed` event is recorded. |
| Big or hostile payloads | The worker rejects messages over 1 MB, drops attachments, caps the payload at 256 KB; the API refuses bodies over 256 KB and parses in memory. Raw emails are never stored (`tests/test_inbound.py` dumps every table). |
| Phishing through the Gmail forwarding confirmation | Only a message DKIM-signed by google.com is treated as a confirmation, and only a `https://mail.google.com/mail/…` or `mail-settings.google.com` link and the code are kept and shown; Vaulta never follows the link. |
| Script injection through email text into alert emails | Every value is HTML-escaped in emails; the app renders text, never HTML. |

### Leaked database dump

| Threat | Mitigation |
|---|---|
| Reading descriptions, merchants, notes, people, goals, chat, reports, alerts from a dump | Field-level envelope encryption (`app/core/crypto.py`): each user has a random 256-bit data key, stored only wrapped (AES-GCM) by `MASTER_KEY`, which lives in the API's environment, never in the database. Columns are AES-256-GCM with the user id as associated data. `tests/test_encryption.py::test_dump_has_no_plaintext` dumps every table and finds none of the fixture's text. |
| Linking rows across users through equal ciphertexts or indexes | Ciphertexts are randomized (fresh 96-bit nonce). Grouping and matching use HMAC-SHA256 blind indexes keyed by `BLIND_INDEX_KEY` and the user id, so the same merchant has a different index for each user. |
| Still visible in a dump | Amounts, dates, categories, kinds, bank names and timestamps (needed for SQL totals); account emails and names (needed for sign-in and email); counts. The threat model accepts this; see "Residual risk". |
| Old credentials in git history | The Neon password committed in 34e5052 was rotated on 2026-10-16. `scripts/secret-check.sh` (gitleaks plus every version of every file) runs in CI and before every push. |

### LLM provider (Groq)

| Threat | Mitigation |
|---|---|
| The provider sees raw narrations, UPI IDs, references or notes | Chat tools return merchant names, categories, amounts and dates only; `llm_safe` (`services/chat_tools.py`) strips raw descriptions, references, UPI IDs and notes; `tests/test_chat.py` asserts the prompts contain none of them. |
| The provider sees data the user didn't choose to share | AI chat can be switched off in Settings (then no chat data is sent). Report summaries are written by Groq from the report's computed figures only, whether or not chat is on, and /security says so; a user who doesn't want that turns the report off. A template is used when no key is configured or the model's text uses a number that isn't in the report. |

## Logging

Structured JSON logs (`app/core/logs.py`): request id, a keyed hash of the user id, route template, status and
latency. Never amounts, merchant names, narrations, email addresses or tokens. `tests/test_logs.py` captures the logs
across the end-to-end fixture and searches them for every one of those.

## Residual risk (accepted, revisit before scale)

- The API holds `MASTER_KEY`, so someone who controls the running API (or its environment on Render) can read
  everything. Encryption protects dumps, backups and database credentials, not a compromised server.
- Amounts, dates and categories stay in plaintext so SQL can total them.
- Firebase ID tokens are accepted until expiry (≤ 1 hour) on non-sensitive routes after revocation.
- Inbound DKIM trust relies on Cloudflare's `Authentication-Results` header (unverified against real bank mail).
- No TOTP MFA (see `docs/security/mfa.md`).
