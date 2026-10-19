# Vaulta design (Phase 7)

- [directions.md](directions.md): three directions explored (Ledger, Monsoon Night, Paper Cut), and why **Ledger** was chosen.
- [performance.md](performance.md): Lighthouse, accessibility checks and bundle sizes, before and after.
- `captures/`: screen recordings (Playwright video) of the showpieces:
  - `landing-scroll-story.webm`, `landing-scroll-story-phone.webm`: the statement taken apart on the device, then the live product
  - `onboarding.webm`: basics, connect, an import with the "removed on this device" preview, first review, finish
  - `money-wrapped.webm`: the annual story and the share card's privacy toggles

## The system

| | Where |
|---|---|
| Tokens: colour (light and dark), elevation, radii, motion | `frontend/src/styles/tokens.css` (contrast unit-tested) |
| Tailwind mapping of the tokens | `frontend/tailwind.config.js` |
| Type | Bricolage Grotesque (display, optical sizes), Geist (UI, tabular figures), Geist Mono, all self-hosted |
| Money | `src/ui/Money.jsx` and `src/lib/money.js`: ₹1,20,000 grouping, sign plus spoken words, tween only on change |
| Core components | `src/ui/`: Sheet, Toast, Meter, BarChart, Field, Empty, Skeleton, ThemeSwitch, Wordmark |
| Shell | `src/components/Layout.jsx`: sidebar on desktop, menu on phones, chat column from 1280 px, ⌘K palette |

**Motion.**
- **Workspace:** CSS only, 120–260 ms, ease-out.
- **Showpieces:** landing story, onboarding and Money Wrapped use Motion, loaded only on those routes.
- **Reduced motion:** every animation has a designed still version.

**Shapes.**
| Element | Radius |
|---|---|
| Buttons, inputs, chips | 8 px |
| Cards | 12 px |
| Sheets and dialogs | 18 px |
| Pills | full |

**Tests and tools.**
- **Visual snapshots:** `frontend/e2e/visual.spec.js` (light and dark; desktop, 360 px and reduced motion).
- **Accessibility:** `e2e/a11y.spec.js` (axe).
- **Lighthouse:** `e2e/lighthouse.mjs`.
- **Recordings:** `e2e/captures.mjs` re-records the captures.
