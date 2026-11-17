# Improvements

Every improvement made so far, in one place: **why** it was needed, what it was **before**, the **change**, and the
**result**. Numbers come from [evals.md](evals.md); a result marked *(test)* is proven by an automated test rather than a
timing. Decisions behind each change are in [decisions.md](decisions.md).

## Headline numbers

| Improvement | Before | After | Phase |
|---|---|---|---|
| Builder strategy vs sandboxed code, same strategy, 2,520 bars | 298.8 ms | **30.4 ms (9.8× faster)**, identical 80/80 fills | 2 |
| Time per run inside a 25-run experiment | 174 ms | **37–39 ms (4.5× faster)** | 3 |
| 25-run experiment on one worker | 5.7 s | **2.4 s (2.4× faster)** | 3 |
| Hand-started run queued behind a 25-run batch | waited behind 22 runs (1.26 s) | **starts next (25 ms)** | 3 |
| Data sent per curve on experiment pages (≈ 2,500-bar runs) | every point | **≤ 500 points**, extremes kept | 3 |
| Test that silently called Yahoo | 2.6 s, real data | **~30 ms, fixture data, network forbidden** | 2 |
| Password hashing in tests | 209.7 ms per hash | **0.024 ms** (test-only hasher) | 1 |
| Known vulnerabilities (`pip-audit`) | 2 advisories | **0** | 0 |
| Indicators available to strategies | 2 (SMA-10, SMA-50) | **8, any period 2–200** | 2 |
| Ways to compare strategies | none | **strategies × symbols matrix + index benchmark** | 3 |
| Logins allowed by a 10/min limit (2 API processes) | 20 | **exactly 10** | 3.5 |
| API throughput at saturation with shared rate limits | 31–41 req/s (stock DB cache) | **52–55 req/s** (upsert) | 3.5 |
| Run interrupted by a deploy | stuck 120–150 s, one retry used | **requeued in 2.26 s**, no retry used | 3.5 |
| Endpoints in the API docs | none (first schema: 17 left out) | **32 operations, 0 warnings, CI-enforced** | 3.5 |
| Known capacity | unknown | **~50 req/s, ~20 users per small API instance; 537 runs/min per worker** | 3.5 |
| Describe a strategy in words → correct strategy | not possible | **60/60 cases, 18/18 refusals, 1.7 s median** (gpt-oss-120b) | 4 |
| Rule comparing something with itself (never fires) | accepted by the validator | **rejected; found by the AI evaluation** | 4 |
| AI prompt: catalog + examples vs format only (gpt-oss-20b, 52 cases) | 54% | **94%** | 4 |
| Re-measuring the AI after a change | ~130,000 tokens, ~20 min | **1 model call** (`--reuse`) | 4 |
| From a goal to a tested strategy | by hand, idea by idea | **AI research agent; held-out test by code, exactly once** (tests only, no live run yet) | 5 |

---

# Phase 0 · Bug fixes

### 0.1 · One price scale per symbol
**Why:** Yahoo restates adjusted prices after every split or dividend. Mixing rows fetched at different times puts two price
scales in one series, which corrupts every indicator and return.
1. **Before:** new bars were inserted next to old ones. After a 2-for-1 split, old ~100 prices sat next to new ~50 ones.
2. **Changes made:** a fetch re-downloads the symbol's whole known span and replaces its bars in one transaction (upsert).
3. **Result:** the regression test fails on the old code (old and new scales side by side) and passes on the new *(test)*.

### 0.2 · Stop re-downloading what Yahoo doesn't have
**Why:** a recently listed stock or a long market closure never "fills" its requested span, so the old coverage guess
downloaded it again on every run.
1. **Before:** coverage was guessed from the stored bars; gaps triggered a download every time.
2. **Changes made:** a `SymbolCoverage` table records the span already requested; the fetch day itself is never counted.
3. **Result:** a covered span is served from the database; a failed or empty fetch keeps old bars and records nothing *(tests)*.

### 0.3 · Optimizations that never finished
**Why:** if the last in-sample run failed through stale-job recovery, nothing ever queued the out-of-sample run.
1. **Before:** the optimization stayed `running` forever.
2. **Changes made:** the recovery loop sweeps for optimizations whose in-sample runs are all finished and queues the missing run (idempotent).
3. **Result:** the test shows `running` before the sweep and `partially_completed` with exactly one out-of-sample run after it *(test)*.

