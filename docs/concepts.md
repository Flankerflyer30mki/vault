# Concepts

A revision sheet: each concept Vault uses, where it lives in the code, and a line you can say in an interview.
Decisions are in [decisions.md](decisions.md); measured evidence in [evals.md](evals.md).

## Three lines to remember
1. **"The API accepts only data; user input never becomes code."** Builder strategies are JSON interpreted against an
   allowlist, which is why they can run on the public site while custom Python stays off. (D-033)
2. **"I prove there's no look-ahead with a metamorphic test, not by assertion."** Rewrite every bar after *t*; nothing
   at or before *t* may change. (`NoLookaheadTests`)
3. **"The builder version matches the hand-written strategy trade for trade."** A differential test, also confirmed
   through the real sandbox: 80/80 fills identical, and the builder is 9.8× faster. (`ParityTests`, evals)

---

Phase 3 adds a fourth: **"I profiled before optimising: the cache I planned saved 13%, the heartbeat the profile found saved
three times more; 25 backtests now take 2.4 s instead of 5.7 s on one worker."**

## Trading and backtesting

| Concept | What it is | Where in Vault | Interview line |
|---|---|---|---|
| Backtest | Replaying a strategy over historical prices to see what it would have done | `engine.simulate` | "Bars in, ledger out; the engine is pure, so it's deterministic and testable without a database." |
| Look-ahead bias | Using information that wasn't available at decision time | Decide on bar *t*, fill at the open of *t+1* (`engine.py`); indicators use bars ≤ *t* | "The fill model removes same-bar look-ahead; a metamorphic test proves indicators don't peek." |
| Slippage and commission | Execution costs: worse price than quoted, plus fees | `Params`, charged once per fill | "Costs are charged exactly once, and sizing includes them so cash never goes negative." |
| Stop-loss / take-profit | Exit at a loss or profit threshold | Engine; "stop wins" if both touched in one bar | "When the data can't tell which came first, assume the worse outcome." |
| Mark to market | Value an open position at the latest price | Final equity = cash + qty × last close | "Open positions aren't magically liquidated at the end." |
| Equity invariant | `equity = cash + quantity × close` on every bar | Engine; tested | "Every metric derives from one equity curve, so they can't disagree." |
| Sharpe, CAGR, drawdown, win rate | Risk-adjusted return, annual growth, worst peak-to-trough, % profitable round trips | `engine.metrics` | "Win rate is net of costs; Sharpe is null when volatility is zero instead of infinity." |
| Sortino | Like Sharpe, but only losing days count as risk (downside deviation) | `engine.metrics` | "Upside volatility isn't risk." |
| Calmar | CAGR ÷ max drawdown | `engine.metrics` | "Growth per unit of worst pain." |
| Exposure, cost drag | Share of bars in the market; costs as a share of starting cash | `engine.metrics`, run serializer | "A strategy that's rarely invested should be judged against that." |
| Benchmark | What a passive alternative earned | NIFTY 50 / S&P 500 buy-and-hold child in comparisons | "Beating zero isn't the bar; beating the index is." |
| Overfitting / data snooping | Tuning until the rules fit noise | Optimizations: in-sample grid, one out-of-sample run | "Judge by the out-of-sample run, never the best in-sample number." |
| In-sample vs out-of-sample | Data used to choose parameters vs data held back to test them | `OOS_FRACTION` = 30%, chronological split | "Time-ordered split, because shuffling time series leaks the future." |
| Adjusted prices | Prices restated after splits and dividends | `data_fetch.py` replaces a symbol's whole span on fetch | "Never mix rows fetched at different times: they can be on different price scales." |
| Survivorship bias | Testing only stocks that still exist | Not handled (known limitation) | "A known limitation, stated rather than hidden." |
| Long-only | Either fully invested or in cash; no shorting | Engine (D-036) | "Indian retail traders can't hold a short overnight in the cash market, so allowing it would be unrealistic." |
| Warm-up / lookback | Bars an indicator needs before it has a value | `spec.warmup_bars`, `load_bars(warmup_bars=…)` | "Warm-up is derived from the spec: SMA-200 gets 200 bars, smoothed indicators 3× their period." |

