# Tradeoffs

For each decision: what we gained, what we gave up, and when to revisit it. IDs match [decisions.md](decisions.md).

## Phase 0

### D-003 · Replace a symbol's bars on every fetch
| Gained | Gave up | Revisit when |
|---|---|---|
| One price scale per symbol, guaranteed | **Reproducibility of old runs.** Re-running an old backtest after a restatement uses the new prices, so results can change. The stored `data_sha256` shows the data changed, but the old bars are gone. | Users need exact re-runs of old results → keep versioned snapshots |
| Simple: one transaction, no adjustment math | **Larger downloads.** Each fetch pulls the whole known span, not just the missing part. | Many symbols with decades of history, or provider rate limits become a problem |
| Concurrent fetches stay safe (upsert) | The first run of every existing symbol after deploy downloads it once | — |

Alternative not taken: storing unadjusted prices plus corporate actions and adjusting ourselves. That's the most correct approach, but it's a data-platform project, and Yahoo's corporate-action data has its own quality problems.

### D-004 · `SymbolCoverage`
| Gained | Gave up | Revisit when |
|---|---|---|
| No endless re-downloads for recently listed stocks or market closures | **Trusting one fetch.** If Yahoo returns a partial history once, that span counts as covered until a request extends past it | Partial-response problems show up → add a "refresh older than N days" rule |
| A fact ("we asked for this") instead of a guess | One more table and migration | — |

### D-005 · Recovery sweep for stuck optimizations
| Gained | Gave up |
|---|---|
| Covers every way a run can end, including unexpected ones | Up to ~30 s delay before the out-of-sample run is queued in those rare cases |
| Idempotent, so it's safe to run often | One extra query every 30 s per worker. It's indexed and cheap, but it grows with the number of optimization jobs |

### D-006 · `close_old_connections()` every loop
| Gained | Gave up |
|---|---|
| The worker recovers by itself after a database restart | A cheap connection check per loop (every 2 s when idle) |

### D-007 · `NUM_PROXIES` default by platform
| Gained | Gave up | Revisit when |
|---|---|---|
| Rate limits can't be bypassed with a made-up header | **Correctness depends on the proxy count.** If it's wrong, all users can end up sharing one IP's limits (too high) or spoofing works again (too low) | Staging check of the real `X-Forwarded-For` chain; any change of proxy such as a Vercel rewrite |

### D-008 · Reject stop ≤ slippage
| Gained | Gave up |
|---|---|
| No meaningless results; past results unchanged | A few unusual settings are no longer allowed (they were never meaningful) |

### D-009 · Load only shown fields
| Gained | Gave up |
|---|---|
| Bounded memory for list endpoints | A small risk: if a list serializer starts showing a skipped field, Django quietly makes one extra query per row. The deferred-fields test guards against this |

## Process

### D-014 · Release once, at the end
| Gained | Gave up |
|---|---|
| Users see one coherent upgrade; no half-finished features in production | **The live demo keeps the old bugs until release.** One large deploy is riskier than several small ones, so we rehearse it on staging with a copy of production data |

### D-011 · Docker deferred
| Gained | Gave up |
|---|---|
| A lighter local setup (WSL), no Docker Desktop | Local and production environments differ more (WSL vs. container image), until the Render decision is made |

## Phase 1

### D-016 · Same-origin proxy with session cookies (vs JWT)
| Gained | Gave up | Revisit when |
|---|---|---|
| The login cookie is `HttpOnly`, so XSS can't steal it | **Every API call goes through Vercel first**, adding latency. Measured locally through the Vite proxy: dashboard p50 24.5 ms, `/auth/me` p50 14.7 ms. Production adds a Vercel round trip | A mobile app or third-party API clients appear (they need tokens), or proxy latency matters |
| No CORS, no token refresh logic, Django's well-tested sessions and CSRF | **Frontend and API deployment are coupled** through the rewrite host (D-029) | Separate staging and production frontends |
| — | `NUM_PROXIES` changes because Vercel is an extra proxy, so it has to be checked on staging | Staging setup |
| — | Database-backed sessions mean one session lookup per request | Hundreds of requests per second: switch to cached sessions |

