# Vault

[![CI](https://github.com/Flankerflyer30mki/vault/actions/workflows/ci.yml/badge.svg)](https://github.com/Flankerflyer30mki/vault/actions/workflows/ci.yml)

**A backtester for daily trading strategies, with results you can check by hand.** Build a strategy from rules, or describe it in words and let the AI fill in the rules. Test it on years of US or Indian market data. Compare and tune strategies against benchmarks, or give an AI research agent a goal and let it search, with a held-out test it never sees.

**Live demo: [vault-lovat-beta.vercel.app](https://vault-lovat-beta.vercel.app)**. Sign in with Google, or click "Try it as a guest". The demo runs on free hosting, so the first request after a quiet spell can take up to a minute while the server wakes up.

**Contents:** [What it does](#what-it-does) · [Architecture](#architecture) · [Key decisions](#key-decisions) · [Measured improvements](#measured-improvements) · [Trade-offs](#trade-offs) · [Lessons from production](#lessons-from-production) · [Stack](#stack) · [Run it](#run-it-locally) · [Tests](#tests-and-ci) · [Docs](#documentation)

---

## What it does

- **Strategy builder:** rules such as "buy when EMA 12 crosses above EMA 26 and RSI 14 < 70". There are eight indicators and seven templates. The spec is JSON that is validated and *interpreted*, never turned into code, so it is safe on a public server.
- **Backtests you can reproduce:** a decision on bar *t* fills at the open of bar *t+1*. Every run stores the exact spec, a hash of the data and the engine version. Costs include an Indian delivery model (STT, exchange and SEBI fees, stamp duty, GST).
- **Comparisons and optimizations:** a strategies × symbols heatmap with index benchmarks. Parameter searches run on the first 70% of the period, and the best result is tested once on the last 30%.
- **AI assistant:** describe a strategy in plain English, or Hindi-English, and get rules filled into the form for you to review. Requests it can't express (shorting, options, intraday) are refused, not approximated.
- **AI research agent:** give it a goal, a symbol and a period. It proposes and backtests candidates, refines them and picks one. Code, not the agent, then tests that pick on a held-out period, and every number in the report is checked against the results.
- **Accounts:** Sign in with Google, email sign-up, guest workspaces, private data for each user, and quotas by tier.

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

There are two processes built from one image, plus one database. The API never runs a backtest or calls the AI provider inside a request: it validates the request, checks limits, inserts a row and returns. Workers claim rows, do the work and commit the results in one transaction. Failure behaviour and every limit are in the [technical reference](docs/reference.md).

## Key decisions

Each of these is written up in [docs/decisions.md](docs/decisions.md) with its context and the alternatives considered (103 decisions in all).

| Decision | Why | Instead of |
|---|---|---|
| **Postgres is the job queue** (`SELECT … FOR UPDATE SKIP LOCKED`) | Durable jobs, transactional hand-off and no extra service to run. A claim stays at 8–12 ms with 100,000 jobs queued | Celery + Redis, or Kafka (v1 used Kafka; it didn't prevent look-ahead and added a paid service) |
| **Workers can only write while they own the job** | Every update checks `worker_id` and an active status, so a worker that lost a job can't overwrite results; retries replace results, never duplicate them | Trusting at-most-once delivery |
| **Fills at the next bar's open; the stop wins if stop and target are hit on the same bar** | Removes same-bar look-ahead, which v1 had; when a bar touches both levels, assume the worse outcome | Filling at the close the strategy just saw |
| **Strategy specs are interpreted, never turned into code** (D-033) | No user input ever becomes code, so builder strategies are safe on a public server; also 9.8× faster than the sandbox | Generating Python from the spec and running it |
| **Session cookies on one origin, not JWT** (D-016) | `HttpOnly` cookies can't be stolen by injected scripts; sign-out and "sign out everywhere" take effect instantly; no CORS | JWT in browser storage, with refresh tokens and a blocklist |
| **AI output is data: validated, repaired, never executed** (D-080) | The model's JSON goes through the same validator as human input; its errors go back to the model, at most twice | Trusting the model's output, or running generated code |
| **AI quality is measured by behaviour, replayed in CI** (D-082) | A spec passes if it makes the same trades as the reference on five fixed price series; a prompt change fails CI until it's measured again | Comparing text, or not measuring |
| **The agent is a resumable state machine on the job queue** (D-090) | One claim is one short step, so no worker is held while backtests run, and restarts or deploys resume from saved state | One long-running agent loop in a process |
| **The held-out test is run by code, once** (D-091), **and report numbers are checked** (D-092) | The agent never sees the held-out dates and can't retry on them; an invented number in its summary is caught | Letting the agent choose and grade its own pick |
| **Sign in with Google, safe against account pre-hijacking** (D-103) | Verifies email without sending any (the host blocks email). Linking an *unverified* account removes its password, since whoever set it never proved they own the address | Supabase Auth or own JWT auth: a rewrite that still wouldn't deliver email |

## Measured improvements

Every row was measured or is proven by a test. The before → after details and method for each are in [docs/improvements.md](docs/improvements.md), with raw numbers in [docs/evals.md](docs/evals.md).

| Improvement | Before | After |
|---|---|---|
| Time per run inside a 25-run experiment, **found by profiling**: progress writes were 70% of a run's time | 174 ms | **37–39 ms (4.5× faster)** |
| A run someone starts by hand, queued behind a 25-run batch (priority lanes) | 1.26 s | **25 ms** |
| Builder strategy vs the same strategy as sandboxed code, 2,520 bars | 298.8 ms | **30.4 ms (9.8× faster)**, identical 80/80 fills |
| API throughput with rate limits shared across processes, **found by load testing** | 31–41 req/s | **52–55 req/s** (one upsert instead of ≥ 3 statements) |
| Logins allowed by a 10-per-minute limit with 2 API processes | 20 | **exactly 10** |
| A run interrupted by a deploy | stuck 120–150 s, one retry used | **requeued in 2.26 s**, no retry used |
| Describe a strategy in words → the correct strategy (gpt-oss-120b, 60 cases) | not possible | **60/60**, 18/18 refusals correct, 1.7 s median |
| AI prompt with the indicator catalog and examples vs format rules only (gpt-oss-20b) | 54% | **94%** |
| Re-measuring the AI after a change | ~130,000 tokens, ~20 min | **1 model call** (cached answers reused) |
| The irreversible production upgrade, rehearsed on a copy of the real data | untested | **4.9 s**, every run, trade and bar kept |
| Known capacity of one small API instance and one worker | unknown | **~50 req/s, ~20 users; 537 backtests/min** |

## Trade-offs

What each choice cost, and when it should change. The full table for every decision is in [docs/tradeoff.md](docs/tradeoff.md).

| Choice | Gave up | Revisit when |
|---|---|---|
| Postgres queue, no Redis | Queue throughput is bounded by the database; per-worker caches aren't shared | Queue throughput, not backtests, becomes the bottleneck |
| Session cookies through the Vercel proxy | Every API call takes an extra hop through Vercel; the frontend and API deploy together | A mobile app or third-party API clients need tokens |
| Interpreted specs instead of code | Strategies can express only what the operators allow: no loops, state or custom maths | Users need more → add operators or nesting (spec v2), never code generation |
| Shared rate-limit counters in Postgres | One database write per throttled request | Request volume where that write matters |
| Priority lanes, no pre-emption | A steady stream of single runs delays batches (bounded by quotas) | Several heavy batches at once → round-robin between them |
| Held-out test on 30% of the period | Research sees only 70% of the data; one held-out period is a sample, not proof | Walk-forward evaluation (designed, not built) |
| Free open models via Groq | Free limits are shared by the whole site; open models make more format mistakes (measured) | Real traffic → a paid tier with a spending cap |
| Free hosting, worker inside the web service | Backtests compete with HTTP for CPU; the service sleeps when idle | Traffic or budget → a separate worker (~$7/month) |

## Lessons from production

Things that only showed up once the system ran for real, and what was done about each:

- **Every API call returned 404 on the live site.** The Vercel rewrite pattern didn't match paths ending in `/`. The smoke test through the real domain caught it, and the fix was live within 7 minutes (D-098). Since then, every check goes through the public domain, not just the API's own URL.
- **Yahoo blocks the host's IP addresses.** Market data is loaded into the production database from a machine Yahoo accepts, using Vault's own fetch code, so the bars and coverage records match what the worker would write (D-099).
- **The host blocks outgoing email.** Verification and reset emails could never be delivered, so I added Sign in with Google, which verifies the address without sending anything (D-103).
- **The rate limits needed to know how many proxies sit in front of the API.** Instead of guessing, the access log records the hop count (never the addresses), and the setting was taken from a real request: 4 hops (D-101).
- **The AI evaluation found a bug in the validator, not the AI:** a rule comparing something with itself ("SMA 20 crosses above SMA 20") was accepted. It's now rejected for hand-built strategies too (D-087).
- **The first live agent run exposed four problems:** a number check that was too strict, answers cut off at the output limit, never leaving the exploration stage, and duplicate candidates. All four are fixed and tested (D-096).

## Stack

**Backend:** Python 3.12, Django 6, Django REST Framework, PostgreSQL 16, gunicorn, drf-spectacular, google-auth, yfinance, Groq (OpenAI-compatible HTTP).<br>
**Frontend:** React 19, Vite, Recharts, axios, lucide icons, Vitest with React Testing Library. A token-based design system (dark and light themes) and a `Ctrl+K` command palette.<br>
**Infrastructure:** Docker Compose; Vercel for the frontend and Render for the API and database; GitHub Actions CI. Request IDs, JSON logs, a Prometheus `/metrics` endpoint and an OpenAPI schema.

## Run it locally

```bash
docker compose up --build
```

Open http://localhost:5173. Compose starts Postgres, the API (which applies migrations), a worker and the frontend. Market data is fetched on first use. The AI features need `AI_PROVIDER=groq` and a `GROQ_API_KEY` in the API's and the worker's environment; Sign in with Google needs `GOOGLE_CLIENT_ID`. Without them, everything else works. The [reference](docs/reference.md#run-locally) covers running without Docker.

## Tests and CI

```bash
cd backend && DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test
cd frontend && npm test
```

There are 223 backend and 49 frontend tests, and none reaches Yahoo, the AI provider or Google. Some go beyond examples:
- a **metamorphic test** proves no indicator uses future data: rewriting every bar after *t* changes nothing at or before *t*
- a **differential test** shows the builder and the Python strategy make identical trades
- a **concurrency test** runs 4 worker threads against Postgres and checks that none of 40 jobs is claimed twice
- **Google sign-in tests** sign real tokens with a throwaway key, so the library's actual checks run

CI runs the suite on PostgreSQL 16 and checks for migration drift. It also checks that the OpenAPI schema has no warnings, that production refuses to start without `SECRET_KEY`, and that the recorded AI evals still match the prompt. It finishes with `pip-audit`, `npm audit` and both Docker builds.

## Documentation

| Document | Contents |
|---|---|
| [docs/reference.md](docs/reference.md) | the full spec: execution model, metrics, costs, data, limits, security, deploy, runbook |
| [docs/decisions.md](docs/decisions.md) | 103 numbered decisions with context and alternatives |
| [docs/improvements.md](docs/improvements.md) | each improvement as why, before, change and measured result |
| [docs/tradeoff.md](docs/tradeoff.md) | what each choice gained, gave up, and when to revisit it |
| [docs/evals.md](docs/evals.md) | measurements: load tests, queue benchmarks, AI evals, live runs |
| [docs/changes.md](docs/changes.md) | what changed in each phase |
| [docs/concepts.md](docs/concepts.md) | the finance and engineering concepts used, explained |

## Limitations

- Long only, a single asset per strategy, daily bars. No shorting, leverage or intraday data.
- Custom Python strategies are off on the public demo: the sandbox is [not a security boundary](docs/reference.md#security), and an isolated runner isn't built yet.
- On the demo, only the pre-loaded symbols (popular US and NSE stocks and indices) have data, and their prices are refreshed by hand.
- Password reset and verification emails aren't delivered on the demo; Google sign-in covers verification.
- The research agent has had one live run. Whether its picks beat a random search on held-out data hasn't been measured yet.
