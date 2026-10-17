# Phase 6.5 report: authentication hardening (+ cross-browser and device testing)

Branch `rebuild/phase6-5`, built on `rebuild/phase6`. Pushed. GitHub Actions run 38974723804 is green: all six jobs,
with the browser job running Chromium, Firefox, WebKit and every device profile. PR #1 is updated and still marked
DO NOT MERGE.

## Audit (start of the phase; `docs/security/auth-audit.md`)

| Item | Before | Now |
|---|---|---|
| Email verification | missing | done (step 1) |
| Password reset / change / policy | missing | done (step 2); the Firebase policy is a console step |
| Account linking | missing | done (step 3) |
| Delete everything deletes the login | partial: rows only; login deleted from the browser, only after a recent sign-in | done (step 4) |
| App Check | missing | done (step 5); enforcement is a console step |
| Email enumeration | partial: sign-up revealed existing addresses | done (step 6); the console setting is a go-live step |
| Sign out everywhere | missing (revocation only *checked* on sensitive routes) | done (step 7) |
| Recent login for sensitive actions | missing | done (step 8) |
| Session UX and activity | partial | done (steps 7, 9) |

## What each step did

1. **Verification.**
   - The web app: email/password sign-ups get a "Check your inbox" screen. Resend has a 60 s cooldown that survives
     reloads, and "I've confirmed my email" refreshes the token.
   - The API: any write, the forwarding address, Telegram, chat and imports answer 403 `email_unverified` for
     unverified password accounts. Google sign-ins count as verified.
   - Tests walk every write route.
2. **Passwords.**
   - "Forgot password?" gives the same message for any address.
   - The reset request and its completion are logged (completion is detected at the next sign-in).
   - Change or add a password in Settings, through the API: it needs a recent sign-in and 10+ characters, and signs
     out every other session.
3. **Linking.**
   - Firebase's one-account-per-email links Google to an existing password account on the same uid. This was
     checked against the emulator.
   - When Firebase raises account-exists-with-different-credential, the login page asks for the password and links
     Google.
   - Settings → Sign-in methods: link Google, add a password, or remove a method (never the last one; removing signs
     out everywhere).
4. **Delete everything.**
   1. One transaction deletes the account's rows and records a pending login deletion.
   2. The Firebase user is deleted (3 attempts), then a confirmation email is sent.
   3. If either fails, the hourly run completes it; until then the login can't open a new account.
   4. `/security` and `/privacy` say exactly this.
5. **App Check.**
   - reCAPTCHA Enterprise in the web app; the API verifies the token on account creation, demo sessions,
     reset requests, imports and chat.
   - It starts in monitor mode; `APP_CHECK_ENFORCE` turns refusal on. The browser tests run enforced, with a debug
     token that production refuses to start with.
   - The CSP allows only what App Check needs.
6. **Enumeration.**
   - Login, sign-up and reset read the same for existing and unknown addresses (browser tests).
   - `docs/go-live.md` step 3a lists every required console setting, with a check for each.
7. **Sign out everywhere.**
   - Refresh tokens are revoked, and the revocation time is cached on the user row. Every request refuses older ID
     tokens, with no extra Firebase call (latency unchanged).
   - It also runs on password change and method removal. Telegram and demo sessions are untouched.
   - A 401 now signs out locally and returns the user to the page they were on after logging in.
8. **Recent login.** Export, delete, password, sign-in methods, address regeneration and Telegram unlink need an
   `auth_time` under 5 minutes (403 `reauth_required`). The app asks to sign in again (password or Google) and
   retries the request.
9. **UX.**
   - Activity labels for every event.
   - axe checks on every sign-in screen in both themes; the privacy page's links fixed.
10. **Verification:** results below.
11. **Engines and devices.**
    - The whole suite on Firefox, WebKit and iPhone WebKit as well as Chromium.
    - `devices.spec.js` on 9 profiles, with per-device screenshots on macOS and Linux.
    - CI runs all three engines.