### 0.4 · Worker survives a database restart
**Why:** outside a request Django never recycles connections, so a worker kept a dead connection forever.
1. **Before:** after a database restart the worker failed every loop; a recovery error crashed the loop.
2. **Changes made:** `close_old_connections()` at the top of each loop; recovery moved inside the error handler.
3. **Result:** the worker reconnects and keeps running *(test)*.

### 0.5 · Rate limits couldn't be dodged
**Why:** the client IP was read from `X-Forwarded-For`, which any client can set.
1. **Before:** a made-up header gave unlimited requests.
2. **Changes made:** `NUM_PROXIES` (trusted proxy count) decides which address is real.
3. **Result:** a spoofed header no longer bypasses the throttle *(test)*.

### 0.6 · A stop tighter than slippage is rejected
**Why:** entries fill at `open × (1 + slippage)`, so a smaller stop sits above the fill and stops out every trade on its first bar.
1. **Before:** accepted silently; results were meaningless.
2. **Changes made:** the API rejects `stop_loss_pct ≤ slippage_pct` (the engine itself was correct).
3. **Result:** `400` with the field named *(test)*.

### 0.7 · Lists load only what they show
**Why:** the optimization list loaded every child run's full equity curve just to show a status.
1. **Before:** every curve of every child was read from the database for each list request.
2. **Changes made:** `Prefetch(... only(...))` and `defer(...)` on list queries.
3. **Result:** curves are never loaded for lists *(test asserts the field is deferred)*.

### 0.8 · Clear errors and a clean dependency audit
1. **Before:** an unrelated `IntegrityError` turned into a confusing 500; `pip-audit` reported 2 advisories (`soupsieve` 2.9.1).
2. **Changes made:** only the idempotency-key conflict is handled, anything else is re-raised; `soupsieve` → 4.0.0.
3. **Result:** honest errors; `pip-audit` 0 vulnerabilities. Suite: 27 → 38 tests, 4.1 s on Postgres.

---

# Phase 1 · Accounts and personal workspace

### 1.1 · Private workspaces
**Why:** anyone could see and use every run, strategy and optimization.
1. **Before:** no accounts; all data visible to everyone.
2. **Changes made:** email accounts and one-click guests; every query filtered by owner; another user's item returns `404` (not `403`, so its existence isn't revealed).
3. **Result:** isolation tests for runs, trades, optimizations, lists, the dashboard and strategy use *(5 tests)*; end-to-end smoke test 15/15.

### 1.2 · Idempotency keys can't leak another user's job
**Why:** found in design review: keys were globally unique, so a matching key from another user would return *their* job.
1. **Before:** `UNIQUE(idempotency_key)` across all users.
2. **Changes made:** `UNIQUE(owner, idempotency_key)`.
3. **Result:** keys are per user *(test)*.

### 1.3 · Exact quotas under concurrent requests
**Why:** "check the quota, then insert" is a race: two simultaneous requests can both see 9 of 10.
1. **Before:** no per-user limits, and the pattern would have raced.
2. **Changes made:** per-tier quotas, checked after locking the user's row (`SELECT … FOR UPDATE`) inside the create transaction.
3. **Result:** quotas are exact, and other users never wait for the lock *(5 quota tests)*.

### 1.4 · Cookie login that browsers accept, with CSRF protection
**Why:** browsers increasingly block cookies sent to a different domain, and DRF doesn't check CSRF for anonymous requests (login CSRF).
1. **Before:** the SPA called the API's domain over CORS.
2. **Changes made:** same-origin API (Vercel rewrite, Vite proxy, nginx); `HttpOnly` session cookie; CSRF enforced even on login and sign-up; token and session rotated on login; CORS package removed.
3. **Result:** smoke test through the real proxy 15/15 (dashboard p50 24.5 ms, `/auth/me` p50 14.7 ms); CSRF rotation pinned by a test.

