# Evals

Measured results per phase: test counts, pass/fail, per-test timings and CI checks. Every number here
comes from an actual run; nothing is estimated.

## How the numbers are produced
```bash
# from backend/, on Linux (the sandbox needs POSIX); Postgres 16 like CI
python manage.py test -v 2 --durations 0 --timing
```
**Environment (Phase 0 runs):** Python 3.12 (`python:3.12-slim` container) on Windows 11 with Docker Desktop
(WSL2 backend), Postgres 16 container, Django 6.0.8. Timings are from a single run, so expect ±10–20% between runs.

## Summary by phase
| Phase | Date | Tests | Passed | Failed | Suite time (Postgres) | Suite time (SQLite) | DB setup (Postgres) | Total (Postgres) |
|---|---|---|---|---|---|---|---|---|
| Baseline (before Phase 0) | 2026-11-16 | 27 | — | — | not measured | not measured | — | — |
| 0 | 2026-11-16 | 38 | 38 | 0 | 4.136 s | 3.838 s | 1.316 s | 5.987 s |
| 1 | 2026-11-16 | 70 | 70 | 0 | 7.531 s | 5.864 s | 1.477 s | 9.935 s |

## Phase 0 · CI checks (run locally, matching `.github/workflows/ci.yml`)
| Check | Result |
|---|---|
| Test suite, Postgres 16 | ✅ 38/38 |
| Test suite, SQLite | ✅ 38/38 |
| `makemigrations --check --dry-run` (no missing migrations) | ✅ No changes detected |
| Production settings refuse to start without `SECRET_KEY` | ✅ |
| `pip-audit` | ✅ No known vulnerabilities (after the `soupsieve` bump; 2 advisories before) |
| `pip check` | ✅ No broken requirements |
| Frontend `npm run lint` | ✅ |
| Frontend `npm run build` | ✅ |
| Frontend `npm audit --omit=dev --audit-level=high` | ✅ 0 vulnerabilities |

## Phase 0 · Proof that the tests catch the bugs
| Test | Run against the old code | Run against the new code |
|---|---|---|
| `test_refetch_replaces_bars_so_one_symbol_stays_on_one_price_scale` | ❌ fails (`AssertionError`: old ~100 prices left next to new ~50 ones) | ✅ |
| `test_optimization_finishes_when_last_in_sample_run_fails_via_stale_recovery` | It asserts the bug inside the test: status is `running` before the sweep | ✅ |

## Phase 0 · Per-test timings
New tests are marked 🆕. Sorted by Postgres time.

