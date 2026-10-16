# Field-level encryption

Code: `backend/app/core/crypto.py` (ciphers, column types), `backend/app/core/scope.py` (whose key is in use),
migration `alembic/versions/f6a2c8e0b1d3_field_encryption.py`, tests `backend/tests/test_encryption.py`.

## What was there before

Until Phase 6, `ENCRYPTION_KEY` (Fernet) protected exactly one value: the forwarding-address token
(`users.inbound_token_encrypted`), found again through an unkeyed SHA-256 (`users.inbound_token_hash`). Every
transaction, person, note, goal, chat message, report and alert was plaintext in the database. `ENCRYPTION_KEY` is now
read only by the migration (to move any existing token across) and can be removed from Render after it has run.

## How it works

```
MASTER_KEY (env, Render only) ──HKDF──▶ KEK ──AES-256-GCM, AAD = user id──▶ users.data_key (wrapped)
                                                                              │ unwrap per request / per job
                                                                              ▼
                                                           user's 256-bit data key ──AES-256-GCM, AAD = user id──▶ columns
BLIND_INDEX_KEY (env) ──HKDF──▶ HMAC-SHA256(user id ‖ value) ──▶ nonce of Searchable columns; keyed lookup hashes
```

- **Random columns (`e1:`)** get a fresh 96-bit nonce: equal values encrypt differently.
- **Searchable columns (`s1:`)** use the first 96 bits of the blind index as the nonce. So within one user, equal
  values encrypt equally, and SQL can still group, compare and keep `UNIQUE` constraints. Two users never share an
  index or a ciphertext. These columns support `=`, `IN`, `GROUP BY` and uniqueness. They don't support `LIKE` or
  ordering: text search is done by `services/keys.py`, after decryption.
- **No user bound means no data.** Reading or writing an encrypted column without `bind_user` raises an error. So
  does a flush that writes another user's row while one user is bound.

| Table | Encrypted (random) | Searchable (blind index) |
|---|---|---|
| transactions | merchant_raw, notes, raw_source_data | merchant_clean |
| transaction_sources | counterparty_raw, raw_row | utr, vpa |
| people | display_name, masked_vpa | key_hash |
| recurring_series | display_name, user_name | key |
| rules | merchant_label | merchant_key |
| goals | name | |
| chat_messages / chat_actions | content / args, summary | |
| reports | json, narrative | |
| anomalies | details | key |
| alerts | message | key |
| review_dismissals | | card_id |
| telegram_entries | payload | |
| users | inbound_token_encrypted | inbound_token_hash (keyed HMAC, no user id: it finds the user) |

**Still in plaintext, on purpose:**
- **Amounts, dates, kinds and categories:** SQL totals them.
- **Account labels such as "HDFC Bank", and bank names on alert events.**
- **Email, name and Firebase uid:** needed to sign in and to send email.
- **Settings.**

`tests/test_encryption.py::test_every_text_column_is_encrypted_or_justified` fails when a new text column is added
without either encrypting it or adding it to that list with a reason.

## Generating the keys

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"    # run twice: MASTER_KEY, then BLIND_INDEX_KEY
```

Both keys must be:
- at least 32 characters long;
- different from each other;
- different in every environment (production, staging, local);
- set on the Render API service only (`docs/deploy.md`).

The API refuses to start without them. **Back up `MASTER_KEY` outside the database** (for example in a password
manager). If it is lost, every encrypted field is lost too, and a database backup doesn't help.

## Migrating an existing database

`alembic upgrade head` runs `f6a2c8e0b1d3`, and the same `MASTER_KEY` and `BLIND_INDEX_KEY` as the API must be in its
environment. The migration:
1. gives every user a data key;
2. encrypts every value in batches of 500 rows;
3. moves Phase 4 forwarding tokens over (with `ENCRYPTION_KEY` set, if any exist).

**Safety:**
- The migration runs as one transaction. An interrupted run leaves the database as it was.
- Values that already decrypt with their user's key are skipped, so re-running is harmless.
- `alembic downgrade a5c1e7f9b0d3` decrypts everything and restores the old column types. `test_migration_encrypts_reverses_and_is_idempotent` proves the data comes back byte for byte.

**While the migration runs:** the API reads values without an `e1:`/`s1:` prefix as legacy plaintext, so a
half-migrated database is still readable. But searchable lookups only match encrypted values. Run the migration
before sending traffic to the new API.

## Rotating MASTER_KEY

Only the wrapped data keys change. Encrypted fields stay untouched.

1. Generate a new key.
2. On the Render API service:
   - set `MASTER_KEY_PREVIOUS` to the current `MASTER_KEY`;
   - set `MASTER_KEY` to the new key;
   - deploy.

   The API now unwraps with either key and wraps new users' keys with the new one.
3. From `backend/`, with the database owner's URL:
   ```sh
   MIGRATION_DATABASE_URL=… MASTER_KEY=<new> MASTER_KEY_PREVIOUS=<old> python scripts/rotate_master_key.py --dry-run
   MIGRATION_DATABASE_URL=… MASTER_KEY=<new> MASTER_KEY_PREVIOUS=<old> python scripts/rotate_master_key.py
   ```
   It prints `rewrapped N, already_current M`. It is safe to stop and re-run.
4. Run it once more and confirm `rewrapped 0`.
5. Remove `MASTER_KEY_PREVIOUS` from Render and deploy.
6. Destroy every copy of the old key, including old backups that are encrypted with it.

`test_master_key_rotation_rewraps_keys_only` covers the script: it is idempotent, it changes no field, and the data is
readable with the new key alone.

## Rotating BLIND_INDEX_KEY

This is not supported in place. Searchable ciphertexts and the forwarding-address hashes depend on the key. Rotating it
means:
1. decrypting with the old key (`alembic downgrade a5c1e7f9b0d3`);
2. setting the new key;
3. upgrading again.

Do this only in a maintenance window, after a Neon snapshot. Forwarding addresses survive this, because the token
itself is encrypted and its hash is recomputed.

## Threats this covers and doesn't

**Covers:** a leaked database dump, Neon branch or backup, or stolen database credentials. None of these contain
`MASTER_KEY`.

**Doesn't cover:** someone controlling the running API or its Render environment
(`docs/security/threat-model.md`, "Residual risk").
