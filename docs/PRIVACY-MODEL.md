# Privacy model

What vaulta.in collects, where it is processed, how it is protected, what the AI sees and how long anything is kept.
This is the engineering view of the same facts as the app's [/privacy](https://vaulta.in/privacy) and
[/security](https://vaulta.in/security) pages (`frontend/src/pages/Privacy.jsx`, `frontend/src/lib/trust.js`). If
they ever disagree, the code is what's true and both need fixing.

## What is collected

| Data | Where it comes from |
|---|---|
| Account: email, name, Firebase uid | Google or email sign-in (Firebase Authentication) |
| Transactions: date, description with personal details masked, amount, direction, payment reference (UTR), account label you chose (e.g. "HDFC Bank"), category, tags, notes | rows you confirm from a statement, forwarded alert emails, manual entries, Telegram |
| What you set up: budgets, goals, rules, people you pay (names as they appear in transactions), settings, onboarding answers | you |
| Chat: your questions and the assistant's answers | AI chat (web and Telegram) |
| Reports and alerts | built by the hourly run |
| Account activity: sign-ins, exports, deletions, Telegram link changes, settings changes (no IP address) | the API |
| Telegram chat id | only if you link Telegram |
| Category corrections for retraining: the masked description and the subcategory you chose, nothing else | only if you opt in (Settings → Categories) |
| Razorpay subscription id and status | only if you subscribe (no payments are configured today) |

**Never collected:** statement files, account and card numbers, balances, statement passwords, your login password,
the text of forwarded emails beyond the transaction found in them, bill photos, location, contacts, advertising ids.
There are no ads and no analytics trackers.

## Where it is processed

| On your device (browser) | On vaulta.in's server (API) |
|---|---|
| Reading statement files: CSV, Excel, PDF (pdf.js), photos (Tesseract.js); assets are served by vaulta.in | Forwarded alert emails: parsed in memory, then discarded |
| The PDF password, used only to open the file | Telegram messages and manual entries |
| Dropping the header, account number and running balance; checking the rows add up to the closing balance | Personal-details stripping for rows that don't come through the browser (`backend/app/services/pii.py`, the same rules as the browser's, kept equal by `fixtures/pii_cases.json`) |
| Personal-details stripping (`frontend/src/import/pii.js`): personal UPI IDs → `R***@okaxis`, phone numbers masked, IFSC codes removed, 9+ digit runs → `XXXX`, your own full name → `SELF` | Categorising those rows with the same merchant model file |
| Categorising with the merchant model (`frontend/src/lib/merchantModel.js`) | Encryption, storage, totals, reports, alerts, chat |

Only the rows you confirm in the preview are sent to the API (`POST /api/import/batch`); the file is not. Every browser
test fails if a request uploads a file or carries a statement's contents.

## Encryption at rest

`backend/app/core/crypto.py`; full detail in [security/encryption.md](security/encryption.md).

- **Envelope encryption per user.** Each user has a random 256-bit data key, stored only wrapped: `MASTER_KEY` (an
  environment variable on Render, never in the database) → HKDF → key-encryption key → AES-256-GCM with the user id as
  associated data. Columns are encrypted with the user's data key, AES-256-GCM, again bound to the user id.
- **Blind indexes.** `BLIND_INDEX_KEY` → HKDF → HMAC-SHA256 over (user id ‖ value). Searchable columns use it as the
  nonce, so equal values encrypt equally within one user and SQL can still group, compare and enforce uniqueness; two
  users never share a ciphertext. The forwarding-address token is found by a keyed hash of it.
- **Encrypted:** merchant names and raw descriptions, notes, source rows, UTRs and UPI IDs, people's names, recurring
  series names, rule labels, goal names, chat messages and actions, report contents, anomaly details, alert messages,
  Telegram entries, the forwarding token.
- **Plaintext, on purpose:** amounts, dates, kinds and categories (SQL adds them up), account labels such as "HDFC
  Bank", email, name and Firebase uid (sign-in and email need them), settings.
  `tests/test_encryption.py::test_every_text_column_is_encrypted_or_justified` fails for a new text column that is
  neither.
- This is encryption at rest, not end-to-end: the API decrypts your data to show it to you. It protects against a
  leaked dump, backup or database credentials, not against someone controlling the running API.

## Row-level security and roles

Full detail in [security/row-level-security.md](security/row-level-security.md).