| # | Test | Group | Postgres | SQLite | Status |
|---|---|---|---|---|---|
| 1 | `test_infinite_loop_is_killed` | Sandbox | 2.004 s | 2.003 s | ✅ |
| 2 | `test_optimization_partial_failure_and_single_oos_run` | Job/API | 0.329 s | 0.331 s | ✅ |
| 3 | 🆕 `test_optimization_list_does_not_load_equity_curves` | Job/API | 0.321 s | 0.222 s | ✅ |
| 4 | `test_run_end_to_end_and_retry_does_not_duplicate_trades` | Job/API | 0.251 s | 0.249 s | ✅ |
| 5 | 🆕 `test_optimization_finishes_when_last_in_sample_run_fails_via_stale_recovery` | Job/API | 0.230 s | 0.208 s | ✅ |
| 6 | `test_imports_and_dunders_blocked` | Sandbox | 0.125 s | 0.123 s | ✅ |
| 7 | `test_huge_output_contained` | Sandbox | 0.098 s | 0.105 s | ✅ |
| 8 | 🆕 `test_spoofed_forwarded_for_does_not_bypass_throttle` | Job/API | 0.088 s | 0.065 s | ✅ |
| 9 | `test_queue_full_returns_503` | Job/API | 0.049 s | 0.032 s | ✅ |
| 10 | 🆕 `test_refetch_replaces_bars_so_one_symbol_stays_on_one_price_scale` | Data | 0.046 s | 0.036 s | ✅ |
| 11 | `test_invalid_decision_rejected` | Sandbox | 0.042 s | 0.037 s | ✅ |
| 12 | `test_no_file_access` | Sandbox | 0.042 s | 0.039 s | ✅ |
| 13 | `test_valid` | Sandbox | 0.041 s | 0.037 s | ✅ |
| 14 | `test_exception_reported` | Sandbox | 0.040 s | 0.043 s | ✅ |
| 15 | `test_custom_code_disabled_by_default` | Job/API | 0.040 s | 0.027 s | ✅ |
| 16 | `test_idempotency_key_returns_same_run` | Job/API | 0.036 s | 0.027 s | ✅ |
| 17 | `test_stale_job_requeued_then_failed` | Job/API | 0.031 s | 0.020 s | ✅ |
| 18 | `test_single_existing_bar_does_not_count_as_coverage` | Data | 0.028 s | 0.021 s | ✅ |
| 19 | 🆕 `test_stop_tighter_than_slippage_rejected` | Job/API | 0.028 s | 0.042 s | ✅ |
| 20 | `test_gaps_are_labelled_and_invalid_rows_rejected` | Data | 0.026 s | 0.048 s | ✅ |
| 21 | `test_health` | Job/API | 0.026 s | 0.018 s | ✅ |
| 22 | `test_grid_limit_enforced_server_side` | Job/API | 0.025 s | 0.020 s | ✅ |
| 23 | 🆕 `test_coverage_excludes_the_fetch_day` | Data | 0.023 s | 0.015 s | ✅ |
| 24 | 🆕 `test_failed_or_empty_fetch_keeps_bars_and_records_no_coverage` | Data | 0.019 s | 0.016 s | ✅ |
| 25 | 🆕 `test_recycles_connections_and_survives_recovery_errors` | Worker | 0.014 s | 0.013 s | ✅ |
| 26 | 🆕 `test_covered_span_is_not_fetched_again` | Data | 0.014 s | 0.010 s | ✅ |
| 27 | `test_no_data_raises` | Data | 0.003 s | 0.003 s | ✅ |
| 28–38 | Ledger (5), Timing (3) and Stop (3) engine tests | Engine | < 0.001 s each | < 0.001 s each | ✅ |

## Phase 0 · Time by group (Postgres)
| Group | Tests | Time | Share of suite |
|---|---|---|---|
| Sandbox | 7 | 2.392 s | 58% |
| Job/API | 12 | 1.454 s | 35% |
| Data | 7 | 0.159 s | 4% |
| Worker | 1 | 0.014 s | <1% |
| Engine (Ledger, Timing, Stops) | 11 | < 0.01 s | <1% |

## Observations
- **One test is half the suite.** `test_infinite_loop_is_killed` takes 2.0 s by design: it waits for the 2-second wall-clock limit. Making the limit shorter would make it faster, but a value too close to Python's startup time could make the test flaky. Keep it.
- **Engine tests are effectively instant** because the engine is pure (no I/O, no Django). That's what makes the "AI agent runs many backtests" idea in Phase 5 cheap.
- **Postgres vs. SQLite:** the suite is 8% slower on Postgres (4.136 s vs. 3.838 s), plus 1.3 s to create the test database. Several API tests are 30–55% slower on Postgres, but a few are faster, so at these sizes (tens of milliseconds) the difference is mostly noise. CI runs Postgres, so treat those numbers as the reference.

---

# Phase 1 · Accounts and personal workspace

**Environment:** same as Phase 0 (`python:3.12-slim`, Postgres 16 container, Django 6.0.8, Docker Desktop on Windows 11). Frontend: `node:20-slim`, Vite 8.