## Indicators (`backend/backtester/indicators.py`)

| Indicator | Formula | Trap to mention |
|---|---|---|
| SMA | mean of the last *n* closes | Builder SMA uses the same Decimal arithmetic as the built-in `sma_N`, so parity is exact |
| EMA | `α·x + (1−α)·prev`, α = 2/(n+1), seeded with an SMA | Depends on its starting point → needs extra warm-up |
| RSI (Wilder) | 100 − 100/(1 + avg gain / avg loss), Wilder smoothing α = 1/n | Many implementations use a simple average and get different numbers |
| MACD | EMA(12) − EMA(26); signal = EMA(9) of that; hist = line − signal | First multi-output indicator → the spec has an `output` field |
| Bollinger | SMA ± k·σ | Population vs sample σ: pick one and document it (population) |
| ATR | Wilder average of true range = max(H−L, \|H−prevC\|, \|L−prevC\|) | True range includes gaps; H−L alone doesn't |
| Donchian | highest high / lowest low of the *n* bars **before** this one | Including the current bar makes "close > highest high" impossible |
| ROC | 100 × (close / close[n] − 1) | Percent, not fraction |
| Crossover | prev `a ≤ b` and now `a > b` | Needs state across two bars, so it's an operator, not a comparison |

## Indian market costs (`backend/backtester/costs.py`)

| Charge | Rate (delivery) | Note |
|---|---|---|
| Brokerage | broker's choice (0 for many discount brokers) | the user's input |
| STT | 0.1% buy and sell | securities transaction tax |
| Exchange transaction charge | 0.00297% (NSE) | both sides |
| SEBI turnover fee | ₹10 per crore | both sides |
| Stamp duty | 0.015% | **buy only**, which is why buy and sell rates differ |
| GST | 18% of brokerage + exchange charge + SEBI fee | not on STT or stamp duty |
| DP charge | flat per sell, per scrip | not modelled (the engine charges percentages) |

Interview line: "One commission rate can't express stamp duty on buys only, so the engine has separate buy and sell rates."

## Design and engineering

