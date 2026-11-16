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

## Security (from Phase 1, still relevant)

| Concept | Where |
|---|---|
| Session cookie `HttpOnly`, `SameSite=Lax`, `Secure` | settings |
| CSRF double-submit + Origin check; login CSRF | `accounts/views.py` `CsrfEnforced` |
| Same-origin API instead of CORS | Vercel rewrite, Vite proxy, nginx |
| 404 instead of 403 for other users' objects | every queryset filtered by owner |
| No account enumeration | login and reset responses |
| Sandbox is not a security boundary | custom code off in production; builder needs no sandbox |