| Role | Used by | Can do |
|---|---|---|
| `vaulta_app` | the API (`DATABASE_URL` on Render) | read and write rows of the bound user only: `NOSUPERUSER NOBYPASSRLS`, owns no table, can't disable RLS |
| `vaulta_backup` | the weekly backup (`BACKUP_DATABASE_URL`, a GitHub secret) | read everything (`pg_read_all_data` + `BYPASSRLS`, which a dump needs), write nothing |
| `neondb_owner` | migrations and key rotation, from the owner's machine only | owns the tables; never given to the API |

Every user-owned table has the policy `user_isolation`: a row is visible only when its `user_id` equals
`app.user_id`, which `bind_user` sets for the current transaction. With no user bound, nothing matches. If the API ever
connects as a role that could bypass RLS, `/health/ready` fails and database routes answer 503.

## What the AI sees

Two features call Groq (`backend/app/services/llm.py`; default model `openai/gpt-oss-120b`). Categorising does not:
it never calls an AI service ([MODEL_CARD.md](MODEL_CARD.md#what-text-goes-to-groq)).

- **Chat** (`backend/app/services/chat.py`): a system prompt with today's date; the last 10 turns of that
  conversation; your question; and the results of the tools the model calls, computed from your data as you.
  Results carry dates, amounts, directions, categories, subcategories, tags, cleaned merchant names, the display
  names of people you pay and what they owe, budgets, recurring payments, goals, forecasts and cash figures.
- **Report summaries** (`backend/app/services/reports.py`, `write_narrative`): that report's JSON. It holds the
  period's totals and the previous period's, budget status, top categories, top merchants (cleaned names), tags,
  recurring-payment changes, anomalies, money owed to and by people (display names, amounts, days), the cash wallet,
  safe-to-spend, and goals (monthly) or the yearly summary (annual). A summary that contains a number not in the
  report is thrown away and a template is used instead.
- **Never sent:** before anything goes to Groq, `llm_safe` (`backend/app/services/chat_tools.py`) removes, wherever
  they appear, `merchant_raw`, `description_raw`, `counterparty_raw`, `reference`, `utr`, `vpa`, `masked_vpa`,
  `raw_row`, `raw_source_data`, `notes` and `idempotency_key`. So Groq never receives raw bank narrations, payment
  references, UPI IDs (even masked), statement rows or your notes. Tests record every request to the AI and check it.
- **Switches:** turning AI chat off in Settings stops chat; report summaries are still written by Groq unless that
  report is turned off. Without `GROQ_API_KEY` chat is unavailable and summaries use the template.
- Groq handles what it receives under its own terms.

## Retention

| What | Kept |
|---|---|
| Chat history | 30 days, then purged by the hourly run (and on each new message) |
| Samples from the "Try it" page | 1 hour, or until "Clear samples" |
| Forwarded alert emails | not kept: only the transaction found and which bank sent it, and when |
| Rate-limit counters | purged after 30 days by the hourly run |
| Everything else | until you delete it or your account |

## Deletion

- **One import:** Settings → Imports deletes the transactions from one uploaded file (`POST /api/import/delete`).
- **Reset my data:** deletes all your financial data and keeps the account (`POST /auth/me/reset-data`).
- **Delete everything:** after a fresh sign-in and typing DELETE (`DELETE /auth/me`), every row of the account, its
  data key, forwarding address and Telegram link are removed at once, then the Firebase sign-in is deleted and a
  confirmation emailed. If Firebase can't be reached, only the uid and email are kept, marked pending, and the hourly
  run finishes the deletion; the sign-in can't be used in the meantime.
- **Export** (Settings → Your data): everything, decrypted, as a zip of JSON and CSV, built on request and not kept.

## Backups

- **Neon's point-in-time restore** covers the recent past (the free plan keeps a short history).
- **Weekly backup:** `pg_dump` as `vaulta_backup`, piped straight into `age` with the owner's public key on the GitHub
  runner, kept as a workflow artifact for 35 days. Only ciphertext is uploaded; the private key is offline. Encrypted
  columns stay encrypted inside the dump, so reading one also needs `MASTER_KEY`.
- Deleted data can remain in these backups until they expire. Backups are restored only to recover from a failure,
  into a new branch first.

## Error reports and logs

Sentry (EU region) gets the error type and the code location. The scrubbers (`backend/app/core/monitoring.py`,
`frontend/src/lib/monitoring.js`) remove request contents, cookies, headers, search terms, user identity, and from any
text emails, UPI IDs, amounts, long numbers and quoted text. There is no session recording or performance tracing. The
API's request log has no access log with query strings (`--no-access-log`; `backend/app/core/logs.py` logs requests
itself) and refers to users by a keyed reference (`user_ref`), not by their id or email.
