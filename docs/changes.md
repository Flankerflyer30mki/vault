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
- `.github/workflows/ci.yml`: `npm test` in the frontend job; Node 20 → 24 (the new test tools need ≥ 22). `frontend/Dockerfile` build stage also moved to `node:24-alpine`
- `README.md`, `CLAUDE.md`, `docs/*` (new `docs/concepts.md`)

### Operational notes for release
- No new env vars. Optional overrides: `QUOTA_<TIER>_STRATEGIES`.
- **Vercel:** set the project's Node.js version to 24.x (or at least 22.x) to match CI; the build itself still works on 20, but keep one version everywhere.
- **Migrations:** rehearsed on Postgres with 500 runs: upgrade 156 ms, rollback 198 ms, re-upgrade 141 ms, 13/13 checks (see evals).
- First builder run on a symbol may download a longer history (up to 600 bars of warm-up).
- The India cost rates are in `costs.py`; confirm them against current exchange circulars before the release.

## Phase 3 · Comparison and optimization · branch `phase-3-experiments` · 2026-11-16

### Behavior changes
| Area | Before | After | Decision |
|---|---|---|---|
| Batches | `OptimizationJob`: one strategy, stop × target grid | `Experiment` with `kind` = optimization or **comparison** | D-055 |
| Comparison | Not possible | Strategies × symbols (≤ 25 cells) on one period and cost setup, plus an index benchmark per currency; heatmap, overlaid curves | D-056, D-065 |
| Optimization | Stop-loss × take-profit only | Also the builder strategy's own parameters (linked paths move together); invalid combinations skipped and listed | D-057, D-064 |
| Queue order | First in, first out | `(priority, id)`: runs started by hand before batch children | D-059 |
| Worker | Every child reloaded bars and recomputed indicators | Per-worker LRU caches for bars and indicator series | D-058 |
| Heartbeat | Every 50 bars | At most once per second | D-063 |
| Metrics | Final value, CAGR, Sharpe, drawdown, win rate, buy & hold | Plus Sortino, Calmar, exposure, round trips, cost drag | D-060 |
| Experiment pages | Full equity curve of every child | Curves downsampled to ≤ 500 points (extremes kept) | D-062 |
| Built-ins | 3 code + 6 builder | Plus "Buy and Hold" (also the benchmark) | D-065 |
| Quota | `optimizations_per_day` | `experiments_per_day` (comparisons and optimizations) | D-066 |

### API
- **New:** `GET/POST /api/experiments/`, `GET /api/experiments/<id>/`. POST with `kind: "comparison"` takes `strategies`, `symbols`, dates, cash, cost model, optional stop/target; with `kind: "optimization"` takes the old fields plus `param_grid: [{paths, values}]`.
- **Kept:** `/api/optimizations/` and `/api/optimizations/<id>/` (optimizations only).
- **Changed:** experiment detail returns each child's `curve` (downsampled) instead of `equity_curve`; runs gain `experiment`, `priority`, `grid_params`, `sortino_ratio`, `calmar_ratio`, `exposure`, `trade_count`, `cost_drag` (and lose `optimization`). Strategies and preview gain `tunable_params`. Catalog gains `limits` and `benchmarks`. Dashboard `optimizations` → `experiments` (with `kind` and `title`).

### UI
New `/compare` (strategy checkboxes, symbols with suggestion chips, live cell count) and `/experiments/<id>` (comparison heatmap coloured per column with benchmark row and curves per symbol; optimization table with searched-parameter columns, new metrics and skipped combinations). The optimization form lists a builder strategy's tunable parameters. Nav gains "Compare"; the run page shows the new metrics. `/optimize/<id>` still opens the experiment page.

### Database
| Migration | What | Reversible |
|---|---|---|
| `backtester.0018_experiments` (hand-written) | rename `OptimizationJob` → `Experiment` and `optimization` → `experiment`; `kind`, `config`; nullable strategy, blank symbol; run `priority`, `grid_params`, 4 metric columns; `sample` up to 10 chars (`bench`); index `idx_run_claim (status, priority, id)` replaces `idx_run_status_id`; unique OOS constraint recreated on the new field | yes (rehearsed) |
| `backtester.0019_buy_and_hold` | seeds the built-in "Buy and Hold" | yes (removes it if nothing ran on it) |