### D-015 · Custom user model
| Gained | Gave up |
|---|---|
| Email login, `tier`, guest and system flags, room to add fields | The unused `auth_user` table stays in existing databases (harmless; the rehearsal confirmed it doesn't conflict) |

### D-018 · Guests
| Gained | Gave up | Revisit when |
|---|---|---|
| Try the app with zero sign-up; guests can save their workspace | Throwaway accounts can be created in bulk. Mitigated by 5 per hour per IP, small quotas and 7-day deletion | Abuse shows up → add CAPTCHA or proof-of-work on guest creation |

### D-019 · Legacy owner
| Gained | Gave up |
|---|---|
| Nothing lost, nothing leaked | Old anonymous runs disappear from the UI for everyone. An admin can still reach them in the database |
| — | Rolling back to Phase 0 leaves the legacy account in `accounts_user` (the data step has no reverse). Harmless: Phase 0 doesn't read that table |

### D-020 · 404 rather than 403 for other users' items
| Gained | Gave up |
|---|---|
| The API doesn't reveal whether an id exists | Slightly harder debugging ("is it missing or not mine?"). Server logs still show the request |

### D-021 / D-025 · Quotas with a lock on the user's row
| Gained | Gave up |
|---|---|
| Exact per-user limits, with no races | Each create takes a short lock on the user's row: one user's simultaneous creates run one after another (others are unaffected). On SQLite `select_for_update` does nothing, which is fine for development |
| Limits are adjustable per environment | Two more queries per create (quota usage) |

### D-030 · MD5 hasher in tests
| Gained | Gave up |
|---|---|
| Account tests measure our logic, not 210 ms hashes | The unit tests don't exercise the real hasher. The end-to-end smoke test does (sign-up about 320 ms with PBKDF2) |

### D-032 · No frontend unit tests yet
| Gained | Gave up | Revisit when |
|---|---|---|
| The highest-risk part (cookies, CSRF, proxy) is proven end to end | UI edge cases (form errors, the guest banner, redirects) are only covered by lint, build and manual checks | **Phase 2**: the builder UI needs component tests |
Status: done in Phase 2 (D-039); see below.

## Phase 2

### D-033 · Interpret the spec instead of generating code
| Gained | Gave up | Revisit when |
|---|---|---|
| No user input ever becomes code; builder strategies run in production with custom code off | Builder strategies can express only what the operators allow (no loops, no state, no custom maths) | Users need logic the spec can't express → add operators or nesting (spec v2), not code generation |
| **9.8× faster** than the sandbox for the same strategy (30 ms vs 299 ms over 2,520 bars) | Two execution paths to maintain (sandbox for code, interpreter for specs) | — |
| One small evaluator to test; parity with the Python built-in proven trade for trade | The "View as Python" text is a rendering, so it could drift from what the interpreter does | A rendering bug reported → add a test that executes the rendered text in a test-only harness and compares signals |

### D-034 · Flat AND/OR groups
| Gained | Gave up |
|---|---|
| A form anyone can fill in; simple for an AI to produce (Phase 5) | No `(A and B) or C`. Workaround: two strategies, compared in Phase 3 |

### D-036 · Long-only
| Gained | Gave up | Revisit when |
|---|---|---|
| Realistic for Indian cash equities (no overnight retail shorts); unchanged engine invariants; clean comparison with buy-and-hold | No profit from falling prices, only avoidance by holding cash | Derivatives arrive (D-040): bearish views via futures/options |

### D-042 · Exit wins, no position state
| Gained | Gave up |
|---|---|
| Signals are a pure function of bars: precomputed in one pass, trivially free of look-ahead | A flat strategy never enters on a bar where its exit rule is also true. Usually what you want; occasionally a missed entry |

### D-043 · Dynamic warm-up
| Gained | Gave up |
|---|---|
| SMA-200 or EMA-50 are valid from the first test bar | Longer data downloads (up to 600 bars ≈ 3.3 calendar years before the start) |
| EMA/RSI seeds mostly fade (3n bars ≈ 5% residual weight for EMA) | Smoothed values still depend slightly on the available history, so the same date can show a slightly different RSI in two runs with different start dates |

### D-038 · India delivery cost model
| Gained | Gave up | Revisit when |
|---|---|---|
| Realistic per-side costs (stamp duty buy-only, GST on some charges) | Flat per-order charges (DP charges, minimum brokerage) aren't modelled | Small-capital backtests where a ₹15 DP charge matters → add a flat-fee term to the engine |
| Rates visible in one module and in the UI | Rates are fixed in code; a regulatory change needs a deploy, and old runs keep the rates they ran with (by design) | Rates change → update `costs.py`, note the date |

### D-045 · Server is the only validator
| Gained | Gave up |
|---|---|
| One allowlist; the client can't drift from the server | A network round trip per edit (debounced to 400 ms; preview is cheap, under the generous read throttle) |
| Error messages identical in live preview and on save | Without the API the form can't validate at all (acceptable: it can't save either) |

