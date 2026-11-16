"""Phase 2: builder strategies (spec.py, indicators.py), cost models (costs.py) and their API.
Run: DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test backtester.test_builder"""
import copy
import importlib
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from unittest import mock

import pandas as pd
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from backtester import costs, engine, indicators as ind, jobs, spec
from backtester.engine import Params, simulate
from backtester.models import BacktestRun, Bar, Experiment, Strategy, SymbolCoverage, Trade

T0 = datetime(2024, 1, 1, tzinfo=UTC)
TEMPLATES = importlib.import_module("backtester.migrations.0017_builder_templates").TEMPLATES
BUILTIN_CODE = importlib.import_module("backtester.migrations.0010_engine_v2_data").BUILTINS


def walk(n=400, seed=7, start=100.0):
    """Deterministic random-walk OHLCV bars with Decimal prices (like the worker's)."""
    rng, price, out = random.Random(seed), start, []
    for i in range(n):
        o = price
        c = max(1.0, o * (1 + rng.gauss(0, 0.02)))
        h, lo = max(o, c) * (1 + abs(rng.gauss(0, 0.005))), min(o, c) * (1 - abs(rng.gauss(0, 0.005)))
        q = lambda x: D(f"{x:.4f}")  # noqa: E731
        out.append({"ts": T0 + timedelta(days=i), "open": q(o), "high": q(h), "low": q(lo), "close": q(c),
                    "volume": rng.randint(1000, 5000)})
        price = c
    return out


def cols(bars):
    return {f: [b[f] for b in bars] for f in spec.PRICE_FIELDS}


def close_enough(test, got, want, tol=1e-9):
    test.assertEqual(len(got), len(want))
    for i, (g, w) in enumerate(zip(got, want)):
        if w is None or (isinstance(w, float) and pd.isna(w)):
            test.assertIsNone(g, f"index {i}")
        else:
            test.assertIsNotNone(g, f"index {i}")
            test.assertAlmostEqual(g, w, delta=tol * max(1.0, abs(w)), msg=f"index {i}")


def opnd(name, output="value", **params):
    return {"ind": name, "params": params, "output": output}


def cond(left, op, right):
    return {"left": left, "op": op, "right": right}


def sma_cross_spec():
    return {"version": 1, "entry": {"all": [cond(opnd("sma", period=10), ">", opnd("sma", period=50))]},
            "exit": {"any": [cond(opnd("sma", period=10), "<", opnd("sma", period=50))]}}


# ======================================================================== indicators

