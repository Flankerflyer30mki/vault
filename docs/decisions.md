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
| D-012 | 2 | Builder: form → JSON spec → generated Python → existing sandbox; API accepts JSON only | Superseded by D-033 |
| D-013 | 4–5 | AI behind one provider module; Gemini free tier first | Accepted in principle |
| D-014 | 6 | Build phase by phase on staging; release once at the end | Accepted |
| D-015 | 1 | Custom User model, email as login | Accepted |
| D-016 | 1 | Same-domain API (Vercel/Vite/nginx proxy `/api`) with Django login cookies and CSRF | Accepted |
| D-017 | 1 | Sign-up, email verification and password reset now; console email in dev | Accepted |
| D-018 | 1 | One-click guest accounts, convertible, deleted after 7 days | Accepted |
| D-019 | 1 | Existing anonymous data moved to a hidden legacy account | Accepted |
| D-020 | 1 | Everything private; other users' items return 404 | Accepted |
| D-021 | 1 | Per-tier quotas plus per-IP limits on login, sign-up, reset and guest | Accepted |
| D-022 | 1 | Dashboard v1 contents (no leaderboard yet) | Accepted |
| D-023 | 1 | Account management: change password, change email, delete account | Accepted |
| D-024 | 1 | Daily quotas use a rolling 24-hour window | Accepted |
| D-025 | 1 | Lock the user's row while creating a job (exact quotas, race-free idempotency) | Accepted |
| D-026 | 1 | Enforce CSRF explicitly on anonymous auth endpoints | Accepted |
| D-027 | 1 | Remove `django-cors-headers` | Accepted |
| D-028 | 1 | Compose frontend image: nginx (serves SPA plus `/api` proxy) instead of `serve` | Accepted |
| D-029 | 1 | `vercel.json` rewrite uses a `VAULT_API_HOST` placeholder, replaced at deployment | Accepted |
| D-030 | 1 | MD5 password hasher in account tests only | Accepted |
| D-031 | 1 | Guest/session cleanup runs inside the worker loop, hourly | Accepted |
| D-032 | 1 | Frontend verified by an end-to-end smoke test through the proxy, not unit tests (yet) | Accepted |
| D-033 | 2 | Builder strategies are a JSON spec interpreted by the engine; no code is generated or run | Accepted |
| D-034 | 2 | Spec v1 format: versioned; entry and exit groups (all/any) of up to 10 conditions | Accepted |
| D-035 | 2 | Eight v1 indicators: SMA, EMA, RSI, MACD, Bollinger, ATR, Donchian, ROC | Accepted |
| D-036 | 2 | Long-only: a strategy is either fully in the stock or in cash; no shorting | Accepted |
| D-037 | 2 | Saved-strategy limits per tier: guest 5, unverified 20, verified 100 | Accepted |
| D-038 | 2 | India as a first-class market: NSE/BSE symbols, INR, an Indian delivery cost preset | Accepted |
| D-039 | 2 | Frontend component tests with Vitest and React Testing Library | Accepted |
| D-040 | Later | Options backtesting: decide after Phase 3 | Superseded by D-051 |
| D-041 | 2 | Keep a concepts glossary (`docs/concepts.md`) for interview revision | Accepted |
| D-042 | 2 | Signals without position state: exit wins over entry on the same bar | Accepted |
| D-043 | 2 | Dynamic warm-up: longest lookback, 3× for smoothed indicators, capped at 600 bars | Accepted |
| D-044 | 2 | Indicator conventions fixed and documented (Wilder, population std, Donchian prior bars, ROC in %) | Accepted |
| D-045 | 2 | Server-driven builder: catalog endpoint + live preview; the server is the only validator | Accepted |
| D-046 | 2 | Strategies editable (runs keep a frozen copy); delete refused once runs exist; built-ins read-only | Accepted |
| D-047 | 2 | Fee rates stored with 9 decimals; separate buy and sell rates | Accepted |
| D-048 | 2 | Tests may never reach the data provider | Accepted |
| D-049 | 2 | Currency inferred from the symbol, display only | Accepted |
| D-050 | All | Target roles: backend, full-stack, AI/agentic; fintech is the domain, not the role | Accepted |
| D-051 | All | Drop options backtesting | Accepted |
| D-052 | All | No ML feature for its own sake | Accepted |
| D-053 | 3.5 | New phase: engineering hardening (load test, observability, OpenAPI, shared throttle cache) | Accepted |
| D-054 | 3 | Phase 3 framed as a backend problem, with only light quant | Accepted |
| D-055 | 3 | One batch model: `OptimizationJob` becomes `Experiment` (kind = comparison or optimization) | Accepted |
| D-056 | 3 | Comparison = strategies × symbols matrix, at most 25 cells, plus an index benchmark | Accepted |
| D-057 | 3 | Parameter search over builder spec values; invalid combinations skipped and reported | Accepted |
| D-058 | 3 | One job per child run, plus a per-worker cache of bars and indicator series | Accepted |
| D-059 | 3 | Priority lanes: runs started by hand are claimed before batch children | Accepted |
| D-060 | 3 | New metrics (Sortino, Calmar, exposure, trades, cost drag) and an index benchmark | Accepted |
| D-061 | 3 | Walk-forward validation deferred; the single 70/30 split stays | Deferred |
| D-062 | 3 | Experiment pages get downsampled equity curves (≤ 500 points, extremes kept) | Accepted |
| D-063 | 3 | Heartbeat by time (≤ 1 per second), not every 50 bars | Accepted |
| D-064 | 3 | Tunable parameters are grouped by indicator instance; a search moves linked paths together | Accepted |
| D-065 | 3 | The benchmark is an ordinary child run of a built-in "Buy and Hold" strategy on the index | Accepted |
| D-066 | 3 | Hand-written rename migration; `/api/optimizations/` kept as an alias; quota renamed `experiments_per_day` | Accepted |
| D-067 | 3.5 | Load testing with Locust (dev-only dependency) | Accepted |
| D-068 | 3.5 | Load test locally with Render-like resource limits now; repeat on staging in Phase 6 | Accepted |
| D-069 | 3.5 | Token-protected `/metrics` in Prometheus text format: RED metrics from middleware, queue health from the DB | Accepted |
| D-070 | 3.5 | JSON log lines with request IDs that link API request → run → worker logs | Accepted |
| D-071 | 3.5 | Sentry error tracking, off unless `SENTRY_DSN` is set; no personal data sent | Accepted |
| D-072 | 3.5 | OpenAPI via drf-spectacular; CI fails on schema warnings; docs off in production by default | Accepted |
| D-073 | 3.5 | Throttle counters in a Postgres database cache shared by all processes (no Redis) | Accepted |
| D-074 | 3.5 | Graceful worker shutdown on SIGTERM: stop claiming, finish within a grace period or requeue | Accepted |
| D-075 | 3.5 | Throttle cache writes as one upsert; expired rows removed by housekeeping (found by the load test) | Accepted |
| D-076 | 3.5 | Every endpoint documented explicitly in the schema; JSON logs replace gunicorn's access log | Accepted |
| D-077 | 4 | Phase 4 scope: describe a strategy in words → the builder form is filled in; the user reviews and saves | Accepted |
| D-078 | 4 | AI requests are queued jobs handled by the worker, never made inside an HTTP request | Accepted |
| D-079 | 4 | Groq (free tier) behind a provider interface; a fake provider for tests; model name in config (refines D-013) | Accepted |
| D-080 | 4 | The model returns the JSON spec (or a refusal) only; `spec.validate` checks it; up to 2 repair rounds with path-keyed errors | Accepted |
| D-081 | 4 | Cost and abuse controls: daily AI quota by tier, 1,000-character prompts, global daily token budget, answer cache | Accepted |
| D-082 | 4 | Evaluation: ~60 cases graded by behaviour (identical signals on fixed price series), refusals, prompt-injection cases, ablation | Accepted |
| D-083 | 4 | Privacy: the UI says descriptions go to Groq; prompts kept 30 days; no account data sent | Accepted |
| D-084 | 4 | "Explain this result" deferred to Phase 5 | Deferred |
| D-085 | 4 | Default model `openai/gpt-oss-120b`, chosen by the evaluation (60/60 vs 57/60 for gpt-oss-20b) | Accepted |
| D-086 | 4 | Ablation cut to what fits the free tier; the full ablation is deferred | Deferred |
| D-087 | 4 | The validator rejects a condition whose two sides are identical (found by the evaluation) | Accepted |
| D-088 | 5 | Research agent: a goal on one symbol → candidates proposed, backtested, refined; the user saves what they want | Accepted |
| D-089 | 5 | Fixed stages (explore → refine → choose); the agent picks actions as checked JSON, not vendor tool-calling | Accepted |
| D-090 | 5 | The agent is a resumable state machine on the job queue: it waits for its backtests without holding a worker | Accepted |
| D-091 | 5 | The last 30% is held out: never shown to the agent, tested once by our code, reported next to buy & hold | Accepted |
| D-092 | 5 | The agent writes the summary; every number in it must come from the results, else a plain summary is used | Accepted |
| D-093 | 5 | Budgets per run (8 decisions, 14 model calls, 40 backtests, 40K tokens); quotas 0/1/3 per day; shared AI budget | Accepted |
| D-094 | 5 | No live evaluation in Phase 5; quality vs baselines deferred; first live run on the Phase 6 checklist | Deferred |
| D-095 | 5 | Research runs use a hidden built-in strategy and a `research` experiment kind; schema and data migrations split | Accepted |
| D-096 | 5 | Fixes from the first live research run: grounding precision, agent output room, explore cap, twin candidates | Accepted |
| D-097 | 6 | Deploy on the existing free Render service and database: Docker, embedded worker, migrations at start; straight to production after a backup and a rehearsal on a copy | Accepted |
| D-098 | 6 | Vercel `/api` rewrite uses a regex source so paths ending in `/` match (production hotfix) | Accepted |
| D-099 | 6 | Yahoo blocks Render's IPs: popular symbols are pre-loaded from a residential connection; a fallback data source follows | Accepted |
| D-100 | 6 | After release, PRs target `main` directly (CI gate); `release/v2` is kept in sync but no longer needed | Accepted |

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

