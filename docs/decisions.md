# Decisions

Each decision records what we chose, what else we considered, and why. Tradeoffs are in [tradeoff.md](tradeoff.md),
the resulting code changes in [changes.md](changes.md), and test evidence in [evals.md](evals.md).

**Status values:** `Accepted` (built or ready to build) · `Accepted in principle` (direction agreed, details settled in that phase) · `Deferred` (decide later; trigger noted) · `Superseded`.

| ID | Phase | Decision | Status |
|---|---|---|---|
| D-000 | All | Phased overhaul; discuss → approve → build; keep these four docs | Accepted |
| D-001 | All | Build Vault's own strategy builder; don't integrate the external Moneylogix repo | Accepted |
| D-002 | 0 | Fix existing bugs before any new feature | Accepted |
| D-003 | 0 | Replace a symbol's bars on every fetch (one price scale) | Accepted |
| D-004 | 0 | Track fetched spans in a `SymbolCoverage` table | Accepted |
| D-005 | 0 | Finish stuck optimizations with a sweep in the recovery loop | Accepted |
| D-006 | 0 | Recycle DB connections at the top of each worker loop | Accepted |
| D-007 | 0 | Set `NUM_PROXIES` by platform, overridable by env | Accepted |
| D-008 | 0 | Reject stop-loss ≤ slippage at the API; don't change the engine | Accepted |
| D-009 | 0 | List endpoints load only the fields they show | Accepted |
| D-010 | 0 | Bump `soupsieve` 2.9.1 → 4.0.0 | Accepted |
| D-011 | Deploy | Docker: not needed locally (WSL instead); Render setup decided at deployment | Deferred |
| D-012 | 2 | Builder: form → JSON spec → generated Python → existing sandbox; API accepts JSON only | Accepted in principle |
| D-013 | 4–5 | AI behind one provider module; Gemini free tier first | Accepted in principle |
| D-014 | 6 | Build phase by phase on staging; release once at the end | Accepted |

---

## D-000 · Phased overhaul with a discuss-first process
- **Context:** Vault is turning from an anonymous demo into a personal backtester with accounts, a builder, comparisons and AI. That's too much to design in one go.
- **Decision:** Seven phases (0 fixes → 1 accounts → 2 builder → 3 comparison → 4 AI assistance → 5 agent → 6 release). Every phase starts with a discussion of options and tradeoffs. Code starts only after explicit approval. Each phase gets one branch and PR and updates these four docs.
- **Why:** Decisions stay deliberate and written down, and each phase can be reviewed on its own.

## D-001 · Our own builder, not an integration
- **Context:** The external Moneylogix Strategy Builder builds static multi-leg *options* positions (Spring Boot, FastAPI, Kafka, Redis). Vault backtests *rule-based signal* strategies on daily bars.
- **Options:** (a) integrate the external repo, (b) build a builder inside Vault.
- **Decision:** (b).
- **Why:** The two products disagree on what a strategy even is, and integrating would mean joining two backends in different languages for no product gain. A builder inside Vault reuses the engine, job queue and tests.

## D-002 · Fix bugs before features
- **Context:** The review found five defects in the engine, data, job queue and API, all of which every later phase builds on.
- **Decision:** Phase 0 fixes them, each with a regression test, before Phase 1 starts.
- **Why:** Features built on wrong data or a queue that can hang would inherit those bugs, and they're cheaper to fix now than once users rely on the behavior.

## D-003 · One price scale per symbol: replace on fetch
- **Context:** Yahoo's adjusted prices are restated after every split and dividend. The old code inserted newly downloaded bars with `ignore_conflicts`, so old rows on the previous scale stayed next to new rows. A 2:1 split showed up as a fake −50% drop.
- **Options:**
  1. Keep inserting with `ignore_conflicts` (the bug).
  2. Upsert only the downloaded range.
  3. Re-download the symbol's whole known span (stored ∪ covered ∪ requested) and replace it in one transaction.
  4. Store unadjusted prices plus corporate actions, and apply adjustments ourselves.
  5. Keep versioned snapshots per fetch.
- **Decision:** Option 3.
- **Why:** It's the smallest change that guarantees one scale per symbol. Daily bars are small (about 250 a year), so re-downloading the span is cheap. Options 4 and 5 are more accurate but are a data-platform project.
- **Interview angle:** idempotency vs. correctness. An idempotent insert can be idempotent and still wrong when the source restates history.

## D-004 · `SymbolCoverage` table instead of guessing coverage from stored bars
- **Context:** Coverage used to be inferred from the stored bars: they had to reach both ends within 5 days with no gap over 5 days. Recently listed stocks and real market closures never passed, so they were downloaded again on every run.
- **Decision:** Record each span requested from the provider. A request inside that span uses stored data, with gaps reported as warnings. The fetch day itself is never counted as covered. A failed or empty fetch records nothing.
- **Why:** "Asked the provider for this span" is a fact. "The bars look complete" is a guess. Recording the fact stops endless re-downloads without hiding real gaps.