## Phase 1 · Checks
| Check | Result |
|---|---|
| Test suite, Postgres 16 | ✅ 70/70 (7.531 s; total with DB setup 9.935 s) |
| Test suite, SQLite | ✅ 70/70 (5.864 s; total 7.041 s) |
| `makemigrations --check --dry-run` | ✅ No changes detected (hand-written migrations match the models) |
| `manage.py check` | ✅ No issues |
| End-to-end smoke test through the Vite proxy (real PBKDF2, Postgres, worker) | ✅ 15/15 |
| Upgrade rehearsal from the actual Phase 0 code (Postgres) | ✅ 8/8 data checks, rollback works |
| Frontend `npm run lint` | ✅ (2 errors found and fixed: impure `Date.now()` during render; `process` not defined in `vite.config.js`) |
| Frontend `npm run build` | ✅ |
| Frontend `npm audit --omit=dev --audit-level=high` | ✅ 0 vulnerabilities |
| Docker builds (backend, frontend), as in CI | ✅ both build; frontend image 74.5 MB (nginx), backend 543 MB |
| `nginx -t` on the new frontend image | ✅ configuration valid |

## Phase 1 · Test count
| | Phase 0 | Phase 1 | Change |
|---|---|---|---|
| backtester tests | 38 | 39 | +2 new (per-user job throttle, anonymous rejected), −1 moved (spoofed-XFF throttle now in accounts, on the auth endpoint) |
| accounts tests | — | 31 | new |
| **Total** | **38** | **70** | **+32** |

## Phase 1 · Time by group (Postgres; SQLite in brackets)
| Group | Tests | Time | Share |
|---|---|---|---|
| backtester Sandbox | 7 | 2.377 s (2.378) | 35% |
| backtester Job/API | 13 | 1.775 s (1.291) | 26% |
| accounts Isolation | 5 | 0.642 s (0.446) | 9% |
| accounts AuthFlow | 16 | 0.582 s (0.411) | 9% |
| accounts Quota | 5 | 0.517 s (0.437) | 8% |
| accounts LegacyMigration | 2 | 0.515 s (0.519) | 8% |
| accounts Dashboard | 1 | 0.202 s (0.159) | 3% |
| backtester Data | 7 | 0.154 s (0.104) | 2% |
| accounts Housekeeping | 2 | 0.061 s (0.029) | 1% |
| backtester Worker | 1 | 0.011 s (0.011) | <1% |
| backtester Engine (Ledger, Timing, Stops) | 11 | <0.001 s each | <1% |
| **Sum of test bodies** | **70** | **6.836 s (5.785)** | |