## D-012 · Builder pipeline (Phase 2, in principle) · *Superseded by D-033*
- **Decision:** Form → validated JSON spec (the source of truth) → server-generated Python built from templates → the existing sandbox. The public API accepts only JSON, never Python. The engine calculates the indicators the strategy declares. The generated code is shown read-only in the UI.
- **Why:** User-built strategies can run on the public site without opening it to arbitrary code, and they reuse the one existing way of running strategies.

## D-013 · AI provider (Phases 4–5, in principle)
- **Decision:** One provider module so switching providers changes one file. Start with Gemini's free tier. The agent will likely need a paid model with a spending cap, or users' own keys; to be decided in Phase 5. The app must work fully when AI is unavailable.
- **Why:** Vault validates everything the AI produces, so model quality affects retries, not safety. That makes cost and limits the deciding factors.

## D-014 · Build in phases, release once
- **Decision:** Each phase merges to `main` with CI passing and is deployed to staging. Production gets one release at the end, after rehearsing migrations on a copy of production data and taking a backup.

---

# Phase 1 · Accounts and personal workspace (approved 2026-11-16)

## D-015 · Custom User model with email as the login
- **Options:** (A) a custom `accounts.User` with email as the login, (B) Django's default `User`.
- **Decision:** A. Fields: `email` (unique, stored lowercase), `display_name`, `email_verified`, `is_guest`, `is_system`, `date_joined`. The user's tier (guest, unverified, verified) is derived from these flags.
- **Why:** Django recommends setting up a custom user model at the start of a project, because switching later means rewriting migrations. Nothing in Vault referenced `auth.User` yet, so this was the cheapest moment. The `auth_user` table already in production stays unused.
- **Interview angle:** why `AUTH_USER_MODEL` has to be decided early, and why it was still safe here (no existing foreign keys to `auth.User`).

## D-016 · Same-domain API with Django session cookies
- **Context:** The frontend (Vercel) and API (Render) are on different domains. Safari and Firefox block cookies sent to a different domain, so cookie logins don't work cross-domain.
- **Options:** (A) a proxy makes `/api` same-domain, plus Django's session cookie (`HttpOnly`) and CSRF protection, (B) JWT tokens (`simplejwt`) with a refresh token stored in the browser, (C) a managed provider (Clerk/Auth0/Supabase).
- **Decision:** A. Vercel forwards `/api/*` to Render, Vite does the same in development, and nginx does it in the compose frontend image. The frontend calls the relative path `/api`. CORS and `django-cors-headers` are removed.
- **Why:** JavaScript can't read the login cookie, so an XSS bug can't steal it. Django's sessions and CSRF protection are well tested. There's no token refresh logic and no CORS. B is the fallback.
- **Interview angle:** cross-domain cookie blocking, `SameSite`, and why login CSRF needs explicit protection (DRF only checks CSRF for users who are already logged in).

## D-017 · Sign-up, email verification and password reset now
- **Decision:** All three are built in Phase 1 using Django's token generators, which are tied to the user's state so a used or outdated link stops working. In development, emails are printed to the console. SMTP (e.g. Resend) is configured by environment variables at deployment. Unverified users can sign in but get the lower quota.
- **Why:** A released app needs password reset. Verification ties the higher quota to a real email address.

## D-018 · One-click guest accounts
- **Decision:** `POST /api/auth/guest/` creates a temporary account and signs the visitor in. A guest can convert to a full account (email and password), keeping their data. Unconverted guests are deleted after `GUEST_TTL_DAYS` (7) by the worker's housekeeping loop.
- **Why:** Recruiters and visitors can try the app with no sign-up, and nobody shares a demo account.

## D-019 · Existing data goes to a hidden legacy account
- **Decision:** A data migration creates an inactive system user (`legacy@system.vault.invalid`, no usable password) and assigns all existing runs, optimizations and custom strategies to it. Built-in strategies have no owner and are shared.

## D-020 · Private by default; other users' items return 404
- **Decision:** Every queryset is filtered to the logged-in user (built-in strategies are also visible). Another user's item returns **404, not 403**, so the API doesn't reveal that it exists. This also covers using another user's strategy in a new run, and their idempotency keys.

## D-021 · Quotas per tier, plus per-IP limits on auth endpoints
- **Decision:**

  | Limit | Guest | Unverified | Verified |
  |---|---|---|---|
  | Active jobs (queued or running runs and optimizations; an optimization counts as 1) | 2 | 3 | 10 |
  | Single backtests per rolling 24 hours | 20 | 30 | 200 |
  | Optimizations per rolling 24 hours | 2 | 3 | 20 |

  Every value can be overridden by an env var (`QUOTA_<TIER>_<LIMIT>`). The global `MAX_ACTIVE_RUNS` cap stays. Login, sign-up and password reset are limited to `THROTTLE_AUTH` (10/min per IP), and guest creation to `THROTTLE_GUEST` (5/hour per IP). The existing job, read and write limits now count per user for signed-in users.
- **Why:** The quotas bound how much compute one person can use. The per-IP limits slow down password guessing and mass sign-ups.

## D-022 · Dashboard v1
- **Includes:** runs in progress with progress; recent runs with return vs. buy & hold; my strategies plus built-ins; quota usage; quick actions; recent optimizations with their out-of-sample result. Served by one `GET /api/dashboard/` call.
- **Excludes for now:** a "best strategies" leaderboard ranked by Sharpe (it encourages picking whatever looked luckiest; it returns in Phase 3 with adjusted Sharpe) and activity charts.