## D-005 · Sweep for stuck optimizations
- **Context:** The out-of-sample run was only queued from `work_one`. If the last in-sample run failed through stale recovery, or a worker died at the wrong moment, the job stayed `running` forever.
- **Options:** (a) call `finish_optimization` inside `recover_stale` only, (b) a general sweep in the 30-second recovery loop, (c) a database trigger.
- **Decision:** (b) `finish_pending_optimizations()`. It's idempotent because a unique constraint allows only one out-of-sample run per job.
- **Why:** It covers every way a run can finish, including ones we haven't thought of, and keeps the logic in Python. (a) misses the killed-worker case. (c) hides logic in the database.
- **Interview angle:** recovery by periodic reconciliation (comparing actual state to expected state on a timer) instead of trying to catch every failure path, made safe by idempotency.

## D-006 · Recycle DB connections in the worker loop
- **Context:** Django only cleans up connections around HTTP requests. A long-running worker kept a dead connection forever after a database restart. Separately, an exception in `recover_stale` crashed the whole loop.
- **Decision:** Call `close_old_connections()` at the top of every loop iteration, and move recovery inside the loop's `try`.
- **Why:** This is Django's standard pattern for long-running processes.

## D-007 · `NUM_PROXIES` by platform
- **Context:** Without `NUM_PROXIES`, DRF identifies the client by the whole `X-Forwarded-For` header, which the client controls. A different made-up header on every request got around all rate limits.
- **Decision:** Default to 1 when `RENDER_EXTERNAL_HOSTNAME` is set and 0 otherwise. The `NUM_PROXIES` env var overrides it.
- **Open item:** Check the real `X-Forwarded-For` chain on Render staging. If the frontend is later proxied through Vercel, the count changes.

## D-008 · Reject stop ≤ slippage instead of changing the engine
- **Context:** With slippage ≥ the stop-loss percentage, every entry was stopped out at the open of its first bar. The review first called this an engine bug. On closer analysis the engine is right: the entry fills at `open × (1 + slippage)`, so the market is already below the stop when the position is opened.
- **Decision:** Reject such settings with a 400 at the API. The engine and `ENGINE_VERSION` are unchanged.
- **Why:** The settings are meaningless, so rejecting them is honest. Changing the engine would have made fills optimistic and changed past results.
- **Interview angle:** correcting your own review finding after a closer look.

## D-009 · Load only what's shown
- **Decision:** The optimization list prefetches runs with only `id, optimization_id, status, sample`. The run list skips `equity_curve` and `strategy_code`.
- **Why:** A page of 50 jobs × 26 runs × about 2,500 curve points could need hundreds of MB, enough to crash a 512 MB instance.

## D-010 · Dependency bump
- **Decision:** `soupsieve` 2.9.1 → 4.0.0. It's a transitive dependency via yfinance → beautifulsoup4. 3.0.2 still had one advisory.
- **Why:** `pip-audit` in CI would fail. `pip check` and the full suite pass after the bump.

## D-011 · Docker: deferred to deployment
- **Context:** Docker Desktop is heavy, and local compose failed on an old TimescaleDB volume.
- **Decision so far:** Docker isn't required locally. Use WSL2 Ubuntu for the backend (the sandbox needs Linux) and plain Windows for the frontend. Render and CI don't depend on local Docker.
- **Deferred:** (A) keep the Dockerfile for Render only, or (B) run Render as native Python and remove Docker entirely. **Revisit when setting up staging and deployment.**

## D-012 · Builder pipeline (Phase 2, in principle)
- **Decision:** Form → validated JSON spec (the source of truth) → server-generated Python built from templates → the existing sandbox. The public API accepts only JSON, never Python. The engine calculates the indicators the strategy declares. The generated code is shown read-only in the UI.
- **Why:** User-built strategies can run on the public site without opening it to arbitrary code, and they reuse the one existing way of running strategies.

## D-013 · AI provider (Phases 4–5, in principle)
- **Decision:** One provider module so switching providers changes one file. Start with Gemini's free tier. The agent will likely need a paid model with a spending cap, or users' own keys; to be decided in Phase 5. The app must work fully when AI is unavailable.
- **Why:** Vault validates everything the AI produces, so model quality affects retries, not safety. That makes cost and limits the deciding factors.

## D-014 · Build in phases, release once
- **Decision:** Each phase merges to `main` with CI passing and is deployed to staging. Production gets one release at the end, after rehearsing migrations on a copy of production data and taking a backup.