## Results (local)

| Check | Result |
|---|---|
| Backend tests (also with UTC sessions, and with the machine's date a day behind India) | 364 passed |
| Frontend unit / lint / build | 217 passed / clean / OK (no test hooks in the production bundle) |
| Playwright, all 17 projects | 308 passed, 8 skipped, 0 failed |
| Bandit, Semgrep, pip-audit, npm audit gate, actionlint | clean |
| Secret check | clean |

### Per engine and device

| Project | Engine | Tests | Result |
|---|---|---|---|
| desktop (1280×800) | Chromium | 51 | pass |
| mobile (360×740) | Chromium | 51 | pass |
| reduced-motion | Chromium | 34 | pass |
| firefox (1280×800) | Firefox | 45 | pass (installable/service worker skipped: Playwright's Firefox) |
| webkit (1280×800) | WebKit | 45 | pass |
| webkit-iphone (iPhone 15 Pro) | WebKit | 45 | pass |
| iphone-se, iphone-15-pro, ipad-mini, ipad-mini-landscape, ipad-pro-11 | WebKit | 5 each | pass |
| pixel-7, galaxy-s24 | Chromium | 5 each | pass |
| laptop-1366, monitor-2560 | Chromium | 5 each | pass (the standalone check is for touch devices only) |

### Fixed because of the new engines and devices

- **Tap targets on iPads:** iPads had mouse-sized tap targets. The 44 px rules now apply to every touch screen.
- **`<select>` in WebKit:** native selects ignored padding and were 23 px tall. They're now drawn at 44 px.
- **iOS zoom:** inputs are 16 px on touch screens, so iOS no longer zooms when one is focused.
- **Phone menu:** on tall phones, the floating Ask button covered the menu's last items. It's now hidden while the
  menu is open.
- **Home indicator, notch and keyboard:**
  - fixed elements and bottom sheets clear the home indicator;
  - landscape notch insets are respected;
  - the installed app's header clears the status bar;
  - a focused field is scrolled into view once the keyboard opens.
- **Subscription banner:** at 320 px it crushed its text into one-word lines. It now stacks.
- **WebKit page error:** a cancelled background prefetch raised an unhandled rejection.
- **Sign out / exit demo:** these could land on `/login` instead of `/welcome`.
- **Time-dependent tests:** cash, sign-in time and revocation seconds.

## Console settings you must change by hand (`docs/go-live.md` step 3a)

1. Email enumeration protection: on.
2. One account per email address: on (the default).
3. Password policy: at least 10 characters, enforced. This needs Identity Platform; without it, the app and API
   still enforce 10 everywhere except a direct call to Firebase's API.
4. Authorized domains: add your domain.
5. App Check with reCAPTCHA Enterprise:
   1. Create the key.
   2. Register the web app.
   3. Set `VITE_RECAPTCHA_ENTERPRISE_SITE_KEY`.
   4. Watch a day in monitor mode.
   5. Set `APP_CHECK_ENFORCE=true`.
   6. Enforce for Authentication in Firebase.
6. Email templates: sender name "Vaulta" (optional).

## Not verified

- **Google popup:** the emulator's popup never reports back inside Playwright's browsers, so the Google tests sign in
  with a Google credential (`signInWithCredential`) through a hook that only exists in the e2e build. The linking
  behaviour is the same; the popup window itself isn't exercised. The same goes for "Link Google" in Settings and the
  account-exists-with-different-credential path, which the emulator can't produce.
- **App Check against real reCAPTCHA Enterprise** (needs the console setup).
- **Firebase's password policy** (Identity Platform).
- **Firefox with the PWA service worker** (blocked in its project, because of Playwright's patched Firefox).
- **Real phones:** on-screen keyboards, notches and the installed-app mode can't be emulated. The code is in place
  and unit-tested where possible.
- **The confirmation email** after deletion (Resend not configured locally; the code path is tested with a fake).