class IndicatorReferenceTests(SimpleTestCase):
    """Hand-computed values plus pandas as an independent reference implementation."""

    def setUp(self):
        self.bars = walk()
        self.c = cols(self.bars)
        self.closes = pd.Series([float(x) for x in self.c["close"]])

    def test_hand_values(self):
        self.assertEqual(ind.sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])
        self.assertEqual(ind.ema([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])  # seed 2, alpha 0.5
        self.assertEqual(ind.rsi([1, 2, 1, 2], 2), [None, None, 50.0, 75.0])  # Wilder: (0.5*1+1)/2 vs (0.5*1+0)/2
        # TR = 2, 3, 1 -> ATR(2) = (2+3)/2 = 2.5, then (2.5*1 + 1)/2 = 1.75
        self.assertEqual(ind.atr([10, 11, 12, 11], [8, 9, 9, 10], [9, 10, 11, 10], 2), [None, None, 2.5, 1.75])
        self.assertEqual(ind.donchian([5, 7, 6, 9], [1, 2, 0, 3], 2),
                         {"upper": [None, None, 7.0, 7.0], "lower": [None, None, 1.0, 0.0]})
        r = ind.roc([100, 110, 99], 1)
        self.assertIsNone(r[0])
        self.assertAlmostEqual(r[1], 10.0, places=12)
        self.assertAlmostEqual(r[2], -10.0, places=12)
        self.assertEqual(ind.rsi([5, 5, 5, 5], 2)[3], 50.0)    # flat: neutral
        self.assertEqual(ind.rsi([1, 2, 3, 4], 2)[3], 100.0)   # only gains
        flat = ind.macd([10.0] * 60, 12, 26, 9)
        self.assertEqual((flat["line"][59], flat["signal"][59], flat["hist"][59]), (0.0, 0.0, 0.0))

    def test_sma_matches_engine_and_pandas(self):
        mine = ind.sma(self.c["close"], 50)
        engine_vals = [engine._sma(self.c["close"][:i + 1], 50) for i in range(len(self.bars))]
        self.assertEqual(mine, engine_vals)  # exact: same Decimal arithmetic as the built-in sma_50
        close_enough(self, mine, self.closes.rolling(50).mean().tolist())

    def test_ema_matches_pandas(self):
        n = 20
        seed = self.closes[:n].mean()
        ref = pd.Series([seed] + self.closes[n:].tolist()).ewm(alpha=2 / (n + 1), adjust=False).mean().tolist()
        close_enough(self, ind.ema(self.c["close"], n), [None] * (n - 1) + ref)

    def test_rsi_matches_pandas_wilder(self):
        n = 14
        d = self.closes.diff()
        gain, loss = d.clip(lower=0), (-d).clip(lower=0)

        def wilder(x):
            seed = x[1:n + 1].mean()
            return [None] * n + pd.Series([seed] + x[n + 1:].tolist()).ewm(alpha=1 / n, adjust=False).mean().tolist()

        ref = [None if g is None else 100 - 100 / (1 + g / lo) for g, lo in zip(wilder(gain), wilder(loss))]
        close_enough(self, ind.rsi(self.c["close"], n), ref)

    def test_macd_is_ema_difference_and_signal(self):
        m = ind.macd(self.c["close"], 12, 26, 9)
        f, s = ind.ema(self.c["close"], 12), ind.ema(self.c["close"], 26)
        close_enough(self, m["line"], [None if b is None else a - b for a, b in zip(f, s)])
        close_enough(self, m["signal"], ind.ema(m["line"], 9))
        close_enough(self, m["hist"], [None if b is None else a - b for a, b in zip(m["line"], m["signal"])])
        self.assertIsNone(m["signal"][25 + 7])
        self.assertIsNotNone(m["signal"][25 + 8])  # first signal value: slow - 1 + signal - 1

    def test_bbands_matches_pandas_population_std(self):
        b = ind.bbands(self.c["close"], 20, 2.0)
        mid, sd = self.closes.rolling(20).mean(), self.closes.rolling(20).std(ddof=0)
        close_enough(self, b["middle"], mid.tolist())
        close_enough(self, b["upper"], (mid + 2 * sd).tolist())
        close_enough(self, b["lower"], (mid - 2 * sd).tolist())

    def test_atr_matches_pandas_wilder(self):
        n = 14
        h, lo = pd.Series([float(x) for x in self.c["high"]]), pd.Series([float(x) for x in self.c["low"]])
        pc = self.closes.shift(1)
        tr = pd.concat([h - lo, (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
        seed = tr[1:n + 1].mean()
        ref = [None] * n + pd.Series([seed] + tr[n + 1:].tolist()).ewm(alpha=1 / n, adjust=False).mean().tolist()
        close_enough(self, ind.atr(self.c["high"], self.c["low"], self.c["close"], n), ref)

    def test_donchian_excludes_current_bar(self):
        d = ind.donchian(self.c["high"], self.c["low"], 20)
        h, lo = pd.Series([float(x) for x in self.c["high"]]), pd.Series([float(x) for x in self.c["low"]])
        close_enough(self, d["upper"], h.rolling(20).max().shift(1).tolist())
        close_enough(self, d["lower"], lo.rolling(20).min().shift(1).tolist())

    def test_roc_matches_pandas(self):
        close_enough(self, ind.roc(self.c["close"], 10), (self.closes.pct_change(10) * 100).tolist())


class NoLookaheadTests(SimpleTestCase):
    """Metamorphic: rewriting every bar after t must not change any indicator value or decision at or before t."""

    def perturbed(self, bars, t):
        out = copy.deepcopy(bars)
        rng = random.Random(t)
        for b in out[t + 1:]:
            k = D(str(round(rng.uniform(0.5, 1.5), 3)))
            for f in ("open", "high", "low", "close"):
                b[f] = (b[f] * k).quantize(D("0.0001"))
            b["volume"] *= 3
        return out

    def test_indicators_never_see_the_future(self):
        bars = walk(300)
        for name, meta in ind.REGISTRY.items():
            params = {p[0]: p[4] for p in meta["params"]}
            base = meta["fn"](cols(bars), params)
            for t in (30, 120, 250):
                again = meta["fn"](cols(self.perturbed(bars, t)), params)
                for out in meta["outputs"]:
                    self.assertEqual(base[out][:t + 1], again[out][:t + 1], f"{name}.{out} changed at t={t}")

    def test_decisions_never_see_the_future(self):
        bars = walk(300)
        every = {"version": 1, "entry": {"any": [
            cond(opnd(name, out, **{p[0]: p[4] for p in meta["params"]}), "crosses_above", {"price": "close"})
            for name, meta in ind.REGISTRY.items() for out in meta["outputs"]][:10]},
            "exit": {"any": [cond({"price": "close"}, "crosses_below", opnd("ema", period=20)),
                             cond(opnd("donchian", "lower", period=20), ">", {"price": "low"}),
                             cond(opnd("roc", period=5), "<", {"const": -3})]}}
        s = spec.validate(every)
        base = spec.signals(s, bars)
        self.assertIn("BUY", base)
        self.assertIn("SELL", base)
        for t in (60, 150, 299):
            self.assertEqual(spec.signals(s, self.perturbed(bars, t))[:t + 1], base[:t + 1], f"t={t}")


# ======================================================================== spec

class SpecValidationTests(SimpleTestCase):
    maxDiff = None

    def errors(self, raw):
        with self.assertRaises(spec.SpecError) as cm:
            spec.validate(raw)
        return cm.exception.errors

    def test_defaults_filled_and_normalised(self):
        s = spec.validate({"version": 1, "entry": {"all": [{"left": {"ind": "rsi"}, "op": "<", "right": {"const": 30}}]},
                           "exit": {"any": [{"left": {"ind": "macd", "params": {"fast": 12.0}}, "op": ">",
                                             "right": {"const": 0}}]}})
        self.assertEqual(s["entry"]["all"][0]["left"], {"ind": "rsi", "params": {"period": 14}, "output": "value"})
        self.assertEqual(s["exit"]["any"][0]["left"],
                         {"ind": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}, "output": "line"})
        self.assertIsInstance(s["exit"]["any"][0]["left"]["params"]["fast"], int)
        self.assertEqual(spec.validate(s), s)  # idempotent

    def test_seeded_templates_are_valid_and_normalised(self):
        self.assertEqual(len(TEMPLATES), 6)
        for name, t in TEMPLATES.items():
            self.assertEqual(spec.validate(t), t, name)
            self.assertIn("def on_bar", spec.render_python(t))

    def test_every_problem_reported_with_its_path(self):
        bad = {"version": 1, "extra": 1,
               "entry": {"all": [
                   cond(opnd("sma", period=500), ">", {"const": 1}),
                   cond(opnd("nope"), "==", {"price": "vwap"}),
                   cond({"const": 1}, ">", {"const": 2}),
                   {"left": {"const": True}, "op": ">", "right": {"price": "close"}, "x": 0},
                   cond(opnd("rsi", period=14.5), ">", opnd("macd", fast=26, slow=12)),
                   cond(opnd("bbands", "top"), ">", {"ind": "ema", "price": "close"}),
               ]},
               "exit": {"any": []}}
        e = self.errors(bad)
        self.assertEqual(e, {
            "extra": "unknown field",
            "entry.all[0].left.params.period": "must be a whole number between 2 and 200",
            "entry.all[1].left.ind": "must be one of sma, ema, rsi, macd, bbands, atr, donchian, roc",
            "entry.all[1].op": "must be one of >, <, >=, <=, crosses_above, crosses_below",
            "entry.all[1].right.price": "must be one of open, high, low, close, volume",
            "entry.all[2]": "compare the market to something: both sides can't be numbers",
            "entry.all[3].x": "unknown field",
            "entry.all[3].left.const": "must be a number between -1e+09 and 1e+09",
            "entry.all[4].left.params.period": "must be a whole number between 2 and 200",
            "entry.all[4].right.params.slow": "must be greater than fast",
            "entry.all[4].right.output": "must be one of line, signal, hist",
            "entry.all[5].left.output": "must be one of upper, middle, lower",
            "entry.all[5].right": 'must have exactly one of "ind", "price" or "const"',
            "exit.any": "must be a list of 1 to 10 conditions",
        })

    def test_shape_errors(self):
        one = [cond({"price": "close"}, ">", {"const": 1})]
        self.assertEqual(self.errors([]), {"spec": "must be an object"})
        self.assertEqual(self.errors({"version": 2, "entry": {"all": one}, "exit": {"all": one}}), {"version": "must be 1"})
        self.assertIn("exit", self.errors({"version": 1, "entry": {"all": one}}))
        self.assertIn("entry", self.errors({"version": 1, "entry": {"all": one, "any": one}, "exit": {"all": one}}))
        self.assertIn("entry.all", self.errors({"version": 1, "entry": {"all": one * 11}, "exit": {"all": one}}))
        self.assertIn("spec", self.errors({"version": 1, "entry": {"all": one}, "exit": {"all": one}, "pad": "x" * 9000}))
        self.assertIn("entry.all[0].right.const",
                      self.errors({"version": 1, "entry": {"all": [cond({"price": "close"}, ">", {"const": float("nan")})]},
                                   "exit": {"all": one}}))

    def test_hash_ignores_key_order(self):
        a = spec.validate(sma_cross_spec())
        b = {"exit": a["exit"], "entry": a["entry"], "version": 1}
        self.assertEqual(spec.spec_hash(a), spec.spec_hash(b))
        c = copy.deepcopy(a)
        c["entry"]["all"][0]["right"]["params"]["period"] = 51
        self.assertNotEqual(spec.spec_hash(a), spec.spec_hash(c))

    def test_warmup(self):
        self.assertEqual(spec.warmup_bars(spec.validate(sma_cross_spec())), 50)  # same as code strategies
        self.assertEqual(spec.warmup_bars(TEMPLATES["MACD Signal Cross (12/26/9)"]), 105)
        self.assertEqual(spec.warmup_bars(TEMPLATES["Trend-Filtered RSI (SMA 200, RSI 14)"]), 200)
        price_only = spec.validate({"version": 1, "entry": {"all": [cond({"price": "close"}, "crosses_above", {"const": 5})]},
                                    "exit": {"all": [cond({"price": "close"}, "<", {"const": 4})]}})
        self.assertEqual(spec.warmup_bars(price_only), 1)
        big = spec.validate({"version": 1, "entry": {"all": [cond(opnd("ema", period=200), ">", {"const": 1})]},
                             "exit": {"all": [cond(opnd("ema", period=200), "<", {"const": 1})]}})
        self.assertEqual(spec.warmup_bars(big), spec.MAX_WARMUP_BARS)

    def test_render_python(self):
        text = spec.render_python(TEMPLATES["MACD Signal Cross (12/26/9)"])
        self.assertIn("crosses_above(ind.macd(12, 26, 9).line, ind.macd(12, 26, 9).signal),", text)
        self.assertIn("never executed", text)
        text = spec.render_python(TEMPLATES["Trend-Filtered RSI (SMA 200, RSI 14)"])
        self.assertIn("bar.close > ind.sma(200),", text)
        self.assertIn("ind.rsi(14) < 35,", text)
        compile(text, "<render>", "exec")  # shaped like real Python, though never run


class SignalTests(SimpleTestCase):
    def sig(self, entry, exit_, closes):
        bars = [{"ts": T0 + timedelta(days=i), "open": D(c), "high": D(c), "low": D(c), "close": D(c), "volume": 1}
                for i, c in enumerate(closes)]
        s = spec.validate({"version": 1, "entry": entry, "exit": exit_})
        return spec.signals(s, bars)

    never = {"all": [cond({"price": "close"}, "<", {"const": -1})]}

    def test_cross_fires_once_comparison_every_bar(self):
        closes = [1, 2, 6, 7, 8, 3, 9]
        cross = self.sig({"all": [cond({"price": "close"}, "crosses_above", {"const": 5})]}, self.never, closes)
        above = self.sig({"all": [cond({"price": "close"}, ">", {"const": 5})]}, self.never, closes)
        self.assertEqual(cross, ["HOLD", "HOLD", "BUY", "HOLD", "HOLD", "HOLD", "BUY"])
        self.assertEqual(above, ["HOLD", "HOLD", "BUY", "BUY", "BUY", "HOLD", "BUY"])
        below = self.sig(self.never, {"all": [cond({"price": "close"}, "crosses_below", {"const": 5})]}, closes)
        self.assertEqual(below, ["HOLD", "HOLD", "HOLD", "HOLD", "HOLD", "SELL", "HOLD"])

    def test_exit_wins_and_groups(self):
        both = self.sig({"all": [cond({"price": "close"}, ">", {"const": 0})]},
                        {"any": [cond({"price": "close"}, ">", {"const": 2})]}, [1, 3])
        self.assertEqual(both, ["BUY", "SELL"])
        all_ = self.sig({"all": [cond({"price": "close"}, ">", {"const": 2}), cond({"price": "close"}, "<", {"const": 4})]},
                        self.never, [1, 3, 5])
        any_ = self.sig({"any": [cond({"price": "close"}, "<", {"const": 2}), cond({"price": "close"}, ">", {"const": 4})]},
                        self.never, [1, 3, 5])
        self.assertEqual((all_, any_), (["HOLD", "BUY", "HOLD"], ["BUY", "HOLD", "BUY"]))

    def test_missing_indicator_value_is_false(self):
        # SMA(3) doesn't exist on the first two bars, so neither "<" nor ">" can be true there.
        s = self.sig({"any": [cond(opnd("sma", period=3), ">", {"const": 0}),
                              cond(opnd("sma", period=3), "<", {"const": 1e6})]}, self.never, [1, 2, 3, 4])
        self.assertEqual(s, ["HOLD", "HOLD", "BUY", "BUY"])


class ParityTests(SimpleTestCase):
    """Differential test: the builder version of 'SMA Crossover (10/50)' must trade exactly like the Python built-in."""

    def test_builder_matches_builtin_code_trade_for_trade(self):
        ns = {}
        exec(BUILTIN_CODE["SMA Crossover (10/50)"], ns)  # trusted seed code, run in-process for the comparison only
        on_bar = ns["on_bar"]
        p = Params(starting_cash=D(10000), commission_pct=D("0.001"), slippage_pct=D("0.0005"),
                   stop_loss_pct=D("0.08"), take_profit_pct=D("0.15"))
        for seed in (1, 7, 42):
            bars = walk(600, seed=seed)
            warm = spec.warmup_bars(spec.validate(sma_cross_spec()))
            code_run = simulate(bars, lambda b, i: on_bar(b, i, {}), p, warmup=warm)
            spec_run = simulate(bars, spec.compile_decide(spec.validate(sma_cross_spec()), bars), p, warmup=warm)
            fills = lambda r: [(f.side, f.ts, f.price, f.quantity, f.reason) for f in r.fills]  # noqa: E731
            self.assertGreater(len(code_run.fills), 4, seed)
            self.assertEqual(fills(spec_run), fills(code_run), seed)
            self.assertEqual(spec_run.equity_curve, code_run.equity_curve, seed)


# ======================================================================== costs

class CostTests(SimpleTestCase):
    def test_india_delivery_hand_calculated(self):
        buy, sell, b = costs.india_delivery()
        # On Rs 1,00,000: STT 100 + exchange 2.97 + SEBI 0.10 + GST 18% of 3.07 (0.5526) [+ stamp 15 on buys]
        self.assertEqual(buy * 100000, D("118.6226"))
        self.assertEqual(sell * 100000, D("103.6226"))
        self.assertEqual(b["gst"], D("0.000005526"))
        buy, sell, _ = costs.india_delivery(D("0.0003"))  # 0.03% brokerage: GST applies to it too
        self.assertEqual(buy, D("0.001540226"))
        self.assertEqual(sell, D("0.001390226"))
        self.assertEqual(costs.rates("flat", D("0.002")), (D("0.002"), D("0.002")))

    def test_engine_charges_sell_rate_on_sells(self):
        p = Params(starting_cash=D(10000), commission_pct=D("0.01"), sell_commission_pct=D("0.02"), slippage_pct=D(0))
        bars = [{"ts": T0 + timedelta(days=i), "open": D(o), "high": D(o), "low": D(o), "close": D(o), "volume": 0}
                for i, o in enumerate([100, 100, 120, 120])]
        decisions = iter(["BUY", "SELL"])
        r = simulate(bars, lambda b, i: next(decisions, "HOLD"), p)
        buy, sell = r.fills
        self.assertEqual(buy.quantity, D("99.009900"))  # 10000 / (100 * 1.01), rounded down
        self.assertEqual(buy.commission, buy.quantity * 100 * D("0.01"))
        self.assertEqual(sell.commission, sell.quantity * 120 * D("0.02"))
        self.assertEqual(r.cash, D(10000) - buy.quantity * 100 * D("1.01") + sell.quantity * 120 * D("0.98"))

    def test_currency(self):
        for sym, cur in (("RELIANCE.NS", "INR"), ("TCS.BO", "INR"), ("^NSEI", "INR"), ("AAPL", "USD"),
                         ("BRK-B", "USD"), ("^GSPC", "USD"), ("VOD.L", None), ("EURUSD=X", None)):
            self.assertEqual(costs.currency(sym), cur, sym)


# ======================================================================== API and worker

FIXTURE_START = date(2023, 1, 2)  # leaves room for the longest template warm-up (210 calendar days) before 2024


def bars_for(symbol, n=730, start=FIXTURE_START):
    out = []
    for i, b in enumerate(walk(n, seed=len(symbol))):
        out.append(Bar(symbol=symbol, ts=datetime.combine(start + timedelta(days=i), datetime.min.time(), UTC),
                       open=b["open"], high=b["high"], low=b["low"], close=b["close"], volume=b["volume"]))
    return out


class BuilderApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("builder@example.com", email_verified=True)
        self.api = APIClient()
        self.api.force_login(self.user)
        for sym in ("AAPL", "RELIANCE.NS"):
            Bar.objects.bulk_create(bars_for(sym))
            SymbolCoverage.objects.create(symbol=sym, start=FIXTURE_START, until=date(2025, 1, 1),
                                          fetched_at=timezone.now())
        # The worker swallows fetch errors (it falls back to stored bars), so record calls and fail afterwards:
        # a test must never reach the real provider.
        patcher = mock.patch("backtester.data_fetch.download", return_value=([], 0))
        self.download = patcher.start()
        self.addCleanup(lambda: self.assertEqual(self.download.call_args_list, [], "network fetch in a test"))
        self.addCleanup(patcher.stop)

    def create(self, spec_=None, name="mine", client=None):
        return (client or self.api).post("/api/strategies/", {"name": name, "kind": "builder",
                                                              "spec": spec_ or sma_cross_spec()}, format="json")

    def run_body(self, strategy_id, **kw):
        return {"strategy": strategy_id, "symbol": "aapl", "start_date": "2024-01-01", "end_date": "2024-12-31",
                "starting_cash": "10000", **kw}

    def test_builder_strategy_created_while_custom_code_is_off(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual((body["kind"], body["code"], body["warmup_bars"]), ("builder", "", 50))
        self.assertIn("never executed", body["python"])
        self.assertEqual(body["spec"], spec.validate(sma_cross_spec()))
        # the code path is still closed
        r = self.api.post("/api/strategies/", {"name": "x", "code": "def on_bar(b,i,s): return 'HOLD'"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_invalid_spec_returns_paths(self):
        bad = sma_cross_spec()
        bad["entry"]["all"][0]["left"]["params"]["period"] = 1
        r = self.create(bad)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json(), {"spec": {"entry.all[0].left.params.period": "must be a whole number between 2 and 200"}})
        r = self.api.post("/api/strategies/", {"name": "x", "kind": "builder", "spec": sma_cross_spec(),
                                               "code": "print(1)"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.api.post("/api/strategies/", {"name": "x", "kind": "builder"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_saved_strategy_limit_per_tier(self):
        guest = User.objects.create_guest()
        client = APIClient()
        client.force_login(guest)
        for i in range(5):
            self.assertEqual(self.create(name=f"s{i}", client=client).status_code, 201)
        r = self.create(name="s5", client=client)
        self.assertEqual(r.status_code, 429)
        self.assertIn("limit 5 for guest", r.json()["detail"])

    def test_edit_and_delete_rules(self):
        sid = self.create().json()["id"]
        new = sma_cross_spec()
        new["entry"]["all"][0]["right"]["params"]["period"] = 40
        r = self.api.patch(f"/api/strategies/{sid}/", {"spec": new}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["spec"]["entry"]["all"][0]["right"]["params"]["period"], 40)
        self.assertEqual(self.api.patch(f"/api/strategies/{sid}/", {"kind": "code"}, format="json").status_code, 400)
        builtin = Strategy.objects.filter(is_builtin=True, kind="builder").first()
        self.assertEqual(self.api.patch(f"/api/strategies/{builtin.id}/", {"name": "x"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"/api/strategies/{builtin.id}/").status_code, 403)
        other = APIClient()
        other.force_login(User.objects.create_user("other@example.com", email_verified=True))
        self.assertEqual(other.get(f"/api/strategies/{sid}/").status_code, 404)
        self.assertEqual(other.delete(f"/api/strategies/{sid}/").status_code, 404)
        self.assertEqual(self.api.post("/api/runs/", self.run_body(sid), format="json").status_code, 201)
        r = self.api.delete(f"/api/strategies/{sid}/")
        self.assertEqual(r.status_code, 409)
        unused = self.create(name="unused").json()["id"]
        self.assertEqual(self.api.delete(f"/api/strategies/{unused}/").status_code, 204)

    def test_catalog_and_preview(self):
        c = self.api.get("/api/strategies/catalog/").json()
        self.assertEqual([i["id"] for i in c["indicators"]], list(ind.REGISTRY))
        self.assertEqual(c["max_conditions"], 10)
        self.assertFalse(c["custom_code_enabled"])
        self.assertEqual(c["india_rates"]["buy_total"], "0.001186226")
        self.assertIn({"symbol": "^NSEI", "name": "NIFTY 50"}, c["suggested_symbols"])
        r = self.api.post("/api/strategies/preview/", {"spec": TEMPLATES["MACD Signal Cross (12/26/9)"]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["warmup_bars"], len(r.json()["hash"])), (105, 64))
        r = self.api.post("/api/strategies/preview/", {"spec": {"version": 1}}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.json()["spec"]), {"entry", "exit"})

    def test_templates_seeded_and_visible(self):
        names = {s["name"] for s in self.api.get("/api/strategies/").json()["results"] if s["kind"] == "builder"}
        self.assertEqual(names, set(TEMPLATES) | {"Buy and Hold"})  # Phase 3 adds Buy and Hold (migration 0019)

    def test_run_end_to_end_freezes_the_spec(self):
        sid = self.create(TEMPLATES["MACD Signal Cross (12/26/9)"]).json()["id"]
        r = self.api.post("/api/runs/", self.run_body(sid), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["strategy_kind"], "builder")
        self.assertTrue(jobs.work_one("w1"))
        run = BacktestRun.objects.get(id=r.json()["id"])
        self.assertEqual(run.status, "completed", run.error_message)
        self.assertEqual(run.data_manifest["warmup_bars"], 105)
        self.assertEqual(run.strategy_hash, spec.spec_hash(run.strategy_spec))
        self.assertGreater(Trade.objects.filter(run=run).count(), 0)
        frozen = copy.deepcopy(run.strategy_spec)
        self.api.patch(f"/api/strategies/{sid}/", {"spec": sma_cross_spec()}, format="json")
        run.refresh_from_db()
        self.assertEqual(run.strategy_spec, frozen)  # editing the strategy never rewrites history
        # re-running the same frozen run gives the same result (deterministic)
        first = (run.final_value, list(Trade.objects.filter(run=run).values_list("side", "ts", "price")))
        BacktestRun.objects.filter(id=run.id).update(status="queued")
        jobs.work_one("w2")
        run.refresh_from_db()
        self.assertEqual((run.final_value, list(Trade.objects.filter(run=run).values_list("side", "ts", "price"))), first)

    def test_india_delivery_run(self):
        sid = self.create().json()["id"]
        bad = self.api.post("/api/runs/", self.run_body(sid, cost_model="india_delivery"), format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("cost_model", bad.json())
        r = self.api.post("/api/runs/", self.run_body(sid, symbol="reliance.ns", cost_model="india_delivery",
                                                      commission_pct="0"), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual((body["currency"], body["commission_pct"], body["sell_commission_pct"]),
                         ("INR", "0.001186226", "0.001036226"))
        jobs.work_one("w")
        run = BacktestRun.objects.get(id=body["id"])
        self.assertEqual(run.status, "completed", run.error_message)
        buy = Trade.objects.filter(run=run, side="BUY").first()
        sell = Trade.objects.filter(run=run, side="SELL").first()
        self.assertEqual(buy.commission.quantize(D("0.000001")),
                         (buy.price * buy.quantity * D("0.001186226")).quantize(D("0.000001")))
        self.assertEqual(sell.commission.quantize(D("0.000001")),
                         (sell.price * sell.quantity * D("0.001036226")).quantize(D("0.000001")))

    def test_optimization_with_builder_and_india_costs(self):
        sid = self.create().json()["id"]
        r = self.api.post("/api/optimizations/", self.run_body(sid, symbol="RELIANCE.NS", cost_model="india_delivery",
                                                               stop_loss_options=["0.05", "0.1"],
                                                               take_profit_options=["0.2"]), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        job = Experiment.objects.get(id=r.json()["id"])
        while jobs.work_one("w"):
            pass
        runs = list(job.runs.all())
        self.assertEqual(len(runs), 3)  # 2 in-sample + 1 out-of-sample
        for run in runs:
            self.assertEqual(run.status, "completed", run.error_message)
            self.assertEqual((run.cost_model, run.commission_pct, run.sell_commission_pct),
                             ("india_delivery", D("0.001186226"), D("0.001036226")))
            self.assertEqual(run.strategy_spec, spec.validate(sma_cross_spec()))
