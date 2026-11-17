"""Phase 3: experiments (comparisons, parameter-grid optimizations), priority lanes, worker caches, new metrics.
Run: DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test backtester.test_experiments
(the multi-worker concurrency test needs Postgres and is skipped on SQLite)."""
import copy
import math
import threading
import unittest
from datetime import date, timedelta
from decimal import Decimal as D
from unittest import mock

from django.core.cache import cache as django_cache
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from backtester import cache, jobs, spec
from backtester.engine import Params, simulate
from backtester.models import BacktestRun, Bar, Experiment, Strategy, SymbolCoverage, Trade
from backtester.test_builder import FIXTURE_START, T0, TEMPLATES, bars_for

SYMBOLS = ("AAPL", "MSFT", "RELIANCE.NS", "^GSPC", "^NSEI")


def seed(symbols=SYMBOLS):
    for sym in symbols:
        Bar.objects.bulk_create(bars_for(sym))
        SymbolCoverage.objects.create(symbol=sym, start=FIXTURE_START, until=date(2025, 1, 1), fetched_at=timezone.now())


def drain():
    order = []
    while True:
        run = jobs.claim("w")
        if run is None:
            return order
        order.append(run.id)
        jobs.execute(run, "w")
        if run.experiment_id:
            jobs.finish_optimization(run.experiment)


# ======================================================================== pure parts