### D-046 · Delete refused when runs exist
| Gained | Gave up | Revisit when |
|---|---|---|
| A result can never lose the strategy that produced it | Users can't clean up a used strategy | Archive/hide instead of delete, if users ask |

### D-047 · 9 decimal places for fees
| Gained | Gave up |
|---|---|
| India rates stored exactly | Rolling back migration `0016` rounds them to 6 places (measured in the rehearsal) |

### D-039 · Frontend component tests
| Gained | Gave up |
|---|---|
| Builder logic tested where bugs live (form ↔ spec, error placement, limits); 13 tests in ~8 s | 5 dev dependencies (Vitest, jsdom, Testing Library). Production `npm audit` stays at 0; the dev tree has 3 moderate advisories, all in `minimatch` under eslint (already a dependency before Phase 2), none from the new packages |

## Phase 3

### D-055 · One `Experiment` model
| Gained | Gave up | Revisit when |
|---|---|---|
| One fan-out/fan-in mechanism; Phase 5's agent reuses it | A rename migration (hand-written, rehearsed: 221 ms up, 313 ms down) and ~110 renamed references | Kinds diverge so much that `config` JSON hides real structure → split per-kind tables |
| Kind-specific settings in `config` JSON, no schema change per kind | `config` isn't validated by the database, only by the serializers | — |

### D-056 · Strategies × symbols matrix
| Gained | Gave up |
|---|---|
| "Which strategy works on which stock" in one view | Every cell shares one period, cost model and stop/target; per-cell settings would need separate experiments |
| Benchmarks per currency for free (D-065) | Mixed-currency comparisons show no single currency; values are compared as percentages |

### D-057 / D-064 · Parameter search with linked paths
| Gained | Gave up |
|---|---|
| Searches the strategy's own parameters; invalid pairs skipped, not failed | Linked paths can't be split: to test "different EMA for entry and exit", build that as a separate strategy |
| Each combination is a frozen, hashed spec: every result reproducible | The 25-run limit counts skipped combinations too, so a grid with many invalid pairs uses its budget less efficiently |

### D-058 · One job per child + per-worker cache
| Gained | Gave up | Revisit when |
|---|---|---|
| Children still run in parallel, retry and report progress individually | The cache is per process: with several workers, each warms its own (measured hit rate is for one worker) | Many workers → a shared cache (Redis) or sending a batch's children to the same worker |
| 32–36% less time per child after D-063 (measured); identical results | Memory: up to 16 bar sets and 128 indicator series per worker | Memory pressure on small instances → lower the LRU sizes |
| A re-download can never serve stale bars (key includes `fetched_at`) | Strategies with different warm-ups don't share bars (the key includes warm-up) | — |

### D-059 · Priority lanes
| Gained | Gave up | Revisit when |
|---|---|---|
| A hand-started run waits for at most the run in progress (measured: 22 ms vs 1.26 s behind a batch) | A steady stream of single runs delays batches (bounded by per-account quotas) | Phase 5: several agent experiments at once → round-robin between batches |
| One query, same `SKIP LOCKED`, one new index | No pre-emption: a long running child still finishes first | — |

### D-063 · Time-based heartbeat
| Gained | Gave up |
|---|---|
| Per-child time 174 → 37–39 ms; no progress writes for fast runs | Progress on the run page updates once a second instead of every 50 bars (invisible for runs that finish in milliseconds) |

### D-062 · Downsampled curves
| Gained | Gave up |
|---|---|
| ≤ 500 points per child; peaks and troughs kept | Hover values on experiment charts are approximate between kept points; the run's own page has the full curve |

## Phase 3.5

