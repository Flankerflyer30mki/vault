# Changes

What changed in each phase, at a level useful for review and release notes. Decisions are in
[decisions.md](decisions.md) and test results in [evals.md](evals.md).

## Phase 0 · Bug fixes · branch `phase-0-fixes` · commit `2eec76b` · 2026-11-16

### Behavior changes
| Area | Before | After | Decision |
|---|---|---|---|
| Market data | New bars were inserted next to old ones; restated history mixed price scales | A fetch re-downloads the symbol's whole known span and replaces its bars in one transaction | D-003 |
| Market data | Recently listed stocks and long market closures were downloaded again on every run | Fetched spans are recorded in `SymbolCoverage`; a request inside one uses stored bars | D-004 |
| Job queue | An optimization could stay `running` forever | The recovery loop queues the missing out-of-sample run | D-005 |
| Worker | A dead DB connection stayed broken forever; a recovery error crashed the loop | Connections are recycled every loop; recovery errors are logged and the loop continues | D-006 |
| API rate limits | A made-up `X-Forwarded-For` header got around them | The client IP is taken from the trusted proxy count (`NUM_PROXIES`) | D-007 |
| API validation | stop-loss ≤ slippage was accepted, and every entry was stopped out on its first bar | `400 {"stop_loss_pct": ...}` | D-008 |
| API performance | The optimization list loaded every child run's equity curve | It loads only the fields needed for status; the run list skips curves and code | D-009 |
| API errors | A rare non-idempotency `IntegrityError` turned into a confusing 500 | The original error is raised | — |

### Files
- `backend/backtester/data_fetch.py`: replace-on-fetch, coverage tracking, `_query` filters on `ts` directly (so the index is used) instead of `ts__date`
- `backend/backtester/models.py`: new `SymbolCoverage`
- `backend/backtester/migrations/0012_symbolcoverage.py`: **new migration** (adds a table, reversible)
- `backend/backtester/jobs.py`: `finish_pending_optimizations()`, `close_old_connections()`, recovery moved inside `try`
- `backend/backtester/views.py`: `Prefetch(... only(...))`, `defer(...)`, `IntegrityError` handling
- `backend/backtester/serializers.py`: stop vs. slippage check
- `backend/vault_core/settings.py`: `NUM_PROXIES`
- `backend/requirements.txt`: `soupsieve` 2.9.1 → 4.0.0
- `backend/backtester/tests.py`: 11 new tests (27 → 38)
- `README.md`, `CLAUDE.md`: docs updated or added

### Operational notes for release
- **New env var:** `NUM_PROXIES` (optional; defaults to 1 on Render, else 0). Check it on staging.
- **One-time downloads:** every existing symbol is downloaded once on its first run after deploy, which also converts old mixed-scale data.
- **Migration:** `0012` only adds a table, so it's safe on a live database.
- **Engine:** `ENGINE_VERSION` unchanged (2.0.0). Past results are unaffected.
