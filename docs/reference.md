# Vault technical reference

The full specification: execution model, metrics, limits, failure behaviour, security, deployment and runbook. The [README](../README.md) is the overview; decisions are in [decisions.md](decisions.md) and measurements in [evals.md](evals.md).

---

## Contents

- [Architecture](#architecture)
- [Execution model](#execution-model)
- [Strategy builder](#strategy-builder)
- [Accounting and metrics](#accounting-and-metrics)
- [Costs and markets](#costs-and-markets)
- [Market data](#market-data)
- [Jobs, limits and failure behaviour](#jobs-limits-and-failure-behaviour)
- [Experiments: comparisons and optimizations](#experiments-comparisons-and-optimizations)
- [AI assistance: describe a strategy in words](#ai-assistance-describe-a-strategy-in-words)
- [AI research agent](#ai-research-agent)
- [Accounts and workspaces](#accounts-and-workspaces)
- [Operations: logs, metrics, capacity](#operations-logs-metrics-capacity)
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
Browser ──▶ React SPA (Vercel) ── same origin: /api/* is rewritten to Render ──┐
               session cookie (HttpOnly) + CSRF token, JSON                     │
               ▼                                                                ▼
         Django REST API (gunicorn, stateless) ──▶ PostgreSQL
               │  validate, throttle, admit,          ▲  strategies, runs (= the job queue),
               │  insert a 'queued' run row           │  trades, bars, results
               ▼                                      │
         Worker process(es): python manage.py run_worker
               │  claim with SELECT … FOR UPDATE SKIP LOCKED,
               │  load and validate bars (fetch from Yahoo when coverage is incomplete),
               │  run the deterministic engine, then commit trades and results in one transaction
               │
               ├─ builder strategy: JSON spec interpreted in-process (spec.py + indicators.py; no code runs)
               ▼
         code strategy only: subprocess per run (rlimits, empty environment, wall-clock deadline)
```

The system has two services: an API and a worker. Both are built from the same image and talk to one PostgreSQL database. There is no Kafka, no Redis and no TimescaleDB ([why](#design-decisions)).

The browser never talks to the API's domain directly. Vercel (production), Vite (development) and nginx (the compose image) forward `/api` to Django, so the login cookie is first-party and there is no CORS. Browsers increasingly block cookies sent to a different domain, so this is what makes cookie logins work.

## Execution model

The rules below are implemented in `backend/backtester/engine.py`, and the tests in `backend/backtester/tests.py` check them.

| Rule | Behaviour |
|---|---|
| Signal time | The strategy sees bar *t*, including its close. Every indicator is computed from bars up to and including bar *t* (code strategies get SMA-10 and SMA-50; builder strategies get the indicators their spec names). |
| Fill time | A decision made on bar *t* fills at the **open of bar *t+1***. A decision on the last bar never fills. |
| Stops / targets | These are checked against each bar's high and low while a position is open. If the bar opens past the level (a gap), the fill is at the open. If the level is touched during the bar, the fill is at the level. **If both levels are touched in one bar, Vault assumes the stop filled** (the conservative choice). The API rejects a stop-loss that is not larger than the slippage: entry fills at `open × (1 + slippage)`, so a tighter stop would sit above the open and stop out every entry on its first bar. |
| Position | **Long only** (fully in the stock or in cash), one position at a time. Fractional shares are rounded down to 1e-6. Shorting is deliberately not modelled: Indian retail traders can't hold a short position overnight in the cash market (decision D-036). |
| Sizing | `qty = cash × max_position_pct / (fill_price × (1 + buy_commission))`. The commission is part of the budget, so cash never goes negative. |
| Costs | Slippage moves the fill price against you. Commission is charged on each fill's notional, with separate buy and sell rates (see [Costs and markets](#costs-and-markets)). Each is charged exactly once. |
| End of run | An open position is **marked to market** at the last close. It is not liquidated. |
| Warm-up | Bars before `start_date` feed the indicators; the strategy never sees them. Code strategies get 50. Builder strategies get the longest lookback their spec needs (smoothed indicators get 3× their period so the starting seed fades), capped at 600. The manifest records the number used and warns when history is shorter. |

## Strategy builder

A builder strategy is a **JSON spec**, validated against an allowlist and **interpreted** by the engine. It is never turned into code and never executed, so it runs on public deployments where custom Python is off.

```json
{"version": 1,
 "entry": {"all": [{"left": {"ind": "ema", "params": {"period": 12}}, "op": "crosses_above",
                    "right": {"ind": "ema", "params": {"period": 26}}},
                   {"left": {"ind": "rsi", "params": {"period": 14}}, "op": "<", "right": {"const": 70}}]},
 "exit":  {"any": [{"left": {"price": "close"}, "op": "<", "right": {"ind": "sma", "params": {"period": 200}}}]}}
```

- **Signals:** on each bar, `SELL` if the exit group is true, otherwise `BUY` if the entry group is true, otherwise `HOLD`. When both are true, **exit wins** (conflicting signals keep a flat strategy out).
- **Groups:** `all` (AND) or `any` (OR), 1–10 conditions each, no nesting.
- **Operands:** an indicator, a price field (`open`, `high`, `low`, `close`, `volume`) or a number. Comparing two numbers is rejected.
- **Operators:** `>`, `<`, `>=`, `<=`, `crosses_above` (previous bar `a ≤ b`, this bar `a > b`), `crosses_below`. A condition touching a missing value (an indicator still warming up) is false.
- **Indicators** (periods 2–200; `backend/backtester/indicators.py`):

| Indicator | Params | Outputs | Convention |
|---|---|---|---|
| `sma` | period | value | arithmetic mean; same arithmetic as the code strategies' `sma_N` |
| `ema` | period | value | seeded with the SMA of the first *n* values, then α = 2/(n+1) |
| `rsi` | period | value | Wilder smoothing (α = 1/n); flat prices give 50 |
| `macd` | fast, slow, signal | line, signal, hist | EMA(fast) − EMA(slow); signal is an EMA of the line |
| `bbands` | period, std | upper, middle, lower | population standard deviation |
| `atr` | period | value | Wilder-smoothed true range (includes gaps) |
| `donchian` | period | upper, lower | the *n* bars **before** the current one, so `close > upper` is a breakout |
| `roc` | period | value | percent: `100 × (close / close[n] − 1)` |

- **Validation** reports every problem at once, keyed by path (`entry.all[0].left.params.period`), and the UI shows each message on its field. Unknown keys, booleans posing as numbers, NaN and specs over 8 KB are rejected.
- **Reproducibility:** each run stores a frozen copy of the spec and the SHA-256 of its canonical JSON (sorted keys). Editing a strategy never changes past runs. A strategy that has runs can't be deleted (`409`).
- **"View as Python"** renders the spec as readable Python for people. Vault never executes that text.
- **Templates:** seven built-in builder strategies: EMA crossover, RSI mean reversion, MACD signal cross, Bollinger breakout, Donchian breakout and trend-filtered RSI (migration `0017`), plus Buy and Hold (`0019`, also used as the comparison benchmark). Built-ins are read-only; "Use as template" copies one into your workspace.
- **Endpoints:** `GET/POST /api/strategies/`, `GET/PATCH/DELETE /api/strategies/<id>/`, `GET /api/strategies/catalog/` (indicators, operators, limits, cost models, suggested symbols; the form is built from this, so the allowlist lives in one place), `POST /api/strategies/preview/` (validate and render without saving; the form calls it as you type).

## Accounting and metrics

- Money uses `Decimal` throughout the engine. Ratios use floats.
- The invariant `equity_t = cash_t + quantity_t × close_t` holds at every bar, and a test checks it.
- **Every metric comes from that one ledger equity curve.** Nothing recomputes cash anywhere else.
- **CAGR** uses the actual first and last simulated bar dates, not the requested dates. It is `null` if the result is undefined.
- **Sharpe** uses daily equity returns with a risk-free rate of 0, annualised with √252. It is `null` when volatility is zero.
- **Sortino** is the same with downside deviation (losing days only, target 0) in place of the standard deviation; `null` with no losing day. **Calmar** is CAGR ÷ max drawdown; `null` with no drawdown.
- **Exposure** is the share of bars that closed with a position open. **Round trips** counts closed buy-sell pairs. **Cost drag** is commission plus slippage as a share of starting cash.
- **Max drawdown** is measured peak to trough on equity.
- **Win rate** is calculated per round trip, **net of commission and slippage**. It is `null` when no round trip has closed.
- **Buy & hold** is a gross benchmark: first open to last close over the same bars.
- A completed run with no trades still produces a valid flat equity curve and metrics.

## Costs and markets

Each run has a `cost_model`:

- **`flat`** (default): `commission_pct` on every buy and sell.
- **`india_delivery`** (NSE/BSE symbols only): `commission_pct` is your broker's brokerage, and the server adds the statutory charges per side. The run stores the resulting buy and sell rates.

| Charge (equity delivery) | Rate | Side |
|---|---|---|
| STT | 0.1% | buy and sell |
| NSE transaction charge | 0.00297% | buy and sell |
| SEBI turnover fee | ₹10 per crore (0.0001%) | buy and sell |
| Stamp duty | 0.015% | buy only |
| GST | 18% of brokerage + transaction charge + SEBI fee | buy and sell |

With zero brokerage that is **0.1186226% per buy and 0.1036226% per sell** (₹118.62 and ₹103.62 on ₹1,00,000). Rates live in `backend/backtester/costs.py`; they change from time to time, so check current exchange circulars before relying on them. Flat per-order charges (DP charges on sells, minimum brokerage) are not modelled. Optimizations take a cost model too: flat uses 0.1%, India uses zero brokerage plus the statutory charges.

**Currency** is inferred from the symbol and only used for display: `.NS`/`.BO` and Indian indices (`^NSEI`, `^NSEBANK`, `^BSESN`, …) are INR, plain US tickers are USD, other exchange suffixes are shown without a currency sign. The symbol field suggests common NSE stocks and indices.

## Market data

Data comes from Yahoo Finance via `yfinance`. Prices are adjusted (`auto_adjust=True`) daily bars, and each bar is stored at midnight UTC of its trading date.

- Symbols are normalised to upper case before any read or write.
- **Coverage is tracked per symbol.** `SymbolCoverage` records the date span already requested from Yahoo. A request inside that span is served from stored bars, whatever Yahoo had (late listings and market closures stay as labelled gaps instead of causing a download on every run). The fetch day itself is never counted as covered, because that day's bar may not exist yet. Stored bars without a coverage record (for example from before this was added) count as not covered. Yahoo's `end` parameter is exclusive, so Vault requests `end + 1 day`.
- **One price scale per symbol.** Yahoo restates adjusted history after every split and dividend. So a fetch downloads the symbol's whole known span (stored, covered and requested) and replaces its bars in one transaction, instead of adding new rows next to old ones on a different scale. A failed or empty fetch changes nothing and records no coverage.
- Concurrent fetches are safe: `UNIQUE (symbol, ts)` plus an upsert means no duplicate bars.
- Rows with non-finite or non-positive prices are rejected, as are rows where `low > min(open, close)` or `high < max(open, close)`.
- Partial data is allowed but **labelled**: the run's `data_manifest.warnings` lists late starts, early ends, gaps, rejected rows and missing warm-up. If no bars are found, the run **fails** with category `data`.
- Each run records `data_manifest`: provider, adjustment, first and last bar, bar count, and a SHA-256 of the bars used.
- The fetch happens in the worker, never inside an HTTP request.

Scope: Vault handles daily bars for single Yahoo tickers. It does not model corporate actions beyond Yahoo's adjustment, it has no intraday data, and it does not handle multiple assets per strategy.

## Jobs, limits and failure behaviour

**Run states:** `queued → preparing_data → running → completed`. Any active state can move to `failed`, which carries a `failure_category` of `data`, `strategy` or `infrastructure`.

- **Durable.** The run row is the job. If the API or the worker restarts, the job is not lost.
- **At-least-once execution with idempotent finalisation.** Trades and results are written in one transaction, and only if the worker still owns the run (`status = running AND worker_id = me`). A retry replaces earlier trades instead of adding to them.
- **Claim order.** Workers claim `ORDER BY priority, id`: runs a person starts by hand (priority 0) go before experiment children (priority 1), first-in-first-out within each lane. Nothing is pre-empted; a running job always finishes. Measured: a hand-started run behind a 25-child batch starts in 25 ms instead of 1.26 s.
- **Stale-job recovery.** Workers update a heartbeat at most once per second while a run is in progress (a run that finishes in under a second writes none). A run with no heartbeat for `STALE_AFTER_S` (120 s) goes back to `queued`, up to `MAX_ATTEMPTS` (3) attempts in total, and then fails as `infrastructure`.
- **Per-worker caches.** Each worker keeps a small LRU of loaded bars (keyed by symbol, dates, warm-up and the coverage's `fetched_at`, so a re-download is never served stale) and of indicator series (keyed by the data hash). Children of one experiment share them; results are identical with or without the cache.
- **Graceful shutdown.** On `SIGTERM` (a deploy or restart) a worker stops claiming new runs and lets the current one finish for up to `WORKER_GRACE_S` (20 s, under Render's 30 s kill window). A run still going after that goes straight back to `queued` without using an attempt, instead of waiting 120–150 s for stale recovery. Measured with a real worker process: back in the queue 2.26 s after `SIGTERM` with a 2 s grace.
- **Strategy errors are not retried.** An exception, a bad return value or a timeout fails the run immediately with a safe message.
- **Bounded concurrency.** Each worker process runs one job at a time. To scale, run more worker processes. The API never starts threads or subprocesses.
- **Progress** is stored on the run row (`bars_processed / bars_total`). The UI shows "progress not available" rather than a fake 0%.

| Limit | Default | Scope |
|---|---|---|
| `MAX_ACTIVE_RUNS` | 50 queued+running | global (soft cap). The API returns `503` when it is reached |
| `MAX_GRID` | 25 child runs | per experiment (optimization combinations or comparison cells), checked server-side |
| `MAX_GRID_PARAMS` | 4 | strategy parameters searched at once |
| `MAX_COMPARE_STRATEGIES` / `MAX_COMPARE_SYMBOLS` | 10 / 10 | per comparison |
| up to 10 values | per stop-loss / take-profit / parameter list | per request |
| `MAX_RANGE_DAYS` | 3660 | per request |
| `MAX_CODE_CHARS` | 10 000 | per code strategy |
| builder spec | 1–10 conditions per group, periods 2–200, 8 KB, warm-up ≤ 600 bars | per builder strategy |
| `RUN_TIMEOUT_S` / `RUN_CPU_S` / `RUN_MEMORY_MB` | 60 / 30 / 256 | per strategy process |
| request body | 64 KB | per request |
| `THROTTLE_JOBS` / `THROTTLE_WRITE` / `THROTTLE_READ` | 10 / 30 / 300 per min | **per user** when signed in. Counters are shared by every API process and instance (Postgres table `vault_cache`) |
| `THROTTLE_AUTH` / `THROTTLE_GUEST` | 10 per min / 5 per hour | **per IP**: login, signup and password reset / guest creation |
| Per-user quotas | see [Accounts](#accounts-and-workspaces) | active jobs, backtests and experiments per rolling 24 h, by tier. The API returns `429` naming the limit |
| `NUM_PROXIES` | 1 on Render, else 0 (compose sets 1 for its nginx); **4 on the live deployment** (measured, D-101) | proxies in front of the API. Throttling identifies the client from the address the last trusted proxy appended, so a client cannot dodge limits by sending its own `X-Forwarded-For` |
| `Idempotency-Key` header | optional | repeating a `POST /runs/` or `/experiments/` with the same key returns the original job. Keys are per user |

## Experiments: comparisons and optimizations

An **experiment** is a batch of ordinary backtests (child runs) created by one request and read together. Its status is derived from the children and never stored: `running`, `completed`, `partially_completed` (some children failed) or `failed` (none completed). It counts as one active job and one experiment per 24 h against the quota. `POST /api/experiments/` takes `kind: "comparison"` or `kind: "optimization"`; `/api/optimizations/` remains as an alias for optimizations.

### Comparison

Strategies × symbols (at most 25 cells) over one period, cash amount, cost model and optional stop/target. Each cell is a normal run you can open. For every currency present, an **index benchmark** runs as one more child: the built-in "Buy and Hold" strategy on NIFTY 50 (`^NSEI`) for INR symbols or the S&P 500 (`^GSPC`) for USD symbols, with zero costs. The page shows a heatmap (total return, Sharpe, Sortino, Calmar, max drawdown, exposure or cost drag; coloured within each symbol's column), a benchmark row, and the strategies' equity curves for any one symbol against its benchmark. Curves on experiment pages are downsampled to at most ~500 points, keeping each bucket's minimum and maximum; a run's own page has the full curve.

### Optimization and out-of-sample evaluation

Picking the best parameters on the same data you then report on overstates performance. Vault therefore splits each optimization by time:

1. The date range is split chronologically. The first 70% is **in-sample** and the last 30% is **out-of-sample** (`OOS_FRACTION`).
2. Every combination runs on the in-sample period only. A combination is stop-loss × take-profit, and for builder strategies also values of the strategy's own parameters. Parameters are grouped by indicator instance (`ema(12).period` covers the EMA-12 in both the buy and the sell rule), so a search changes them together. Each combination is its own validated, frozen spec. A value out of range rejects the request; a combination that is only invalid together (MACD fast ≥ slow) is skipped and listed.
3. When all in-sample runs are finished, the best one by Sharpe is queued **once** on the out-of-sample period. A unique constraint guarantees exactly one such run.

The UI labels in-sample results as optimised and shows the out-of-sample result separately, next to buy & hold. A high in-sample Sharpe is not evidence of an edge.

## AI assistance: describe a strategy in words

On the builder page, type a description ("buy when the 20-day EMA crosses above the 50-day and RSI 14 is under 70; sell when they cross back") and the AI fills in the rules. **You review them and save; the AI never saves or runs anything.** Requests it can't express (short selling, options, intraday, several symbols, fundamentals or sentiment) get a refusal naming what isn't supported, never a look-alike strategy. Stop-loss, take-profit and position size are run settings, so they come back as notes.

How it works (decisions D-077 to D-083):

1. `POST /api/assist/strategy/` stores the request as a job (`AssistRequest`) and returns at once; the client polls `GET /api/assist/<id>/`. The worker answers AI requests before backtests: a person is waiting, and a model call takes seconds, so it never runs inside an HTTP request.
2. The worker sends the provider a fixed system prompt and the user's text, marked as data rather than instructions. No email or account data is sent. The prompt's indicator list, parameter ranges and operators are generated from the same registry the validator uses.
3. The model must return one JSON object: a spec, or a refusal. The spec goes through `spec.validate`, the same allowlist as hand-built strategies, so whatever the model writes is data that is checked and interpreted, never executed. If validation fails, its path-keyed errors go back to the model, at most twice.
4. **Provider:** Groq (OpenAI-compatible HTTP API, no SDK), model set by `AI_MODEL`. With no provider configured the panel is hidden and everything else works.

| Control | Default | |
|---|---|---|
| AI requests per 24 h | guest 5 / unverified 10 / verified 50 | `QUOTA_<TIER>_AI_REQUESTS_PER_DAY`; one active request per user |
| Description length | 1,000 characters | `AI_MAX_PROMPT_CHARS` |
| Daily token budget (whole deployment, UTC day) | 150,000 | `AI_DAILY_TOKEN_BUDGET`; keep it below the provider's free daily limit. When used up, AI answers 503 and nothing else is affected |
| Answer cache | 7 days | the same description (ignoring case and spacing), prompt version and model reuses the earlier answer |
| Retention | 30 days | requests (including descriptions) are deleted by housekeeping, and with the account |

**Privacy:** descriptions are sent to Groq. Groq says it doesn't train on API data; switch on Zero Data Retention in the Groq console so it keeps nothing either. Descriptions never appear in Vault's logs, which record only outcomes, token counts and timings.

**Evaluation:** `python manage.py assist_eval` runs 60 cases (simple and multi-condition rules, every indicator, vague wording, Hindi-English, unsupported requests, prompt injection) live or from a recording. Answers are graded by behaviour: a spec passes if it holds exactly the same positions as a reference strategy on five fixed price series, so equivalent formulations pass and near misses fail. CI replays the committed recordings, and a prompt change fails CI until a new live run is recorded. Results (2026-11-17, Groq free tier, details in [docs/evals.md](evals.md#phase-4--ai-assistance-describe-a-strategy--spec)):

| Model | Passed | Refusals correct | Median / p95 latency |
|---|---|---|---|
| **openai/gpt-oss-120b** (default) | **60/60** | 18/18 | 1.7 s / 2.8 s |
| openai/gpt-oss-20b | 57/60 | 16/18 | 1.2 s / 1.8 s |

The first run also found a validator gap: a rule comparing something with itself ("SMA 20 crosses above SMA 20") was accepted. It is now rejected, and the repair round fixes the model's answer.

## AI research agent

On the **Research** page you give a goal ("a trend-following strategy for RELIANCE.NS that beats buy and hold, max drawdown 25%"), a symbol, a period and what to optimise (Sharpe, Calmar or total return). An agent then does the research loop itself (decisions D-088 to D-095):

1. **Explore:** it proposes clearly different strategies and backtests them as one round.
2. **Refine:** it reads the results and tries variations or searches one parameter of a promising candidate.
3. **Choose:** it picks one; a candidate must have at least 3 round trips and meet the drawdown constraint to be eligible.
4. **Held-out test (code, not the agent):** the last 30% of the period is held out. The agent never sees it, and every one of its backtests ends before it. The choice is tested there **once**.
5. **Report:** research and held-out results side by side, buy & hold for each, how many candidates were tried, whether it beat buy & hold, a summary by the agent whose every number is checked against the results (otherwise a plain summary is used), and process checks (held-out tested once, never seen by the agent, budgets respected, summary grounded, drawdown constraint on held-out data).

You see each decision and its reason in a live timeline, can open any candidate's backtest, and **save** any candidate as a strategy. The agent can spend backtests, but it can't save, change costs or stops, or reach anything outside Vault.

**How it runs:** each research run is a job. One claim is one short step (one model call, or code work). After queueing a round of backtests the run waits, so no worker is held, and the worker wakes it when the round finishes. Steps survive restarts and deploys. Each decision is one checked JSON action (`test`, `search`, `next_stage`, `choose`); a rejected one goes back to the agent with path-keyed errors. Its prompt is rebuilt from the run's state each time, so cost per step stays flat.

| Limit | Default | |
|---|---|---|
| Per research run | 8 decisions, 14 model calls, 40 backtests, 40,000 tokens | `RESEARCH_MAX_*`; when one runs out, code picks the best eligible candidate |
| Per round | 6 candidates, or 6 values in a parameter search | `RESEARCH_MAX_CANDIDATES_PER_ROUND`, `RESEARCH_MAX_SEARCH_VALUES` |
| Research runs per 24 h | guest 0 / unverified 1 / verified 3; one at a time | `QUOTA_<TIER>_RESEARCH_PER_DAY`; counts as one active job; its backtests aren't counted as yours |
| Period | at least 730 days | `RESEARCH_MIN_DAYS` |

Research tokens share the daily AI budget with the assistant. **Status:** tested with a scripted model and real backtests, plus **one live run** with gpt-oss-120b (AAPL): it completed, and reported honestly that its pick lost to buy & hold on the held-out years. That run also exposed four problems, fixed in D-096: a too-strict number check, answers cut off at the output limit, never leaving exploration, and duplicate strategies. Quality (whether its picks beat buy & hold, the best template or a random search on held-out data) **is not measured**. See [docs/evals.md](evals.md#phase-5--first-live-research-run-local-gpt-oss-120b-2026-11-17).

## Accounts and workspaces

Everything a user creates is private. Another user's run, trades or experiment returns `404`, not `403`, so the API doesn't reveal that it exists. Built-in strategies are shared and read-only.

| Tier | How you get it | Active jobs | Backtests / 24 h | Experiments / 24 h | Saved strategies |
|---|---|---|---|---|---|
| guest | "Try it as a guest" (one click, no email) | 2 | 20 | 2 | 5 |
| unverified | sign up, or save a guest workspace as an account | 3 | 30 | 3 | 20 |
| verified | click the link in the verification email, or **Sign in with Google** | 10 | 200 | 20 | 100 |

An experiment (comparison or optimization) counts as one active job while any of its runs is active. Built-in strategies don't count towards saved strategies. Every value can be overridden by an env var (`QUOTA_<TIER>_<LIMIT>`, e.g. `QUOTA_VERIFIED_RUNS_PER_DAY`). The global `MAX_ACTIVE_RUNS` still caps everyone's work combined.

- **Guests** get a temporary workspace that is deleted after `GUEST_TTL_DAYS` (7) unless they save it as an account. Their data is kept when they do.
- **Housekeeping:** the worker deletes expired guests and expired sessions once an hour, so no cron job is needed.
- **Pre-accounts data:** runs, optimizations and custom strategies created before accounts existed belong to a hidden, inactive legacy user (migration `0014`).
- **Endpoints** (`/api/auth/`): `csrf`, `me`, `signup`, `login`, `logout`, `guest`, `guest/convert`, `google`, `verify-email`, `verify-email/resend`, `password-reset`, `password-reset/confirm`, `password-change`, `email-change` and `delete-account`. `/api/dashboard/` returns everything the dashboard shows in one call.

## Operations: logs, metrics, capacity

- **Request IDs.** Every response carries `X-Request-ID` (a valid incoming one is kept, anything else replaced). The ID is on every log line written during the request and is stored on the runs and experiments the request created. The worker logs with both `request_id` and `run_id`, so "this click → this run → this worker error" is one search. The UI shows the ID in server-error messages so a user can quote it.
- **Logs** are JSON lines (`LOG_FORMAT=text` for reading locally). One access line per request: method, **route pattern** (never the raw URL, so no IDs or tokens from paths), status, duration, user ID and the proxy hop count (`xff_hops`, `via_vercel`; never the addresses); no emails. Health checks and `/metrics` aren't logged. This replaces gunicorn's access log.
- **Metrics:** `GET /metrics` in Prometheus text format, disabled (404) unless `METRICS_TOKEN` is set, then requires `Authorization: Bearer <token>`. It has HTTP rate, errors and duration by route (**per API process**: each scrape sees the process that answered), and **queue health computed from the database** (valid across all processes): queued runs by lane (interactive/batch), age of the oldest queued run, active runs, completions and failures by category in the last hour, run-time p50/p95, and stale runs.
- **API docs:** OpenAPI schema at `/api/schema/` and Swagger UI at `/api/docs/` (bundled, no CDN). On by default with `DEBUG`, otherwise only with `API_DOCS=1`. CI fails if the schema has any warning, so every endpoint is documented.
- **Error tracking:** Sentry, only if `SENTRY_DSN` is set (`SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` optional). Personal data is never sent (`send_default_pii=False`).
- **Rate limits are shared.** Throttle counters live in the Postgres table `vault_cache` (migration `0021`), written with one upsert per request; the worker's hourly housekeeping deletes expired rows. `THROTTLE_CACHE=locmem|django` exist only for load-test comparisons.

**Capacity** (measured locally, see [docs/evals.md](evals.md#phase-35--engineering-hardening); repeat on staging before relying on it). API container limited to 0.5 CPU and 512 MB like a small Render instance, 2 gunicorn processes, `DEBUG=0`, Postgres 16, Locust users browsing and starting runs with no failures:

| Users | Requests/s | p50 | p95 |
|---|---|---|---|
| 10 | 30 | 28 ms | 110 ms |
| 20 | 48 | 98 ms | 380 ms |
| 40 | 52 | 460 ms | 760 ms |
| 80 | 55 | 1.2 s | 1.4 s |

The API saturates around **50 requests/s; latency climbs past ~20 concurrent active users**. That's the point to add CPU or instances. These are single runs on a shared machine; identical repeats differed by up to a third in throughput at 20 users. Workers: one worker process completed **537 builder runs/min** (EMA crossover, ~2,900 bars), 2 workers 964, 4 workers 1,263 (sharing the machine's CPU and Postgres). Claiming a run takes ~8–12 ms median whether 100 or 100,000 runs are queued (the claim index is used).

| Env var | Default | Purpose |
|---|---|---|
| `METRICS_TOKEN` | unset (endpoint off) | bearer token for `/metrics` |
| `API_DOCS` | on with `DEBUG`, else off | serve `/api/schema/` and `/api/docs/` |
| `SENTRY_DSN` | unset (off) | error tracking |
| `LOG_FORMAT` | `json` | `text` for local reading |
| `WORKER_GRACE_S` | 20 | seconds a worker may finish its run after `SIGTERM` |
| `THROTTLE_CACHE` | `upsert` | throttle counter store; leave as is outside load tests |

**Load test** (dev only): `pip install -r requirements-dev.txt`, then `locust -f loadtest/locustfile.py --host http://<api>`. Each simulated user creates a guest, so raise `THROTTLE_*` and `QUOTA_GUEST_*` on the target, and never point it at production.

## Security

**The strategy subprocess is not a security boundary.** It runs with an AST filter (only `import math`, no `_private` attributes and no dunder names), reduced builtins, an empty environment, `cwd=/`, rlimits (CPU, address space, no forking, no file writes, no core dumps), a hard wall-clock deadline that kills the whole process group, a 4 KB limit on each output line, and strict validation of every output. That contains accidents such as infinite loops, memory blow-ups, crashes and garbage output. **It does not contain hostile Python.** It has no network or filesystem namespace, and Python introspection is broad.

For that reason:

- `ALLOW_CUSTOM_CODE` is **off by default**. With it off, creating a **code** strategy returns `403` and only built-in code strategies can run. **Builder strategies are always allowed**: a spec is data checked against an allowlist and interpreted by the engine, so no user input ever becomes code (decision D-033). The built-in code strategies are seeded by migration `0010` and the builder templates by `0017`.
- Docker Compose turns it **on for local use only**.
- Before enabling it on a public deployment, move strategy execution to a separate isolated runner: a container or VM with no network, a read-only root filesystem, a non-root user, dropped capabilities, CPU, memory and PID limits, no Docker socket, and no database or application secrets. The worker would send it only the code and the bars. This runner is **not built yet**.

Other security controls:

- Production refuses to start without `SECRET_KEY` and database credentials. `DEBUG` is off unless `DEBUG=1`.
- `ALLOWED_HOSTS` is an explicit allowlist. There is no CORS: the browser reaches the API on the frontend's own origin.
- **Sessions:** the session cookie is `HttpOnly` (JavaScript, and so XSS, can't read it), `SameSite=Lax`, and `Secure` in production. Logging in issues a new session id (no session fixation). Changing the password signs out every other session.
- **CSRF:** a double-submit token (`csrftoken` cookie echoed in `X-CSRFToken`) plus Django's Origin check. DRF only checks CSRF for users who are already signed in, so login, signup and the other anonymous endpoints enforce it explicitly. That blocks login CSRF. The token rotates on login.
- **Passwords:** PBKDF2 (Django's default, 1.2M iterations), at least 10 characters, and Django's similarity, common-password and all-numeric validators.
- **Sign in with Google** (on when `GOOGLE_CLIENT_ID` is set, D-103): Google's button gives the browser a signed ID token; the API checks its signature against Google's keys, that it was issued for Vault's client ID, the issuer, the expiry and that Google marks the email verified, then signs in with the usual session cookie. The account is verified at once and has no password. Linking to an existing **unverified** account removes its password and signs out its sessions, because whoever set them never proved they own the address (account pre-hijacking). A guest who signs in with Google keeps their data. Google-only accounts can delete themselves without a password and can't change a password or email.
- **No account enumeration:** a failed login gives the same message whether or not the email exists, and so does a password reset request.
- **Email links:** verification and reset tokens are tied to the user's state, so they stop working once used (or when the password or email changes) and expire after 24 hours.
- The API serves JSON only and has no admin. Errors return safe messages, and details go to the server logs.
- The Docker image runs as a non-root user.
- CI runs `pip-audit` and `npm audit`.

## Run locally

Prerequisite: Docker.

```bash
docker compose up --build
```

- App: http://localhost:5173 (nginx serves the SPA and forwards `/api` to Django)
- Health: http://localhost:8000/health/ready

Compose starts Postgres 16, the API (which applies migrations on start), one worker and the frontend. Bars are fetched on first use; no ingest step is needed. In development, emails (verification, password reset) are printed to the API's log instead of being sent.

Without Docker (Python 3.12):

```bash
cd backend
pip install -r requirements.txt
export DEBUG=1 DATABASE_URL=sqlite:///db.sqlite3 ALLOW_CUSTOM_CODE=1
python manage.py migrate
python manage.py runserver &          # API
python manage.py run_worker           # worker, in another shell
cd ../frontend && npm ci && npm run dev   # http://localhost:5173, proxies /api to :8000
```

The worker runs strategies in a POSIX subprocess, so on Windows run the backend in WSL (Ubuntu). The frontend can stay on Windows.

## Tests

```bash
cd backend
DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test
cd ../frontend && npm test        # Vitest + React Testing Library (jsdom)
```

CI also runs the suite on PostgreSQL 16, along with a migration-drift check, an OpenAPI schema check (no warnings allowed), `pip-audit`, frontend lint, tests and build, `npm audit` and both Docker builds. Measured results for every phase are in [docs/evals.md](evals.md). The suite covers:

- a hand-calculated buy/sell with commission and slippage
- the equity = cash + holdings invariant
- sizing that never overspends, and a win rate that is net of costs
- a no-trade run
- next-bar fills (regression test for same-bar lookahead), last-bar signals and warm-up being hidden from the strategy
- a stop and a target touched in the same bar, a gap through a stop, and an intrabar target
- sandbox cases: infinite loop, invalid output, exception, blocked imports and dunders, no `open`, huge output
- data cases: one stored bar not counting as coverage, gap labelling, invalid OHLC rejected, no data, a provider restatement replacing old bars (one price scale), a covered span not downloaded again, a failed fetch keeping stored bars, the fetch day not counted as covered
- API cases: custom code disabled, end-to-end run, a retry that does not duplicate trades, idempotency key, queue full (503), grid limit, per-user job throttle, anonymous requests rejected
- accounts: signup, login, logout, CSRF required even for anonymous login, CSRF rotation on login, session rotation, verification link (works once), password reset without account enumeration, password change signing out other sessions, email change re-verification, weak passwords rejected, guest flow and conversion, account deletion, per-IP auth and guest throttles with spoofed `X-Forwarded-For`
- isolation: other users' runs, trades and optimizations return 404; lists and dashboard show only your own items; you can't use another user's strategy; idempotency keys are per user
- quotas: guest active-job limit, rolling 24-hour daily limit, an optimization counting as one job, verification raising limits, env overrides
- housekeeping (expired guests and sessions), a worker finishing a run whose owner was deleted, and the legacy-data migration (0014)
- stale-job requeue and then fail, and an optimization still finishing when its last in-sample run fails that way
- the worker loop recycling database connections and surviving recovery errors
- the optimization list not loading equity curves, a stop tighter than slippage rejected
- partial optimization failure with exactly one out-of-sample run
- health endpoints
- builder indicators: hand-computed values, plus pandas as an independent reference for SMA, EMA, RSI, ATR, Bollinger, Donchian and ROC
- **no look-ahead (metamorphic test):** rewriting every bar after *t* changes no indicator value or decision at or before *t*
- **parity (differential test):** the builder version of "SMA Crossover (10/50)" makes exactly the same trades and equity curve as the Python built-in
- spec validation (every error reported with its path), canonical hashing, warm-up, signals (crossovers, exit wins, missing values), read-only Python rendering
- India costs hand-calculated, the engine charging the sell rate on sells, currency inference
- builder API: create with custom code off, edit and delete rules, saved-strategy limit, catalog and preview, an end-to-end run that freezes the spec and is deterministic on re-run, an India-cost run and optimization; no test may reach the real data provider
- frontend: form ↔ spec round trip, the builder page (indicator parameters, condition limit, numbers saved as numbers, server errors on the exact field, templates), money formatting
- experiments: a comparison matrix with benchmarks end to end, **a comparison cell equal to the same standalone run**, validation and idempotency, partial failure; parameter grids with linked paths, skipped invalid combinations and rejected bad values; the old `/api/optimizations/` route
- queue and worker: **priority lanes** (a hand-started run claimed before older batch children), **4 real worker threads on Postgres never claiming a run twice**, worker caches giving identical results and never serving bars after a re-download, time-based heartbeat (no writes for fast runs, still beating for slow ones)
- curve downsampling keeping extremes and ends, the new metrics hand-checked, tunable-parameter grouping
- frontend: comparison form (cell count and limits, request body), experiment page (heatmap values and colours, benchmark row, failures, metric switch; optimization columns and skipped combinations)
- AI assistance (no test reaches the network): a valid answer, code fences tolerated, validator errors sent back and repaired, giving up after the repair budget, refusals, answers that aren't a spec (including `import os` as the spec) rejected, bounded names and notes, the Groq client (request shape, retry after a rate limit, no retry on a bad key, non-JSON output handed to repair), the API end to end with the request ID stored, off without a key, other users' requests 404, length limits, one-at-a-time and daily quotas, the answer cache, the token budget, failures not retried, descriptions never logged and never sent with account data, shutdown requeue, stale requests failed, old requests deleted, AI requests answered before backtests, `/metrics`; the evaluation's grading (equivalent formulations match, near misses don't, every reference trades), a perfect and a lazy fake model, and the committed live recordings replaying to their recorded scores; frontend: the panel hidden without AI, filling the form and showing notes, showing a refusal without touching the form
- AI research agent (scripted model, real backtests): a complete run (explore, refine with a parameter search, choose, held-out test, report), the held-out period never in the agent's prompts and tested exactly once, rejected actions returned with exact errors, budgets ending a run with code's choice, clean failure when nothing is eligible, an invented number in the summary caught, waiting without holding a worker, crash recovery, shutdown, the shared daily AI budget, the hidden placeholder strategy, research rounds kept out of experiment lists and quotas, every action check; frontend: starting a run, progress and timeline, the report with checks, saving a candidate, a failed run
- operations: JSON log lines with request and run IDs, request IDs kept or replaced and stored on runs, the access line using the route pattern, `/metrics` (off without a token, Bearer check, queue health), throttle counters shared between cache instances and written in one statement, expired cache rows removed, the OpenAPI schema generated without warnings, and graceful shutdown (no claims after `SIGTERM`, a run past the grace period requeued without using an attempt)

## Deploy (Vercel + Render)

Flow: push to GitHub, CI runs, and Vercel and Render auto-deploy from `main`. Turn on Render's "auto-deploy after CI checks pass" so a red build does not ship.

**Frontend (Vercel):** root `frontend/`, build `npm run build`, output `dist/`. `frontend/vercel.json` rewrites `/api/*` to the Render API host (`vault-api-pqje.onrender.com`; change it if the API moves). That rewrite is what makes `/api` same-origin. Don't set `VITE_API_URL` (v1 used it; remove it from the Vercel project).

**API (Render web service, Docker, root `backend/`):**

| Setting | Value |
|---|---|
| Start command | default image `CMD` (`./start.sh`, which runs gunicorn) |
| Pre-deploy command | `python manage.py migrate --noinput` (if your plan has it). Otherwise set `RUN_MIGRATIONS=1` on a **single-instance** service |
| Health check path | `/health/ready` |
| Env | `SECRET_KEY` (generate), `DATABASE_URL` (from Render Postgres), `ALLOWED_HOSTS=<api-host>`, `CSRF_TRUSTED_ORIGINS=https://<vercel-domain>`, `FRONTEND_URL=https://<vercel-domain>` (links in emails), `SECURE_PROXY_SSL_HEADER=1`, `DB_SSLMODE=require` |
| Email | `EMAIL_HOST`, `EMAIL_PORT` (587), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` (any SMTP provider, e.g. Resend). Without `EMAIL_HOST`, emails go to the log |
| `NUM_PROXIES` | the number of proxies between the browser and the API. Measure it, don't guess: each access log line has `xff_hops` (and `via_vercel`); set `NUM_PROXIES` to `xff_hops` for requests made through the frontend domain. Vercel → Render measured **4** (D-101) |
| Optional | `SECURE_HSTS_SECONDS=31536000` once HTTPS is verified, `WEB_CONCURRENCY`, `METRICS_TOKEN`, `SENTRY_DSN`, and the limits listed above |
| Google sign-in (optional) | `GOOGLE_CLIENT_ID`: a Google OAuth *web* client ID (public, not a secret) with the frontend's origin as an authorized JavaScript origin. Without it the button is hidden |
| AI (optional) | `AI_PROVIDER=groq`, `GROQ_API_KEY` (a secret), `AI_MODEL`, `AI_DAILY_TOKEN_BUDGET` below the provider's daily limit. Set them on the API (it reports whether AI is on) **and** the worker (it makes the calls) |

**Worker (Render background worker, same repo and image):** command `python manage.py run_worker`, with the same env as the API minus the HTTP-only settings. Keep `WORKER_GRACE_S` below the platform's shutdown window (Render: 30 s).

**No budget for a separate worker?** Set `EMBEDDED_WORKER=1` on the web service. Each gunicorn process then starts one queue-consumer thread. Jobs stay durable because the queue is in Postgres, but backtests then compete with HTTP traffic for CPU. On a free plan that sleeps when idle, queued jobs wait until the service wakes, and interrupted jobs are recovered as stale.

**Database:** standard managed PostgreSQL. Migrations `0009`–`0011` upgrade an existing v1 database in place:

- builtin strategies are seeded
- links from old optimizations to their runs are kept
- each old run gets a code snapshot
- `pending` runs are re-queued
- `running` runs are marked failed

**Back up the database before the first v2 deploy.**

Rollback: redeploy the previous image from Render's deploy history. Migrations 0009–0011 are not reversible without data loss, so restore from the backup if you need to go back to v1 code.

**The live deployment (since 2026-11-17, D-097):** Vercel `vault-lovat-beta.vercel.app` → Render `vault-api-pqje` (free plan, Docker, `EMBEDDED_WORKER=1`, `RUN_MIGRATIONS=1`) → Render Postgres 16 (free; **expires 2026-12-10**: upgrade it or move the data before then with `pg_dump` / `pg_restore`). Follow-up changes are PRs to `main`; each merge deploys (D-100). Smoke-test **through the Vercel domain**, not only the Render URL: the release's one routing bug only showed there (D-098).

**Market data on Render:** Yahoo refuses requests from Render's IPs (D-099). Symbols must be loaded from a machine Yahoo accepts, using Vault's own fetch code against the production database (`DATABASE_URL` = the database's external URL, `DB_SSLMODE=require`): `load_bars(symbol, date(2005, 1, 3), date.today(), warmup_bars=0)` for each symbol. The 17 suggested symbols and `^GSPC` were loaded on 2026-11-17. Until a fallback provider exists, other symbols fail on production with "No market data", and stored prices don't update by themselves.

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

- *A user reports an error:* ask for the request ID shown in the message and search the logs for it. The run (if any) has the same `request_id`, and the worker's lines for it carry its `run_id`.
- *Is the queue healthy?* `curl -H "Authorization: Bearer $METRICS_TOKEN" https://<api-host>/metrics`: `vault_queue_depth`, `vault_queue_oldest_age_seconds` and `vault_runs_stale` show a backlog or a dead worker.
- *A job looks stuck:* check `status`, `heartbeat_at`, `attempts` and `worker_id` on the run. Recovery runs every 30 s in each worker. It also queues the out-of-sample run for any optimization whose in-sample runs have all finished. If no worker is running, jobs stay `queued`.
- *Queue full (503):* there are more than `MAX_ACTIVE_RUNS` active runs. Add a worker or raise the limit.
- *Database down:* `/health/ready` returns 503. API calls return a safe 500 or 503 without a stack trace. Workers log the error and keep polling. They drop broken connections at the top of each loop, so they reconnect once the database is back.
- *"No market data" on production for a valid ticker:* Yahoo blocks Render; load the symbol from another machine (see Deploy, "Market data on Render").
- *Yahoo down:* runs over data that is already stored still work. Runs that need new data fail with category `data` and the message "No market data".

## Design decisions

- **Kafka removed.** Replaying a finite, ordered history needs an ordered query, not a broker. Kafka never prevented lookahead: v1 filled at the same close the strategy had just seen. Lookahead is prevented by the fill model in the engine. Kafka added one topic per run, broker startup dependencies, a 15 s consumer timeout that could pass off a truncated stream as complete, and a paid service in production.
- **Redis removed.** v1 used Redis for an indicator cache keyed without a data revision (so it could go stale) and for progress values whose failures were silently ignored. SMAs are now computed during the replay, which is trivial work, and progress lives on the run row.
- **Postgres as the queue instead of Celery + Redis.** `SELECT … FOR UPDATE SKIP LOCKED` gives a durable queue with no extra infrastructure. This is enough at portfolio scale. Move to Celery or a dedicated queue if queue throughput becomes the bottleneck, which it is not at one job per worker.
- **TimescaleDB dropped.** The v1 README told users to manually drop the `bar` primary key, which made the schema diverge from the migrations. A few thousand daily bars per symbol do not need hypertables.
- **Built-in-only public demo.** Exposing an unsafe code runner would be worse than having none.

## Known limitations

- There is no isolated strategy runner yet, so custom code is disabled on public deployments (see [Security](#security)).
- HTTP metrics on `/metrics` are per API process (queue metrics are global). Summing across processes needs a scraper that reaches each one, or a shared metrics store.
- In production the API docs page is served through Django with `API_DOCS=1` (fine for occasional use; it is off by default).
- No "Sign in with Google" yet, and no multi-factor authentication.
- Admission control (`MAX_ACTIVE_RUNS`) is a soft cap: concurrent requests can overshoot it slightly.
- Strategies are long only, single asset, daily bars, with no shorting, leverage, dividends-as-cash or order types beyond market-on-open and stop/target.
- Builder specs have flat AND/OR groups (no nesting) and eight indicators. Smoothed indicators (EMA, RSI, ATR, MACD) depend slightly on how much history precedes the start date, as in any charting tool.
- The India cost model covers percentage charges only (no DP charges or minimum brokerage), and its rates are fixed in code. Currency is inferred from the symbol for display only.
- Rolling back migration `0016` rounds 9-decimal fee rates to 6 places and leaves builder strategies with no code.
- Out-of-sample evaluation uses a single chronological split. Walk-forward evaluation and parameter-sensitivity reports are not built (D-061).
- Worker caches are per process: several workers each warm their own. An experiment's limit stays 25 child runs: a 25-child batch takes about 3 s on one worker, so the limit is about result readability, not capacity.
- Runs created by the v1 engine are flagged in the UI as unreliable. Re-run them.
- The research agent has had one live run so far, and its fixes (D-096) are tested but not yet confirmed live. Its quality (vs buy & hold, the best template and a random search on held-out data) hasn't been measured. One symbol per run; its held-out test is a single period.
- AI answers can be wrong in ways the validator can't see (a valid strategy that isn't what you meant), which is why the AI only fills the form for you to review. The provider's free limits are shared by the whole deployment, and providers retire models; switching `AI_MODEL` needs a new evaluation run.
- Capacity numbers come from a local machine with Render-like container limits, not from Render itself; repeat the load test on staging.
