# Two-factor sign-in (TOTP): not enabled yet

**Decision (Phase 6):** Vaulta doesn't offer TOTP two-factor sign-in yet. Sign-in stays with Google or email and
password through Firebase Authentication.

## Why not now

1. **It needs Identity Platform.** Firebase's TOTP second factor isn't part of plain Firebase Authentication. The
   project has to be upgraded to *Firebase Authentication with Identity Platform*, and multi-factor plus TOTP have to be
   enabled with the Admin API (`projects.updateConfig`, `mfa.providerConfigs: [{state: ENABLED, totpProviderConfig:
   {adjacentIntervals: 5}}]`). That upgrade needs the Blaze (pay-as-you-go) plan. From this repository there was no
   way to check which plan the `vaulta-a3d7a` project is on, and upgrading is a billing decision for you.
2. **It can't be tested end to end here.** The browser tests use the Firebase Auth emulator, and the emulator doesn't
   support TOTP enrolment. So TOTP sign-in would ship without a single automated test, and the rule for this phase is
   that what we claim is tested.
3. **Google sign-in already has 2-step verification.** Most users sign in with Google, so their Google account's own
   second factor applies. Vaulta's TOTP would only add protection for email-and-password accounts.

## What protects accounts today

- Firebase verifies every request's ID token. Tokens expire after at most 1 hour.
- Delete, export, Telegram link and unlink, forwarding-address regeneration and settings changes check with Firebase
  that the session hasn't been revoked (`get_sensitive_user`). So "sign out of all devices" or a password change cuts
  off a stolen token straight away on those routes.
- Repeated bad tokens from one IP are rate limited (`app/core/auth.py`, 30 per 10 minutes).
- Settings → Activity lists sign-ins, exports, deletions and setting changes, so a user can spot activity that isn't
  theirs.

## To turn it on later

1. Upgrade the Firebase project to Identity Platform (Blaze plan) in the Firebase console, under **Authentication →
   Settings**.
2. Enable TOTP MFA with the Admin SDK or REST:
   ```sh
   curl -X PATCH "https://identitytoolkit.googleapis.com/admin/v2/projects/vaulta-a3d7a/config?updateMask=mfa" \
     -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" \
     -d '{"mfa":{"providerConfigs":[{"state":"ENABLED","totpProviderConfig":{"adjacentIntervals":5}}]}}'
   ```
3. In the web app:
   - add enrolment in Settings with `multiFactor(user).getSession()`, `TotpMultiFactorGenerator.generateSecret` and a
     QR code;
   - handle `auth/multi-factor-auth-required` on sign-in with `getMultiFactorResolver`.
4. Test it against a real staging Firebase project, since the emulator can't do it.
5. Only then, add it to `/security`.