### 1.5 · Fast account tests without weakening production
**Why:** Django's default password hashing is deliberately slow, and account tests hash dozens of times.
1. **Before:** 209.7 ms per hash.
2. **Changes made:** a fast MD5 hasher in account tests only; production keeps PBKDF2 (exercised by the smoke test).
3. **Result:** 0.024 ms per hash in tests; the whole accounts suite runs in ~0.6 s.

### 1.6 · Existing data kept through the upgrade
**Why:** runs created before accounts had no owner, and an owner column can't be required on rows that have none.
1. **Before:** ownerless rows.
2. **Changes made:** a three-step migration (nullable → assign a hidden legacy owner → required).
3. **Result:** rehearsed from the actual Phase 0 code: upgrade 1,189 ms, 8/8 data checks, rollback 1,091 ms with the old code reading everything back.

---

# Phase 2 · Strategy builder

### 2.1 · User strategies on the public site
**Why:** user Python can't run on a public deployment (the sandbox isn't a security boundary), so the live site could only run three built-ins.
1. **Before:** making a strategy meant writing Python, and only where custom code was enabled (never on the public site).
2. **Changes made:** a JSON rule spec validated against an allowlist and **interpreted**; no code is generated or run.
3. **Result:** builder strategies run everywhere with custom code off; seven templates to start from.

### 2.2 · 9.8× faster strategy execution
**Why:** the sandbox starts a subprocess per run and exchanges JSON with it on every bar.
1. **Before:** 298.8 ms for SMA 10/50 over 2,520 bars.
2. **Changes made:** the interpreter computes each indicator once over the whole series, then the engine looks up a precomputed decision per bar.
3. **Result:** 30.4 ms, with **identical fills (80/80) and equity curve** through the real sandbox.

### 2.3 · From 2 indicators to 8
1. **Before:** strategies could only read SMA-10 and SMA-50.
2. **Changes made:** SMA, EMA, RSI, MACD, Bollinger, ATR, Donchian and ROC, any period 2–200, with documented conventions.
3. **Result:** each checked against hand-computed values and pandas as an independent reference (tolerance 1e-9); builder SMA equals the engine's built-in exactly *(9 tests)*.

### 2.4 · Look-ahead proven, not asserted
1. **Before:** "no look-ahead" relied on the fill model and code review.
2. **Changes made:** a metamorphic test rewrites every bar after *t* and requires all indicator values and decisions up to *t* to stay identical.
3. **Result:** identical at every cut point for all 15 indicator outputs and full strategies *(2 tests)*.

### 2.5 · Realistic Indian trading costs
**Why:** one commission rate can't express stamp duty on buys only, or GST on some charges but not others.
1. **Before:** one rate for buys and sells, stored with 6 decimals.
2. **Changes made:** separate buy and sell rates; an India delivery model (STT, exchange charge, SEBI fee, stamp duty, GST); 9 decimals.
3. **Result:** ₹118.6226 per ₹1 lakh bought and ₹103.6226 sold, exact to the paisa fraction; 6 decimals would have lost ₹0.02 per lakh on every fill *(test)*.

### 2.6 · Money shown in the right currency
1. **Before:** always `$`, no thousands separators.
2. **Changes made:** currency inferred from the symbol; Indian digit grouping for INR; no sign when unknown.
3. **Result:** `₹1,00,000.00`, `$10,000.00`, `1,234.50` *(test)*.

### 2.7 · Tests can't reach the network
**Why:** found while testing: a template's longer warm-up reached past the fixture's data, so the worker quietly downloaded real AAPL prices during a test.
1. **Before:** that test took 2.6 s and ran on real Yahoo data instead of its fixture.
2. **Changes made:** fixtures cover the full warm-up; downloads are patched and a test fails if one is attempted; `load_bars` looks the downloader up per call so it can be patched.
3. **Result:** ~30 ms, deterministic, and any future network call fails loudly.

### 2.8 · Server-driven form with errors on the exact field
1. **Before:** no builder; the browser's own validation would have shown a popup instead of the server's message.
2. **Changes made:** the form is built from a catalog endpoint, validated live through a preview endpoint, with errors keyed by path; native validation off.
3. **Result:** one allowlist; adding an indicator needs no frontend change *(13 frontend tests)*.

