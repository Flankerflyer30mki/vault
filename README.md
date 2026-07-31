# Vault — Sandboxed Strategy Backtesting Platform

Vault lets you write a trading strategy as real Python code and test it against years of real historical market data — safely, and honestly. "Safely" because your strategy code runs inside an isolated, locked-down sandbox process. "Honestly" because prices are replayed through Kafka one day at a time, so a strategy can never accidentally see tomorrow's price while deciding today's trade.

**Live demo:** [vault-lovat-beta.vercel.app](https://vault-lovat-beta.vercel.app)
*(Note: live backtests will show a graceful "Live Demo Limitation" message — see [Live Demo vs. Full Functionality](#live-demo-vs-full-functionality) below for why, and how to run the complete system in 5 minutes.)*

---

## Table of Contents

- [What Vault Does](#what-vault-does)
- [Why This Exists](#why-this-exists)
- [Architecture](#architecture)
- [Design Choices, Explained](#design-choices-explained)
- [Live Demo vs. Full Functionality](#live-demo-vs-full-functionality)
- [Getting Started (Full Local Setup)](#getting-started-full-local-setup)
- [Feature Walkthrough](#feature-walkthrough)
- [Tech Stack](#tech-stack)
- [Known Limitations & Roadmap](#known-limitations--roadmap)

---

## What Vault Does

1. **Write a strategy** — a Python function that looks at today's price and a couple of moving averages, and returns `BUY`, `SELL`, or `HOLD`.
2. **Run a backtest** — pick a stock, a date range, and risk parameters (stop-loss, take-profit, position sizing, commission, slippage). Vault replays real historical prices through your strategy, day by day, in strict chronological order.
3. **See real results** — final P&L, CAGR, Sharpe ratio, max drawdown, win rate, an equity curve chart, and a full trade log.
4. **Optimize parameters** — instead of testing one configuration, run a grid of stop-loss/take-profit combinations concurrently and see which one actually performed best, ranked and compared side by side.

## Why This Exists

Most student backtesters are a for-loop over a CSV that prints a profit number. That's fine as a script, but it hides two real, unsolved-in-general engineering problems that any serious backtesting platform actually has to deal with:

- **How do you stop a strategy from cheating?** Even by accident — a strategy that computes "the average price over the whole dataset" is secretly looking into the future. This is called *lookahead bias*, and it's the single most common way people fool themselves with backtests.
- **How do you safely run someone else's code?** If users submit their own strategies, that's arbitrary code executing on your server. It needs to be isolated — no filesystem access, no network access, no way to hang or crash the system.

Vault is built specifically to solve both of these, not just to produce a number at the end.

## Architecture

```
┌─────────────┐         ┌──────────────────┐
│   React     │────────▶│  Django REST API │
│  Frontend   │◀────────│                  │
└─────────────┘         └────────┬─────────┘
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
          ┌─────────────┐   ┌───────────┐    ┌─────────────┐
          │ TimescaleDB │   │   Kafka   │    │    Redis    │
          │ (bars,      │   │ (per-run  │    │ (indicator  │
          │  strategies,│   │  replay,  │    │  cache +    │
          │  runs,      │   │  ordered) │    │  live       │
          │  trades)    │   └─────┬─────┘    │  progress)  │
          └─────────────┘         │          └─────────────┘
                                  ▼
                      ┌───────────────────────┐
                      │   Sandboxed Engine    │
                      │  (subprocess, AST     │
                      │   import whitelist,   │
                      │   restricted builtins)│
                      └───────────────────────┘
```

**Flow of a single backtest run:**

`User writes strategy → triggers run → Django spawns a background thread → engine pulls bars from TimescaleDB → publishes them in order to a run-specific Kafka topic → engine consumes them one at a time → feeds each bar + precomputed indicators (cached in Redis) into a sandboxed subprocess running the user's code → subprocess returns BUY/SELL/HOLD → engine applies risk rules, slippage, commission → logs trades to Postgres → computes CAGR/Sharpe/drawdown/win-rate → frontend polls progress via Redis and displays results.`

## Design Choices, Explained

**Why TimescaleDB, not plain Postgres?**
Vault's core access pattern is "give me every price bar for symbol X between date A and date B, in order" — this happens on every single backtest. TimescaleDB is Postgres with an extension that automatically chunks tables by time range internally, so time-range queries stay fast as the dataset grows. At Vault's current demo scale (5 symbols, ~750 bars each) this isn't something you'd *notice* — the benefit is real but scale-dependent, and using it here is the correct architectural choice for what a real version of this system needs to become.

**Why Kafka, not just an ordered database query?**
A careful `ORDER BY timestamp` query *can* prevent lookahead bias — if every line of code that ever touches it is written correctly, forever. Kafka makes the correct behavior the *only* possible behavior: bars are published to a topic in strict chronological order, and the engine consumes them one message at a time. A Kafka consumer physically cannot receive message #51 before message #50 has been delivered — there's no "whole dataset" sitting in memory that a bug could accidentally reach into. Each backtest run also gets its own isolated topic, which is what lets multiple runs (e.g. a 9-way parameter optimization) execute fully concurrently with zero risk of cross-contamination.

**Why a sandboxed subprocess, not just `exec()` in-process?**
User-submitted strategy code is untrusted by definition. Before execution, the code is parsed with Python's `ast` module and rejected outright if it imports anything outside a small whitelist (`math` only). It then runs inside a **separate OS process** (not the main Django process) with a stripped-down set of builtins — no `open()`, no `__import__()`, nothing that reaches the filesystem or network. If the code crashes, hangs, or misbehaves, it only takes down that one subprocess.

**Why Redis, specifically?**
Two concrete jobs, not a decorative inclusion: (1) **indicator caching** — SMA-10 and SMA-50 are computed once per run and cached, keyed by symbol/window/date-range, so repeated requests don't recompute; (2) **live progress** — the engine writes `{processed, total}` to a Redis key once per bar, which the frontend polls to render a real-time progress bar, without hammering Postgres with a write per bar.

**Why a background thread instead of Celery/RQ?**
A real task queue is the correct production answer, and is explicitly on the roadmap. Given the project's timeline, triggering `run_backtest` in a Python thread and having the frontend poll for status was the pragmatic choice — it's a known, stated tradeoff, not an oversight.

## Live Demo vs. Full Functionality

The live demo is deployed across two free-tier services:
- **Frontend** → Vercel (no compromises, fully functional)
- **Backend + Postgres** → Render (fully functional, using plain Postgres instead of TimescaleDB — Timescale's own free tier is trial-only and would expire, which is worse than a documented tradeoff)

**Kafka is not deployed live.** Free-tier hosting for a raw TCP message broker doesn't fit cleanly into either platform's model without either a paid tier or a rewrite of the connection logic (SASL/SSL auth for a serverless Kafka provider) — a change that wasn't worth making to already-tested, working code just to satisfy one host's constraints.

**What this means concretely:** on the live demo, you can create strategies, browse the UI, and trigger a run — but the run will fail with a clear, graceful message explaining exactly why, and linking back here. **Every part of the system that depends on Kafka only shows up when you run the full stack locally**, which takes about 5 minutes via Docker Compose (below).

## Getting Started (Full Local Setup)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git

That's it — no need to separately install Python, Node, Postgres, Kafka, or Redis.

### 1. Clone the repository
```bash
git clone https://github.com/Flankerflyer30mki/vault.git
cd vault
```

### 2. Start the full stack
```bash
docker compose up --build
```
This builds and starts five containers: TimescaleDB, Kafka, Redis, the Django backend, and the React frontend. First run takes a few minutes. Leave this running.

### 3. Set up the database (one-time)
In a new terminal:
```bash
docker compose exec backend python manage.py migrate
docker compose exec db psql -U postgres -d vault -c "ALTER TABLE backtester_bar DROP CONSTRAINT backtester_bar_pkey;"
docker compose exec db psql -U postgres -d vault -c "SELECT create_hypertable('backtester_bar', 'ts');"
```

### 4. Ingest historical market data (one-time)
```bash
docker compose exec backend python ingest.py
```
Pulls ~3 years of daily OHLCV data for AAPL, MSFT, TSLA, SPY, and GOOGL from Yahoo Finance. Any other valid ticker is fetched automatically the first time you request it.

### 5. Open the app
- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:8000/api/strategies/](http://localhost:8000/api/strategies/)

### 6. Try it
- **Strategies** → pick a template, create a strategy
- **New Backtest** → select it, run against AAPL — this runs the real engine end-to-end
- **Optimize** → run a stop-loss/take-profit grid search and compare results

### Shutting down
```bash
docker compose down
```
Your ingested data persists across restarts (stored in a Docker volume) — no need to re-ingest next time.

## Feature Walkthrough

| Page | What it does |
|---|---|
| **Strategies** | Write and save strategies, or start from a template (SMA Crossover, Momentum Threshold) |
| **New Backtest** | Configure symbol, date range, starting cash, and risk parameters (stop-loss, take-profit, position sizing, commission, slippage) |
| **Run Detail** | Live progress bar while running; on completion, shows execution metrics, sandbox pass/fail status, CAGR/Sharpe/drawdown/win-rate, equity curve chart, and full trade log |
| **Optimize** | Define a grid of stop-loss × take-profit values, run all combinations concurrently |
| **Comparison** | Sortable results table (ranked by any metric) plus an overlaid equity curve chart across all runs in an optimization job |

## Tech Stack

**Backend:** Django, Django REST Framework, PostgreSQL, TimescaleDB, Kafka, Redis, Python subprocess sandboxing
**Frontend:** React, Vite, React Router, Recharts, Axios
**Infra:** Docker, Docker Compose
**Data:** yfinance (real historical OHLCV data)

## Known Limitations & Roadmap

**Deliberate, stated tradeoffs (not oversights):**
- Live deployment runs plain Postgres, not TimescaleDB (see [above](#live-demo-vs-full-functionality))
- Kafka is not deployed live — full functionality requires local Docker Compose
- Background threads handle async execution instead of a task queue (Celery/RQ)

**Genuine roadmap items, in rough priority order:**
- [ ] Docker-per-run sandbox isolation (stronger than the current subprocess + AST whitelist approach)
- [ ] Celery/RQ-based task queue in place of background threads
- [ ] Scheduled daily data refresh for tracked symbols
- [ ] Additional built-in strategy templates
- [ ] Support for intraday (not just daily) bar granularity