class LRUTests(SimpleTestCase):
    def test_eviction_order_and_counters(self):
        c = cache.LRU(maxsize=2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(c.get("a"), 1)  # a is now most recent
        c.put("c", 3)  # evicts b, the least recently used
        self.assertIsNone(c.get("b"))
        self.assertEqual((c.get("a"), c.get("c")), (1, 3))
        self.assertEqual(c.stats(), {"hits": 3, "misses": 1, "size": 2})


class DownsampleTests(SimpleTestCase):
    def curve(self, n):
        # A wave with one deep trough and one high peak in the middle, which every-n-th sampling could miss.
        pts = [[f"d{i}", 100 + 10 * math.sin(i / 50)] for i in range(n)]
        pts[n // 3][1], pts[2 * n // 3][1] = 1.0, 999.0
        return pts

    def test_keeps_extremes_order_and_ends(self):
        c = self.curve(2520)
        d = cache.downsample(c, 500)
        self.assertLessEqual(len(d), 500)
        self.assertGreater(len(d), 400)
        self.assertEqual((d[0], d[-1]), (c[0], c[-1]))
        self.assertIn(c[2520 // 3], d)  # the trough survives
        self.assertIn(c[2 * 2520 // 3], d)  # the peak survives
        idx = [int(p[0][1:]) for p in d]
        self.assertEqual(idx, sorted(idx))  # still in time order

    def test_short_curves_unchanged(self):
        c = self.curve(300)
        self.assertEqual(cache.downsample(c, 500), c)


class MetricTests(SimpleTestCase):
    def bars(self, closes):
        return [{"ts": T0 + timedelta(days=i), "open": D(c), "high": D(c), "low": D(c), "close": D(c), "volume": 0}
                for i, c in enumerate(closes)]

    def test_sortino_calmar_exposure_trades_hand_checked(self):
        from backtester.engine import metrics
        p = Params(starting_cash=D(1000), commission_pct=D(0), slippage_pct=D(0))
        decisions = iter(["BUY"])
        bars = self.bars([100, 100, 90, 108, 108])
        r = simulate(bars, lambda b, i: next(decisions, "HOLD"), p)
        m = metrics(r, p, bars)
        # Bought at bar 1's open (100) with all 1000 -> 10 shares. Equity: 1000, 1000, 900, 1080, 1080.
        rets = [0.0, -0.1, 0.2, 0.0]
        mean = sum(rets) / 4
        downside = math.sqrt(0.01 / 4)
        self.assertAlmostEqual(m["sortino_ratio"], mean / downside * math.sqrt(252))
        self.assertAlmostEqual(m["max_drawdown"], 0.1)
        self.assertAlmostEqual(m["calmar_ratio"], m["cagr"] / 0.1)
        self.assertEqual(m["exposure"], 4 / 5)  # in the market at the close of bars 1-4
        self.assertEqual(m["trade_count"], 0)  # open position, no closed round trip

    def test_undefined_values_are_none(self):
        from backtester.engine import metrics
        p = Params(starting_cash=D(1000), commission_pct=D(0), slippage_pct=D(0))
        bars = self.bars([100, 110, 121])
        m = metrics(simulate(bars, lambda b, i: "HOLD", p), p, bars)
        self.assertEqual((m["sortino_ratio"], m["calmar_ratio"], m["exposure"], m["trade_count"]), (None, None, 0.0, 0))


class TunableParamTests(SimpleTestCase):
    def test_one_group_per_indicator_instance(self):
        groups = spec.tunable_params(TEMPLATES["EMA Crossover (12/26)"])
        self.assertEqual([(g["label"], g["paths"]) for g in groups], [
            ("ema(12).period", ["entry.all[0].left.params.period", "exit.any[0].left.params.period"]),
            ("ema(26).period", ["entry.all[0].right.params.period", "exit.any[0].right.params.period"]),
        ])
        macd = spec.tunable_params(TEMPLATES["MACD Signal Cross (12/26/9)"])
        self.assertEqual([g["label"] for g in macd], ["macd(12, 26, 9).fast", "macd(12, 26, 9).slow",
                                                     "macd(12, 26, 9).signal"])
        self.assertTrue(all(len(g["paths"]) == 4 for g in macd))  # line and signal, entry and exit

    def test_with_params_changes_every_linked_path_and_nothing_else(self):
        base = TEMPLATES["EMA Crossover (12/26)"]
        g = spec.tunable_params(base)[0]
        out = spec.with_params(base, [(g["paths"], 8)])
        self.assertEqual(out["entry"]["all"][0]["left"]["params"]["period"], 8)
        self.assertEqual(out["exit"]["any"][0]["left"]["params"]["period"], 8)
        self.assertEqual(out["entry"]["all"][0]["right"]["params"]["period"], 26)
        self.assertEqual(base["entry"]["all"][0]["left"]["params"]["period"], 12)  # the original is untouched
        for bad in ("entry.all[5].left.params.period", "exit.all[0].left.params.period",
                    "entry.all[0].left.params.nope", "entry.all[0].left.ind"):
            with self.assertRaises(KeyError):
                spec.with_params(base, [([bad], 1)])


# ======================================================================== queue

class PriorityLaneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("lanes@example.com", email_verified=True)
        self.hold = Strategy.objects.get(name="Buy and Hold", is_builtin=True)

    def make(self, priority, n=1):
        return [BacktestRun.objects.create(owner=self.user, strategy=self.hold, symbol="AAPL", priority=priority,
                                           start_date=date(2024, 1, 1), end_date=date(2024, 2, 1),
                                           **jobs.frozen_strategy(self.hold)) for _ in range(n)]

    def test_interactive_run_is_claimed_before_older_batch_children(self):
        batch = self.make(BacktestRun.BATCH, 3)
        single = self.make(BacktestRun.INTERACTIVE)[0]
        claimed = [jobs.claim("w").id for _ in range(4)]
        self.assertEqual(claimed, [single.id] + [r.id for r in batch])  # then FIFO within the batch lane
        self.assertIsNone(jobs.claim("w"))


# ======================================================================== API

class ExperimentApiBase(TestCase):
    def setUp(self):
        django_cache.clear()
        cache.BARS.clear()
        cache.INDICATORS.clear()
        self.user = User.objects.create_user("exp@example.com", email_verified=True)
        self.api = APIClient()
        self.api.force_login(self.user)
        seed()
        patcher = mock.patch("backtester.data_fetch.download", return_value=([], 0))
        self.download = patcher.start()
        self.addCleanup(lambda: self.assertEqual(self.download.call_args_list, [], "network fetch in a test"))
        self.addCleanup(patcher.stop)
        self.ema = self.mine("EMA Crossover (12/26)")
        self.macd = self.mine("MACD Signal Cross (12/26/9)")
        self.hold = Strategy.objects.get(name="Buy and Hold", is_builtin=True)

    def mine(self, template):
        r = self.api.post("/api/strategies/", {"name": template, "kind": "builder", "spec": TEMPLATES[template]},
                          format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def dates(self, **kw):
        return {"start_date": "2024-01-01", "end_date": "2024-12-31", "starting_cash": "10000", **kw}


class ComparisonTests(ExperimentApiBase):
    def compare(self, strategies, symbols, **kw):
        return self.api.post("/api/experiments/", {"kind": "comparison", "strategies": strategies, "symbols": symbols,
                                                   **self.dates(**kw)}, format="json")

    def test_matrix_with_benchmarks_end_to_end(self):
        r = self.compare([self.ema["id"], self.macd["id"]], ["aapl", "RELIANCE.NS"], stop_loss_pct="0.08")
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual((body["kind"], body["status"], body["currency"]), ("comparison", "running", None))  # mixed
        self.assertEqual(body["config"]["benchmarks"], {"USD": "^GSPC", "INR": "^NSEI"})
        job = Experiment.objects.get(id=body["id"])
        runs = list(job.runs.all())
        self.assertEqual(len(runs), 6)  # 2 strategies × 2 symbols + 2 benchmarks
        self.assertTrue(all(run.priority == BacktestRun.BATCH for run in runs))
        bench = [run for run in runs if run.sample == "bench"]
        self.assertEqual({(b.symbol, b.strategy_id, b.commission_pct, b.slippage_pct) for b in bench},
                         {("^GSPC", self.hold.id, 0, 0), ("^NSEI", self.hold.id, 0, 0)})
        drain()
        detail = self.api.get(f"/api/experiments/{job.id}/").json()
        self.assertEqual(detail["status"], "completed")
        self.assertEqual(len(detail["runs"]), 6)
        for run in detail["runs"]:
            self.assertTrue(run["curve"])
            self.assertNotIn("equity_curve", run)
            for k in ("sortino_ratio", "calmar_ratio", "exposure", "trade_count", "cost_drag"):
                self.assertIn(k, run)
        self.assertEqual(self.api.get("/api/dashboard/").json()["experiments"][0]["title"], "2 strategies × 2 symbols")

    def test_a_cell_equals_the_same_standalone_run(self):
        r = self.compare([self.ema["id"]], ["AAPL"], stop_loss_pct="0.08", take_profit_pct="0.2")
        cell = Experiment.objects.get(id=r.json()["id"]).runs.get(sample="full")
        single = self.api.post("/api/runs/", {"strategy": self.ema["id"], "symbol": "AAPL", "stop_loss_pct": "0.08",
                                              "take_profit_pct": "0.2", **self.dates()}, format="json").json()
        drain()
        cell.refresh_from_db()
        alone = BacktestRun.objects.get(id=single["id"])
        self.assertEqual((cell.status, alone.status), ("completed", "completed"))
        self.assertEqual(cell.final_value, alone.final_value)
        trades = lambda run: list(Trade.objects.filter(run=run).values_list("side", "ts", "price", "quantity"))  # noqa: E731
        self.assertEqual(trades(cell), trades(alone))
        self.assertEqual(cell.equity_curve, alone.equity_curve)

    def test_validation(self):
        code = Strategy.objects.get(name__startswith="SMA Crossover")  # built-in code strategy: allowed
        many = [self.mine("Donchian Breakout (20/10)")["id"], self.ema["id"], self.macd["id"]]
        cases = [
            (self.compare(many, ["A", "B", "C", "D", "E", "F", "G", "H", "I"]), "non_field_errors"),  # 27 cells > 25
            (self.compare([self.ema["id"]], ["AAPL"], cost_model="india_delivery"), "cost_model"),
            (self.compare([self.ema["id"]], ["AAPL", "aapl"]), "symbols"),
            (self.compare([self.ema["id"], self.ema["id"]], ["AAPL"]), "strategies"),
            (self.compare([], ["AAPL"]), "strategies"),
            (self.compare([self.ema["id"]], ["AAPL"], slippage_pct="0.01", stop_loss_pct="0.005"), "stop_loss_pct"),
        ]
        for response, field in cases:
            self.assertEqual(response.status_code, 400, response.content)
            self.assertIn(field, response.json())
        custom = Strategy.objects.create(owner=self.user, name="mine", code="def on_bar(b,i,s):\n    return 'HOLD'")
        r = self.compare([custom.id], ["AAPL"])
        self.assertEqual(r.status_code, 400)
        self.assertIn("Custom code", str(r.json()))
        other = User.objects.create_user("other@example.com", email_verified=True)
        theirs = Strategy.objects.create(owner=other, name="x", kind="builder", spec=TEMPLATES["EMA Crossover (12/26)"])
        self.assertEqual(self.compare([theirs.id], ["AAPL"]).status_code, 400)  # invisible: "does not exist"
        self.assertEqual(self.compare([code.id], ["AAPL"]).status_code, 201)
        self.assertFalse(Experiment.objects.filter(config__symbols=["A", "B", "C", "D", "E", "F", "G", "H", "I"]).exists())

    def test_idempotent_and_no_benchmark_for_unknown_currency(self):
        a = self.api.post("/api/experiments/", {"kind": "comparison", "strategies": [self.ema["id"]],
                                                "symbols": ["VOD.L"], **self.dates()}, format="json",
                          HTTP_IDEMPOTENCY_KEY="cmp-1")
        b = self.api.post("/api/experiments/", {"kind": "comparison", "strategies": [self.ema["id"]],
                                                "symbols": ["VOD.L"], **self.dates()}, format="json",
                          HTTP_IDEMPOTENCY_KEY="cmp-1")
        self.assertEqual((a.status_code, b.status_code, a.json()["id"]), (201, 200, b.json()["id"]))
        job = Experiment.objects.get(id=a.json()["id"])
        self.assertEqual((job.config["benchmarks"], job.runs.count()), ({}, 1))

    def test_partial_failure_and_quota_counts_one_job(self):
        r = self.compare([self.ema["id"]], ["AAPL", "NODATA"])
        job = Experiment.objects.get(id=r.json()["id"])
        self.assertEqual(self.api.get("/api/dashboard/").json()["quota"]["usage"]["active_jobs"], 1)
        drain()
        self.assertEqual(jobs.experiment_status(job), "partially_completed")
        failed = job.runs.get(symbol="NODATA")
        self.assertEqual((failed.status, failed.failure_category), ("failed", "data"))
        self.download.reset_mock()  # NODATA had no coverage, so the worker tried the provider (mocked): expected here


class ParamGridTests(ExperimentApiBase):
    def optimize(self, strategy, **kw):
        body = {"strategy": strategy["id"], "symbol": "AAPL", "stop_loss_options": ["0.05"],
                "take_profit_options": ["0.2"], **self.dates(), **kw}
        return self.api.post("/api/experiments/", {"kind": "optimization", **body}, format="json")

    def grid(self, strategy, *pairs):
        groups = {g["label"]: g["paths"] for g in strategy["tunable_params"]}
        return [{"paths": groups[label], "values": values} for label, values in pairs]

    def test_grid_over_linked_spec_params_end_to_end(self):
        self.assertEqual([g["label"] for g in self.ema["tunable_params"]], ["ema(12).period", "ema(26).period"])
        r = self.optimize(self.ema, param_grid=self.grid(self.ema, ("ema(12).period", [8, 12]),
                                                          ("ema(26).period", [20, 26])),
                          stop_loss_options=["0.05", "0.1"])
        self.assertEqual(r.status_code, 201, r.content)
        job = Experiment.objects.get(id=r.json()["id"])
        ins = list(job.runs.filter(sample="in").order_by("id"))
        self.assertEqual(len(ins), 8)  # 2 × 2 params × 2 stops × 1 target
        seen = set()
        for run in ins:
            fast = run.grid_params["ema(12).period"]
            slow = run.grid_params["ema(26).period"]
            s = run.strategy_spec
            # Linked paths moved together: entry and exit use the same EMA lengths.
            self.assertEqual(s["entry"]["all"][0]["left"]["params"]["period"], fast)
            self.assertEqual(s["exit"]["any"][0]["left"]["params"]["period"], fast)
            self.assertEqual(s["exit"]["any"][0]["right"]["params"]["period"], slow)
            self.assertEqual(run.strategy_hash, spec.spec_hash(s))
            seen.add((fast, slow, run.grid_params["stop_loss_pct"]))
        self.assertEqual(len(seen), 8)
        drain()
        oos = job.runs.get(sample="out")
        best = max(job.runs.filter(sample="in", status="completed"),
                   key=lambda x: (x.sharpe_ratio is not None, x.sharpe_ratio or 0, x.final_value or 0))
        self.assertEqual((oos.status, oos.grid_params, oos.strategy_spec), ("completed", best.grid_params,
                                                                             best.strategy_spec))
        self.assertEqual(r.json()["config"]["param_grid"][0]["values"], [8, 12])

    def test_invalid_combinations_are_skipped_and_reported(self):
        r = self.optimize(self.macd, param_grid=self.grid(self.macd, ("macd(12, 26, 9).fast", [12, 30]),
                                                           ("macd(12, 26, 9).slow", [26, 40])))
        self.assertEqual(r.status_code, 201, r.content)
        skipped = r.json()["config"]["skipped"]
        self.assertEqual(skipped, [{"params": {"macd(12, 26, 9).fast": 30, "macd(12, 26, 9).slow": 26},
                                    "reason": "must be greater than fast"}])
        self.assertEqual(Experiment.objects.get(id=r.json()["id"]).runs.count(), 3)

    def test_rejections(self):
        out_of_range = self.optimize(self.ema, param_grid=self.grid(self.ema, ("ema(12).period", [5, 500])))
        self.assertEqual(out_of_range.status_code, 400)
        self.assertEqual(out_of_range.json(), {"param_grid": {"ema(12).period": "500: must be a whole number between 2 "
                                                                                "and 200"}})
        fraction = self.optimize(self.ema, param_grid=self.grid(self.ema, ("ema(12).period", [5.5])))
        self.assertEqual(fraction.json(), {"param_grid": {"ema(12).period": "must be whole numbers"}})
        unlinked = self.optimize(self.ema, param_grid=[{"paths": ["entry.all[0].left.params.period"], "values": [5]}])
        self.assertEqual(unlinked.status_code, 400)  # half of a linked group would build an accidental strategy
        code = Strategy.objects.get(name__startswith="SMA Crossover")
        r = self.optimize({"id": code.id}, param_grid=self.grid(self.ema, ("ema(12).period", [5])))
        self.assertIn("Only builder strategies", str(r.json()))
        too_big = self.optimize(self.ema, param_grid=self.grid(self.ema, ("ema(12).period", [5, 8, 10, 12, 15]),
                                                                ("ema(26).period", [20, 26, 30, 40, 50, 60])))
        self.assertIn("30 combinations requested; the limit is 25", str(too_big.json()))
        none_valid = self.optimize(self.macd, param_grid=self.grid(self.macd, ("macd(12, 26, 9).fast", [30, 40])))
        self.assertIn("Every combination is invalid", str(none_valid.json()))
        self.assertEqual(Experiment.objects.count(), 0)

    def test_old_endpoint_still_works(self):
        r = self.api.post("/api/optimizations/", {"strategy": self.ema["id"], "symbol": "AAPL",
                                                  "stop_loss_options": ["0.05"], "take_profit_options": ["0.2"],
                                                  **self.dates()}, format="json")
        self.assertEqual((r.status_code, r.json()["kind"]), (201, "optimization"))
        self.api.post("/api/experiments/", {"kind": "comparison", "strategies": [self.ema["id"]], "symbols": ["AAPL"],
                                            **self.dates()}, format="json")
        self.assertEqual(self.api.get("/api/optimizations/").json()["count"], 1)  # only optimizations
        self.assertEqual(self.api.get("/api/experiments/").json()["count"], 2)


class WorkerCacheTests(ExperimentApiBase):
    def test_children_share_bars_and_indicators_and_results_are_unchanged(self):
        r = self.api.post("/api/experiments/", {"kind": "optimization", "strategy": self.ema["id"], "symbol": "AAPL",
                                                "stop_loss_options": ["0.03", "0.05", "0.08", "0.1"],
                                                "take_profit_options": ["0.2"], **self.dates()}, format="json")
        job = Experiment.objects.get(id=r.json()["id"])
        drain()
        # 4 in-sample children + 1 out-of-sample: the 3 later in-sample children reuse the first child's bars;
        # the OOS run covers a different period, so it loads its own.
        self.assertEqual(cache.BARS.stats()["hits"], 3)
        self.assertEqual(cache.INDICATORS.stats()["hits"], 3 * 2)  # EMA 12 and EMA 26 reused by each later child
        warm = {run.id: (run.final_value, run.equity_curve) for run in job.runs.all()}
        # Same runs with cold caches give identical results: the cache only removes repeated work.
        cache.BARS.clear()
        cache.INDICATORS.clear()
        job.runs.update(status="queued", worker_id="")
        drain()
        cold = {run.id: (run.final_value, run.equity_curve) for run in job.runs.all()}
        self.assertEqual(warm, cold)

    def test_a_redownload_invalidates_cached_bars(self):
        run = BacktestRun.objects.create(owner=self.user, strategy=self.hold, symbol="AAPL",
                                         start_date=date(2024, 1, 1), end_date=date(2024, 3, 1),
                                         **jobs.frozen_strategy(self.hold))
        drain()
        self.assertEqual(cache.BARS.stats()["misses"], 1)
        SymbolCoverage.objects.filter(symbol="AAPL").update(fetched_at=timezone.now() + timedelta(minutes=1))
        BacktestRun.objects.filter(id=run.id).update(status="queued", worker_id="")
        drain()
        self.assertEqual(cache.BARS.stats()["hits"], 0)  # new fetched_at -> new key -> fresh load


class HeartbeatTests(ExperimentApiBase):
    """Heartbeats are time-based: a fast run doesn't pay one UPDATE per 50 bars, a slow run still beats."""

    def progress_updates(self):
        run = BacktestRun.objects.create(owner=self.user, strategy=self.hold, symbol="AAPL",
                                         start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
                                         **jobs.frozen_strategy(self.hold))
        with mock.patch.object(jobs, "_update", wraps=jobs._update) as spy:
            drain()
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        return sum(1 for c in spy.call_args_list if "bars_processed" in c.kwargs and "status" not in c.kwargs)

    def test_fast_run_writes_no_progress_rows(self):
        self.assertEqual(self.progress_updates(), 0)  # was 7 for these 366 bars at one per 50 bars

    def test_slow_run_still_heartbeats(self):
        with mock.patch.object(jobs, "HEARTBEAT_EVERY_S", 0):  # every bar counts as "a second later"
            self.assertGreater(self.progress_updates(), 300)


@unittest.skipUnless(connection.vendor == "postgresql", "needs row locks (SKIP LOCKED) from Postgres")
class ConcurrentWorkerTests(TransactionTestCase):
    """Several real worker threads, each with its own database connection, drain one queue."""
    serialized_rollback = True  # keep the migration-seeded built-ins for the tests that follow

    def test_every_run_claimed_exactly_once(self):
        seed(("AAPL",))
        user = User.objects.create_user("workers@example.com", email_verified=True)
        hold = Strategy.objects.get(name="Buy and Hold", is_builtin=True)
        ids = [BacktestRun.objects.create(owner=user, strategy=hold, symbol="AAPL", priority=i % 2,
                                          start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
                                          **jobs.frozen_strategy(hold)).id for i in range(40)]
        claimed, lock = [], threading.Lock()

        def worker(n):
            try:
                while True:
                    run = jobs.claim(f"w{n}")
                    if run is None:
                        return
                    with lock:
                        claimed.append(run.id)
                    jobs.execute(run, f"w{n}")
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        self.assertEqual(sorted(claimed), sorted(ids))  # no run lost, none claimed twice
        runs = BacktestRun.objects.filter(id__in=ids)
        self.assertEqual(set(runs.values_list("status", flat=True)), {"completed"})
        self.assertEqual(set(runs.values_list("attempts", flat=True)), {1})
        self.assertGreater(len(set(runs.values_list("worker_id", flat=True))), 1)  # the work was really shared
        self.assertEqual(len({copy.deepcopy(r.equity_curve)[-1][1] for r in runs}), 1)  # same inputs, same result