### 2.9 · Test and CI robustness
1. **Before:** a migration test left the schema behind, breaking the next test once a newer migration existed; CI ran Node 20 (end of life), and the new test tools need 22+.
2. **Changes made:** the migration test migrates forward to the newest migration when it ends; CI and the Docker build moved to Node 24.
3. **Result:** future migrations won't break that test; CI green.

### 2.10 · Bounded storage per account
1. **Before:** unlimited saved strategies.
2. **Changes made:** 5 / 20 / 100 by tier, checked under the same user-row lock.
3. **Result:** the 6th guest strategy gets a `429` naming the limit *(test)*.

---

# Phase 3 · Comparison and optimization

### 3.1 · Heartbeat writes were 70% of the work *(found by profiling)*
**Why:** after adding the cache, a batch got only 12–13% faster despite a high hit rate. Instead of guessing, one run was profiled.
1. **Before:** a progress `UPDATE` every 50 bars, sized for slow sandbox runs. Profile of one 219 ms child: **153 ms (70%) in 41 progress writes**; the simulation itself ≈ 17 ms.
2. **Changes made:** heartbeat at most once per second (stale recovery waits 120 s, so this is still frequent enough).
3. **Result:** median per child **174 → 37–39 ms**; 25-child batch **5.7 → 2.4 s**; fast runs write no progress rows, slow runs still beat *(2 tests)*.

