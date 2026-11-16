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

## Phase 1 · Accounts and personal workspace · branch `phase-1-accounts` · 2026-11-16

### Behavior changes
| Area | Before | After | Decision |
|---|---|---|---|
| Access | Anyone could use every endpoint anonymously | Every `/api/*` endpoint except `/api/auth/*` requires sign-in (403 otherwise). `/health/*` stays public | D-016 |
| Data visibility | All runs, optimizations and strategies were visible to everyone | Only your own, plus built-in strategies. Another user's id returns 404. You can't use another user's strategy | D-020 |
| Limits | Per-IP throttles only | Per-tier quotas (429 naming the limit), job/read/write throttles per user, per-IP throttles on auth and guest creation | D-021 |
| Idempotency keys | Global: a matching key from another user returned *their* job | Per user (`UNIQUE(owner, idempotency_key)`) | D-020, D-025 |
| API origin | The SPA called the Render host directly over CORS | The SPA calls the relative `/api`, forwarded by Vercel, Vite or nginx. CORS removed | D-016, D-027 |
| Home page | Strategy list | Dashboard: quota usage, running jobs, recent backtests with return vs. buy & hold, recent optimizations with their out-of-sample result, strategies | D-022 |

### New API
`/api/auth/`: `csrf`, `me`, `signup`, `login`, `logout`, `guest`, `guest/convert`, `verify-email`, `verify-email/resend`, `password-reset`, `password-reset/confirm`, `password-change`, `email-change`, `delete-account`. Plus `/api/dashboard/`.

### New UI routes
`/login`, `/signup`, `/forgot-password`, `/reset-password`, `/verify-email`, `/account`, `/` (dashboard). The strategy list moved to `/strategies`. Banners appear for guests and unverified users. The nav shows the signed-in user and a sign-out button.

### Database
| Migration | What | Reversible |
|---|---|---|
| `accounts.0001_initial` | `accounts_user` table | yes |
| `backtester.0013_owner_fields` | nullable `owner` on strategy, run and optimization; idempotency keys no longer globally unique | yes |
| `backtester.0014_assign_legacy_owner` | gives existing rows to an inactive legacy user (only if there are any) | yes (no-op reverse; the legacy user remains) |
| `backtester.0015_owner_required` | `owner` required on runs and optimizations; built-in XOR owner check on strategies; `UNIQUE(owner, idempotency_key)`; indexes on `(owner, -created_at)` | yes |
| `sessions.0001_initial` | Django sessions table | yes |

### Files
- **New** `backend/accounts/`: `models.py` (User, manager, guests), `views.py` (auth API), `serializers.py`, `tokens.py`, `emails.py`, `quotas.py`, `housekeeping.py`, `urls.py`, `tests.py` (31 tests), migration `0001`
- `backend/backtester/`: `models.py` (owners, constraints, indexes), `views.py` (per-user querysets, quotas, user-row lock, `DashboardView`), `serializers.py` (strategy field limited to visible strategies), `jobs.py` (out-of-sample run inherits owner, hourly housekeeping), `urls.py`, `tests.py`, migrations `0013`–`0015`
- `backend/vault_core/`: `settings.py` (sessions, CSRF, user model, password rules, email, quotas, throttles; CORS removed), `urls.py`
- `backend/requirements.txt`: removed `django-cors-headers`
- **New** `frontend/src/auth.jsx`, `frontend/src/pages/{Auth,Account,Dashboard}.jsx`, `frontend/nginx.conf`
- `frontend/src/{App.jsx,api.js,App.css}`, `frontend/vite.config.js` (dev proxy), `frontend/vercel.json` (API rewrite), `frontend/Dockerfile` (nginx), `docker-compose.yml`
- `README.md`, `CLAUDE.md`, `docs/*`

