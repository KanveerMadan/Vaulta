# Browser tests (Playwright)

Every flow runs twice: desktop (1280×800) and phone (360×740, touch). A test fails on any console
error, any request that uploads a file or carries statement file content, and any request to an
origin other than the app, the API or Firebase Auth. On the phone viewport, key screens are also
checked for sideways scrolling and for tap targets smaller than 44 px.

What runs (all local, started by `playwright.config.js`):

| Server | Port | What |
|---|---|---|
| Firebase Auth emulator | 9099 | real Firebase sign-in flow, no Google project (`e2e/firebase.json`) |
| fake LLM | 8002 | `servers/fake_llm.py`, OpenAI-format answers so chat is deterministic |
| API | 8001 | `servers/backend.py`: drops and recreates the test database, runs `alembic upgrade head`, starts uvicorn with test settings |
| app | 4173 | `vite build --mode e2e` (`.env.e2e`) served by `vite preview`, service worker included |

Needs: a local Postgres the tests may wipe (default `postgresql://vaulta@localhost:54329/vaulta_e2e`;
non-local URLs are refused), Node, and a Python with the backend requirements.

```sh
cd frontend
npx playwright install chromium            # once
E2E_PYTHON=../backend/venv/bin/python \
E2E_DATABASE_URL=postgresql://vaulta@localhost:54329/vaulta_e2e \
npm run test:e2e
```

`E2E_REUSE=1` reuses servers you already started; `E2E_WORKERS` sets parallelism (default 3).
Each test signs up its own user in the emulator and seeds data through the real API, so tests are
independent of each other and of order.

**Security headers.** `vite preview` serves the headers from `vercel.json` (with the local API, emulator and auth
domain swapped in), so every test runs under the production Content-Security-Policy; a CSP violation is a console
error, which fails the test.

**Visual baselines per OS.** `visual.spec.js` keeps one set of screenshots per operating system of the browser
(`…-darwin.png`, `…-linux.png`; CI runs Linux). To render the Linux set from a Mac, run the browser in Playwright's
Linux image and point the tests at it:

```sh
docker run -d --name pw-server -p 3000:3000 --init --ipc=host mcr.microsoft.com/playwright:v1.56.1-noble \
  /bin/sh -c "npx -y playwright@1.56.1 run-server --port 3000 --host 0.0.0.0"
PW_WS_ENDPOINT=ws://127.0.0.1:3000/ PW_BROWSER_OS=linux npx playwright test e2e/visual.spec.js --update-snapshots
docker rm -f pw-server
```

**Engines and devices** (`playwright.config.js`):

| Project | What runs | Engine |
|---|---|---|
| `desktop`, `mobile` (360 px), `reduced-motion` | the whole suite, plus `visual.spec.js` | Chromium |
| `firefox` | the whole suite (service workers blocked: Playwright's Firefox closes a page that reloads under one) | Firefox |
| `webkit`, `webkit-iphone` (iPhone 15 Pro) | the whole suite | WebKit |
| `iphone-se`, `iphone-15-pro`, `ipad-mini`, `ipad-mini-landscape`, `ipad-pro-11` | `devices.spec.js` | WebKit |
| `pixel-7`, `galaxy-s24`, `laptop-1366`, `monitor-2560` | `devices.spec.js` | Chromium |

`devices.spec.js` covers each device in turn:
- landing, home, transactions, import preview, chat and Money Wrapped, each with a screenshot;
- no sideways scrolling and 44 px tap targets on touch devices;
- the landing page with WebGL unavailable;
- the sticky header while scrolling;
- a focused field staying in view;
- what the installed (standalone) app relies on.

Install the engines once with `npx playwright install chromium firefox webkit`, then run one project with
`--project=<name>`.

Real iOS keyboards, notches and installed-app mode can't be emulated. `src/lib/keyboard.js` (unit-tested) and the
safe-area CSS in `src/index.css` handle them, but they still need checking on a real device.