| Concept | What it is | Where in Vault | Interview line |
|---|---|---|---|
| DSL (domain-specific language) | A small language for one domain | The JSON strategy spec | "Users describe what they want, not how to compute it." |
| Interpreter pattern | Walk a tree and evaluate each node | `spec.signals`: operand → series, condition → bools, group → all/any | "A fixed set of operators means a fixed attack surface." |
| Data, not code | Never `eval`/`exec` user input or build code from strings | Builder path never generates code; `render_python` is display-only | "The Python you see is a rendering; nothing executes it." |
| Allowlist validation | Accept only known values; reject everything else | `spec.validate` rejects unknown keys, booleans posing as numbers, NaN | "Validate by allowlist, not by blocklist." |
| Bounded input | Limits on size and complexity | ≤ 10 conditions, periods ≤ 200, 8 KB spec, warm-up ≤ 600 | "Every limit is also denial-of-service protection." |
| Errors keyed by path | `entry.all[1].right.params.period` | Validator → API → field in the UI | "The UI puts each error on the exact input." |
| Schema versioning | `"version": 1` | Spec | "Later phases can extend the format without breaking saved strategies." |
| Canonical JSON + hash | Sorted keys, fixed separators, SHA-256 | `spec.spec_hash`, stored on each run | "Same strategy, same hash, whatever the key order." |
| Immutable snapshot | Copy what a job will run at creation | `jobs.frozen_strategy` → `strategy_spec` / `strategy_code` | "Editing a strategy never rewrites history." |
| Functional core, imperative shell | Pure logic wrapped by I/O | `engine`, `indicators`, `spec` are pure; `jobs` does I/O | "The core is tested without a database in milliseconds." |
| Precompute + deduplicate | Compute each distinct indicator once, over all bars | `signals` caches by `(indicator, params)` | "Three conditions on RSI-14 share one computation." |
| Server-driven UI | The server describes the form | `GET /api/strategies/catalog/` | "Add an indicator to the registry and it appears in the UI with no frontend change." |
| Single source of truth for validation | Client doesn't re-implement rules | Live `POST /strategies/preview/`, `noValidate` form | "The client can never accept something the server rejects." |
| Database check constraint | Invariants enforced by the DB | `ck_strategy_kind_body`, `ck_strategy_builtin_xor_owner` | "Neither the API nor a script can create an invalid row." |
| Row lock for quotas | `SELECT … FOR UPDATE` on the user row | `IdempotentCreate`, strategy create | "Check-then-act races fixed per user, so other users never wait." |
| Queue in Postgres | `FOR UPDATE SKIP LOCKED` | `jobs.claim` | "A durable queue without Redis or Celery." |
| Semantic versioning | major.minor.patch | `ENGINE_VERSION` 2.1.0 stored per run | "Minor = new capability, same results for old strategies (proven by the parity test)." |
| Expand–contract migration | Add nullable → backfill → require | Phase 1 owners (0013–0015) | "Zero-downtime schema changes." |
| Fan-out / fan-in | One request becomes many jobs; a result is assembled from all of them | `Experiment` → child runs; `experiment_status`, `finish_optimization` | "One batch abstraction for comparisons, optimizations and, later, the agent." |
| Derived state | Compute status from the source of truth instead of storing a copy | `experiment_status` from the children | "No status column to drift out of sync." |
| Priority queue lanes | Interactive work claimed before background batch work | `ORDER BY priority, id` + `idx_run_claim` | "A click isn't stuck behind 25 batch jobs: 25 ms instead of 1.26 s, measured." |
| No pre-emption | Running work always finishes; priority only affects what starts next | `claim` | "Priority without the complexity of killing jobs." |
| LRU cache | Bounded map that evicts the least recently used entry | `cache.LRU` for bars and indicator series | "Bounded memory; a miss just recomputes." |
| Cache invalidation by key | Put the data's version in the key so stale entries are never hit | bars key includes `SymbolCoverage.fetched_at`; indicators keyed by data hash | "I never delete stale entries; they just stop matching." |
| Profiling before optimising | Measure where time goes, then fix that | `cProfile` on `jobs.execute` found 70% in heartbeat writes | "The planned fix (cache) helped; the profile found a fix three times bigger." |
| Heartbeat interval | How often a worker proves it's alive | ≤ 1/s vs a 120 s stale timeout | "Tune it to the failure detector, not to the work size." |
| Downsampling (min/max per bucket) | Shrink a series for display, keeping its extremes | `cache.downsample` | "A chart can't show more points than pixels; drawdowns must survive." |
| Hand-written rename migration | Rename instead of drop-and-create | `0018_experiments` | "Autogenerated migrations can silently drop data on renames." |
| API compatibility alias | Keep an old route mapped to the new view | `/api/optimizations/` → experiments | "Old tests run unchanged against the new code." |
| Combinatorial grid with constraint pruning | Cartesian product; invalid combinations skipped and reported | `OptimizationCreateSerializer` | "Fail the request for a bad value; skip only what's invalid in combination." |
| Correlation (request) ID | One ID follows a request through every log line and into the jobs it creates | `RequestContextMiddleware`, `request_id` on runs, `jobs.work_one` | "A user quotes the ID from the error and I find the request, the run and the worker's traceback in one search." |
| Context variables | Per-request (per-thread/task) state without passing it through every function | `request_id_var`, `run_id_var` read by the log filter | "Every log line gets the IDs without changing any call site." |
| Structured (JSON) logging | Log lines as key/value objects, not prose | `JSONFormatter` | "Logs you can query, not grep." |
| RED metrics | Rate, Errors, Duration per endpoint | middleware → `/metrics` | "The three numbers that tell you whether users are hurting." |
| Prometheus exposition format | Plain-text metrics any scraper understands | `/metrics`, `ops.render_queue_metrics` | "No client library needed; any monitoring stack can read it later." |
| Low-cardinality labels | Label metrics by route pattern, never by raw URL or user | `route` label = `api/runs/<int:pk>/` | "One series per endpoint, not one per run ID." |
| Queue health as SQL | Derive backlog, age, failures from the queue table | `ops.queue_snapshot` | "The queue is Postgres, so its health is a query that's true for every process." |
| Distributed rate limiting | Counters shared across processes and machines | `UpsertDatabaseCache` (`vault_cache`) | "Two processes with their own counters double every limit; I measured 20 logins against a limit of 10." |
| Upsert | `INSERT … ON CONFLICT DO UPDATE`: insert or update in one atomic statement | `throttle_cache.set` | "Django's cache did five round trips per write; one statement brought back the lost throughput." |
| Graceful shutdown | On `SIGTERM`: stop taking work, finish or hand back what's in progress before the deadline | `jobs.SHUTDOWN`, `run_worker` signal handlers | "A deploy puts the run back in the queue in 2 s instead of leaving it stuck for 2 minutes." |
| Grace period vs kill window | Finish within less time than the platform waits before `SIGKILL` | `WORKER_GRACE_S` 20 s < Render's 30 s | "Hand the run back while we still can, not after we're killed." |
| Contract-first API docs (OpenAPI) | A machine-readable description of every endpoint | drf-spectacular, `/api/schema/`, CI `--fail-on-warn` | "The docs can't drift, because CI fails when they would." |
| Load testing and the knee | Raise concurrent users until latency climbs while throughput stops growing | Locust: knee ~20 users, ~50 req/s on half a CPU | "Capacity is a measured number, and the knee is where I'd scale." |
| Percentiles (p50/p95/p99) | Latency most users get vs what the slowest see | load-test tables, run-time p95 metric | "Averages hide the tail; p95 is what a busy user feels." |
| Secure-by-default ops endpoints | Off unless configured; constant-time token comparison | `/metrics` 404 without `METRICS_TOKEN`, `hmac.compare_digest` | "An ops endpoint shouldn't be a new attack surface." |