### 3.2 · Shared work across a batch (worker cache)
**Why:** every child of an experiment reloaded the same bars and recomputed the same indicators.
1. **Before:** 25 children, 26 bar loads, 52 indicator computations.
2. **Changes made:** per-worker LRU caches for bars (key includes the coverage's `fetched_at`, so a re-download is never served stale) and indicator series (key = data hash).
3. **Result:** 24/26 bar hits and 48/52 indicator hits on a stop × target grid; **32–36% less time per child** once the heartbeat no longer dominated; results identical with and without the cache *(tests)*.

### 3.3 · A click isn't stuck behind a batch (priority lanes)
**Why:** an account is one person; the real contention is their own batch (and later the AI agent's) delaying their own quick runs.
1. **Before:** first in, first out: a hand-started run waited behind 22 batch children, **1.26 s** (3.7 s before the heartbeat fix).
2. **Changes made:** the claim query orders by `(priority, id)`; hand-started runs are priority 0, batch children 1; nothing is pre-empted.
3. **Result:** the hand-started run starts next, **25 ms** after the click; `EXPLAIN` confirms the new index is used.

### 3.4 · Strategies compared with each other
**Why:** the original question of the overhaul: optimization only compared settings of one strategy.
1. **Before:** no way to compare strategies.
2. **Changes made:** comparisons of strategies × symbols (≤ 25 cells) plus an index benchmark per currency (NIFTY 50 or S&P 500), shown as a heatmap and overlaid curves.
3. **Result:** a comparison cell equals the same standalone run (final value, trades, curve) *(test)*.

### 3.5 · Searching the strategy's own parameters
1. **Before:** optimization could only vary stop-loss and take-profit.
2. **Changes made:** builder parameters can be searched too; a parameter used in both the buy and sell rule moves together; invalid combinations are skipped and listed, bad values rejected.
3. **Result:** 8 distinct, hashed specs from a 2 × 2 × 2 grid; MACD fast 30 / slow 26 skipped with its reason; six kinds of bad request rejected before any work *(tests)*.

### 3.6 · One batch model for everything
1. **Before:** an optimization-only job model.
2. **Changes made:** `Experiment` (comparison or optimization) with derived status; a hand-written rename migration; the old endpoint kept as an alias.
3. **Result:** all Phase 0–2 tests still pass through the old endpoint; rehearsal on 500 runs: upgrade 221 ms, rollback 313 ms, 13/13 checks, every run still linked to its parent.

### 3.7 · Lighter experiment pages
1. **Before:** every child's full equity curve (25 × ~2,500 points).
2. **Changes made:** curves downsampled to ≤ 500 points, keeping each bucket's minimum and maximum.
3. **Result:** ≤ 500 points per child with peaks, troughs and both ends kept *(test)*; full curves remain on each run's page.

### 3.8 · Concurrency proven, not assumed
1. **Before:** "`SKIP LOCKED` means no run is claimed twice" was a claim.
2. **Changes made:** a test runs 4 real worker threads with their own Postgres connections against one queue.
3. **Result:** 40/40 runs completed, every one claimed exactly once (`attempts = 1`), work spread across workers.

### 3.9 · Better risk metrics
1. **Before:** final value, CAGR, Sharpe, max drawdown, win rate, buy and hold.
2. **Changes made:** Sortino, Calmar, exposure, round trips and cost drag, all from the same ledger.
3. **Result:** hand-checked on a 5-bar ledger; undefined values are `null`, never infinity *(2 tests)*.

### 3.10 · Smaller fixes found by tests
| Before | Change | Result |
|---|---|---|
| An invalid MACD pair was reported 4 times (once per linked rule) | Reasons de-duplicated | Reported once *(test)* |
| CI failed on an error after a passing frontend test (timing on a slower machine) | The data-hook mock defaults to "loading" | CI green; the test also checks the navigation |

---

# Phase 3.5 · Engineering hardening

### 3.5.1 · Rate limits that mean what they say
**Why:** gunicorn runs 2 processes, and each kept its own throttle counters, so every limit was really twice as high. The login
limit exists to slow password guessing.
1. **Before:** 30 rapid wrong-password logins against the real 2-process server (limit 10/min): **20 allowed** (16 on another try).
2. **Changes made:** counters in a Postgres table shared by every process and instance (D-073), created by a migration, no Redis.
3. **Result:** the same test allows **exactly 10, refuses 20** *(measured; plus a test that two cache instances share one counter)*.

### 3.5.2 · Shared counters without the throughput cost *(found by the load test)*
**Why:** the first load test with Django's stock database cache was clearly slower; reading its `set()` showed why.
1. **Before:** each counter write ran `SELECT COUNT(*)` over the table, a savepoint, a `SELECT`, an `UPDATE`/`INSERT` and a release.
   Load test: **31–41 requests/s** at 40–80 users, p95 590 ms at 20 users (two runs, consistent).
2. **Changes made:** `UpsertDatabaseCache`: one `INSERT … ON CONFLICT DO UPDATE`; expired rows deleted by the hourly housekeeping (D-075).
3. **Result:** **52–55 requests/s** at 40–80 users, p95 **380 ms** at 20 users; 1 statement per write instead of ≥ 3 *(test)*.
   Same as per-process counters within measurement noise.

### 3.5.3 · A deploy doesn't strand a run
**Why:** every deploy restarts the worker. The worker already finished its current run on `SIGTERM`, but had no deadline, and
the platform kills it 30 s later.
1. **Before:** a run still going at the kill stayed `running` for **120–150 s** (stale recovery) and used one of its 3 attempts.
2. **Changes made:** no claims after `SIGTERM`; past `WORKER_GRACE_S` (20 s) the run is requeued at once without counting the attempt (D-074).
3. **Result:** real worker process, 2 s grace: the run was **back in the queue 2.26 s** after `SIGTERM`, `attempts = 0` *(measured; 4 tests)*.

### 3.5.4 · Every endpoint documented, and kept that way
1. **Before:** no API docs. The first generated schema silently left out **17 endpoints** and had **13 untyped fields**.
2. **Changes made:** OpenAPI with drf-spectacular, explicit request/response declarations on every view, type hints, Swagger UI with bundled assets; CI fails on any schema warning (D-072, D-076).
3. **Result:** **0 warnings, 32 operations** documented; a new undocumented view fails CI.

### 3.5.5 · A click can be traced to the worker error
1. **Before:** text logs; no way to connect an API request to the run it created or the worker's lines about that run.
2. **Changes made:** request IDs (kept from a valid incoming header, else generated), returned in `X-Request-ID`, stored on runs and experiments, on every JSON log line, and set by the worker while it processes the run (D-070). Server-error messages in the UI show the ID.
3. **Result:** one search on the ID finds the request, the run and the worker's lines *(tests)*; access lines carry route patterns, not URLs, and no emails *(test)*.

### 3.5.6 · The system reports its own health
1. **Before:** health checks only; queue backlog or a dead worker was invisible until users complained.
2. **Changes made:** token-protected `/metrics` (Prometheus text): HTTP rate, errors and latency by route, and queue health from the database: depth per lane, oldest queued age, active, completed and failed per category, run-time p50/p95, stale runs (D-069). Sentry ready behind `SENTRY_DSN`, without personal data (D-071).
3. **Result:** off without a token (404), 401 for a wrong one *(tests)*; queue numbers are correct across all processes because they come from the queue table.

### 3.5.7 · Capacity is a number, not a guess
1. **Before:** "no load test has been run" (README known limitations); `MAX_GRID` 25 was a placeholder "until Phase 3.5 measures capacity".
2. **Changes made:** a Locust scenario of real user behaviour, run against a container limited like a small Render instance; worker and queue benchmarks (D-067, D-068).
3. **Result:** API knee at **~20 users, ~50 requests/s**, no failed requests up to 80 users; one worker **537 runs/min**, 4 workers 1,263;
   claim latency **flat (8–12 ms median) from 100 to 100,000 queued**. A 25-child experiment is ~3 s of one worker, so `MAX_GRID`
   stays 25 for readability, not capacity.

---

# Phase 4 · AI assistance

### 4.1 · Describe a strategy in words
**Why:** building rules in a form is slow for people who think in sentences ("golden cross, out on the death cross").
1. **Before:** strategies could only be built field by field.
2. **Changes made:** the AI turns a description into the builder's JSON spec; `spec.validate` checks it, validator errors go back for up to 2 repairs, and the result fills the form for the user to review (D-077 to D-080). Requests run as worker jobs, within quotas and a daily token budget.
3. **Result:** gpt-oss-120b: **60/60** on the evaluation, including **18/18** unsupported and injection requests refused, 0 strategies wrongly refused, 0 prompt leaks; **1.7 s** median, 2.8 s p95.

### 4.2 · A validator gap found by the AI evaluation
**Why:** the first live run failed one case, "Buy on a golden cross", with 99.5% bar agreement, so the answer was close but not right.
1. **Before:** the model answered "SMA 20 crosses above SMA 20", a rule that can never fire, and `spec.validate` **accepted it**. A person could save the same rule in the form.
2. **Changes made:** a condition whose two sides are identical (after defaults are filled in) is rejected with a path-keyed error (+1 test).
3. **Result:** on the re-run the validator rejected that answer, the repair round sent its error back, and the model answered the 50/200 cross: **59/60 → 60/60**. The fix also protects hand-built strategies.

### 4.3 · The model is chosen by measurement
1. **Before:** "the bigger model is probably better" was a guess.
2. **Changes made:** the same 60 cases on gpt-oss-120b and gpt-oss-20b (D-085).
3. **Result:** 120b 60/60 vs 20b 57/60. 20b's three failures were valid but wrong: comparisons reversed, a false note promising leverage, futures quietly treated as the index. 20b is 0.5 s faster at the median; 120b stays the default.

### 4.4 · What the prompt's catalog and examples are worth
1. **Before:** a format-only prompt.
2. **Changes made:** the prompt lists every indicator, parameter range and operator (generated from the registry), the execution semantics and three worked examples.
3. **Result:** on gpt-oss-20b, over the same 52 cases: **28/52 (54%) → 49/52 (94%)**. Partial and unrecorded: the bare run hit the daily token limit (D-086).

### 4.5 · Honest latency
1. **Before:** the first run's per-call time included waiting out the free tier's 8,000 tokens/min limit (70 retries): "median 5.8 s".
2. **Changes made:** the recorder subtracts rate-limit waits and keeps them separately; latency comes from runs paced to stay under the limit.
3. **Result:** **1.7 s** median for gpt-oss-120b (1.2 s for 20b): the model, not the queue in front of it.

### 4.6 · Re-measuring costs a call, not a day's tokens
1. **Before:** any change meant a full run: ~130,000 tokens (most of a model's free day) and ~20 minutes.
2. **Changes made:** `assist_eval --reuse` answers already-recorded messages from the recording and calls the model only for new ones.
3. **Result:** after the validator fix, the re-run made **1 live call** (60 reused).

### 4.7 · CI keeps the evaluation honest
1. **Before:** an evaluation is a number in a document that goes stale when the prompt or validator changes.
2. **Changes made:** the live runs are committed as recordings; CI replays them (no network, no tokens) and requires the recorded scores.
3. **Result:** the validator fix broke the replay at once (v01 needed an unrecorded repair round), and the score couldn't be claimed until it was re-measured *(test)*.

### 4.8 · Smaller fixes found by tests
| Before | Change | Result |
|---|---|---|
| A new worker-loop test hung on Postgres only (CPU spinning, no DB connection) | Found that `close_old_connections()` closes a test's transaction on Postgres; patched it in the test and capped the loop | Postgres suite 187/187 in 43.6 s; a regression can no longer hang CI |

---

# Phase 5 · AI research agent

*Not run against a real model yet (D-094): results below are from tests with a scripted model and real backtests.*

### 5.1 · From one strategy to a researched answer
**Why:** finding a strategy means trying ideas, comparing them and refining the good ones: tedious by hand.
1. **Before:** the user built, compared and optimized each idea by hand (Phase 4 drafts one strategy at a time).
2. **Changes made:** a research agent that proposes candidates, backtests them as rounds, refines with parameter searches and chooses, inside fixed stages and hard budgets (D-088, D-089, D-093).
3. **Result:** a complete run in the tests: 4 decisions, 5 backtests, 5 model calls, a report with process checks; every rejected action returned to the agent with path-keyed errors *(18 tests)*.

### 5.2 · Honest about its own overfitting
**Why:** an agent that tries many strategies on the same data will find a lucky one; the research number alone misleads.
1. **Before:** nothing stopped a search from reporting its best in-sample result as if it were real.
2. **Changes made:** the last 30% is held out; the agent never sees it (its prompts are checked on every step); code tests the choice once there and reports it next to buy & hold, with the number of candidates tried (D-091).
3. **Result:** held-out tested exactly once, agent prompts never contain those dates, all candidate backtests end before the split *(tests, plus a check in every report)*.

### 5.3 · An agent that doesn't hold a worker
1. **Before (design risk):** an agent waiting on its own backtests would block the worker they need; with one worker, for ever.
2. **Changes made:** a resumable state machine: one short step per claim; `waiting` while its round runs; woken when the round finishes (D-090).
3. **Result:** while backtests run, research needs no worker; a crashed step resumes from saved state; shutdown re-queues without using an attempt *(tests)*.

### 5.4 · A summary that can't invent numbers
1. **Before:** model-written summaries can state figures that were never computed.
2. **Changes made:** every number in the agent's summary must appear in the facts; one rewrite, then a plain code-written summary (D-092).
3. **Result:** an invented "987.6%" and "Sharpe 9.99" were caught, the rewrite request named both, and the plain summary replaced them *(test)*.

### 5.5 · Smaller fixes found by tests
| Before | Change | Result |
|---|---|---|
| A step re-queued after a crash while its backtests ran asked the agent about unfinished results; the run failed | Such a step goes back to `waiting` without a model call | Crash-and-resume test completes the run *(test)* |
| A migration that both seeds a row and alters a table couldn't be rolled back on Postgres | Split into schema (`0022`) and data (`0023`) | Postgres suite 205/205 including the migration rollback test |

### 5.6 · What the first live run taught *(D-096)*
**Why:** a scripted model can't show how a real one behaves; one local run with gpt-oss-120b did.
| Before (live run) | Change | Result |
|---|---|---|
| A correct summary was thrown away: 10 real numbers quoted to 4 decimals were flagged as invented | Number check accepts up to 4 decimals | The live values pass, an altered one ("1.2908") still fails *(test)* |
| 4 of 7 answers hit the 2,000-token output cap; steps slowed to 27 s; malformed specs rejected | 4,000 tokens and low reasoning effort for agent steps | Agent calls use the research limits *(test)*; to confirm live |
| The agent explored for all 4 decisions and never refined or chose | Explore capped at 2 rounds, then refine | The run moves on by itself and the agent chooses *(test)*; to confirm live |
| Two candidates were the same strategy in different words (equal results) | Twins marked "same results as cN" | Shown to the agent and in the UI *(tests)* |
| A replaced summary showed as a failed rule (red ✗) | Shown as a warning that Vault's plain summary is used | *(frontend test)* |