### Files
- **New** `backend/backtester/cache.py` (LRU, indicator-cache adapter, `downsample`), `test_experiments.py` (22 tests), migrations `0018`, `0019`
- `backend/backtester/`: `models.py`, `engine.py` (exposure counter, Sortino, Calmar, round trips), `spec.py` (`signals(cache=…)`, `tunable_params`, `with_params`), `jobs.py` (priority claim, cached loading, time-based heartbeat, `experiment_status`, OOS copies grid params), `serializers.py` (experiment read/create serializers, downsampled run curves, `cost_drag`, `tunable_params`), `views.py` (experiments, benchmarks, generic idempotent create), `urls.py`, `tests.py`, `test_builder.py` (renames; the detail page's `curve`; Buy and Hold in the template list)
- `backend/accounts/`: `quotas.py` (`experiments_per_day`), `tests.py` (renamed keys), `housekeeping.py`, `views.py` (comments)
- `backend/vault_core/settings.py`: quota rename, `MAX_GRID_PARAMS`, `MAX_COMPARE_STRATEGIES`, `MAX_COMPARE_SYMBOLS`, `BENCHMARKS`
- **New** `frontend/src/experiments.js` (+ tests), `pages/ComparisonTrigger.jsx`, `pages/ExperimentDetail.jsx` (replaces `pages/Comparison.jsx`), `pages/ExperimentPages.test.jsx`; fixtures extended
- `frontend/src/`: `pages/OptimizationTrigger.jsx` (parameter search), `Dashboard.jsx`, `RunDetail.jsx`, `Account.jsx`, `App.jsx`, `App.css`
- `README.md`, `CLAUDE.md`, `docs/*`

### Operational notes for release
- **Renamed env var:** `QUOTA_<TIER>_OPTIMIZATIONS_PER_DAY` → `QUOTA_<TIER>_EXPERIMENTS_PER_DAY` (only if overridden). New optional: `MAX_GRID_PARAMS`, `MAX_COMPARE_STRATEGIES`, `MAX_COMPARE_SYMBOLS`.
- **Migrations:** rehearsed on Postgres with 500 runs and 20 optimizations: upgrade 221 ms, rollback 313 ms, re-upgrade 215 ms, 13/13 checks.
- Comparisons fetch `^NSEI` / `^GSPC` on first use (normal data path).

---

## Phase 3.5 · Engineering hardening · branch `phase-35-hardening` · 2026-11-17

### Behavior changes
| Area | Before | After | Decision |
|---|---|---|---|
| Request tracing | None | `X-Request-ID` on every response (valid incoming IDs kept); stored on runs and experiments; on every log line of the request and of the worker processing its runs | D-070 |
| Logs | Key-value text, gunicorn access log | JSON lines with `request_id` / `run_id`; one access line per request with the **route pattern**, status, duration, user ID (no emails, no raw URLs); `LOG_FORMAT=text` locally | D-070, D-076 |
| Metrics | None | `GET /metrics` (Prometheus text), 404 without `METRICS_TOKEN`, Bearer check: HTTP rate/errors/duration by route + queue health from the DB | D-069 |
| API docs | None | `/api/schema/`, `/api/docs/` (Swagger, bundled assets); on with `DEBUG` or `API_DOCS=1`; CI fails on schema warnings | D-072, D-076 |
| Error tracking | None | Sentry only if `SENTRY_DSN` is set; `send_default_pii=False` | D-071 |
| Rate limits | Counted per gunicorn process (2 processes → each limit doubled) | Shared Postgres table `vault_cache`, one upsert per write; expired rows cleaned hourly | D-073, D-075 |
| Worker shutdown | Finished its run, however long; if the platform killed it, the run sat `running` for 120–150 s and lost an attempt | No claims after `SIGTERM`; past `WORKER_GRACE_S` (20 s) the run is requeued at once, attempt not counted | D-074 |
| Capacity | Unknown | Locust load test with measured knee; worker throughput, claim latency at depth | D-067, D-068 |
| UI errors | Server errors showed only the message | 5xx messages add "(request ID: …)" | D-070 |

### API
- **New:** `GET /metrics` (token-protected), `GET /api/schema/`, `GET /api/docs/` (when docs are on).
- **Changed:** every response has `X-Request-ID`; runs and experiments gain read-only `request_id`. No other request or response shape changed (the schema annotations describe existing behaviour).

### Database
| Migration | What | Reversible |
|---|---|---|
| `backtester.0020_request_ids` | `request_id` (≤ 64 chars, blank) on `BacktestRun` and `Experiment`; default reads the current request's ID | yes (checked on Postgres: down, up, no drift) |
| `backtester.0021_cache_table` (hand-written) | creates the `vault_cache` table via `createcachetable` | yes (drops the table) |

### Files
- **New** `backend/vault_core/observability.py` (context variables, JSON formatter, metrics registry, request middleware, Sentry options), `backend/vault_core/throttle_cache.py` (`UpsertDatabaseCache`), `backend/backtester/ops.py` (queue snapshot and metrics), `backend/backtester/test_ops.py` (21 tests), migrations `0020`, `0021`, `backend/loadtest/locustfile.py`, `backend/requirements-dev.txt`
- `backend/backtester/`: `jobs.py` (`SHUTDOWN`, requeue past the grace period, request/run IDs while working), `management/commands/run_worker.py` (signal handlers), `models.py` (`request_id`), `serializers.py` and `views.py` (schema annotations, `request_id`)
- `backend/accounts/`: `views.py` (schema annotations), `serializers.py` (type hints), `housekeeping.py` (expired cache rows)
- `backend/vault_core/`: `settings.py` (middleware, logging, caches, spectacular, Sentry, `METRICS_TOKEN`, `API_DOCS`, `WORKER_GRACE_S`), `urls.py` (`/metrics`, docs routes); `backend/gunicorn.conf.py` (access log off); `backend/requirements.txt`
- `frontend/src/api.js` (request ID in 5xx messages) + test; `.github/workflows/ci.yml` (schema check)
- `README.md`, `CLAUDE.md`, `docs/*`

### Operational notes for release
- **New env vars (all optional):** `METRICS_TOKEN`, `API_DOCS`, `SENTRY_DSN` (+ `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`), `LOG_FORMAT`, `WORKER_GRACE_S` (keep under the platform's kill window), `THROTTLE_CACHE` (leave unset).
- **Log format changes to JSON.** Anything that parsed the old text lines needs updating (nothing does today).
- **New dependencies:** `drf-spectacular`, `drf-spectacular-sidecar`, `sentry-sdk` (+ transitive). `locust` is dev-only.
- Turning on Sentry sends error data to an external service: a deployment decision.
- Repeat the load test on staging (D-068) and set `NUM_PROXIES` there as before.

---

## Phase 4 · AI assistance · branch `phase-4-assist` · 2026-11-17

### Behavior changes
| Area | Before | After | Decision |
|---|---|---|---|
| Building a strategy | Form only | Also "describe it in words": the AI fills in the form, the user reviews and saves | D-077 |
| Unsupported requests | — | Refused with the reason (shorting, options, intraday, several symbols, fundamentals, sentiment, prompt injection) | D-077, D-080 |
| Worker | Backtests only | Answers AI requests first, then backtests | D-078 |
| Quotas | 4 per tier | Plus `ai_requests_per_day` (5 / 10 / 50) and one active AI request per user; dashboard shows it | D-081 |
| `/metrics` | Queue and HTTP | Plus AI queue depth, outcomes in the last hour, cache hits, tokens today vs budget | D-081 |
| Housekeeping | Guests, sessions, cache rows | Plus AI requests older than 30 days | D-083 |
| Spec validation | A condition could compare something with itself ("SMA 20 crosses above SMA 20") | Rejected: "compares something with itself: the two sides must differ" (found by the AI evaluation) | D-087 |

### API
- **New:** `POST /api/assist/strategy/` (`{"prompt"}` → the request; 503 when AI is off, over budget or the queue is full; 429 for quotas), `GET /api/assist/<id>/` (own requests only).
- **Changed:** the catalog gains `ai_enabled`; dashboard quota gains `ai_requests_per_day`.

### UI
A "Describe your strategy in words" panel at the top of the builder (only when AI is on): character count, privacy note, the AI's notes, refusals and errors. A successful answer replaces the form's rules and fills an empty name; nothing is saved until the user clicks Save.

### Database
| Migration | What | Reversible |
|---|---|---|
| `assist.0001_initial` | `AssistRequest` (prompt, hash, status, outcome, result, provider, model, prompt version, tokens, calls, repairs, latency, cached, attempts, worker, request ID) with claim index `(status, id)` | yes (drops the table) |

### Files
- **New app** `backend/assist/`: `models.py`, `providers.py` (Groq, fake, recording, replay), `prompts.py`, `strategy.py` (generate + repair), `jobs.py` (queue, budget, cache, recovery, retention), `ops.py` (metrics), `serializers.py`, `views.py`, `urls.py`, `tests.py` (39 tests), `evals/` (`cases.py` 60 cases, `grading.py`, `runner.py`, `recordings/` with 3 live runs: gpt-oss-120b full and a 20-case latency sample, gpt-oss-20b full), `management/commands/assist_eval.py` (`--record`, `--replay`, `--reuse`)
- `backend/backtester/spec.py` (identical sides rejected), `test_builder.py` (+1), `jobs.py` (worker loop: AI first, AI stale recovery), `views.py` (`ai_enabled`); `backend/accounts/quotas.py` (`check_ai`, usage), `housekeeping.py`, `tests.py` (usage keys); `backend/vault_core/settings.py` (`AI`, quotas, app), `urls.py` (`/api/assist/`, metrics)
- **New** `frontend/src/builder/AssistPanel.jsx`; `pages/StrategyBuilder.jsx`, `pages/StrategyBuilder.test.jsx` (+3), `pages/Dashboard.jsx`, `App.css`
- `README.md`, `CLAUDE.md`, `docs/*`

### Operational notes for release
- **New env vars (optional; AI is off without them):** `AI_PROVIDER=groq`, `GROQ_API_KEY` (secret; on the API and the worker), `AI_MODEL`, `AI_REASONING_EFFORT`, `AI_DAILY_TOKEN_BUDGET` (below the provider's daily token limit), `AI_MAX_PROMPT_CHARS`, `AI_MAX_REPAIRS`, `AI_TIMEOUT_S`, `AI_MAX_OUTPUT_TOKENS`, `AI_MAX_QUEUED`, `AI_CACHE_DAYS`, `AI_RETENTION_DAYS`, `AI_STALE_AFTER_S`; `QUOTA_<TIER>_AI_REQUESTS_PER_DAY`.
- In the Groq console: switch on Zero Data Retention.
- No new Python dependency (the Groq API is called with `requests`).

---

## Phase 5 · AI research agent · branch `phase-5-agent` · 2026-11-17

### Behavior changes
| Area | Before | After | Decision |
|---|---|---|---|
| Research | The user builds, compares and optimizes by hand | "AI research": a goal → the agent proposes, backtests, refines and chooses; code tests the choice once on a held-out period; a report with checks | D-088 to D-092 |
| Worker | AI requests, then backtests | AI requests, then one research step, then a backtest; a finished research round wakes its run | D-090 |
| Strategies | All built-ins visible | Hidden built-ins (`is_hidden`) are never listed or runnable by users | D-095 |
| Experiments | optimization, comparison | Plus `research` rounds, excluded from experiment lists, the dashboard and the experiments quota | D-095 |
| Quotas | — | `research_per_day` (guest 0 / unverified 1 / verified 3), one research run at a time, counted as one active job | D-093 |
| AI budget | Assistant tokens | Assistant + research tokens share the daily budget | D-093 |

### API
- **New:** `GET/POST /api/research/` (start: `goal`, `symbol`, `start_date`, `end_date`, `objective`, `max_drawdown_pct`, `starting_cash`, `cost_model`; 503 when AI is off or over budget, 429 for quotas, 400 for under 730 days), `GET /api/research/<id>/` (run, budgets, timeline of steps, candidates with in-sample metrics, report).
- **Changed:** `/api/experiments/` and the dashboard no longer list research rounds; dashboard quota gains `research_per_day`.

### UI
New **Research** page (`/research`: goal form, list of runs) and `/research/<id>`: stage bar, budgets used, the report (research vs held-out results, buy & hold, whether it beat buy & hold, the agent's summary, process checks), the candidates table (each links to its backtest; "Save as strategy"), and the timeline of the agent's actions with its reasons and any rejected actions. Nav gains "Research".

### Database
| Migration | What | Reversible |
|---|---|---|
| `backtester.0022_research` | `Strategy.is_hidden`; experiment kind `research` | yes |
| `backtester.0023_research_candidate` | seeds the hidden "AI research candidate" strategy | yes (removes it if unused) |
| `assist.0002_research` | `ResearchRun` (goal, period, split, objective, constraint, status, stage, state, rounds, report, budgets used, worker, request ID; claim index) and `ResearchStep` (timeline) | yes |

### Files
- **New** `backend/assist/agent.py` (prompts, action checks, grounding), `research.py` (state machine, rounds, held-out test, report, queue), `research_urls.py`, `test_research.py` (18 tests); `assist/models.py`, `serializers.py`, `views.py`, `jobs.py` (shared token budget)
- `backend/backtester/models.py` (`is_hidden`, `research` kind), `jobs.py` (worker loop, wake on round finished), `views.py` (research rounds excluded), migrations `0022`, `0023`; `backend/accounts/quotas.py` (`check_research`, usage, hidden strategies), `tests.py`; `backend/vault_core/settings.py` (`RESEARCH`, quotas, schema enum names), `urls.py`
- **New** `frontend/src/pages/Research.jsx`, `ResearchDetail.jsx`, `ResearchPages.test.jsx` (5 tests), `src/research.js`; `App.jsx`, `App.css`, `pages/Dashboard.jsx`
- `README.md`, `CLAUDE.md`, `docs/*`

### Operational notes for release
- **New env vars (optional):** `RESEARCH_MAX_STEPS`, `RESEARCH_MAX_MODEL_CALLS`, `RESEARCH_MAX_BACKTESTS`, `RESEARCH_MAX_TOKENS`, `RESEARCH_MAX_CANDIDATES_PER_ROUND`, `RESEARCH_MAX_SEARCH_VALUES`, `RESEARCH_MIN_TRADES`, `RESEARCH_MIN_DAYS`, `RESEARCH_STALE_AFTER_S`, `RESEARCH_MAX_ATTEMPTS`; `QUOTA_<TIER>_RESEARCH_PER_DAY`. Research needs the Phase 4 AI settings.
- **Not yet run against a real model** (D-094): do one live research run on staging before announcing it.
- A research run costs roughly 10–40K tokens; with the free tier's 200K a day per model, plan for a handful of runs a day.

### Follow-up: fixes from the first live run · branch `phase-5-live-fixes` · 2026-11-17 (D-096)
- Number check accepts values to 4 decimals; agent steps get 4,000 output tokens and low reasoning effort
  (`RESEARCH_MAX_OUTPUT_TOKENS`, `RESEARCH_REASONING_EFFORT`); explore capped at `RESEARCH_MAX_EXPLORE_ROUNDS` (2);
  candidates with identical results flagged (`same_as` in the API, "(same results as cN)" in the UI); a replaced summary
  is shown as a warning.
- `providers.get_provider(max_tokens, reasoning_effort)`; files: `assist/agent.py`, `research.py`, `providers.py`,
  `serializers.py`, `test_research.py` (+4); `vault_core/settings.py`; `frontend/src/pages/ResearchDetail.jsx` (+ test),
  `App.css`; docs.

---

## Phase 6 · Release · `main` · 2026-11-17/18

### What shipped
v2 (Phases 0–5) merged into `main` (PR #10, `2552517`) and deployed: frontend on Vercel (`vault-lovat-beta.vercel.app`),
API with an embedded worker on Render (`vault-api-pqje.onrender.com`, free plan, Docker), database upgraded in place.

### Changes
| Change | PR | Decision |
|---|---|---|
| `vercel.json` rewrites `/api/*` to the Render API; tab title "Vault" and a Vault icon (was "frontend" and Vite's) | #9 | D-029, D-097 |
| Hotfix: the rewrite's source is a regex so `/api/.../` (trailing slash) matches | #11 | D-098 |
| Production data: 17 suggested symbols + `^GSPC` pre-loaded (2005 → 2026-11-16) from a residential connection | — (ops) | D-099 |
| Phase 6 docs (decisions, release record, README deploy notes) | #12 | D-097–D-100 |
| Access log: `xff_hops` and `via_vercel` (counts only) to measure the proxy chain | #13 | D-101 |
| `NUM_PROXIES=4` set on Render from the measured hop count | — (config) | D-101 |
| README rewritten as an overview; the full spec moved to `docs/reference.md`; `CLAUDE.md` untracked | #14 | D-102 |
| Emails logged without SMTP are plain text: links were quoted-printable (`=3D`, split lines) and failed when copied | #15 | — |
| Sign in with Google (`POST /api/auth/google/`, button on sign-in, sign-up and the guest Account page); `has_password` on the user; `google_client_id` on `/api/auth/me/`; a `/privacy` page (required by Google's consent screen) and a footer | #16 | D-103 |
| UI redesign 1/6, foundation: design tokens (dark default + light theme), Inter + JetBrains Mono self-hosted, sidebar layout (top bar on phones), restyled controls, tables, badges and cards; fixes centred text (Vite template leftover) and grey buttons | #18 | D-104 |
| UI redesign 2/6, lists: page headers; dashboard as clickable rows (result vs buy & hold, status badges), "Running now" only while something runs, empty states with a next step, usage moved to the bottom; Strategies as one expandable list with a name filter and a Backtest shortcut per strategy (`/run?strategy=<id>` preselects it); skeleton placeholders replace "Loading…" on every page | #19 | D-104 |
| UI redesign 3/6, results: run page leads with total return, the gap to buy & hold (in points), CAGR, Sharpe and max drawdown; equity chart themed, drawn linear (the monotone spline invented wiggles between daily closes) with the starting cash marked; trades, assumptions and reproducibility in keyboard-accessible tabs; "Run again" opens New Backtest with the strategy and symbol filled in; experiment charts use the same theme | #20 | D-104 |
| UI redesign 4/6, builder: rules on the left, a sticky summary on the right that reads them back as sentences ("Buy when close is above SMA(200) and RSI(14) is below 35") with warm-up, problems and Save; the all/any choice sits inside the sentence; numbered condition cards laid out the same way every time (left side, then "is above" + right side); the Python view is a collapsible code block; fix: icon-only buttons (remove, delete) were squeezed to a dot by the small-button padding | #21 | D-104 |
| UI redesign 5/6, experiments and research: New Backtest, Compare, Optimize and AI research forms as sectioned cards with related fields side by side (fixes the cramped research labels); experiment and research pages get page headers with status badges, styled tables and stage chips; fix: Compare had the same stop-loss/take-profit step bug as New Backtest (0.08 and 0.15 refused), regression test added | #22 | D-104 |
| UI redesign 6/6, polish: `Ctrl+K` / `⌘K` command palette (pages, "Backtest: <strategy>" for every strategy, theme switch, sign out; WAI-ARIA combobox, arrow keys, Enter, Esc, focus restored) opened from the keyboard or a sidebar search button; theme state shared through `useSyncExternalStore` so every toggle stays in step; Account page header and a red danger zone for deleting the account; README stack line and test count | #23 | D-104 |
| Fix: warm-up lookback gets a week of margin, so runs starting right after a weekend or holiday get their warm-up bars (Buy and Hold from 2024-01-01 reported "only 0 of 1 warm-up bars"); regression test | #24 | D-105 |
| Fix: New Backtest couldn't be submitted with stop-loss/take-profit set (step 0.01 counted from min 0.001 made 0.08 and 0.15 invalid; the browser refused silently). Both now start blank and accept any 0.001 step; regression tests added | #18 | D-104 |

### Configuration applied (Render `vault-api`)
Added `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `FRONTEND_URL` (the Vercel domain), `SECURE_PROXY_SSL_HEADER=1`,
`DB_SSLMODE=require`, `RUN_MIGRATIONS=1`, `EMBEDDED_WORKER=1`, `AI_PROVIDER=groq`, `GROQ_API_KEY`; removed
`CORS_ALLOWED_ORIGINS`; kept `SECRET_KEY`, `DATABASE_URL`; health check `/health/ready`. Vercel: removed `VITE_API_URL`.

### Database
v1 at backtester `0011` (no accounts) → v2 at `0023` + `accounts`, `assist`, `sessions` on deploy, as rehearsed. Backup:
`pg_dump` custom format taken before the release (kept outside the repo).

### Not done yet
Email provider, `METRICS_TOKEN`, Sentry, HSTS; a fallback data source; CSS/UX fixes; restricting Render to traffic
from Vercel (D-101); the free database expires 2026-12-10.