## Phase 1 · Per-test timings, accounts (Postgres / SQLite)
| Test | Postgres | SQLite | Status |
|---|---|---|---|
| LegacyMigration `test_existing_rows_move_to_legacy_user` | 0.513 s | 0.519 s | ✅ |
| Quota `test_daily_limit_counts_finished_runs_and_suggests_verifying` | 0.300 s | 0.251 s | ✅ |
| Isolation `test_dashboard_contains_only_own_data` | 0.247 s | 0.142 s | ✅ |
| Dashboard `test_dashboard_contents` | 0.202 s | 0.159 s | ✅ |
| AuthFlow `test_delete_account_removes_only_that_users_data` | 0.191 s | 0.151 s | ✅ |
| Isolation `test_idempotency_keys_are_per_user` | 0.112 s | 0.057 s | ✅ |
| Isolation `test_other_users_items_are_404_not_403` | 0.105 s | 0.091 s | ✅ |
| Isolation `test_cannot_run_or_optimize_another_users_strategy` | 0.091 s | 0.072 s | ✅ |
| Isolation `test_lists_show_only_own_items_plus_builtins` | 0.087 s | 0.084 s | ✅ |
| Quota `test_guest_active_job_limit` | 0.070 s | 0.082 s | ✅ |
| AuthFlow `test_guest_flow_keeps_data_after_conversion` | 0.066 s | 0.043 s | ✅ |
| AuthFlow `test_auth_throttle_is_per_ip_and_ignores_spoofed_forwarded_for` | 0.058 s | 0.048 s | ✅ |
| Quota `test_optimization_counts_as_one_active_job` | 0.057 s | 0.041 s | ✅ |
| Quota `test_verifying_raises_limits` | 0.047 s | 0.029 s | ✅ |
| Housekeeping `test_worker_finalising_a_deleted_users_run_is_harmless` | 0.044 s | 0.023 s | ✅ |
| Quota `test_quota_values_come_from_env` | 0.043 s | 0.034 s | ✅ |
| AuthFlow `test_password_change_keeps_this_session_and_signs_out_others` | 0.043 s | 0.022 s | ✅ |
| AuthFlow `test_csrf_token_rotates_on_login_and_old_token_is_rejected` | 0.035 s | 0.022 s | ✅ |
| AuthFlow `test_guest_creation_is_throttled_per_ip` | 0.031 s | 0.019 s | ✅ |
| AuthFlow `test_email_change_requires_password_and_reverification` | 0.027 s | 0.015 s | ✅ |
| AuthFlow `test_password_reset_flow_without_account_enumeration` | 0.026 s | 0.020 s | ✅ |
| AuthFlow `test_login_generic_error_and_session_rotation` | 0.020 s | 0.013 s | ✅ |
| AuthFlow `test_verification_link_raises_tier_and_works_once` | 0.019 s | 0.015 s | ✅ |
| Housekeeping `test_expired_guests_and_sessions_are_deleted` | 0.017 s | 0.006 s | ✅ |
| AuthFlow `test_duplicate_email_is_case_insensitive` | 0.015 s | 0.007 s | ✅ |
| AuthFlow `test_weak_passwords_rejected` | 0.014 s | 0.009 s | ✅ |
| AuthFlow `test_logout_ends_session` | 0.013 s | 0.009 s | ✅ |
| AuthFlow `test_signup_signs_in_and_sends_verification` | 0.011 s | 0.008 s | ✅ |
| AuthFlow `test_guests_legacy_and_inactive_users_cannot_password_login` | 0.011 s | 0.008 s | ✅ |
| LegacyMigration `test_fresh_database_gets_no_legacy_user` | 0.002 s | <0.001 s | ✅ |
| AuthFlow `test_csrf_is_required_even_for_anonymous_login` | 0.002 s | 0.002 s | ✅ |

New or changed backtester tests: `test_job_throttle_is_per_user` 0.161 s / 0.107 s ✅, `test_anonymous_requests_are_rejected` 0.038 s / 0.021 s ✅. Every other backtester test is listed in the Phase 0 table and still passes.

