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