### Operational notes for release
- **New env vars (API and worker):** `CSRF_TRUSTED_ORIGINS` (the Vercel origin), `FRONTEND_URL`, `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`DEFAULT_FROM_EMAIL`, optional `QUOTA_*`, `THROTTLE_AUTH`, `THROTTLE_GUEST`, `GUEST_TTL_DAYS`.
- **Removed env var:** `CORS_ALLOWED_ORIGINS`. **Vercel:** remove `VITE_API_URL`.
- **`frontend/vercel.json`:** replace `VAULT_API_HOST` with the Render API host.
- **`NUM_PROXIES`:** check on staging (Vercel and then Render).
- **Migrations:** rehearsed from the actual Phase 0 code on Postgres: upgrade 1,189 ms, rollback 1,091 ms (see evals).
- Existing anonymous runs disappear from the UI (they're owned by the legacy user).

## Phase 2 · Strategy builder · branch `phase-2-builder` · 2026-11-16

### Behavior changes
| Area | Before | After | Decision |
|---|---|---|---|
| Making a strategy | Only by writing Python, and only where `ALLOW_CUSTOM_CODE=1` (so never on the public site) | A form builds a JSON spec of entry/exit rules; it runs everywhere, including with custom code off | D-033, D-034 |
| Indicators | `sma_10` and `sma_50` only | Builder: SMA, EMA, RSI, MACD, Bollinger, ATR, Donchian, ROC with chosen periods. Code strategies unchanged | D-035, D-044 |
| Warm-up | Always 50 bars | Builder strategies get their longest lookback (≤ 600); code strategies keep 50. Warning text now says "only X of N warm-up bars" | D-043 |
| Strategies API | List and create only | Also retrieve, edit (`PATCH`), delete (`409` if it has runs), catalog, live preview. Built-ins read-only (`403`) | D-045, D-046 |
| Built-ins | 3 code strategies | Plus 6 builder templates, usable as a starting point | — |
| Costs | One commission rate for buys and sells | Separate buy/sell rates; new `india_delivery` model (STT, exchange charge, SEBI fee, buy-side stamp duty, GST); `cost_model` on runs and optimizations | D-038, D-047 |
| Money display | Always `$`, no separators | In the symbol's currency (`₹1,00,000.00` for NSE/BSE, `$10,000.00` for US, no sign when unknown) | D-049 |
| Quotas | Jobs per tier | Plus saved strategies per tier (5/20/100), shown on the dashboard | D-037 |
| Engine | 2.0.0 | 2.1.0 (sell-side rate). Results of existing strategies are unchanged: same fills and equity (parity test) | D-047 |

### New API
`GET/PATCH/DELETE /api/strategies/<id>/`, `GET /api/strategies/catalog/`, `POST /api/strategies/preview/`. Strategy payloads gain `kind`, `spec`, `python` (read-only rendering) and `warmup_bars`. Runs gain `cost_model`, `sell_commission_pct`, `currency` and `strategy_kind`; optimizations gain `cost_model` and `currency`.

### New UI
`/strategies/new` (blank, or `?from=<id>` to copy a template) and `/strategies/<id>/edit`: entry and exit groups with an AND/OR choice, condition rows built from the catalog, live validation with each error on its field, and a read-only "View as Python" panel. The strategies page has "Use as template", "Edit" and "Delete", and shows the code editor only when custom code is enabled. The run and optimization forms have a cost model selector and symbol suggestions (NSE stocks and indices included).

### Database
| Migration | What | Reversible |
|---|---|---|
| `backtester.0016_builder_and_costs` | `Strategy.kind`, `Strategy.spec`, `code` may be blank, check `ck_strategy_kind_body`; `BacktestRun.strategy_spec`, `cost_model`, `sell_commission_pct`, `commission_pct` → 9 decimals; `OptimizationJob.cost_model` | yes; rollback rounds fees to 6 places and leaves builder strategies with no code |
| `backtester.0017_builder_templates` | seeds 6 built-in builder strategies | yes (removes templates nothing ran against) |

### Files
- **New** `backend/backtester/`: `indicators.py`, `spec.py`, `costs.py`, `test_builder.py` (34 tests), migrations `0016`, `0017`
- `backend/backtester/`: `engine.py` (sell rate, 2.1.0), `data_fetch.py` (warm-up parameter; `download` looked up per call), `models.py`, `serializers.py`, `views.py` (detail, catalog, preview, strategy quota with user-row lock, frozen spec), `jobs.py` (`frozen_strategy`, builder path, OOS run copies costs and spec), `urls.py`
- `backend/accounts/`: `quotas.py` (`strategies` usage and `check_strategy`), `tests.py` (usage dicts; the legacy-migration test now migrates forward to the newest migration when done)
- `backend/vault_core/settings.py`: `strategies` quota per tier
- **New** `frontend/src/pages/StrategyBuilder.jsx`, `frontend/src/builder/spec.js`, tests `src/builder/spec.test.js`, `src/pages/StrategyBuilder.test.jsx`, `src/api.test.js`, fixture `src/test/fixtures.js`
- `frontend/src/`: `pages/StrategyList.jsx` (rewritten), `RunTrigger.jsx`, `OptimizationTrigger.jsx`, `RunDetail.jsx`, `Comparison.jsx`, `Dashboard.jsx`, `components.jsx` (`SymbolInput`, `CostModelFields`, cost-aware assumptions), `api.js` (`money(v, currency)`), `App.jsx` (routes), `App.css`
- `frontend/package.json` (`npm test`; dev deps `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/dom`, `@testing-library/user-event`), `vite.config.js` (`test.environment = jsdom`)
- `.github/workflows/ci.yml`: `npm test` in the frontend job
- `README.md`, `CLAUDE.md`, `docs/*` (new `docs/concepts.md`)

### Operational notes for release
- No new env vars. Optional overrides: `QUOTA_<TIER>_STRATEGIES`.
- **Migrations:** rehearsed on Postgres with 500 runs: upgrade 156 ms, rollback 198 ms, re-upgrade 141 ms, 13/13 checks (see evals).
- First builder run on a symbol may download a longer history (up to 600 bars of warm-up).
- The India cost rates are in `costs.py`; confirm them against current exchange circulars before the release.