## D-023 · Account management
- **Decision:** Change password (requires the current one; the session stays signed in), change email (requires the password; email has to be verified again), and delete account (requires the password, except for guests; deletes all the user's data).

## Phase 1 · Implementation decisions made while building

## D-024 · Rolling 24-hour window for daily quotas
- **Options:** (A) a rolling 24-hour window, (B) a calendar day (resetting at midnight UTC).
- **Decision:** A.
- **Why:** There's no burst at midnight UTC and no timezone confusion for users in India or the US. It's one indexed query on `(owner, created_at)`.

## D-025 · Lock the user's row while creating a job
- **Context:** A quota check followed by an insert is a race. Two requests sent at the same moment can both see "9 of 10" and both get in. The same race affected duplicate `Idempotency-Key` requests.
- **Decision:** `IdempotentCreate` runs `select_for_update()` on the requesting user's row inside the create transaction, then re-checks the idempotency key and the quota.
- **Why:** It only serialises one user's own requests, so other users never wait. Quotas become exact (unlike the global `MAX_ACTIVE_RUNS`, which stays a soft cap), and a duplicate key waits for the first request instead of failing.
- **Interview angle:** check-then-act races, and why a lock per user beats a global lock.

## D-026 · Explicit CSRF on anonymous endpoints
- **Context:** DRF's `SessionAuthentication` only checks CSRF once a request is already signed in. Without an extra check, a hostile site could submit the login form and sign the victim into the attacker's account (login CSRF).
- **Decision:** A `CsrfEnforced` mixin runs Django's CSRF check on every unsafe request to the auth views, signed in or not. A test client that behaves like a browser (`BrowserClient`) proves it, including that the token rotates on login.

## D-027 · Remove `django-cors-headers`
- **Decision:** Remove the package and its settings.
- **Why:** With the API on the same origin, CORS has no job left. Keeping an allowlist nobody uses is a misconfiguration waiting to happen. It's also one less dependency to audit.

## D-028 · nginx for the compose frontend image
- **Decision:** The frontend image now serves the built SPA with nginx and forwards `/api` to `backend:8000`, passing the `Host` header (with port) through so Django's CSRF Origin check passes.
- **Why:** `serve -s` can't proxy, and the same-origin setup has to work in every environment. Production uses Vercel, development uses Vite, and compose now uses nginx.

## D-029 · Placeholder API host in `vercel.json`
- **Context:** Vercel can't read environment variables inside `rewrites`.
- **Decision:** `vercel.json` contains `https://VAULT_API_HOST/api/:path*`. Replacing it is a deployment checklist item, documented in the README.
- **Revisit:** if a staging and a production frontend need different API hosts, use a Vercel middleware that reads an env var.

## D-030 · Fast password hasher in account tests only
- **Context:** PBKDF2 at Django's default of 1.2M iterations measured **209.7 ms per hash**. MD5 measured **0.024 ms**. The account tests hash passwords dozens of times.
- **Decision:** Account test classes use `@override_settings(PASSWORD_HASHERS=[MD5])`. Production keeps PBKDF2, which the end-to-end smoke test exercises (sign-up took about 320 ms there).
- **Why:** The tests check our logic, not Django's hashing. Without this, account tests would spend most of their time hashing.

## D-031 · Cleanup inside the worker loop
- **Decision:** `accounts.housekeeping.run()` (deletes expired guests and expired sessions) runs from `work_forever` once an hour.
- **Why:** There's no cron and no scheduler service on Render's free tier, and the worker already runs a timed loop for stale-job recovery.

## D-032 · How the frontend is verified
- **Options:** (A) add Vitest and React Testing Library unit tests now, (B) an end-to-end smoke test through the real proxy plus lint and build.
- **Decision:** B for Phase 1.
- **Why:** The riskiest frontend change is the cookie, CSRF and proxy setup, which only an end-to-end test proves. Component unit tests are proposed for Phase 2, when the builder UI brings real client-side logic.

---

# Phase 2 · Strategy builder (approved 2026-11-16)

Context: before Phase 2 we compared Vault with the Moneylogix strategy builder that inspired the overhaul. That project is an
**options position builder** (legs, payoff at expiry, Greeks, margin) evaluated at one point in time. Vault's builder is a
**rule builder** (when to buy and sell) tested on years of real prices. Same word, different problem; the two are
complementary rather than competing. Condition rows of the form *indicator · comparison · indicator or value*, combined with
AND/OR, are the standard way retail tools (for example Zerodha Streak, TradingView's strategy tester, Amibroker) build rule strategies.

## D-033 · Interpret the spec; never generate or run code (supersedes D-012)
- **Options:** (A) generate Python from templates and run it in the existing sandbox (the D-012 plan); (B) interpret the
  validated JSON spec inside the engine's process.
- **Decision:** B. A read-only "View as Python" rendering is produced for people to read; it is never executed.
- **Why:** (1) **Safety:** user input stays data. There is no string-built code, so there is nothing to escape and no exception
  to the "no custom code in production" rule (`ALLOW_CUSTOM_CODE` stays off). (2) **Speed:** no subprocess and no JSON round trip
  per bar, which matters for the grids in Phase 3 and the many candidate strategies in Phase 5. (3) **Testability:** one small
  evaluator with a fixed set of operators.
- **Gave up:** builder strategies can't contain anything the operators don't express. That's intended: the custom-code path
  still exists where an operator enables it.
- **Interview angle:** "The API accepts only data; user input never becomes code."

## D-034 · Spec v1 format
- **Decision:** `{"version": 1, "entry": {"all"|"any": [conditions]}, "exit": {"all"|"any": [conditions]}}`. A condition is
  `{"left": operand, "op": op, "right": operand}`. An operand is an indicator (`ind`, `params`, `output`), a price field
  (open, high, low, close, volume) or a constant. Operators: `>`, `<`, `>=`, `<=`, `crosses_above`, `crosses_below`. Each group
  holds 1–10 conditions. No nested groups in v1.
- **Why:** flat groups are easy to fill in on a form and hard for an AI to get wrong (Phase 5). `version` lets later phases
  extend the format without breaking saved strategies. Stop-loss and take-profit stay run parameters, so the existing
  optimization grid keeps working unchanged.

## D-035 · v1 indicators
- **Decision:** SMA, EMA, RSI (Wilder), MACD (line, signal, histogram), Bollinger Bands (upper, middle, lower), ATR, Donchian
  channel (upper, lower), ROC. Periods 2–200.
- **Why:** they cover the four common rule styles: trend, momentum, volatility and breakout. More indicators add reference tests
  and code without changing what the builder demonstrates.

## D-036 · Long-only (no shorting)
- **What it means:** a strategy is either **fully in the stock** or **in cash**. `BUY` while in cash opens a position; `SELL`
  while holding closes it; any other signal is ignored. A bearish signal means "step aside into cash", not "bet on the fall".
- **Options:** (A) long-only; (B) add short selling to the engine.
- **Decision:** A.
- **Why:**
  1. **Realism for Indian equities.** In the Indian cash market, retail traders can't hold a short position in delivery (overnight):
     shorting is intraday only, or done through futures and options. A backtest that let a strategy short `RELIANCE.NS` for months
     would report results nobody could actually get.
  2. **Unlimited loss changes the engine's core.** A long position can lose at most 100%; a short can lose more. Shorting needs
     margin, forced closing (margin calls), borrow costs and a check that shares can be borrowed at all.
  3. **Stops and targets flip.** For a short, the stop sits above entry and the target below; every fill rule (gaps, intrabar
     touches, "stop wins") would need rewriting and re-testing.
  4. **The ledger invariant changes.** Today `equity = cash + quantity × close` with `quantity ≥ 0`. A short makes the quantity
     negative, and cash includes sale proceeds you don't really own.
  5. **Cleaner comparisons in Phase 3.** Long-only results compare directly with buy-and-hold.
- **Gave up:** a strategy can't profit from falling prices; it can only avoid them by holding cash. For daily-bar rule strategies on
  single stocks this matches how most retail systems trade delivery.
- **Revisit when:** derivatives arrive (see D-040). In India, the realistic way to express a bearish view is futures or options,
  not shorting the cash stock.
- **Interview angle:** "Vault is long-only on purpose: Indian retail traders can't carry a short position overnight in the cash
  market, so a backtest that allowed it would be unrealistic."

## D-037 · Saved-strategy limits
- **Decision:** guest 5, unverified 20, verified 100 saved strategies (env-overridable like the other quotas). Built-ins don't count.
- **Why:** without a limit one account can fill the database. Same tiers as Phase 1, so verification still unlocks more.

## D-038 · India as a first-class market
- **Decision:** (1) symbol suggestions include NSE stocks and indices (`RELIANCE.NS`, `^NSEI`, …); (2) the currency is inferred
  from the symbol (`.NS`/`.BO` and Indian indices → INR, no suffix → USD, anything else → unknown) and money is shown in it;
  (3) a new **India delivery cost model** adds statutory charges per side on top of the broker's brokerage: STT, exchange
  transaction charges, SEBI fee, stamp duty (buy side only) and GST. Buys and sells cost different amounts, so the engine gets a
  separate sell-side rate.
- **Why:** relevant to Indian fintech roles, and a realistic cost model shows domain knowledge. A single "commission %" can't
  express stamp duty (buy only) or GST on some charges but not others.
- **Gave up:** flat per-order charges (DP charges on sells, minimum brokerage) aren't modelled; only percentage charges are.

## D-039 · Frontend component tests
- **Decision:** add Vitest and React Testing Library (dev dependencies only) and run them in CI.
- **Why:** the builder is the first page with real client-side logic (form state ↔ spec). Round-trip and rendering bugs live there,
  and the end-to-end smoke test from Phase 1 can't reach them cheaply.

## D-040 · Options backtesting: decide after Phase 3 (Deferred)
- **Options considered:** (A) real NSE end-of-day options data from the free F&O bhavcopy files (largest, strongest); (B) option
  prices modelled with Black-Scholes from the underlying (quick but misleading: ignores the volatility smile and real premiums).
- **Decision:** decide after Phase 3, when we know how solid the core is and how much time is left. B is not recommended.

## D-041 · Concepts glossary
- **Decision:** keep `docs/concepts.md`: each concept used in Vault, where it lives in the code, and how to say it in an interview.

## Phase 2 · Implementation decisions made while building

## D-042 · Exit wins; no position state in the interpreter
- **Context:** a spec needs "buy when flat if entry, sell when holding if exit". Passing the position into the strategy would change
  the engine's `decide(bar, indicators)` contract that code strategies use.
- **Decision:** per bar, `SELL` if exit is true, else `BUY` if entry is true, else `HOLD`. The long-only engine already ignores a
  `BUY` while holding and a `SELL` while flat, so the result is the same as position-aware logic in every case but one: entry
  and exit both true while flat. Then the strategy stays out.
- **Why:** signals become a pure function of the bars, so they can be precomputed for the whole series in one pass (fast, and
  trivially free of look-ahead). Staying out on contradictory signals is the conservative choice, in the same spirit as the
  engine's "stop wins". The parity test proves this matches the Python built-in exactly.

## D-043 · Dynamic warm-up
- **Decision:** warm-up = the largest lookback among the spec's indicators: the bars needed for a value to exist one bar before
  the first decision (so a crossover can fire on the first bar), plus 2n more for EMA-based indicators so the seed fades. Capped
  at 600 bars. Code strategies keep 50. `load_bars` asks for `warmup × 2` calendar days and the manifest records the count.
- **Why:** a fixed 50 would leave SMA-200 empty for 150 bars of the test period, silently changing the strategy. Smoothed
  indicators never fully forget their seed; 3n bars is a standard compromise (seed weight ≈ e⁻³ ≈ 5% for EMA).
- **Consequence:** an EMA or RSI value on a date depends slightly on how much history precedes it, as in every charting tool.
  Recorded in [tradeoff.md](tradeoff.md).

## D-044 · Indicator conventions
- **Decision:** EMA seeded with an SMA then α = 2/(n+1); RSI and ATR use Wilder smoothing (α = 1/n); Bollinger uses the
  population standard deviation; Donchian uses the n bars before the current one; ROC is a percentage; RSI of flat prices is 50.
- **Why:** implementations disagree on each of these, and an unstated choice makes results impossible to reconcile. Each choice
  is the original author's definition or the common charting default, and each is pinned by a reference test.

## D-045 · Server-driven builder form
- **Decision:** `GET /api/strategies/catalog/` describes everything the form offers (indicators with parameter ranges and
  defaults, operators, limits, cost models, suggested symbols). `POST /api/strategies/preview/` validates and renders a spec
  without saving; the form calls it 400 ms after each change. Errors come back keyed by path and are shown on the matching
  field. The form disables the browser's own validation (`noValidate`) so the server's wording is the only message.
- **Why:** one allowlist, in one place. Adding an indicator to `indicators.REGISTRY` makes it appear in the UI with no frontend
  change, and the client can never accept something the server rejects.

## D-046 · Edit, delete and templates
- **Decision:** owners can edit a strategy's name and spec (`PATCH`); its kind can't change. Runs keep their frozen copy, so
  editing never rewrites results. Deleting a strategy that has runs returns `409` (deleting it would cascade to those runs).
  Built-ins are read-only (`403`); "Use as template" opens a copy in the builder.
- **Why:** reproducibility. A result must always be traceable to exactly what produced it.

## D-047 · Fee precision and separate sell rate
- **Decision:** `commission_pct` and the new `sell_commission_pct` are stored with 9 decimal places; the engine charges the
  sell rate on sells (`Params.sell_commission_pct`, defaulting to the buy rate). `ENGINE_VERSION` 2.0.0 → 2.1.0.
- **Why:** India's buy rate with zero brokerage is 0.001186226; 6 places would round away ₹0.02 per ₹1 lakh on every fill. Stamp
  duty applies only to buys, so one rate can't describe both sides.

## D-048 · Tests may never reach the data provider
- **Context:** while building, a test's warm-up reached further back than the fixture's coverage, and the worker quietly
  downloaded real AAPL data from Yahoo during the test (2.6 s instead of ~30 ms, and real prices replaced the fixture).
- **Decision:** fixtures cover the whole warm-up span, and builder API tests patch `data_fetch.download` and fail if it was
  called. `load_bars` now looks `download` up on each call (it was bound as a default argument, which made patching impossible).
- **Why:** a test that depends on the network is slow, flaky, and no longer tests the data it claims to.

## D-049 · Currency from the symbol, display only
- **Decision:** `.NS`/`.BO` and Indian indices → INR; plain US tickers and US indices → USD; any other suffix → unknown (shown
  without a currency sign). Never used in a calculation.
- **Why:** asking Yahoo for metadata costs a network call per symbol and fails often. A wrong currency sign would be worse
  than none, hence "unknown" rather than a USD default for foreign exchanges.

---

# Direction after Phase 2 (agreed 2026-11-16)

## D-050 · Target roles shape the roadmap
- **Decision:** Vault is **an engineering project set in a fintech domain**. The target roles are backend, full-stack and
  AI/agentic engineering, including at fintech companies, where these are also the job titles.
- **Consequence:** prefer work that shows engineering depth (concurrency, reliability, measured performance, observability,
  agent evaluation) over more market features. The domain work already done (India costs, INR, long-only rationale,
  reproducibility) is kept as domain credibility and isn't extended for its own sake.

## D-051 · Drop options backtesting (supersedes D-040)
- **Why:** a large domain subsystem (bhavcopy data pipeline, expiries, lot sizes, margin) that adds little backend or AI
  signal and would take time from the AI phases.

## D-052 · No ML feature for its own sake
- **Why:** price prediction overfits, and interviewers know it. ML only if it falls naturally out of Phase 5, measured
  against a baseline.

## D-053 · New Phase 3.5: engineering hardening
- **Scope:** a load test with real capacity numbers (runs per minute by worker count, p50/p95 API latency, queue throughput),
  observability (`/metrics`, request IDs in logs, error tracking), OpenAPI docs, and throttle counters in a shared cache.
- **Why:** "I measured what the system handles" is one of the strongest backend interview lines, and Vault can't say it yet.

## D-054 · Phase 3 is framed as a backend problem
- **Decision:** comparison and optimization are built as batch orchestration (fan-out, fan-in, partial failure, fair
  scheduling, shared computation), with only light quant (a benchmark and a few extra risk metrics).

---

# Phase 3 · Comparison and optimization (approved 2026-11-16)

Starting point: optimization covers one strategy and only stop-loss × take-profit. Every child run reloads its bars and
recomputes its indicators. The queue is strictly first-in-first-out. There's no way to compare strategies with each other,
which was the original question that started the overhaul ("the optimization is intra-strategy; what about inter-strategy?").

## D-055 · One batch model: `Experiment`
- **Options:** (A) rename `OptimizationJob` to a general `Experiment` with a `kind` (comparison or optimization) and a
  `config` JSON; (B) add a separate `ComparisonJob` next to it.
- **Decision:** A. Child runs link to their experiment; status is still derived from the children, never stored.
- **Why:** one fan-out/fan-in mechanism for every batch, which Phase 5's agent will also use. B would mean two nearly identical
  systems, and a third for the agent.
- **Cost:** a rename migration on an existing table (rehearsed like the others). `/api/optimizations/` stays as an alias of
  `/api/experiments/` for optimizations, so existing clients and tests keep working.

## D-056 · Comparison is a strategies × symbols matrix
- **Options:** (A) N strategies on one symbol; (B) strategies × symbols, at most 25 cells.
- **Decision:** B, shown as a heatmap table plus overlaid equity curves, with an index benchmark (D-060).
- **Why:** answers "which strategy works on which stocks", and the larger fan-out is a better orchestration problem.

## D-057 · Parameter search over builder specs
- **Decision:** an optimization of a builder strategy can vary any numeric indicator parameter, addressed by its path
  (`entry.all[0].left.params.period`), combined with the stop-loss × take-profit grid. Each combination is a copy of the spec,
  validated on its own. A value out of range rejects the request (400, with the path); a **combination** that's invalid only
  together (for example MACD fast ≥ slow) is **skipped and reported**, not failed. The limit stays 25 combinations until the
  Phase 3.5 load test measures what the system handles. Code strategies keep the stop-loss × take-profit grid only.
- **Why:** this is the optimization users actually want ("which EMA lengths?"), and a spec can be rewritten safely where code can't.

## D-058 · One job per child, plus a per-worker cache
- **Options:** (A) each child independent, reloading everything (today); (B) the whole batch as one job; (C) A plus a
  per-worker cache of bars and indicator series.
- **Decision:** C. Bars are cached by `(symbol, dates, warm-up, coverage fetched_at)`, so a re-download invalidates them;
  indicator series by `(data hash, indicator, params)`. Both caches are bounded (LRU) and per process.
- **Why:** the job stays small, so batches still spread across workers, retry per child and report progress per child, while
  the duplicated work disappears. B would put a whole batch on one worker and lose it all on one crash. The hit rate and
  the time saved are measured in evals.

## D-059 · Priority lanes, not per-user fairness
- **Context:** an account is one person, and the demo's other users are a few recruiters on guest accounts. Contention between
  accounts is rare, and per-account quotas already cap it. The contention that does happen is **within one account**: a batch
  (and, in Phase 5, the agent's batches) queued ahead of a quick run the same person starts by hand.
- **Options:** (A) first come, first served; (B) priority lanes; (C) B plus round-robin between batches.
- **Decision:** B. Runs started by hand get priority 0 and batch children priority 1; the claim query orders by
  `(priority, id)` with the same `SKIP LOCKED`. Nothing is pre-empted: the running job always finishes. Revisit C in Phase 5,
  when the agent runs several experiments at once.
- **Example:** a 25-run comparison is queued, and you start one backtest while child 4 is running. FIFO starts your run after
  the remaining ~22 children (~22 s at ~1 s each); priority lanes start it as soon as child 4 finishes (~1 s).
- **Interview angle:** interactive work ahead of background batch work, the same pattern as interactive and batch queues in real systems.

## D-060 · Light quant: metrics and benchmark
- **Decision:** add Sortino, Calmar, exposure (share of bars in the market), number of round trips and cost drag (costs as a
  share of starting cash), all derived from the same ledger. Comparisons add an **index benchmark** per currency (NIFTY 50
  `^NSEI` for INR, S&P 500 `^GSPC` for USD) as an extra child run of a built-in buy-and-hold strategy with zero costs.
- **Why:** cheap, standard, and the benchmark reuses the data pipeline and the queue instead of a special path.

## D-061 · Walk-forward validation deferred
- **Decision:** keep the single chronological 70/30 split. The `Experiment` model leaves room for stages, so walk-forward can
  be added later without a redesign. (D-054: light quant.)

## D-062 · Downsampled curves for experiment pages
- **Decision:** the experiment detail API returns each child's equity curve reduced to at most ~500 points, keeping each
  bucket's minimum and maximum so peaks and drawdowns stay visible. A single run's page still gets the full curve.
- **Why:** 25 curves × 2,500 points is ~60k points to send and draw; the chart can't show more than its pixel width anyway.

## Phase 3 · Implementation decisions made while building

## D-063 · Heartbeat by time, not by bar count (found by profiling)
- **Context:** after adding the worker cache, a 25-child experiment got only 12–13% faster although the cache hit rate was
  high. Profiling one child (`cProfile` on `jobs.execute`) showed **153 of 219 ms (70%) in 41 progress `UPDATE`s**, one every
  50 bars. That interval was sized when strategies ran in a sandbox and a run took seconds; with interpreted specs a run's
  simulation takes milliseconds, so the bookkeeping cost more than the work.
- **Decision:** heartbeat (and progress) at most once per second. Stale recovery waits 120 s, so this is still far more often
  than needed; a fast run now writes no progress rows at all, a slow run still beats every second (both tested).
- **Result:** median per child 174 → 37–39 ms; 25-child wall time 5.7 → 2.4 s; the cache's own saving rose from 13–15% to
  32–36% once the heartbeat stopped dominating.
- **Interview angle:** measure before optimising: the cache was the planned fix, but the profile found the real cost.

## D-064 · Linked parameters
- **Context:** templates use the same indicator in both rules (EMA 12 crosses above EMA 26 to buy, below to sell). Varying the
  entry's EMA without the exit's would test "enter on EMA 10, exit on EMA 12", which nobody asked for.
- **Decision:** `spec.tunable_params` groups every path of one indicator instance (same indicator and parameters) under one
  label, such as `ema(12).period` with two paths or `macd(12, 26, 9).fast` with four. A search must name a whole group; half
  a group is rejected.

## D-065 · Benchmark as an ordinary child run
- **Decision:** a built-in builder strategy "Buy and Hold" (enter on the first bar, never exit; migration `0019`) runs on the
  index with zero costs as one more child (`sample="bench"`). No special code path: same queue, data pipeline, metrics and
  pages. It also appears as a template users can pick.

## D-066 · Rename mechanics and compatibility
- **Decision:** migration `0018` is hand-written (rename model and field; constraints and the claim index dropped and recreated),
  because `makemigrations` can't tell a rename from "drop and create" without asking, and guessing wrong loses data.
  `/api/optimizations/` stays as an alias of `/api/experiments/` (limited to optimizations) so the Phase 0–2 tests run
  unchanged against it. The quota key becomes `experiments_per_day` (env `QUOTA_<TIER>_EXPERIMENTS_PER_DAY`); comparisons and
  optimizations share it.

---

# Phase 3.5 · Engineering hardening (approved 2026-11-16)

Starting point: key-value text logs, health checks, and nothing else operational. No metrics, no way to link an API request to
the worker run it created, rate-limit counters kept per process (so two gunicorn processes double every limit), no API docs,
no capacity numbers, and a deploy that kills a worker mid-run leaves that run stuck for 120 s until stale recovery.

## D-067 · Locust for load testing
- **Options:** (A) Locust; (B) k6; (C) a custom script.
- **Decision:** A, in a new `requirements-dev.txt` so it never ships.
- **Why:** same language as the backend, scenarios are plain code, CSV output feeds the evals. Its slower load generator doesn't
  matter at this scale.

## D-068 · Where the load test runs
- **Decision:** locally now, with the API container limited to Render-like resources and the hardware stated next to every
  number; repeat on staging in Phase 6. Capacity runs raise rate limits through env vars; the limits have their own tests.
- **Why:** honest numbers now instead of none until deployment.

## D-069 · Metrics endpoint
- **Options:** (A) a Prometheus client library plus a Prometheus/Grafana server; (B) `/metrics` in Prometheus text format,
  computed by Vault, protected by a token; (C) logs only.
- **Decision:** B. RED metrics (rate, errors, duration by route) come from the request middleware; queue health (depth by
  priority, oldest queued age, active runs, completions and failures by category in the last hour, run-time percentiles) comes
  straight from the queue table. Disabled (404) unless `METRICS_TOKEN` is set.
- **Why:** the queue is Postgres, so its health is a SQL query, valid across all processes. No new infrastructure, and the
  format is ready for any scraper later.

## D-070 · JSON logs with request IDs
- **Decision:** every request gets an ID (a valid incoming `X-Request-ID` is kept, anything else replaced), returned in the
  response and attached to every log line written during it. A run stores the ID of the request that created it, and the worker
  logs that run's lines with both IDs. One access-log line per request: method, **route pattern** (not the raw URL), status,
  duration, user ID; no emails. Logs are JSON lines.
- **Why:** "this user's click → this run → this worker error" becomes one search.

## D-071 · Sentry, off by default
- **Decision:** the Sentry SDK initialises only when `SENTRY_DSN` is set, with `send_default_pii=False`. Turning it on sends
  error data to an external service, so that's a deployment decision for the user.

## D-072 · OpenAPI with drf-spectacular
- **Decision:** `/api/schema/` and `/api/docs/` (Swagger UI from a bundled package, no CDN), on in development and only with
  `API_DOCS=1` in production. CI runs the schema generator with `--fail-on-warn`, so the docs can't drift from the code.

## D-073 · Throttle counters in Postgres
- **Options:** (A) Django's database cache in Postgres; (B) Redis; (C) keep them per process.
- **Decision:** A. The cache table is created by a migration, so deploys need nothing extra.
- **Why:** correct limits across processes and instances without reintroducing a service the project removed on purpose. The
  load test measures what it costs per request.

## D-074 · Graceful worker shutdown
- **Context (corrected while building):** the worker already stopped claiming on `SIGTERM` and finished its current run before
  exiting. What was missing was a deadline: a run still going when the platform kills the process (Render: 30 s after
  `SIGTERM`) was left `running` until stale recovery, 120–150 s later, and that attempt counted against `MAX_ATTEMPTS`.
- **Decision:** on `SIGTERM` (or `SIGINT`) the worker stops claiming new runs. The current run may finish within
  `WORKER_GRACE_S` (20 s, under Render's 30 s); past that, the progress callback raises and the run goes straight back to
  the queue without counting an attempt.
- **Why:** deploys restart workers; a run shouldn't wait two minutes, or burn a retry, because of a deploy.

## Phase 3.5 · Implementation decisions made while building

## D-075 · One-statement throttle-cache writes (found by the load test)
- **Context:** with Django's stock database cache, the load test showed +13–18 ms at p50 and ~20% less throughput at saturation
  than per-process counters (later runs: 31–41 req/s at 40–80 users in two runs, against 52–55 with the upsert). Reading `DatabaseCache.set()` explained it: every write runs `SELECT COUNT(*)` over the whole
  table (to decide whether to cull), a savepoint, a `SELECT` of the key, an `UPDATE`/`INSERT` and the savepoint release, and a
  rate-limited request writes its counter every time.
- **Decision:** `vault_core.throttle_cache.UpsertDatabaseCache`: `set()` is a single `INSERT … ON CONFLICT (cache_key) DO
  UPDATE`; expired rows are deleted by the worker's hourly housekeeping instead of on the request path. Same table and format
  as Django's cache, so the two are interchangeable.
- **Why:** keeps the correctness of shared counters (D-073) without paying for culling on every request.

## D-076 · Explicit schema for every endpoint; one access log
- **Context:** the first schema check found 17 endpoints it couldn't document (all auth views, dashboard, catalog, preview)
  and 13 untyped fields, so generated docs would have silently left them out. The docs page also needed template and static
  configuration that an API-only project didn't have.
- **Decision:** each view declares its request and response with `extend_schema`; computed fields have type hints; enum
  names are fixed; CI fails on any warning. gunicorn's access log is turned off because the JSON access line replaces it.

---

# Phase 4 · AI assistance (approved 2026-11-17)

Starting point: strategies are built by hand in the form. Phase 4 adds a single-shot assistant with the user in control;
Phase 5 adds the agent. What Phase 4 builds (provider module, AI job queue, quotas and budget, evaluation harness) is what
Phase 5 reuses.

## D-077 · Scope: words → a filled-in builder form
- **Decision:** the user describes a strategy in plain language; the AI returns a spec, which loads into the builder form for
  the user to review, change and save. The AI never saves or runs anything. Unsupported requests (shorting, options,
  intraday, several assets, fundamentals) get an honest refusal naming what isn't supported, never a look-alike strategy.
  Stop-loss and take-profit are run settings, not spec rules, so the AI reports them as notes.
- **Why:** shows the interesting AI engineering (structured output, validation, repair, evaluation) on a feature with a clear
  right answer, and keeps a person between the model and anything that costs money or changes data.

## D-078 · AI requests run in the worker
- **Options:** (A) call the model inside the HTTP request; (B) queue an `AssistRequest` row that the worker processes; the
  UI polls.
- **Decision:** B. The worker checks AI requests before backtests (they are interactive and short).
- **Why:** a call takes seconds, and Phase 3.5 measured 2 gunicorn processes per instance: two people waiting on the AI
  would stall the API. Matches "the request path never waits on outside services", and reuses claims, request IDs,
  graceful shutdown and stale recovery. Cost: about a second of polling, and a worker is busy while the model answers.

## D-079 · Groq behind a provider interface (refines D-013)
- **Options:** Gemini free tier; Groq free tier; a paid model with a cap.
- **Decision:** one `Provider` interface (`complete(messages) → text + token counts`), a fake for tests and CI, and Groq as
  the real provider through its OpenAI-compatible HTTP API (no SDK). Provider, model and key come from env
  (`AI_PROVIDER`, `AI_MODEL`, `GROQ_API_KEY`); without them AI is off and everything else works.
- **Why:** free with no card; fast, which matters even more for Phase 5's agent loop; Groq says it keeps no inference
  data by default and doesn't train on API data, where free Gemini may use prompts. Groq hosts several models on one key,
  so the evaluation can compare models at no cost.

## D-080 · Output contract, validation and repair
- **Decision:** the model must answer with one JSON object: `{"status": "ok", "name", "spec", "notes"}` or
  `{"status": "unsupported", "reason"}`. The spec goes through the same `spec.validate` allowlist as hand-built strategies.
  If it fails, the path-keyed errors go back to the model, at most twice. The prompt (indicator list, parameter ranges,
  operators, semantics) is generated from `indicators.REGISTRY`, so a new indicator reaches the AI with no prompt edit.
  The user's text is marked as data, not instructions.
- **Why:** the model only ever produces data that the existing validator already treats as untrusted (D-033), so a bad or
  manipulated answer costs a retry, never safety.

## D-081 · Cost and abuse controls
- **Decision:** AI requests per 24 h by tier (guest 5, unverified 10, verified 50), one active AI request per user, prompts
  ≤ 1,000 characters, a global daily token budget (`AI_DAILY_TOKEN_BUDGET`, set below the provider's free limit; when it's
  used up, AI answers 503 and nothing else is affected), and identical descriptions answered from earlier results (same
  normalised text, prompt version and model, within 7 days). Tokens, outcomes and queue depth go to `/metrics`.
- **Why:** the free tier's limits belong to the whole deployment, not to each user.

## D-082 · Evaluation
- **Decision:** about 60 cases in categories (simple, several conditions, each indicator, vague wording, Hindi-English mix,
  unsupported, prompt injection). A spec answer passes if it produces **exactly the same signals** as the reference spec on
  fixed synthetic price series (trend, range, crash, random walk), since the same strategy can be written many ways; a
  test checks every reference actually trades on those series, so an empty match can't pass. Unsupported and injection
  cases must be refused; a marker in the system prompt must never appear in an answer. Reported: valid rate, valid on the
  first try, behaviour match, correct refusals, false refusals, repair rounds, p50/p95 latency, tokens. An ablation shows
  what each part earns (bare prompt → + catalog → + examples → + repair). CI replays a recorded live run, so it is free and
  deterministic, and fails if the prompt changes without a new recording.
- **Why:** "it seemed to work" isn't evidence; the AI roles the project targets ask how a model feature is measured.

## D-083 · Privacy
- **Decision:** the assistant panel says the description is sent to an AI service (Groq). Only the user's text and the
  fixed system prompt are sent: no email, no account data, no other strategies. Requests are kept 30 days (for support and
  the answer cache), then deleted by housekeeping, and are deleted with the account. Groq's Zero Data Retention setting
  should be switched on in its console (a deployment step for the owner).

## D-084 · "Explain this result" deferred to Phase 5
- **Why:** the agent has to explain its choices anyway; keeping Phase 4 to one feature keeps its evaluation sharp.

## Phase 4 · Decisions made from the evaluation

## D-085 · Default model: gpt-oss-120b
- **Options:** `openai/gpt-oss-120b` or `openai/gpt-oss-20b` (both free on Groq; no Llama model was available on the account).
- **Decision:** 120b. It passed 60/60 against 57/60, and 20b's misses were the dangerous kind: valid specs that mean
  something else (comparisons reversed), a note promising leverage that doesn't exist, futures quietly treated as the index.
- **Cost:** ~0.5 s slower at the median (1.7 s vs 1.2 s). `AI_MODEL` switches it; a switch needs a new evaluation run.

## D-086 · Ablation cut short
- **Context:** each model's free tier allows 200,000 tokens a day, about one full 60-case run. The bare-prompt run on
  gpt-oss-20b ran out after 52 cases (without the catalog it needed more repair rounds).
- **Decision:** stop it; report it as partial and unrecorded (54% vs 94% on the same 52 cases); skip the "catalog without
  examples" step. "No repair" comes from the recorded full runs (temperature 0). Redo the full ablation if a paid tier or a
  prompt change makes it worth the tokens.
- **Why:** the user asked to skip what isn't needed; the model comparison and the recorded 60/60 are the evidence.

## D-087 · A condition can't compare something with itself
- **Context:** the first live run produced "SMA 20 crosses above SMA 20" for "golden cross", and `spec.validate` accepted
  it. Such a rule never fires (or, with `>=`, always does); the form could save it too.
- **Decision:** reject a condition whose two normalised sides are equal: "compares something with itself: the two sides
  must differ". Same indicator with different outputs (Bollinger upper vs lower) is still allowed.
- **Result:** the repair loop turned the model's answer into the 50/200 cross; the evaluation went from 59/60 to 60/60.

---

# Phase 5 · AI research agent (approved 2026-11-17)

Starting point: the Phase 4 assistant turns one sentence into one strategy for the user to review. Phase 5 lets an
agent do the research loop itself (propose, backtest, read results, refine, choose) within hard limits, with the
honesty problem of any search ("try enough strategies and one looks great by luck") designed in from the start.
Constraint agreed with the user: finish today, so no live evaluation runs (D-094).

## D-088 · Scope
- **Decision:** the user gives a goal, a symbol, a period, an objective (Sharpe, Calmar or total return) and optionally a
  maximum drawdown. The agent proposes builder strategies, backtests them, refines the promising ones and chooses one.
  It may queue backtests on its own (inside quotas and budgets); it can't save strategies, change costs, stops or the
  symbol, or reach anything outside Vault. The user saves any candidate with one click. One symbol per run; builder
  strategies only.
- **Why:** an agent that acts on its own (it spends backtests) but whose output is decided on by a person.

## D-089 · Fixed stages, JSON actions
- **Options:** (A) a fixed pipeline with the model at set points; (B) a free tool-calling loop; (C) the model chooses
  actions inside stages that code controls.
- **Decision:** C. Stages: explore (`test`, `next_stage`) → refine (`test`, `search`, `choose`) → validate and report
  (code only). The agent answers each step with one JSON action, checked by `agent.check` (allowed in this stage, specs
  through `spec.validate`, no repeats, within budget, chosen candidate eligible). A rejected action goes back with
  path-keyed errors. Each step's prompt is rebuilt from the run's state (goal, budgets, a table of tested candidates), so
  the context doesn't grow with the number of steps.
- **Why JSON actions rather than the provider's tool-calling API:** the same JSON mode produced 140/140 valid answers on
  this model in Phase 4, tool calling on Groq was never measured, and plain JSON keeps the agent provider-independent.

## D-090 · A resumable state machine on the job queue
- **Context:** an agent that queues 20 backtests and then waits would hold the worker those backtests need; with one
  worker it would wait for ever.
- **Decision:** `ResearchRun` is a job like a run. Each claim is one short step (one model call, or code work). After
  queueing a round it goes to `waiting`; when the round's last backtest finishes, the worker re-queues it
  (`on_backtest_finished`, plus a sweep). Steps' writes are atomic and ownership-checked; a step that crashed is
  re-queued by stale recovery, and a step re-queued while its round is unfinished goes back to waiting instead of
  asking the agent about unfinished results (a bug the tests found). Graceful shutdown re-queues without using an
  attempt.

## D-091 · Held-out period, tested once by code
- **Decision:** the last 30% of the period (`OOS_FRACTION`) is held out. Every candidate backtest ends the day before it;
  the agent's prompts never contain the held-out dates (checked on every step). After the choice, code runs the chosen
  candidate once on the held-out period. The report shows the research and held-out results side by side, buy & hold
  over each, how many candidates were tried, and process checks: held-out tested exactly once, agent never saw it,
  budgets respected, summary grounded, drawdown constraint on the held-out period.
- **Why:** an agent that searches is a data-snooping machine; the held-out result is the honest number, and showing how
  many strategies were tried says how optimistic the research number is.

## D-092 · Grounded report
- **Decision:** the agent writes the summary from a JSON of facts. Every number in its text must appear in those facts
  (as given, rounded, or as a percentage); otherwise it gets one chance to rewrite, then a plain code-written summary is
  used and the check is marked failed. The tables and checks are always rendered by code, never by the model.

## D-093 · Budgets and quotas
- **Decision:** per research run: 8 decisions, 14 model calls (including rejected answers and the report), 40 backtests,
  40,000 tokens; up to 6 candidates per round and 6 values per search; a candidate needs ≥ 3 round trips to be eligible.
  When a budget runs out, code chooses the best eligible candidate. Research tokens count against the same daily AI
  budget as the assistant. Research runs per 24 h: guest 0, unverified 1, verified 3; one at a time; one counts as one
  active job; its backtests are part of the run, not of the backtest or experiment quotas. At least 730 days per run.

## D-094 · No live evaluation in Phase 5
- **Context:** the user wants the revamp finished today; the free tier's daily tokens were already spent on Phase 4's
  evaluation.
- **Decision:** ship with tests only: a scripted fake model drives complete runs (real backtests, waiting and resuming,
  held-out test, report), plus checks of every rejection path, budgets, crashes, shutdown and grounding. The quality
  question (does the agent beat buy & hold, the best template and a random search with the same budget on held-out data?)
  is deferred. A first live run is on the Phase 6 checklist. The docs say Phase 5 has not been run against a real model.

## D-095 · Placeholder strategy and the `research` kind
- **Decision:** `BacktestRun.strategy` is required, so research backtests point at a hidden built-in strategy
  ("AI research candidate", `is_hidden`), each with its own frozen spec, as optimization children do. Hidden strategies
  never appear in lists and can't be run by users. Research rounds are Experiments of kind `research`, excluded from
  experiment lists, the dashboard and the experiments quota. The migration is split (0022 schema, 0023 data): on
  Postgres, rolling back a data change and an `ALTER TABLE` in one transaction fails with "pending trigger events" (found
  by the legacy-migration test).

## D-096 · Fixes from the first live research run
- **Context:** the user ran the agent locally against gpt-oss-120b (AAPL, 2015-01-01 to 2023-06-21, Sharpe, max drawdown
  30%). It finished honestly (19 candidates; the pick did not beat buy & hold on the held-out years, and the report said
  so) but showed four problems the scripted tests couldn't: (1) the summary was rejected for quoting real values to four
  decimals ("1.2907"); (2) 4 of 7 agent answers used exactly the 2,000-token output cap, and steps slowed from 4 s to 27 s;
  (3) the agent explored for all 4 of its decisions and never refined; (4) two candidates were different rules with
  identical trades (MACD histogram over zero vs line over signal). The UI also showed the replaced summary as a failed
  rule (red ✗).
- **Decision:** (1) the number check accepts a fact's value rounded to up to 4 decimals (and as a percentage);
  (2) agent steps get `RESEARCH_MAX_OUTPUT_TOKENS` 4,000 and `RESEARCH_REASONING_EFFORT` "low";
  (3) after `RESEARCH_MAX_EXPLORE_ROUNDS` (2) explore rounds the run moves to refine by itself (logged as a system step);
  (4) a candidate whose results equal an earlier one's is marked "same results as cN" for the agent and in the UI; the
  replaced summary is shown as a warning, not a ✗.
- **Not yet re-verified live:** the day's free tokens were used by that run; the next live run should confirm (2) and (3).

---

# Phase 6 · Release (2026-11-17/18)

Starting point: `main` was v1, live on Vercel (`vault-lovat-beta.vercel.app`) and a free Render web service
(`vault-api-pqje`, Docker) with a free Render Postgres 16 (v1 data at backtester `0011`, no accounts app; it expires
2026-12-10). The user wanted the revamp finished the same day.

## D-097 · How v2 was deployed
- **Options:** a staging copy first, or production directly with safeguards.
- **Decision:** production directly, on the existing services, after: a `pg_dump` backup (restore-verified), a
  **rehearsal of the v2 migrations on a restored copy of the production data** (v1 → v2 in 4.9 s, every row kept), and
  `check --deploy` with production settings. Free plan, so: no separate worker (`EMBEDDED_WORKER=1`), migrations at start
  (`RUN_MIGRATIONS=1`, single instance), same Dockerfile as CI. Existing database upgraded in place; v1's runs moved to the
  hidden legacy user as designed in Phase 1. Email and Sentry left off; `METRICS_TOKEN` not set yet.
- **Why:** a staging copy would have doubled the setup (and `vercel.json` names one API host); the rehearsal on real
  data removed the main risk (the irreversible schema upgrade), and the backup covers the rest.
- **Rollback:** Render → previous deploy **and** restore the backup (v1 code can't run on the v2 schema).

## D-098 · Vercel rewrite: regex source (production hotfix)
- **Context:** after release, the live site couldn't reach its API: `"/api/:path*"` didn't match Django's URLs ending in
  `/`, so `/api/auth/csrf/` was served the SPA's `index.html` (while `/api/auth/csrf` reached Django and was redirected
  to the slash URL, which proved the cause). No test covered Vercel's routing; local dev uses Vite's proxy.
- **Decision:** `{"source": "/api/(.*)", "destination": "https://vault-api-pqje.onrender.com/api/$1"}`; shipped as a
  hotfix PR to `main` (CI green), live within a minute. The smoke test now calls the API through the Vercel domain.

## D-099 · Yahoo blocks Render; pre-load now, a fallback source next
- **Context:** the first live backtest on a symbol not yet stored (MSFT) failed with "No market data": Yahoo refuses
  requests from Render's datacenter IPs, while the same code works from a residential connection.
- **Decision (now):** pre-load the 17 suggested symbols and `^GSPC` (2005 → 2026-11-16, ~95,000 bars) into the
  production database from the user's machine, with Vault's own `load_bars` (same bars and coverage the worker would
  write). Result: the MSFT backtest completed in 26 ms. **Limits:** other symbols still fail on production, and stored
  data stops updating (each request retries Yahoo, fails, and uses what's stored).
- **Next:** a fallback provider that allows server access, used when Yahoo fails.

## D-100 · Workflow after release
- **Decision:** with `main` deployed, follow-up PRs branch from and target `main` (CI must pass; each merge deploys).
  `release/v2` was fast-forwarded to `main` after the hotfix and is no longer needed for day-to-day work.

## D-101 · `NUM_PROXIES` = 4, measured
- **Context:** per-IP limits (login, signup, guest creation) identify the client by counting proxies back from the end of
  `X-Forwarded-For`. The code default (1 on Render) was a guess. Too low makes every visitor look like the same proxy,
  so real users throttle each other; too high lets a client choose its own address.
- **Decision:** measure instead of guessing. The access log records `xff_hops` and `via_vercel` (the count, never the
  addresses; PR #13). Requests through the Vercel domain on 2026-11-18 showed `xff_hops: 4, via_vercel: true`, so
  `NUM_PROXIES=4` is set on Render.
- **Limit:** a client calling the Render hostname directly passes fewer proxies and can still choose the address used
  for its per-IP limits. Per-user limits are unaffected. Closing this means making Render accept only traffic from Vercel.

## D-102 · README as an overview; the spec moves to `docs/reference.md`
- **Context:** the README had grown into a 500-line specification. Visitors (reviewers, recruiters) need what Vault does,
  how it's built and the measured results first.
- **Decision:** the README is a short overview (features, engineering highlights with numbers, architecture, stack, how to
  run and test, links). The full specification moved unchanged, apart from link fixes and the `NUM_PROXIES` rows, to
  `docs/reference.md` (its earlier history is in `README.md`), and that file is now the one to keep in sync with behaviour.
  `CLAUDE.md` (local assistant notes) is no longer tracked and is git-ignored; older commits still contain it.

