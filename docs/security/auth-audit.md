# Authentication audit (start of Phase 6.5)

State of `rebuild/phase6` before Phase 6.5. Evidence is quoted from the code at that commit.

| # | Item | State | Evidence |
|---|---|---|---|
| 1 | Email verification | **Missing** | `frontend/src/pages/Login.jsx` calls `createUserWithEmailAndPassword` and goes straight to `/`; there is no `sendEmailVerification`. `backend/app/core/auth.py` never reads `email_verified` (the only use is the unrelated onboarding coverage flag in `services/coverage.py`). |
| 2 | Password reset / change / policy | **Missing** | No `sendPasswordResetEmail` or `updatePassword` anywhere. The minimum is Firebase's default of 6 characters (`ERROR_MAP['auth/weak-password']`). |
| 3 | Account linking | **Missing** | No `linkWith*` and no handling of `auth/account-exists-with-different-credential`. `Login.jsx` maps `auth/email-already-in-use` to "An account with this email already exists." Users are keyed by `firebase_uid` (`models/user.py`), so linking in Firebase would keep one vaulta.in account, but nothing exercises it. |
| 4 | Delete everything removes the login | **Partial** | `DELETE /auth/me` (`api/routes/auth.py`) deletes the database rows (cascade; tested by `tests/test_delete_account.py`). The Firebase user is deleted only from the browser, `currentUser?.delete()` in `pages/Settings.jsx`, falling back to `signOut` when Firebase wants a recent login. So the login usually survives. There is no server-side delete, no retry, no record of a pending deletion and no confirmation email. |
| 5 | Bot protection (App Check) | **Missing** | No `firebase/app-check` import; no backend verification. Only the Postgres rate limits from Phase 6 (`core/ratelimit.py`). |
| 6 | Email enumeration | **Partial** | Sign-in shows one message for wrong password and unknown email (`auth/invalid-credential`), but sign-up says "An account with this email already exists." The console setting is not documented. |
| 7 | Sign out everywhere | **Missing** | No `revoke_refresh_tokens`. Revocation is only *checked* (`get_sensitive_user`, `check_revoked=True`) on delete, export, Telegram link/unlink, address regeneration and settings. |
| 8 | Recent login for sensitive actions | **Missing** | `auth_time` is read only to log sign-ins (`_note_sign_in`). No route checks its age. |
| 9 | Session UX and activity | **Partial** | Activity log exists (`services/activity.py`: sign_in, export, deleted, telegram_linked/unlinked, address_regenerated, settings_changed, profile_changed). Sign-in method, sign-up, re-auth, reset, linking, sign-out-everywhere and deletion events are missing. An expired session sends the user to `/login` (`lib/api.js`) or `/welcome` (`App.jsx` `PrivateRoute`) with no way back to the page they were on. |

Phase 6.5 builds every missing and partial item: see `docs/archive/reports/phase-6-5.md`.
