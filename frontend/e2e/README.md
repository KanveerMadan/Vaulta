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
