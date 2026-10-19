# Row-level security

Code: migration `alembic/versions/a7c3e9f1d2b4_row_level_security.py`, binding in `backend/app/core/scope.py`, the
role check in `backend/app/core/database.py`, tests in `backend/tests/test_rls.py`.

## How it works

- **The policy.** Every user-owned table, plus `users` and `households`, has RLS enabled and one policy,
  `user_isolation`: a row is visible and writable only when its `user_id` (for `users`, its `id`) equals
  `app.user_id`.
- **Setting `app.user_id`.** `bind_user` sets it with `set_config('app.user_id', …, true)`. The value lasts for the
  current transaction only, so a session listener applies it again at the start of every transaction. With no user
  bound it is empty, and no row matches.
- **Who binds.**
  - Requests: `get_current_user`, for every request.
  - Internal jobs (hourly reports and alerts, demo reset, inbound email, Telegram updates, unsubscribe links, the
    Razorpay webhook): once per user, before touching that user's data.
- **Finding a user before anyone is bound.** This goes through four `SECURITY DEFINER` functions, which return ids only:
  - `vaulta_find_user(field, value)`
  - `vaulta_user_ids()`
  - `vaulta_telegram_code_user(hash)`
  - `vaulta_release_telegram_chat(chat)`

  The row itself is then read as that user.
- **Who the policies apply to.** The API connects as `vaulta_app`, which is not a superuser, has no `BYPASSRLS` and
  owns no table, so the policies apply to it. Migrations run as the tables' owner, which RLS exempts (it is enabled,
  not forced).
- **The production guard.** If the API finds itself connected as a role that would bypass the policies, every
  database route answers 503 and the log says why (`check_role`).

Tests prove:
- An unfiltered `SELECT` or ORM query returns only the bound user's rows.
- An unbound session sees nothing.
- `UPDATE`/`DELETE` of another user's rows affects 0 rows, and `INSERT` for another user is refused.
- `vaulta_app` can't disable RLS.
- Every table with a `user_id` has a policy.
- Delete everything still removes every row.

The isolation tests in `tests/test_ownership.py` (every route, as a second user) still run on top of this.

Not covered by RLS:
- **`rate_limits`:** keyed by hashed IP, chat or user. It holds no user data.
- **`alembic_version`:** `vaulta_app` can read it, not write it.

## Neon roles (you run these)

Neon has two kinds of roles here:
- **`neondb_owner`:** the existing owner. It runs the migrations.
- **`vaulta_app`:** the new role for the API. Create it **with SQL, not in the Neon console**: roles made in the
  console join `neon_superuser`, which can bypass RLS.

1. Create the role. Connect as `neondb_owner` to the branch (staging first, then production), using the **direct**
   (non-pooler) host:
   ```sql
   CREATE ROLE vaulta_app WITH LOGIN PASSWORD '<32+ random characters>' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
   GRANT CONNECT ON DATABASE neondb TO vaulta_app;
   ```
   Generate the password with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and keep it only in the
   connection string on Render.
2. Run the migrations as the owner:
   ```sh
   MIGRATION_DATABASE_URL='postgresql://neondb_owner:…@<direct host>/neondb?sslmode=require' alembic upgrade head
   ```
   `a7c3e9f1d2b4` grants `vaulta_app` what it needs:
   - `SELECT/INSERT/UPDATE/DELETE` on the tables;
   - `SELECT` on `alembic_version`;
   - `EXECUTE` on the lookup functions;
   - default privileges for later tables.

   If you create the role *after* migrating, run `alembic downgrade a7c3e9f1d2b4-1 && alembic upgrade head`, or the
   `GRANT` block of the migration by hand.
3. Check the role:
   ```sql
   SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'vaulta_app';   -- f, f
   SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = 'vaulta_app';   -- 0
   ```
4. Point the Render API service at it:
   ```
   DATABASE_URL=postgresql://vaulta_app:<password>@<pooler host>/neondb?sslmode=require
   ```
   The pooled host is fine: the setting is transaction-scoped, which works with PgBouncer's transaction pooling. Keep
   the owner's URL out of the API service. It is needed only where migrations run (your machine, or a one-off job).
5. Verify that `GET /health/ready` reports `"rls": "enforced"`.

To roll back: point `DATABASE_URL` back at the owner. RLS is then bypassed, and `/health/ready` reports it. Then run
`alembic downgrade f6a2c8e0b1d3`, which drops the policies and functions.
