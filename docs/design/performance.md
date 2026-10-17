# Performance and accessibility (Phase 7)

## Lighthouse

Lighthouse 13.5, mobile profile (simulated slow 4G, mid-range phone CPU), production build served
locally, **cold load**: the service worker and its caches are cleared before each run, and only the
sign-in is kept. Reproduce with `node e2e/lighthouse.mjs` while the browser-test servers are running.
Raw numbers: [lighthouse.json](lighthouse.json).

| Page | Performance | Accessibility | Best practices | LCP | CLS | TBT |
|---|---|---|---|---|---|---|
| Landing (`/welcome`) | 100 | 100 | 100 | 1.3 s | 0 | 0 ms |
| Home (`/`, signed in) | 98 | 100 | 100 | 2.0 s | 0.07 | 0 ms |

**Phase 8** (tour, checklist, samples), five cold runs ([lighthouse-phase8.json](lighthouse-phase8.json) is the last):

| Page | Performance | Accessibility | Best practices | LCP | CLS | TBT |
|---|---|---|---|---|---|---|
| Landing (`/welcome`) | 100 in all five | 100 | 100 | 1.3–1.4 s | 0 | 10–40 ms |
| Home (`/`, signed in) | 99–100 | 100 | 100 | 1.9–2.1 s | 0 | 10–90 ms |

- **Home CLS** went from 0.07 to 0. The free-tier banner, fetched on its own, used to push the page down
  as it arrived. A first Phase 8 build made that worse (CLS 0.099 in three runs of five).
- **The fix:**
  - The banner and the month header now appear together with the page's data.
  - The checklist and the sample count come with `/api/home` instead of separate requests.

What it took to get there (the first cold run scored 96 and 94, with LCP 2.7 s and 2.9 s):
- **Main bundle:** the landing shell moved into the main bundle, and its animated parts load after the headline paints.
- **Shell prefetch:** the app shell and home download while Firebase restores the session.
- **Service worker:** registration no longer blocks rendering.
- **Google script:** Firebase Auth no longer loads `apis.google.com` on every visit. Google's sign-in helper loads only when someone clicks *Sign in with Google*.

## Accessibility

- **axe-core** (WCAG 2.0, 2.1 and 2.2, A and AA rule sets) runs in `e2e/a11y.spec.js`. It covers:
  - every public page and every workspace page;
  - onboarding and Money Wrapped (including the share card);
  - both themes, at desktop and 360 px;
  - zero violations.
- **Theme contrast:** every text-colour pair in the token file is unit-tested at ≥ 4.5:1 in both themes (`src/styles/tokens.test.js`).
- **Built in:**
  - **Money:** every amount has screen-reader words ("₹1,200 received").
  - **Charts:** a table view is available.
  - **Navigation:** a skip link, one visible focus style, keyboard shortcuts with on-screen hints, and designed reduced-motion versions of every animation.

## Bundles (gzip)

Before: [bundle-before.txt](bundle-before.txt). After: [bundle-after.txt](bundle-after.txt).

| | Before | After |
|---|---|---|
| Entry chunk (everything not split) | 180.6 KB | 80.6 KB |
| CSS | 7.0 KB | 11.3 KB |
| First paint of the landing | 180.6 KB JS | 80.6 KB JS (story and scenes follow: 5.8 + 4.9 KB, plus Motion 39.9 KB) |
| Home, signed in | 180.6 KB JS | 80.6 + Firebase 43.8 + shell 21.3 + home 11.7 + API client 16.8 KB |
| Motion (animation library) | none | 39.9 KB, only on the landing, onboarding and Money Wrapped; a browser test checks the workspace never requests it |

Total JavaScript across all chunks grew (446 to 579 KB). Most of that is new features and per-route
chunking: Motion, the virtualised list, icons, the landing story, Wrapped. Every route now loads less
than the single entry chunk did before. The statement parsers (PDF 97 KB, Excel 161 KB) are loaded
only when a statement is imported, as before.
