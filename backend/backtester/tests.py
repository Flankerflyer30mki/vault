"""Run: DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test   (CI also runs this on Postgres)."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from backtester import data_fetch, engine, jobs
from backtester.engine import Params, StrategyError, simulate
from backtester.models import BacktestRun, Bar, OptimizationJob, Strategy, Trade
from backtester.sandbox_runner import StrategyProcess

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def bar(i, o, h=None, low=None, c=None):
    c = o if c is None else c
    return {"ts": T0 + timedelta(days=i), "open": D(o), "high": D(h if h is not None else max(o, c)),
            "low": D(low if low is not None else min(o, c)), "close": D(c), "volume": 0}


def script(*decisions):
    it = iter(decisions)
    return lambda b, ind: next(it, "HOLD")


ZERO = Params(starting_cash=D(1000), commission_pct=D(0), slippage_pct=D(0))


class LedgerTests(TestCase):
    def test_buy_sell_with_costs_hand_calculated(self):
        p = Params(starting_cash=D(10000), commission_pct=D("0.01"), slippage_pct=D("0.01"))
        bars = [bar(0, 100), bar(1, 100), bar(2, 120), bar(3, 120)]
        r = simulate(bars, script("BUY", "SELL"), p)
        buy, sell = r.fills
        # BUY at bar1 open: 100 * 1.01 = 101; qty = 10000 / (101 * 1.01) = 98.0296049..., rounded down
        self.assertEqual(buy.price, D("101.00"))
        self.assertEqual(buy.quantity, D("98.029604"))
        # SELL at bar2 open: 120 * 0.99 = 118.8
        self.assertEqual(sell.price, D("118.80"))
        cash_after_buy = D(10000) - buy.quantity * D(101) * D("1.01")
        expected = cash_after_buy + buy.quantity * D("118.8") * D("0.99")
        self.assertEqual(r.cash, expected)
        self.assertEqual(r.equity_curve[-1][1], expected)  # sell ADDS proceeds; it never overwrites cash

    def test_sizing_includes_fees_so_cash_never_negative(self):
        p = Params(starting_cash=D(1000), commission_pct=D("0.05"), slippage_pct=D("0.01"))
        r = simulate([bar(0, 50), bar(1, 50), bar(2, 50)], script("BUY"), p)
        self.assertGreaterEqual(r.cash, 0)
        self.assertLess(r.cash, D("0.01"))

    def test_equity_equals_cash_plus_holdings_every_bar(self):
        bars = [bar(i, 100 + i, c=101 + i) for i in range(10)]
        cash, qty, curve = D(1000), D(0), []
        r = simulate(bars, script("BUY", "HOLD", "HOLD", "SELL", "BUY"), ZERO)
        fills = iter(r.fills)
        nxt = next(fills, None)
        for b in bars:
            while nxt and nxt.ts == b["ts"]:
                cash, qty = nxt.cash_after, (nxt.quantity if nxt.side == "BUY" else D(0))
                nxt = next(fills, None)
            curve.append(cash + qty * b["close"])
        self.assertEqual([v for _, v in r.equity_curve], curve)

    def test_no_trade_run_has_flat_curve_and_defined_metrics(self):
        bars = [bar(i, 100 + i) for i in range(30)]
        r = simulate(bars, script(), ZERO)
        m = engine.metrics(r, ZERO, bars)
        self.assertEqual(r.fills, [])
        self.assertEqual(m["final_value"], D("1000.0000"))
        self.assertEqual(m["max_drawdown"], 0.0)
        self.assertIsNone(m["sharpe_ratio"])  # zero volatility: undefined, not 0
        self.assertIsNone(m["win_rate"])      # no closed trades: undefined
        self.assertAlmostEqual(m["cagr"], 0.0)

    def test_win_rate_is_net_of_costs(self):
        # Price rises 0.5% but round-trip costs exceed it: a loss, not a win.
        p = Params(starting_cash=D(1000), commission_pct=D("0.005"), slippage_pct=D(0))
        bars = [bar(0, 100), bar(1, 100), bar(2, "100.5"), bar(3, "100.5")]
        r = simulate(bars, script("BUY", "SELL"), p)
        self.assertEqual(engine.metrics(r, p, bars)["win_rate"], 0.0)


class TimingTests(TestCase):
    def test_signal_fills_next_open_not_same_close(self):
        bars = [bar(0, 100, c=150), bar(1, 160, c=170)]  # jump at bar0 close
        r = simulate(bars, script("BUY"), ZERO)
        self.assertEqual(r.fills[0].ts, bars[1]["ts"])
        self.assertEqual(r.fills[0].price, D(160))

    def test_last_bar_signal_never_fills(self):
        r = simulate([bar(0, 100)], script("BUY"), ZERO)
        self.assertEqual(r.fills, [])

    def test_strategy_sees_only_past_and_present(self):
        seen = []
        bars = [bar(i, 100 + i) for i in range(60)]
        simulate(bars, lambda b, ind: seen.append((b["ts"], ind["sma_10"])) or "HOLD", ZERO, warmup=50)
        self.assertEqual(seen[0][0], bars[50]["ts"])  # warm-up bars are hidden from the strategy
        self.assertEqual(seen[0][1], float(sum(D(100 + i) for i in range(41, 51)) / 10))  # SMA through bar t only


class StopTests(TestCase):
    P = Params(starting_cash=D(1000), commission_pct=D(0), slippage_pct=D(0),
               stop_loss_pct=D("0.1"), take_profit_pct=D("0.1"))

    def test_both_touched_assumes_stop(self):
        r = simulate([bar(0, 100), bar(1, 100), bar(2, 100, h=115, low=85)], script("BUY"), self.P)
        self.assertEqual((r.fills[1].reason, r.fills[1].price), ("stop_loss", D(90)))

    def test_gap_through_stop_fills_at_open(self):
        r = simulate([bar(0, 100), bar(1, 100), bar(2, 80, c=82)], script("BUY"), self.P)
        self.assertEqual((r.fills[1].reason, r.fills[1].price), ("stop_loss", D(80)))

    def test_intrabar_target(self):
        r = simulate([bar(0, 100), bar(1, 100), bar(2, 101, h=112, c=105)], script("BUY"), self.P)
        self.assertEqual((r.fills[1].reason, r.fills[1].price), ("take_profit", D(110)))


class SandboxTests(TestCase):
    def run_code(self, code, timeout=5):
        p = StrategyProcess(code, timeout_s=timeout, cpu_s=timeout)
        try:
            return p.decide({"close": 1.0}, {})
        finally:
            p.close()

    def test_valid(self):
        self.assertEqual(self.run_code("def on_bar(b, i, s):\n    return 'BUY'"), "BUY")

    def test_infinite_loop_is_killed(self):
        with self.assertRaisesRegex(StrategyError, "time limit|exited"):
            self.run_code("def on_bar(b, i, s):\n    while True:\n        pass", timeout=2)

    def test_invalid_decision_rejected(self):
        with self.assertRaisesRegex(StrategyError, "BUY, SELL or HOLD"):
            self.run_code("def on_bar(b, i, s):\n    return 'YOLO'")

    def test_exception_reported(self):
        with self.assertRaisesRegex(StrategyError, "ZeroDivisionError"):
            self.run_code("def on_bar(b, i, s):\n    return 1/0")

    def test_imports_and_dunders_blocked(self):
        for code in ("import os\ndef on_bar(b,i,s): return 'HOLD'",
                     "def on_bar(b,i,s):\n    return ().__class__.__name__",
                     "def on_bar(b,i,s):\n    return __import__('os')"):
            with self.assertRaises(StrategyError):
                self.run_code(code)

    def test_no_file_access(self):
        with self.assertRaisesRegex(StrategyError, "NameError"):
            self.run_code("def on_bar(b,i,s):\n    return open('/etc/passwd').read()")

    def test_huge_output_contained(self):
        with self.assertRaisesRegex(StrategyError, "BUY, SELL or HOLD|too much output"):
            self.run_code("def on_bar(b,i,s):\n    return 'x' * 10000000")


def make_bars(symbol, start, n, price=100):
    out = []
    for i in range(n):
        p = D(price + i % 7)
        out.append(Bar(symbol=symbol, ts=datetime.combine(start + timedelta(days=i), datetime.min.time(), UTC),
                       open=p, high=p + 1, low=p - 1, close=p, volume=1))
    return out


class DataTests(TestCase):
    def test_single_existing_bar_does_not_count_as_coverage(self):
        Bar.objects.bulk_create(make_bars("AAPL", date(2024, 3, 1), 1))
        fetch = mock.Mock(return_value=(make_bars("AAPL", date(2023, 9, 1), 400), 0))
        _, bars, manifest = data_fetch.load_bars("AAPL", date(2024, 1, 1), date(2024, 6, 30), fetch=fetch)
        fetch.assert_called_once()
        self.assertEqual(manifest["warnings"], [])
        self.assertEqual(manifest["warmup_bars"], engine.WARMUP_BARS)

    def test_gaps_are_labelled_and_invalid_rows_rejected(self):
        rows = make_bars("MSFT", date(2023, 9, 1), 200) + make_bars("MSFT", date(2024, 5, 1), 60)
        data_fetch.load_bars("MSFT", date(2024, 1, 1), date(2024, 6, 29), fetch=lambda *a: (rows, 3))
        _, _, m = data_fetch.load_bars("MSFT", date(2024, 1, 1), date(2024, 6, 29), fetch=lambda *a: ([], 3))
        self.assertTrue(any(w.startswith("gap") for w in m["warnings"]))
        self.assertIsNone(data_fetch._to_bar("X", T0, 10, 9, 8, 11, 0))  # high < close
        self.assertIsNone(data_fetch._to_bar("X", T0, float("nan"), 1, 1, 1, 0))

    def test_no_data_raises(self):
        with self.assertRaises(data_fetch.DataError):
            data_fetch.load_bars("NOPE", date(2024, 1, 1), date(2024, 2, 1), fetch=lambda *a: ([], 0))


@override_settings(VAULT={**settings.VAULT, "MAX_ACTIVE_RUNS": 30, "MAX_GRID": 4})
class JobAndApiTests(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters
        self.api = APIClient()
        self.builtin = Strategy.objects.get(name__startswith="SMA Crossover")
        self.custom = Strategy.objects.create(name="c", code="def on_bar(b,i,s):\n    return 'HOLD'")
        Bar.objects.bulk_create(make_bars("AAPL", date(2023, 9, 1), 500))

    def body(self, **kw):
        return {"strategy": self.builtin.id, "symbol": "aapl", "start_date": "2024-01-01",
                "end_date": "2024-12-31", "starting_cash": "10000", **kw}

    def test_custom_code_disabled_by_default(self):
        r = self.api.post("/api/strategies/", {"name": "x", "code": "def on_bar(b,i,s): return 'HOLD'"},
                          format="json")
        self.assertEqual(r.status_code, 403)
        r = self.api.post("/api/runs/", self.body(strategy=self.custom.id), format="json")
        self.assertEqual(r.status_code, 400)

    def test_run_end_to_end_and_retry_does_not_duplicate_trades(self):
        r = self.api.post("/api/runs/", self.body(), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["symbol"], "AAPL")
        self.assertTrue(jobs.work_one("w1"))
        run = BacktestRun.objects.get(id=r.json()["id"])
        self.assertEqual(run.status, "completed", run.error_message)
        self.assertEqual(run.engine_version, engine.ENGINE_VERSION)
        self.assertEqual(run.bars_processed, run.data_manifest["bar_count"])
        n = Trade.objects.filter(run=run).count()
        self.assertGreater(n, 0)
        # simulate a crash after completion was lost: requeue and re-run
        BacktestRun.objects.filter(id=run.id).update(status="queued")
        jobs.work_one("w2")
        self.assertEqual(Trade.objects.filter(run=run).count(), n)

    def test_idempotency_key_returns_same_run(self):
        a = self.api.post("/api/runs/", self.body(), format="json", HTTP_IDEMPOTENCY_KEY="k1")
        b = self.api.post("/api/runs/", self.body(), format="json", HTTP_IDEMPOTENCY_KEY="k1")
        self.assertEqual(a.json()["id"], b.json()["id"])
        self.assertEqual(BacktestRun.objects.count(), 1)

    def test_queue_full_returns_503(self):
        for _ in range(30):
            BacktestRun.objects.create(strategy=self.builtin, symbol="AAPL", start_date=date(2024, 1, 1),
                                       end_date=date(2024, 2, 1))
        self.assertEqual(self.api.post("/api/runs/", self.body(), format="json").status_code, 503)

    def test_grid_limit_enforced_server_side(self):
        r = self.api.post("/api/optimizations/", self.body(stop_loss_options=["0.05", "0.1", "0.15"],
                                                           take_profit_options=["0.1", "0.2"]), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit is 4", str(r.content))

    def test_stale_job_requeued_then_failed(self):
        run = BacktestRun.objects.create(strategy=self.builtin, symbol="AAPL", start_date=date(2024, 1, 1),
                                         end_date=date(2024, 2, 1), status="running", attempts=1,
                                         heartbeat_at=timezone.now() - timedelta(hours=1))
        jobs.recover_stale()
        run.refresh_from_db()
        self.assertEqual(run.status, "queued")
        BacktestRun.objects.filter(id=run.id).update(status="running", attempts=3,
                                                     heartbeat_at=timezone.now() - timedelta(hours=1))
        jobs.recover_stale()
        run.refresh_from_db()
        self.assertEqual((run.status, run.failure_category), ("failed", "infrastructure"))

    def test_optimization_partial_failure_and_single_oos_run(self):
        r = self.api.post("/api/optimizations/", self.body(stop_loss_options=["0.05", "0.1"],
                                                           take_profit_options=["0.2"]), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        job = OptimizationJob.objects.get(id=r.json()["id"])
        first, second = job.runs.order_by("id")
        BacktestRun.objects.filter(id=second.id).update(strategy_code="def on_bar(b,i,s):\n    return 1/0")
        while jobs.work_one("w"):
            pass
        jobs.finish_optimization(job)  # a second call must not create another OOS run
        self.assertEqual(job.runs.filter(sample="out").count(), 1)
        oos = job.runs.get(sample="out")
        self.assertEqual((oos.status, oos.start_date), ("completed", job.split_date))
        self.assertLess(job.runs.get(id=first.id).end_date, job.split_date)  # train never overlaps test
        self.assertEqual(jobs.optimization_status(job), "partially_completed")
        detail = self.api.get(f"/api/optimizations/{job.id}/").json()
        self.assertEqual(len(detail["runs"]), 3)
        self.assertTrue(detail["runs"][0]["equity_curve"])

    def test_health(self):
        self.assertEqual(self.api.get("/health/live").status_code, 200)
        self.assertEqual(self.api.get("/health/ready").status_code, 200)
