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
