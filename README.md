# Vault: a strategy backtester you can check

Vault runs a trading strategy against historical daily market data and reports results that you can reconcile by hand. You write `on_bar(bar, indicators, state)` returning `BUY`, `SELL` or `HOLD`. Vault replays the history one bar at a time with a documented fill model, and it records enough metadata (code hash, data hash, engine version) to reproduce each run.

**Live demo:** [vault-lovat-beta.vercel.app](https://vault-lovat-beta.vercel.app). The public demo runs **built-in strategies only**. See [Security](#security) for the reason.

---

## Contents

- [Architecture](#architecture)
- [Execution model](#execution-model)
- [Accounting and metrics](#accounting-and-metrics)
- [Market data](#market-data)
- [Jobs, limits and failure behaviour](#jobs-limits-and-failure-behaviour)
- [Optimization and out-of-sample evaluation](#optimization-and-out-of-sample-evaluation)
- [Security](#security)
- [Run locally](#run-locally)
- [Tests](#tests)
- [Deploy (Vercel + Render)](#deploy-vercel--render)
- [Runbook](#runbook)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)

---

## Architecture

```
Browser ──▶ React/Vite (Vercel)
               │ HTTPS, JSON
               ▼
         Django REST API (gunicorn, stateless) ──▶ PostgreSQL
               │  validate, throttle, admit,          ▲  strategies, runs (= the job queue),
               │  insert a 'queued' run row           │  trades, bars, results
               ▼                                      │
         Worker process(es): python manage.py run_worker
               │  claim with SELECT … FOR UPDATE SKIP LOCKED,
               │  load and validate bars (fetch from Yahoo when coverage is incomplete),
               │  run the deterministic engine, then commit trades and results in one transaction
               ▼
         Strategy subprocess (one per run): rlimits, empty environment, wall-clock deadline
```

The system has two services: an API and a worker. Both are built from the same image and talk to one PostgreSQL database. There is no Kafka, no Redis and no TimescaleDB ([why](#design-decisions)).

## Execution model

The rules below are implemented in `backend/backtester/engine.py`, and the tests in `backend/backtester/tests.py` check them.

| Rule | Behaviour |
|---|---|
| Signal time | The strategy sees bar *t*, including its close. SMA-10 and SMA-50 are computed from closes up to and including bar *t*. |
| Fill time | A decision made on bar *t* fills at the **open of bar *t+1***. A decision on the last bar never fills. |
| Stops / targets | These are checked against each bar's high and low while a position is open. If the bar opens past the level (a gap), the fill is at the open. If the level is touched during the bar, the fill is at the level. **If both levels are touched in one bar, Vault assumes the stop filled** (the conservative choice). |
| Position | Long only, one position at a time. Fractional shares are rounded down to 1e-6. |
| Sizing | `qty = cash × max_position_pct / (fill_price × (1 + commission))`. The commission is part of the budget, so cash never goes negative. |
| Costs | Slippage moves the fill price against you. Commission is charged on each fill's notional. Each is charged exactly once. |
| End of run | An open position is **marked to market** at the last close. It is not liquidated. |
| Warm-up | Up to 50 bars before `start_date` feed the indicators. The strategy never sees those bars. |

## Accounting and metrics

- Money uses `Decimal` throughout the engine. Ratios use floats.
- The invariant `equity_t = cash_t + quantity_t × close_t` holds at every bar, and a test checks it.
- **Every metric comes from that one ledger equity curve.** Nothing recomputes cash anywhere else.
- **CAGR** uses the actual first and last simulated bar dates, not the requested dates. It is `null` if the result is undefined.
- **Sharpe** uses daily equity returns with a risk-free rate of 0, annualised with √252. It is `null` when volatility is zero.
- **Max drawdown** is measured peak to trough on equity.
- **Win rate** is calculated per round trip, **net of commission and slippage**. It is `null` when no round trip has closed.
- **Buy & hold** is a gross benchmark: first open to last close over the same bars.
- A completed run with no trades still produces a valid flat equity curve and metrics.

## Market data

Data comes from Yahoo Finance via `yfinance`. Prices are adjusted (`auto_adjust=True`) daily bars, and each bar is stored at midnight UTC of its trading date.

- Symbols are normalised to upper case before any read or write.
- **Coverage is checked properly.** A range counts as covered only if the stored bars reach both ends (within 5 days) and contain no gap longer than 5 days. Otherwise Vault fetches the whole range from Yahoo. Yahoo's `end` parameter is exclusive, so Vault requests `end + 1 day`.
- The fetch is idempotent. A `UNIQUE (symbol, ts)` constraint means concurrent fetches cannot create duplicate bars.
- Rows with non-finite or non-positive prices are rejected, as are rows where `low > min(open, close)` or `high < max(open, close)`.
- Partial data is allowed but **labelled**: the run's `data_manifest.warnings` lists late starts, early ends, gaps, rejected rows and missing warm-up. If no bars are found, the run **fails** with category `data`.
- Each run records `data_manifest`: provider, adjustment, first and last bar, bar count, and a SHA-256 of the bars used.
- The fetch happens in the worker, never inside an HTTP request.

Scope: Vault handles daily bars for single Yahoo tickers. It does not model corporate actions beyond Yahoo's adjustment, it has no intraday data, and it does not handle multiple assets per strategy.

## Jobs, limits and failure behaviour

**Run states:** `queued → preparing_data → running → completed`. Any active state can move to `failed`, which carries a `failure_category` of `data`, `strategy` or `infrastructure`.

- **Durable.** The run row is the job. If the API or the worker restarts, the job is not lost.
- **At-least-once execution with idempotent finalisation.** Trades and results are written in one transaction, and only if the worker still owns the run (`status = running AND worker_id = me`). A retry replaces earlier trades instead of adding to them.
- **Stale-job recovery.** Workers update a heartbeat every 50 bars. A run with no heartbeat for `STALE_AFTER_S` (120 s) goes back to `queued`, up to `MAX_ATTEMPTS` (3) attempts in total, and then fails as `infrastructure`.
- **Strategy errors are not retried.** An exception, a bad return value or a timeout fails the run immediately with a safe message.
- **Bounded concurrency.** Each worker process runs one job at a time. To scale, run more worker processes. The API never starts threads or subprocesses.
- **Progress** is stored on the run row (`bars_processed / bars_total`). The UI shows "progress not available" rather than a fake 0%.

| Limit | Default | Scope |
|---|---|---|
| `MAX_ACTIVE_RUNS` | 50 queued+running | global (soft cap). The API returns `503` when it is reached |
| `MAX_GRID` | 25 combinations | per optimization, checked server-side |
| up to 10 values | per stop-loss / take-profit list | per request |
| `MAX_RANGE_DAYS` | 3660 | per request |
| `MAX_CODE_CHARS` | 10 000 | per strategy |
| `RUN_TIMEOUT_S` / `RUN_CPU_S` / `RUN_MEMORY_MB` | 60 / 30 / 256 | per strategy process |
| request body | 64 KB | per request |
| `THROTTLE_JOBS` / `THROTTLE_WRITE` / `THROTTLE_READ` | 10 / 30 / 300 per min | **per IP, per API process** (in-memory cache) |
| `Idempotency-Key` header | optional | repeating a `POST /runs/` or `/optimizations/` with the same key returns the original job |

## Optimization and out-of-sample evaluation

Picking the best parameters on the same data you then report on overstates performance. Vault therefore splits each optimization by time:

1. The date range is split chronologically. The first 70% is **in-sample** and the last 30% is **out-of-sample** (`OOS_FRACTION`).
2. Every stop-loss × take-profit combination runs on the in-sample period only.
3. When all in-sample runs are finished, the best one by Sharpe is queued **once** on the out-of-sample period. A unique constraint guarantees exactly one such run.
4. Job status is derived from the child runs and never stored: `running`, `completed`, `partially_completed` (some children failed, or the out-of-sample run failed) or `failed` (no child completed).

The UI labels in-sample results as optimised and shows the out-of-sample result separately, next to buy & hold. A high in-sample Sharpe is not evidence of an edge.

## Security

**The strategy subprocess is not a security boundary.** It runs with an AST filter (only `import math`, no `_private` attributes and no dunder names), reduced builtins, an empty environment, `cwd=/`, rlimits (CPU, address space, no forking, no file writes, no core dumps), a hard wall-clock deadline that kills the whole process group, a 4 KB limit on each output line, and strict validation of every output. That contains accidents such as infinite loops, memory blow-ups, crashes and garbage output. **It does not contain hostile Python.** It has no network or filesystem namespace, and Python introspection is broad.

For that reason:

- `ALLOW_CUSTOM_CODE` is **off by default**. With it off, `POST /api/strategies/` returns `403` and only `is_builtin` strategies can run. The built-in strategies are seeded by migration `0010`.
- Docker Compose turns it **on for local use only**.
- Before enabling it on a public deployment, move strategy execution to a separate isolated runner: a container or VM with no network, a read-only root filesystem, a non-root user, dropped capabilities, CPU, memory and PID limits, no Docker socket, and no database or application secrets. The worker would send it only the code and the bars. This runner is **not built yet**.

Other security controls:

- Production refuses to start without `SECRET_KEY` and database credentials. `DEBUG` is off unless `DEBUG=1`.
- `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` are explicit allowlists.
- The API serves JSON only. It has no admin, sessions or cookies, so CSRF is not applicable. Errors return safe messages, and details go to the server logs.
- The Docker image runs as a non-root user.
- CI runs `pip-audit` and `npm audit`.

## Run locally

Prerequisite: Docker.

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000/api/strategies/
- Health: http://localhost:8000/health/ready

Compose starts Postgres 16, the API (which applies migrations on start), one worker and the frontend. Bars are fetched on first use; no ingest step is needed.

Without Docker (Python 3.12):

```bash
cd backend
pip install -r requirements.txt
export DEBUG=1 DATABASE_URL=sqlite:///db.sqlite3 ALLOW_CUSTOM_CODE=1
python manage.py migrate
python manage.py runserver &          # API
python manage.py run_worker           # worker, in another shell
```

## Tests

```bash
cd backend
DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test
```

CI also runs the suite on PostgreSQL 16, along with a migration-drift check, `pip-audit`, frontend lint and build, `npm audit` and both Docker builds. The suite covers:

- a hand-calculated buy/sell with commission and slippage
- the equity = cash + holdings invariant
- sizing that never overspends, and a win rate that is net of costs
- a no-trade run
- next-bar fills (regression test for same-bar lookahead), last-bar signals and warm-up being hidden from the strategy
- a stop and a target touched in the same bar, a gap through a stop, and an intrabar target
- sandbox cases: infinite loop, invalid output, exception, blocked imports and dunders, no `open`, huge output
- data cases: one stored bar not counting as coverage, gap labelling, invalid OHLC rejected, no data
- API cases: custom code disabled, end-to-end run, a retry that does not duplicate trades, idempotency key, queue full (503), grid limit
- stale-job requeue and then fail
- partial optimization failure with exactly one out-of-sample run
- health endpoints

## Deploy (Vercel + Render)

Flow: push to GitHub, CI runs, and Vercel and Render auto-deploy from `main`. Turn on Render's "auto-deploy after CI checks pass" so a red build does not ship.

**Frontend (Vercel):** root `frontend/`, build `npm run build`, output `dist/`. Set `VITE_API_URL=https://<render-api-host>/api`. This value is public configuration, not a secret.

**API (Render web service, Docker, root `backend/`):**

| Setting | Value |
|---|---|
| Start command | default image `CMD` (`./start.sh`, which runs gunicorn) |
| Pre-deploy command | `python manage.py migrate --noinput` (if your plan has it). Otherwise set `RUN_MIGRATIONS=1` on a **single-instance** service |
| Health check path | `/health/ready` |
| Env | `SECRET_KEY` (generate), `DATABASE_URL` (from Render Postgres), `ALLOWED_HOSTS=<api-host>`, `CORS_ALLOWED_ORIGINS=https://<vercel-domain>`, `SECURE_PROXY_SSL_HEADER=1`, `DB_SSLMODE=require` |
| Optional | `SECURE_HSTS_SECONDS=31536000` once HTTPS is verified, `WEB_CONCURRENCY`, and the limits listed above |

**Worker (Render background worker, same repo and image):** command `python manage.py run_worker`, with the same env as the API minus the HTTP-only settings.

**No budget for a separate worker?** Set `EMBEDDED_WORKER=1` on the web service. Each gunicorn process then starts one queue-consumer thread. Jobs stay durable because the queue is in Postgres, but backtests then compete with HTTP traffic for CPU. On a free plan that sleeps when idle, queued jobs wait until the service wakes, and interrupted jobs are recovered as stale.

**Database:** standard managed PostgreSQL. Migrations `0009`–`0011` upgrade an existing v1 database in place:

- builtin strategies are seeded
- links from old optimizations to their runs are kept
- each old run gets a code snapshot
- `pending` runs are re-queued
- `running` runs are marked failed

**Back up the database before the first v2 deploy.**

Rollback: redeploy the previous image from Render's deploy history. Migrations 0009–0011 are not reversible without data loss, so restore from the backup if you need to go back to v1 code.

## Runbook

**Render alert "Exited with status 1" (incident 2026-10-15).** The root cause has **not** been established. The email shows only that the process exited. Before you change anything:

1. In Render, open the service, then **Logs**. Find the first traceback before the exit, not the exit line itself. Then check **Events/Deploys** for the same time window to see whether a deploy, restart or health-check failure preceded the exit.
2. Record the deployed commit, the start command, and whether the exit happens at startup or on a request.
3. Preserve the logs before you redeploy.

Plausible causes in the v1 code, to confirm or rule out against the logs. None of these is a conclusion.

- The v1 start command was `migrate && runserver`. Any migration or DB-connection failure at boot exits with status 1, and `runserver` is a development server.
- The v1 `requirements.txt` was UTF-16 with NUL bytes, which breaks a clean `pip install` (a build failure).
- The optimizer started one thread and one subprocess per grid cell with no limit, which can exhaust memory or CPU. Confirm with memory events; do not infer it from exit code 1 alone.

What v2 changes for this class of failure:

- gunicorn instead of `runserver`
- migrations moved out of the start path
- missing `SECRET_KEY` or database settings fail fast with a clear `ImproperlyConfigured` message
- no threads or subprocesses inside the web process (unless `EMBEDDED_WORKER=1`)
- bounded work per request
- `/health/ready` reports database state

After deploy, watch Logs and Events for the same signature over several hours before calling it fixed.

**Other procedures:**

- *A job looks stuck:* check `status`, `heartbeat_at`, `attempts` and `worker_id` on the run. Recovery runs every 30 s in each worker. If no worker is running, jobs stay `queued`.
- *Queue full (503):* there are more than `MAX_ACTIVE_RUNS` active runs. Add a worker or raise the limit.
- *Database down:* `/health/ready` returns 503. API calls return a safe 500 or 503 without a stack trace. Workers log the error and keep polling.
- *Yahoo down:* runs over data that is already stored still work. Runs that need new data fail with category `data` and the message "No market data".

## Design decisions

- **Kafka removed.** Replaying a finite, ordered history needs an ordered query, not a broker. Kafka never prevented lookahead: v1 filled at the same close the strategy had just seen. Lookahead is prevented by the fill model in the engine. Kafka added one topic per run, broker startup dependencies, a 15 s consumer timeout that could pass off a truncated stream as complete, and a paid service in production.
- **Redis removed.** v1 used Redis for an indicator cache keyed without a data revision (so it could go stale) and for progress values whose failures were silently ignored. SMAs are now computed during the replay, which is trivial work, and progress lives on the run row.
- **Postgres as the queue instead of Celery + Redis.** `SELECT … FOR UPDATE SKIP LOCKED` gives a durable queue with no extra infrastructure. This is enough at portfolio scale. Move to Celery or a dedicated queue if queue throughput becomes the bottleneck, which it is not at one job per worker.
- **TimescaleDB dropped.** The v1 README told users to manually drop the `bar` primary key, which made the schema diverge from the migrations. A few thousand daily bars per symbol do not need hypertables.
- **Built-in-only public demo.** Exposing an unsafe code runner would be worse than having none.

## Known limitations

- There is no isolated strategy runner yet, so custom code is disabled on public deployments (see [Security](#security)).
- There is no authentication, so quotas are per IP, not per user. Throttle counters are per API process.
- Admission control (`MAX_ACTIVE_RUNS`) is a soft cap: concurrent requests can overshoot it slightly.
- Strategies are long only, single asset, daily bars, with no shorting, leverage, dividends-as-cash or order types beyond market-on-open and stop/target.
- Out-of-sample evaluation uses a single chronological split. Walk-forward evaluation and parameter-sensitivity reports are not built.
- Runs created by the v1 engine are flagged in the UI as unreliable. Re-run them.
- No load test has been run, so there are no capacity numbers.