## Phase 1 · End-to-end smoke test through the proxy
Django `runserver` and `run_worker` on Postgres, the Vite dev server forwarding `/api`, and a Python client acting like the SPA (it only talks to `localhost:5173`). Real PBKDF2 hashing. Offline seeded market data (371 bars). Second run shown; the first run failed one check because of a bug in the smoke script (it didn't decode the quoted-printable email), not in the app.

| # | Check | Time | Result |
|---|---|---|---|
| 1 | anonymous `/me` returns no user and sets `csrftoken` | 72.2 ms | ✅ |
| 2 | sign-up without `X-CSRFToken` rejected | 9.5 ms | ✅ 403 |
| 3 | sign-up from a foreign `Origin` rejected | 8.4 ms | ✅ 403 |
| 4 | sign-up succeeds and sets an HttpOnly session cookie | 322.9 ms | ✅ 201 (PBKDF2 dominates) |
| 5 | verification link from the email verifies the account | 30.0 ms | ✅ tier → verified |
| 6 | create run | 41.5 ms | ✅ 201 |
| 7 | worker completes the run (queue → done, includes 250 ms polling) | 840.6 ms | ✅ engine 154 ms, 371 bars |
| 8 | trades endpoint | 18.4 ms | ✅ 14 trades |
| 9 | dashboard shows the run with return vs. buy & hold | 27.9 ms | ✅ |
| 10 | another user gets 404 for the run | 57.0 ms | ✅ |
| 11 | one-click guest | 35.4 ms | ✅ |
| 12 | guest can queue a run | 30.9 ms | ✅ |
| 13 | dashboard latency ×30 via proxy | p50 24.5 / p95 27.9 / max 32.1 ms | ✅ |
| 14 | `/auth/me` latency ×30 via proxy | p50 14.7 / p95 19.9 / max 22.1 ms | ✅ |
| 15 | logout ends the session | 20.4 ms | ✅ 204, then 403 |

## Phase 1 · Upgrade rehearsal (actual Phase 0 code → Phase 1 code, Postgres 16)
1. Phase 0 code: `migrate` (up to `backtester.0012`), then create 1 custom strategy, 4 runs (3 with idempotency keys) and 1 optimization. With the 3 built-ins: 4 strategies, 4 runs, 1 optimization.
2. Phase 1 code: `migrate` applied `accounts.0001`, `backtester.0013`–`0015` and `sessions.0001` in **1,189 ms** with exit code 0. The new `accounts_user` table sits alongside the existing `auth_user` with no conflict.
3. Data checks: **8/8 pass**. The legacy user is inactive, a system user, and has no usable password; all runs, optimizations and the custom strategy belong to it; built-ins have no owner; row counts are unchanged (4/4/1); idempotency keys were kept; no other users exist.
4. Rollback `migrate backtester 0012` in **1,091 ms**. The Phase 0 code then reads all 4 strategies, 4 runs, 1 optimization and keys `k-0..k-2`.

## Phase 1 · Other measurements
| Measurement | Value |
|---|---|
| PBKDF2-SHA256 (Django default, 1,200,000 iterations), one hash | 209.7 ms (median of 5) |
| MD5 (test-only hasher), one hash | 0.024 ms (median of 5) |
| Frontend JS bundle, Phase 0 → Phase 1 | 658,624 → 678,075 bytes raw (+19,451, +3.0%); gzip 199,470 → 203,807 (+4,337, +2.2%) |
| Frontend CSS, Phase 0 → Phase 1 | 5,928 → 8,627 bytes raw; gzip 1,900 → 2,555 (+655) |
| Vite "chunk > 500 kB" warning | Already present in Phase 0 (charting library); not caused by Phase 1 |

## Phase 1 · Bugs and surprises found while testing
| What | Found by | Outcome |
|---|---|---|
| Django rotates the CSRF token on login, so a client that sends a fixed token fails after signing in | The first account test run (7 failures) | The app is correct. The test client now re-reads the cookie each request, like axios does. A test pins this behavior down |
| Idempotency keys were global: a matching key from another user would have returned that user's job | Design review while adding ownership | Fixed (`UNIQUE(owner, key)`), with a test |
| The out-of-sample run is created by the worker, so it needed the owner set explicitly | Design review | Fixed in `finish_optimization`, with an assertion in the test |
| Lint: `Date.now()` during render; `process` undefined in the Vite config | `npm run lint` | Fixed |
| Emails are quoted-printable in the console log | Smoke test, first run | Script fixed; the app is correct |

## Phase 1 · Observations
- **The suite grew from 38 to 70 tests and its run time from 4.1 s to 7.5 s on Postgres.** The 2-second sandbox timeout test is still the largest single item (27%).
- **Isolation and quota tests are the slowest account tests** because they really run backtests through the worker. That's deliberate: they check end to end, not just the querysets.
- **The migration test is the slowest account test (0.5 s)** because it rolls the schema back and forward. It runs last (`TransactionTestCase`) and restores data with `serialized_rollback`.
- **Requests through the proxy are fast locally** (p50 15–25 ms). Production will add a Vercel hop; measure it on staging.