### D-067 / D-068 · Locust, run locally with container limits
| Gained | Gave up | Revisit when |
|---|---|---|
| Capacity numbers now, scenarios in Python, CSV straight into evals | A laptop isn't Render: shared CPU made identical repeats differ by up to a third at 20 users | Phase 6 staging: rerun the same locustfile there |
| No new language or tool in the stack (dev-only dependency) | Locust's own load generator is slower than k6's (irrelevant at ≤ 80 users) | Tests needing thousands of users |

### D-069 · Hand-rolled `/metrics` instead of a client library + Prometheus server
| Gained | Gave up | Revisit when |
|---|---|---|
| No new service; queue health is one SQL query, true across all processes | HTTP metrics are per process: a scrape sees only the process that answered | Several API instances and real dashboards → `prometheus_client` multiprocess mode or OpenTelemetry |
| Off unless a token is set; constant-time token check | No history or alerting without a scraper | A scraper is attached at deployment |

### D-070 / D-076 · JSON logs, request IDs, one access log
| Gained | Gave up |
|---|---|
| Click → run → worker error is one search; IDs survive into the database | JSON is harder to read by eye locally (`LOG_FORMAT=text` restores it) |
| Route patterns, not URLs: no IDs or tokens from paths in logs, and low-cardinality metrics | You can't see which run ID a request hit from the access line alone (it's in the route's own logs) |
| One access line from Django instead of two formats | gunicorn's own access log is off |

### D-071 · Sentry off by default
| Gained | Gave up |
|---|---|
| No external data flow until the user decides | No error tracking in production until it's turned on |

### D-072 / D-076 · OpenAPI with CI enforcement
| Gained | Gave up |
|---|---|
| 32 operations documented; docs can't drift (CI fails on any warning) | Every new view needs `extend_schema` and computed fields need type hints: some boilerplate per endpoint |
| Bundled Swagger assets, no CDN | Two more dependencies; in production the docs need `API_DOCS=1` and are served by Django |

### D-073 / D-075 · Shared throttle counters in Postgres, written by upsert
| Gained | Gave up | Revisit when |
|---|---|---|
| Limits are exact across processes: 10 logins allowed, not 20 (measured) | One database write per throttled request | Request volume where that write matters → Redis (the project removed it on purpose) |
| Upsert removes the stock cache's per-write `COUNT(*)` and savepoints: 52–55 req/s at saturation vs 31–41 with Django's stock database cache | Expired rows stay until the hourly housekeeping (the table holds about one row per client and scope seen in the last hour) | — |
| No new service | Same throughput as per-process counters within measurement noise, not better | — |

### D-074 · Graceful shutdown with a grace period
| Gained | Gave up |
|---|---|
| A deploy-interrupted run is back in the queue 2.26 s after `SIGTERM` (2 s grace) instead of 120–150 s; no retry used | Work done before the deadline is thrown away and the run restarts from the first bar |
| No new failure states: the run simply becomes `queued` again | A run that always takes longer than the grace period and is always interrupted would never finish (only during back-to-back deploys) |

## Phase 4

### D-077 · The AI fills the form; the user saves
| Gained | Gave up | Revisit when |
|---|---|---|
| A person checks every strategy before it exists; a wrong answer costs a glance, not a bad backtest | One more click than "describe and run" | Phase 5: the agent runs experiments itself, inside quotas, with its reasoning shown |
| One feature with a clear right answer, so it can be measured | "Explain this result" waits for Phase 5 (D-084) | — |

### D-078 · AI requests as worker jobs
| Gained | Gave up | Revisit when |
|---|---|---|
| The API never waits on the provider: 2 people asking can't stall it | ~1 s of polling on top of the model's time | Many AI users → a separate worker process for AI requests |
| Request IDs, shutdown, stale recovery and metrics for free | A worker answering an AI request isn't running a backtest (AI goes first, and is short) | — |

### D-079 · Groq, behind an interface, with no SDK
| Gained | Gave up | Revisit when |
|---|---|---|
| Free, fast, no training on API data; two models compared at no cost | Free limits (8K tokens/min, 200K/day per model) are shared by the whole deployment | Real traffic → a paid tier with a spending cap |
| One file knows the vendor; tests and CI never touch the network | Open models make more format mistakes than the strongest paid ones (measured: see evals) | The evaluation shows a model can't reach the bar |
| No SDK dependency (plain `requests`) | Retry and error handling written by hand (tested) | — |

