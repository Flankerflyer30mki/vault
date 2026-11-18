# Vault

**A backtester for daily trading strategies, with results you can check by hand.** Build a strategy from rules, or describe it in words and let the AI fill in the rules. Test it on years of US or Indian market data. Compare and tune strategies against benchmarks, or give an AI research agent a goal and let it search, with a held-out test it never sees.

**Live demo: [vault-lovat-beta.vercel.app](https://vault-lovat-beta.vercel.app)**. Click "Try it as a guest"; no email is needed. The demo runs on free hosting, so the first request after a quiet spell can take up to a minute while the server wakes up.

---

## What it does

- **Strategy builder:** rules such as "buy when EMA 12 crosses above EMA 26 and RSI 14 < 70". There are eight indicators and seven templates. The spec is JSON that is validated and *interpreted*, never turned into code, so it is safe on a public server.
- **Backtests you can reproduce:** a decision on bar *t* fills at the open of bar *t+1*. Every run stores the exact spec, a hash of the data and the engine version. Costs include an Indian delivery model (STT, exchange and SEBI fees, stamp duty, GST).
- **Comparisons and optimizations:** a strategies × symbols heatmap with index benchmarks. Parameter searches run on the first 70% of the period, and the best result is tested once on the last 30%.
- **AI assistant:** describe a strategy in plain English, or Hindi-English, and get rules filled into the form for you to review. Requests it can't express (shorting, options, intraday) are refused, not approximated.
- **AI research agent:** give it a goal, a symbol and a period. It proposes and backtests candidates, refines them, and picks one. Code, not the agent, then tests that pick on a held-out period, and the report's every number is checked against the results.
- **Accounts:** Sign in with Google, guest workspaces, email sign-up and verification, private data for each user, and quotas by tier.

## Engineering highlights

| Area | What was built | Measured |
|---|---|---|
| **Job queue on Postgres** | `SELECT … FOR UPDATE SKIP LOCKED`, two priority lanes, ownership-checked writes, stale-job recovery, graceful shutdown. No Redis, Celery or Kafka | claim 8–12 ms with 100 or 100,000 runs queued; a hand-started run behind a 25-run batch starts in 25 ms (was 1.26 s); a run interrupted by a deploy is requeued 2.26 s after `SIGTERM` |
| **Deterministic engine** | pure Python, `Decimal` money, one equity curve that every metric derives from | tests for a hand-calculated trade, `equity = cash + qty × close` at every bar, and a metamorphic **no-look-ahead** test |
| **Throughput** | per-worker caches for bars and indicators; heartbeats once per second instead of once per bar (those writes took 70% of a run's time) | 537 builder backtests per minute on one worker, 1,263 on four |
| **API capacity** | Django REST, stateless, rate limits shared across processes in Postgres | about 50 requests/s at 0.5 CPU; p95 110 ms at 10 users |
| **LLM feature** | provider isolated in one module; the model's JSON is checked by the same validator as human input, with up to two repair rounds; quotas, a token budget and an answer cache | **60/60** cases pass on a behavioural eval (same trades on 5 fixed price series), median 1.7 s; CI replays the recorded answers |
| **Agent** | a resumable state machine on the job queue, one checked JSON action per step, budgets, a held-out test run once by code, a grounded report | it survives restarts and deploys and holds no worker while waiting; tested end to end with a scripted model and one live run |
| **Operations** | request IDs from the click to the run to the worker log, JSON logs, a Prometheus `/metrics` endpoint, an OpenAPI schema checked in CI | |
| **Security** | session cookie and CSRF on one origin with no CORS, no account enumeration, per-IP limits that can't be dodged with a fake `X-Forwarded-For` header, each user's data hidden from others (404) | custom Python stays off in public, because the sandbox is [not a security boundary](docs/reference.md#security) |

## Architecture

```
Browser ──▶ React SPA (Vercel) ── /api/* rewritten, same origin ──▶ Django REST API (gunicorn)
                                                                        │ validate, throttle, admit
                                                                        ▼ insert a 'queued' row
                                                                   PostgreSQL  ◀── the job queue, data, results
                                                                        ▲
                       Worker: claim (SKIP LOCKED) ─ load bars (Yahoo) ─ run engine ─ commit in one transaction
                               └─ AI requests and research steps are jobs on the same queue
```

There are two processes built from one image, plus one database. The API never runs backtests or calls the AI provider inside a request. Details, failure behaviour and every limit are in the [technical reference](docs/reference.md).

## Stack

**Backend:** Python 3.12, Django 6, Django REST Framework, PostgreSQL 16, gunicorn, drf-spectacular, yfinance, Groq (OpenAI-compatible HTTP).<br>
**Frontend:** React 19, Vite, Recharts, axios, Vitest with React Testing Library.<br>
**Infrastructure:** Docker Compose; Vercel for the frontend and Render for the API and database; GitHub Actions CI.

## Run it locally

```bash
docker compose up --build
```

Open http://localhost:5173. Compose starts Postgres, the API (which applies migrations), a worker and the frontend. Market data is fetched on first use. The AI features need `AI_PROVIDER=groq` and a `GROQ_API_KEY` in the API's and the worker's environment; without them, everything else works. The [reference](docs/reference.md#run-locally) covers running without Docker.

## Tests and CI

```bash
cd backend && DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test
cd frontend && npm test
```

There are 223 backend and 34 frontend tests. No test reaches Yahoo, the AI provider or Google. CI runs the suite on PostgreSQL 16 and checks for migration drift. It also checks that the OpenAPI schema has no warnings, that production refuses to start without `SECRET_KEY`, and that recorded AI evals still match the prompt. It finishes with `pip-audit`, `npm audit` and both Docker builds.

## Documentation

| Document | Contents |
|---|---|
| [docs/reference.md](docs/reference.md) | the full spec: execution model, metrics, costs, data, limits, security, deploy, runbook |
| [docs/decisions.md](docs/decisions.md) | about 100 numbered decisions with context and alternatives |
| [docs/evals.md](docs/evals.md) | measurements: load tests, queue benchmarks, AI evals, live runs |
| [docs/improvements.md](docs/improvements.md) | each improvement as why, before, change and measured result |
| [docs/tradeoff.md](docs/tradeoff.md) | what each choice costs |
| [docs/changes.md](docs/changes.md) | what changed in each phase |
| [docs/concepts.md](docs/concepts.md) | the finance and engineering concepts used, explained |

## Limitations

- Long only, a single asset per strategy, daily bars. No shorting, leverage or intraday data.
- Custom Python strategies are off on the public demo until an isolated runner exists.
- Yahoo blocks the demo's host, so the demo serves the pre-loaded suggested symbols (US and NSE), and their prices are refreshed by hand.
- The research agent has had one live run. Whether its picks beat a random search on held-out data hasn't been measured yet.
