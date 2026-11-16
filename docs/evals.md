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