### D-080 · JSON answer, validated, repaired
| Gained | Gave up |
|---|---|
| The model can only produce data that the existing allowlist checks; nothing it writes runs | A valid spec can still be the wrong strategy: the validator checks form, not meaning (the evaluation and the user's review check meaning) |
| Repair turns near misses into answers using the validator's own messages | Each repair round is another call: more tokens and latency |

### D-081 · Quotas, budget, cache
| Gained | Gave up |
|---|---|
| One user can't spend the deployment's free tokens; the app degrades to "build it in the form" | Over budget, AI is off for everyone until midnight UTC |
| Repeated descriptions cost nothing | A cached answer can't improve until the prompt version or model changes |

### D-082 · Behavioural grading with recorded runs
| Gained | Gave up |
|---|---|
| Equivalent formulations pass and near misses fail, judged by what the strategy does | Five synthetic series can miss a difference that only shows on other data (mitigated: every reference must trade on them) |
| CI runs the evaluation for free and catches prompt changes that weren't re-measured | A recording reflects one day's model; providers change models, so numbers need re-running |
| Ambiguous wording has several accepted references | Choosing which readings count as "right" is a judgment, written down per case |

### D-083 · Privacy
| Gained | Gave up |
|---|---|
| Only the description leaves Vault; never logged; deleted after 30 days | Support can't look at a description older than 30 days |

## Phase 5

### D-089 · Fixed stages with JSON actions
| Gained | Gave up | Revisit when |
|---|---|---|
| Bounded, testable behaviour: code owns stage changes, budgets, the held-out test and saving | Less freedom than an open tool loop (no "look at trades", no new tools mid-run) | Real runs show the agent needs more tools |
| The JSON format already proven on this model (140/140 in Phase 4); provider-independent | Not the provider's native tool calling (a common interview topic) | A provider's tool calling is measured to be as reliable |
| Flat prompt size per step (state rebuilt each time) | The agent has no memory of its earlier reasoning, only of results and its last error | Decisions look repetitive in live runs → keep a short running summary |

### D-090 · Resumable state machine
| Gained | Gave up |
|---|---|
| No worker is held while backtests run; restarts and deploys resume from saved state | More moving parts than a loop in one process: waking, stale recovery, ownership checks (all tested) |
| Every step is in the timeline the user sees | A step's latency includes the queue: a few seconds between decisions |

### D-091 · Held-out test by code
| Gained | Gave up |
|---|---|
| The honest number is computed where the agent can't influence it, exactly once | Research uses only 70% of the data; the held-out 30% is one period, so it's a sample, not proof |
| Reports show how optimistic the research number is | A held-out loss looks bad, and is shown anyway |

### D-092 · Grounded report
| Gained | Gave up |
|---|---|
| The summary can't invent a figure; tables and checks come from code | A correct but differently rounded number may be rejected (one rewrite allowed, then a plain summary) |

### D-093 · Budgets and quotas
| Gained | Gave up | Revisit when |
|---|---|---|
| A run costs at most ~40K tokens and 40 backtests; the deployment's free tokens can't be drained by one user | A handful of research runs per day on the free tier; guests can't use it | A paid tier with a spending cap |

### D-094 · No live evaluation
| Gained | Gave up |
|---|---|
| The revamp finishes today | No measured answer to "does the agent beat a random search?" and no live run yet; stated plainly in the README and evals |

## Phase 6

### D-097 · Straight to production with a backup and a rehearsal
| Gained | Gave up | Revisit when |
|---|---|---|
| Released the same day; the irreversible step tested on a copy of the real data | No staging: routing and network issues showed up in production (both found by the smoke test within minutes) | Users depend on the site → a staging service and preview frontend |
| $0: free web service with the worker embedded | Backtests compete with HTTP for CPU; the service sleeps when idle (first request ~24 s) | Traffic or budget → a separate background worker (~$7/month) |

### D-099 · Pre-loaded data
| Gained | Gave up |
|---|---|
| The suggested symbols and benchmarks work today | Other symbols fail on production, and stored data doesn't update until a fallback provider exists |

### D-103 · Sign in with Google
| Gained | Gave up | Revisit when |
|---|---|---|
| Verified accounts without sending any email; one click to sign up | A Google dependency for those users; Google-only accounts can't set a password or change their email yet | Users ask for it → "set a password" via a reset email once an email provider works |
