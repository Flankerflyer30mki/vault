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
