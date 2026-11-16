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