## AI engineering (Phase 4)

| Concept | What it is | Where in Vault | Interview line |
|---|---|---|---|
| Structured output | Make the model answer in a fixed machine-readable shape | JSON mode + one-object contract (`spec` or `unsupported`) | "The model returns data in my schema, not prose I have to parse." |
| LLM output as untrusted input | Validate everything the model says, as you would a user | `spec.validate` on every answer; nothing executed | "A wrong or manipulated answer costs a retry, never safety." |
| Validate-and-repair loop | Feed the validator's errors back so the model fixes its answer | `strategy.generate`, ≤ 2 rounds, path-keyed errors | "The validator's own messages are the best repair prompt." |
| Grounding the prompt in the code | Generate the prompt's catalog from the same registry the validator uses | `prompts._catalog()` from `indicators.REGISTRY` | "Add an indicator and the AI knows it, with no prompt edit." |
| Few-shot examples | Worked examples in the prompt | `prompts.EXAMPLES` (kept out of the eval set) | "Examples teach the format; the eval proves they don't leak answers." |
| Refusal as a first-class answer | The model must say "can't" instead of approximating | `"status": "unsupported"` with a reason | "Long-only means shorting is refused, not quietly turned into something else." |
| Prompt injection | User text trying to override instructions | text fenced as data; injection cases in the eval; a canary string | "I test that it refuses and never leaks the prompt (a canary must never appear)." |
| Provider abstraction | One interface; vendors behind it; fakes for tests | `providers.py` | "Switching vendors changes one file; CI never calls a model." |
| Record/replay testing | Record live answers once, replay them in CI | `RecordingProvider`, `ReplayProvider`, committed recordings | "Evals in CI are free and deterministic, and fail when the prompt changes unmeasured." |
| Behavioural (execution-based) grading | Judge generated code/specs by running them, not by text match | `grading.match`: identical positions on 5 series | "Two different JSONs that trade identically are both right; one period off is wrong." |
| Ablation | Remove one part at a time to see what it earns | bare → catalog → examples → repair | "Each part of the prompt has a measured contribution." |
| Golden dataset with categories | Fixed cases covering normal, edge and adversarial inputs | 60 cases in 8 categories | "Per-category scores show where it fails, not just an average." |
| Token budget and rate limits | Cap spend per day; back off on 429s | `AI_DAILY_TOKEN_BUDGET`, `retry-after` | "Free tiers are per deployment, so one user can't spend everyone's tokens." |
| Response cache | Reuse answers to identical inputs | prompt hash = version + model + normalised text | "The cache key includes the prompt version, so a better prompt invalidates old answers." |
| Human in the loop | The AI proposes; a person approves | the form is filled, never saved | "For anything that costs money or changes data, the model drafts and a person decides." |
| Data minimisation | Send and keep only what's needed | only the description goes out; 30-day retention; never logged | "The provider never sees an email; our logs never see the description." |

