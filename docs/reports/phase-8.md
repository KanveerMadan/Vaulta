# Phase 8 report: guided tour, getting-started checklist, samples and simulations

Branch `rebuild/phase8`, built on `rebuild/phase9`. That is the brief's first choice: Phase 9's report says it
finished, with CI green. Pushed; PR #1 updated and still marked DO NOT MERGE.

## What each step did

1. **Guided tour** (`components/GuidedTour.jsx`, `lib/tour.js`, `GET/PATCH /api/tour`).
   - **Content:** 7 steps on the home page, written for the user's own numbers (safe to spend, open questions,
     transactions), with wording for what will appear when there's no data yet.
   - **Where it runs:** its place is kept on the server, so it resumes on any device. It starts by itself once setup
     is finished; the "?" button in the header and Settings replay it.
   - **Layout:**
     - Desktop: a card next to a spotlit element with an accent outline, visible in dark mode too.
     - Phones: a bottom sheet.
     - It is rendered in a portal, so no ancestor's transform can shift it.
   - **Keyboard and motion:** arrows move, Escape skips, focus stays in the card. With reduced motion there's no
     smooth scrolling or transitions. Not in the demo.
2. **Getting-started checklist** (`components/GettingStarted.jsx`, `GET/PATCH /api/checklist`).
   - **Items:** 10, ticked from what the user actually did, worked out on the server: verified email, statement
     import, forwarded alert, Telegram, cash expense, budget, review queue opened, a question asked, a category
     changed, a report opened.
   - **Links:** each undone item links to where it's done (`/connect?do=import`, `#forwarding`, `#telegram`,
     `/?ask=1` opens chat).
   - The progress ring is the coverage meter's. It can be hidden on the home page and restored in Settings. Not in the
     demo.
3. **Preview layer** (`core/samples.py`).
   - **Schema:** `is_sample` and `simulation_id` (migration `b7c3d5e9f0a2`).
   - **One central rule:** every ORM select of transactions or their source records excludes samples unless it asks
     for them. Only the transactions list (labelled "Sample") and clearing ask.
   - **Never mixed with real data:** samples never merge with real rows in either direction, can't be edited and
     never count in model metrics.
   - **Clean-up:** deleted an hour after they were made (on read and by the hourly run), or at once with
     "Clear samples".
   - **Guard test:** with three months of real data, every service gives identical answers after adding ten sample
     rows of every kind and re-running detection. That covers analytics in every grouping, budgets, forecast, outlook,
     safe-to-spend, recurring, upcoming, people, goals, cash, coverage, review cards, the monthly report, the
     checklist, the model's memory, re-categorisation, export, anomalies, alerts, every read-only chat tool, and each
     transaction's detected state.
4. **Simulations** (`/try`; `POST /api/simulations/bank-alert`, `POST /api/simulations/quick-add`).
   - **Bank alert:** a sample alert in four banks' formats goes through the real sender check and parse
     (`inbound.read_alert`, which forwarded emails now use too) and the import pipeline, as a sample.
   - **Statement:** a made-up HDFC statement is read and masked on the device, with "This is a sample. Nothing is
     imported." and no Import button. A test checks nothing is sent.
   - **Quick add / Telegram:** "150 auto cash" shows the bot's reply, and can be saved as a sample.
   - **Calls to action** link to the real thing.
   - **The demo** runs all three and nothing is written.
   - **Limits:** rate-limited per user, or per visitor in the shared demo.
5. **Devices and engines.** Snapshots of the tour, checklist and `/try` on all 9 device profiles and in
   light/dark at desktop, 360 px and reduced motion, on macOS and Linux. The full matrix was rerun on Chromium,
   Firefox and WebKit (Phase 6.5 had already built it).
6. **Verification:** below.

## Fixed along the way

- **Floating Ask button** covered a page's last button on phones. Content now leaves room below.
- **Home page layout shift:** the free-tier banner pushed the page down as it arrived (CLS 0.07 in Phase 7, and up
  to 0.099 with this phase's extra requests). It now appears with the page's data, and the checklist and sample
  count come with `/api/home`. CLS is 0.
- **Tour step with no data:** "questions here" always showed its no-data wording (`attention` is an object), fixed
  before release.
- **Onboarding restarted:** the tour and checklist share `users.onboarding`, and writing them made an account with
  old data count as "setup started". There's a regression test.
- **WebKit errors when leaving a page:** WebKit reported cut-off downloads and API calls as errors from the page
  being left.
  - The API client now cancels its in-flight requests on `pagehide`.
  - e2e sign-in waits for the landing page to render.
- **Snapshots broke when the day changed:** the masks for dates and the forecast took the size of their content, so
  they moved the next day. Their size is now pinned before comparing.

## Results

| Check | Result |
|---|---|
| Backend tests | 403 passed |
| Frontend unit / lint / build | 224 passed / clean / OK |
| Playwright, all 18 projects (macOS): Chromium, Firefox, WebKit, iPhone WebKit and 9 device profiles | 364 passed, 8 skipped, 0 failed |
| Visual and device snapshots on Linux (Docker) | 76 passed |
| Lighthouse (5 cold runs, mobile profile) | Landing 100/100/100, CLS 0 · Home 99–100/100/100, LCP 1.9–2.1 s, CLS 0 |
| New third-party requests | none: no CSP or origin change, and the e2e guard fails on any unexpected origin |
| Bandit, Semgrep, pip-audit, npm audit gate, actionlint | clean |
| Secret check | clean |

## Steps you need to do

- Production migration `b7c3d5e9f0a2` (head after Phase 8), together with Phase 9's.
- Nothing else is new: no new environment variables or console settings.

## Not verified

- **Real phones:** the tour's bottom sheet and the try-it page were checked in emulated phones on three engines,
  not on hardware.
- **Sample alert formats:** they're the formats the inbound tests use, not live emails from the banks.
