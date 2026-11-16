# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Vault is a daily-bar, single-asset, long-only strategy backtester: a Django REST API + Postgres-backed worker (`backend/`) and a React/Vite UI (`frontend/`). README.md is the authoritative spec for the execution model, metrics, limits, security posture and deploy; keep it in sync when behaviour changes.

## Commands

Full stack (Postgres 16, API with migrations, one worker, frontend on :5173, API on :8000):
```bash
docker compose up --build
```

Backend (Python 3.12, run from `backend/`):
```bash
pip install -r requirements.txt
DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test                                # full suite
DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test backtester.tests.TimingTests   # one class
DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test backtester.tests.LedgerTests.<method>  # one test
python manage.py makemigrations --check --dry-run   # CI fails on migration drift
python manage.py runserver                          # API (dev)
python manage.py run_worker                         # queue consumer, separate process
```
Local non-Docker dev also needs `ALLOW_CUSTOM_CODE=1` to create custom strategies.

The strategy sandbox (`sandbox_runner.py`) uses `resource` rlimits and `preexec_fn`, which are POSIX-only. On Windows, sandbox/end-to-end tests won't run natively; run them in a Linux container. Use a throwaway Postgres: the compose `pgdata` volume may hold an old v1 TimescaleDB database that `postgres:16` can't start.
```bash
docker network create vault-test
docker run -d --name vault-testdb --network vault-test -e POSTGRES_PASSWORD=ci postgres:16
MSYS_NO_PATHCONV=1 docker run --rm --network vault-test -v "$PWD/backend:/app" -w /app \
  -e DEBUG=1 -e DATABASE_URL=postgres://postgres:ci@vault-testdb:5432/postgres -e DB_SSLMODE=disable \
  python:3.12-slim sh -c "pip install -q -r requirements.txt && python manage.py test"
```

Frontend (from `frontend/`): `npm ci`, `npm run dev` (proxies `/api` to `VITE_PROXY_TARGET`, default `http://localhost:8000`), `npm run lint`, `npm run build`. The SPA always calls the relative path `/api`.

CI (`.github/workflows/ci.yml`) runs tests on Postgres 16, the migration-drift check, a check that `DEBUG=0` refuses to start without `SECRET_KEY`, `pip-audit`, frontend lint/build, `npm audit`, and both Docker builds.

## Architecture

Two processes from one image, one Postgres database. No Redis/Kafka/Celery by design (see README "Design decisions"; don't reintroduce them).

- **The `BacktestRun` row is the job.** `views.py` validates, throttles, enforces admission limits (`MAX_ACTIVE_RUNS` → 503) and inserts a `queued` row. It never runs backtests, fetches data, or spawns threads/subprocesses in the request path. `Idempotency-Key` on POSTs returns the original job.
- **`jobs.py`** is the queue: `claim` via `SELECT … FOR UPDATE SKIP LOCKED`, states `queued → preparing_data → running → completed|failed` (`failure_category` = `data` / `strategy` / `infrastructure`). All updates go through `_update`, which is conditional on `worker_id` and an active status, so a worker that lost ownership can't write. Finalisation deletes and re-inserts trades plus results in one transaction (retries replace, never append). `recover_stale` requeues runs with no heartbeat for `STALE_AFTER_S`, up to `MAX_ATTEMPTS`. Strategy errors are never retried.
- **`engine.py`** is pure: no Django, no I/O. Bars in, ledger out. `Decimal` for money. Core invariants the tests enforce: decisions on bar *t* fill at the open of *t+1*; stop wins if stop and target are touched in one bar; `equity = cash + qty × close` at every bar; all metrics derive from the one equity curve. Bump `ENGINE_VERSION` when simulation semantics change (it is stored on every run).
- **`sandbox_runner.py`** runs user `on_bar(bar, indicators, state)` in a child process speaking newline-delimited JSON over stdin/stdout. It has an AST filter (only `import math`, no `_private`/dunder names), rlimits and a wall-clock deadline. **It is not a security boundary.** `ALLOW_CUSTOM_CODE` stays off by default; public deploys run only `is_builtin` strategies (seeded by migration `0010`).
- **`data_fetch.py`** loads bars from the DB and fetches from Yahoo (`yfinance`, adjusted daily) only in the worker, when the span isn't in `SymbolCoverage`. A fetch re-downloads the symbol's whole known span and replaces its bars, because adjusted prices get restated after splits and dividends. Never mix rows fetched at different times. It validates OHLC, records `data_manifest` (hash + warnings) and supplies up to 50 warm-up bars the strategy never sees.
- **Optimizations:** the grid (≤ `MAX_GRID`) runs on the first 70% (in-sample). `finish_optimization` then queues exactly one out-of-sample run for the best Sharpe (a unique constraint guards against duplicates). Job status is derived from the child runs by `optimization_status`, never stored.
- **`vault_core/settings.py`**: all config comes from env. Production (`DEBUG` unset) raises `ImproperlyConfigured` without `SECRET_KEY`, `ALLOWED_HOSTS` and DB credentials. Limits live in `settings.VAULT`. `gunicorn.conf.py` can start an in-process consumer thread when `EMBEDDED_WORKER=1`. `start.sh` runs migrations only if `RUN_MIGRATIONS=1`.
- **Accounts (`backend/accounts/`):** custom `User` (email login; `tier` = guest/unverified/verified drives `quotas.py`). Session-cookie auth with the API on the same origin (Vercel rewrite, Vite proxy, nginx), so there's no CORS. Auth views enforce CSRF even for anonymous requests (`CsrfEnforced`). Every backtester queryset is filtered by `owner=request.user` (built-ins are visible to all); another user's object must 404. `IdempotentCreate` locks the user row with `select_for_update` so quota checks and per-user idempotency keys don't race. `housekeeping.run()` (called hourly by the worker loop) deletes expired guests and sessions. Account tests use `FAST_HASHERS` (MD5) and `BrowserClient`, which echoes the current `csrftoken` the way axios does.
- **Frontend:** `src/auth.jsx` (AuthProvider, RequireAuth, GuestOnly) mirrors `/api/auth/me/`; a 403 "Authentication credentials…" response signs the user out in the UI. `src/api.js` holds the axios client, `errorText` (DRF error → readable text) and `usePoll` (polls until status is in `TERMINAL`). Pages are in `src/pages/`. Deployed on Vercel; the backend is on Render.

Migrations `0009`–`0011` upgrade v1 databases in place and aren't reversible without data loss.