## Testing

| Concept | What it is | Where in Vault |
|---|---|---|
| Reference (golden) test | Compare with known-correct values within a tolerance | `IndicatorReferenceTests`: hand values + pandas |
| Independent reference implementation | A second implementation computes the same thing differently | pandas `rolling`/`ewm` vs our loops |
| Floating-point tolerance | `abs(a−b) ≤ ε·max(1,|b|)` instead of `==` | Indicators; money stays `Decimal` |
| Metamorphic test | Change input in a known way, check a relation holds | `NoLookaheadTests` |
| Differential (parity) test | Two implementations must agree | `ParityTests`; also through the real sandbox in the benchmark |
| Round-trip test | `A → B → A` gives back `A` | `spec.test.js`: form state ↔ spec |
| Negative tests | Invalid input rejected with the right error | 13-problem spec → 13 path-keyed errors |
| Hermetic tests | No network or outside state | `download` patched; the test fails if called (D-048) |
| Migration rehearsal | Run real migrations on realistic data, up and down | evals: 156 ms up, 198 ms down, 13/13 checks |
| Component testing | Render, act like a user, assert what they see | `StrategyBuilder.test.jsx` (Testing Library) |
| Benchmarking | Measure, don't guess; report median and range | evals: builder 30.4 ms vs sandbox 298.8 ms |
| Concurrency test with real workers | Several threads with their own DB connections drain one queue | `ConcurrentWorkerTests`: 40 runs, 4 workers, every `attempts = 1` |
| Equivalence test | The new path gives the same answer as the old one | a comparison cell = the same standalone run; cache on = cache off |
| Query-plan check | `EXPLAIN` proves an index is used | migration rehearsal: claim query uses `idx_run_claim` |
| Load test | Simulated users against a resource-limited server; throughput and percentiles per step | `loadtest/locustfile.py`, evals Phase 3.5 |
| Query-count assertion | Count the SQL statements an operation runs | upsert cache: 1 statement vs ≥ 3 for Django's |
| Benchmark against real processes | Real `run_worker` processes and signals instead of in-process calls | worker throughput, shutdown with a real `SIGTERM` |
| Measurement noise | Repeat identical runs before claiming a difference | load-test repeats differed by up to a third; only repeated differences are claimed |

## Security (from Phase 1, still relevant)

| Concept | Where |
|---|---|
| Session cookie `HttpOnly`, `SameSite=Lax`, `Secure` | settings |
| CSRF double-submit + Origin check; login CSRF | `accounts/views.py` `CsrfEnforced` |
| Same-origin API instead of CORS | Vercel rewrite, Vite proxy, nginx |
| 404 instead of 403 for other users' objects | every queryset filtered by owner |
| No account enumeration | login and reset responses |
| Sandbox is not a security boundary | custom code off in production; builder needs no sandbox |
