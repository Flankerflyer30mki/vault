"""Phase 5: the AI research agent. A scripted fake model drives real research runs end to end (real backtests on fixture
bars, the worker's wait/resume, the single held-out test, the report), and the pure checks are tested directly.
No test reaches the network. Run: DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test assist.test_research"""
import json
from datetime import date, timedelta
from unittest import mock

from django.core.cache import cache as django_cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from assist import agent, providers, research
from assist.models import ResearchRun as RR
from assist.tests import AI_ON
from backtester import jobs as bt_jobs
from backtester import spec
from backtester.models import BacktestRun, Bar, Experiment, Strategy, SymbolCoverage
from backtester.test_builder import FIXTURE_START, bars_for

RESEARCH = {"MAX_STEPS": 8, "MAX_MODEL_CALLS": 14, "MAX_BACKTESTS": 40, "MAX_TOKENS": 40_000,
            "MAX_CANDIDATES_PER_ROUND": 6, "MAX_SEARCH_VALUES": 6, "MIN_TRADES": 3, "MIN_DAYS": 365,
            "STALE_AFTER_S": 300, "MAX_ATTEMPTS": 3}


def ind(name, output="value", **params):
    return {"ind": name, "params": params, "output": output}


def S(entry, exit_, emode="all", xmode="any"):
    return {"version": 1, "entry": {emode: entry}, "exit": {xmode: exit_}}


SMA_CROSS = S([{"left": ind("sma", period=5), "op": "crosses_above", "right": ind("sma", period=20)}],
              [{"left": ind("sma", period=5), "op": "crosses_below", "right": ind("sma", period=20)}])
RSI_DIP = S([{"left": ind("rsi", period=14), "op": "<", "right": {"const": 35}}],
            [{"left": ind("rsi", period=14), "op": ">", "right": {"const": 60}}])
TEST = {"action": "test", "why": "Two different families to start: trend and mean reversion.",
        "candidates": [{"name": "SMA 5/20 cross", "spec": SMA_CROSS}, {"name": "RSI dip", "spec": RSI_DIP}]}
NEXT = {"action": "next_stage", "why": "The crossover trades often enough; refine it."}
SEARCH = {"action": "search", "why": "Check how sensitive the cross is to the fast average.", "candidate": "c1",
          "parameter": "sma(5).period", "values": [3, 8, 10]}
CHOOSE = {"action": "choose", "why": "The original 5/20 is as good as its neighbours, so it isn't a lucky setting.",
          "candidate": "c1"}
REPORT = {"summary": "The agent compared trend and mean-reversion rules and chose the moving-average cross. It was "
                     "tested once on the held-out period, next to buy and hold.",
          "why": "It was the best eligible candidate and its neighbours behaved alike.",
          "caveats": ["Chosen from several candidates on the same data."]}


def seed(symbol="AAPL"):
    Bar.objects.bulk_create(bars_for(symbol))
    SymbolCoverage.objects.create(symbol=symbol, start=FIXTURE_START, until=date(2025, 1, 1),
                                  fetched_at=timezone.now())


def drain(limit=200):
    """The worker loop without sleeping: research steps and backtests until nothing is left."""
    for _ in range(limit):
        if not (research.work_one("w") or bt_jobs.work_one("w")):
            return
    raise AssertionError("work never ran out")


@override_settings(AI={**AI_ON, "DAILY_TOKEN_BUDGET": 1_000_000}, RESEARCH=RESEARCH)
class ResearchRunTests(TestCase):
    def setUp(self):
        django_cache.clear()
        seed()
        self.user = User.objects.create_user("agent@example.com", email_verified=True)
        self.api = APIClient()
        self.api.force_login(self.user)
        no_network = mock.patch("backtester.data_fetch.download", side_effect=AssertionError("network"))
        no_network.start()
        self.addCleanup(no_network.stop)

    def start(self, answers, **extra):
        self.fake = providers.FakeProvider(answers, tokens=(2000, 300))
        p = mock.patch("assist.research.providers.get_provider", return_value=self.fake)
        p.start()
        self.addCleanup(p.stop)
        body = {"goal": "A simple trend strategy for AAPL that beats buy and hold.", "symbol": "AAPL",
                "start_date": "2023-05-01", "end_date": "2024-12-31", **extra}
        r = self.api.post("/api/research/", body, format="json", HTTP_X_REQUEST_ID="research-click-1")
        self.assertEqual(r.status_code, 201, r.data)
        return RR.objects.get(id=r.data["id"])

    def test_full_run(self):
        run = self.start([TEST, NEXT, SEARCH, CHOOSE, REPORT])
        self.assertEqual(run.split_date, date(2023, 5, 1) + timedelta(days=round(610 * 0.7)))
        self.assertEqual(self.api.get("/api/dashboard/").data["quota"]["usage"]["active_jobs"], 1)
        drain()
        run.refresh_from_db()
        self.assertEqual((run.status, run.stage), ("completed", "done"), run.error_message)
        self.assertEqual((run.steps_used, run.backtests_used, run.model_calls), (4, 5, 5))
        self.assertEqual((run.tokens_in, run.tokens_out), (10_000, 1_500))

        # Every candidate ran on the research period only; the held-out period ran exactly once, for the choice.
        cands = research.candidates(run)
        self.assertEqual([c["id"] for c in cands], ["c1", "c2", "c3", "c4", "c5"])
        cand_runs = BacktestRun.objects.filter(id__in=[c["run_id"] for c in cands])
        self.assertTrue(all(r.end_date < run.split_date and r.start_date == run.start_date for r in cand_runs))
        held = BacktestRun.objects.get(experiment=run.holdout_experiment)
        self.assertEqual((held.sample, held.start_date, held.end_date, held.status),
                         ("out", run.split_date, run.end_date, "completed"))
        self.assertEqual(held.strategy_spec, spec.validate(SMA_CROSS))
        self.assertEqual(held.request_id, "research-click-1")
        # The agent's prompts never mentioned the held-out dates.
        sent = json.dumps(self.fake.calls[:4])
        self.assertNotIn(run.split_date.isoformat(), sent)
        self.assertNotIn(run.end_date.isoformat(), sent)

        rep = run.report
        self.assertEqual(rep["checks"], {"held_out_tested_once": True, "agent_never_saw_held_out_period": True,
                                         "budgets_respected": True, "summary_numbers_grounded": True,
                                         "drawdown_constraint_met_held_out": None})
        self.assertEqual((rep["text_source"], rep["candidates_tested"], rep["chosen"]["id"]), ("agent", 5, "c1"))
        self.assertEqual(rep["held_out_result"]["total_return"], float(held.final_value / held.starting_cash - 1))
        self.assertEqual(rep["held_out_result"]["buy_and_hold_return"], held.buy_and_hold_return)

        detail = self.api.get(f"/api/research/{run.id}/").data
        self.assertEqual([s["action"] for s in detail["steps"]],
                         ["test", "next_stage", "search", "choose", "holdout", "report"])
        self.assertEqual(detail["steps"][0]["note"], TEST["why"])
        self.assertEqual(detail["steps"][2]["args"]["parameter"], "sma(5).period")
        self.assertEqual(len(detail["candidates"]), 5)
        self.assertIn("crosses_above(ind.sma(5), ind.sma(20))", detail["candidates"][0]["rules"])

        # Research rounds stay out of experiment lists, the dashboard and the experiments quota.
        self.assertEqual(self.api.get("/api/experiments/").data["count"] if isinstance(
            self.api.get("/api/experiments/").data, dict) else len(self.api.get("/api/experiments/").data), 0)
        some_round = Experiment.objects.filter(kind=Experiment.RESEARCH).first()
        self.assertEqual(self.api.get(f"/api/experiments/{some_round.id}/").status_code, 404)
        usage = self.api.get("/api/dashboard/").data["quota"]["usage"]
        self.assertEqual((usage["experiments_per_day"], usage["runs_per_day"], usage["research_per_day"],
                          usage["active_jobs"]), (0, 0, 1, 0))

    def test_rejected_actions_go_back_with_their_errors(self):
        bad = {"action": "test", "why": "x", "candidates": [
            {"name": "bad", "spec": S([{"left": ind("sma", period=500), "op": ">", "right": {"price": "close"}}],
                                      [{"left": ind("sma", period=5), "op": "<", "right": {"price": "close"}}])}]}
        run = self.start([{"action": "choose", "candidate": "c1"}, bad, TEST, NEXT, CHOOSE, REPORT])
        drain()
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        second, third = self.fake.calls[1][1]["content"], self.fake.calls[2][1]["content"]
        self.assertIn("action: must be one of test, next_stage in the explore stage", second)
        self.assertIn("candidates[0].spec.entry.all[0].left.params.period: must be a whole number between 2 and 200",
                      third)
        steps = list(run.steps.values_list("action", "ok"))
        self.assertEqual(steps[:3], [("rejected", False), ("rejected", False), ("test", True)])
        self.assertEqual(run.steps_used, 3)  # rejected answers cost model calls, not steps
        self.assertEqual(run.model_calls, 6)

    def test_budget_runs_out_and_code_chooses(self):
        with override_settings(RESEARCH={**RESEARCH, "MAX_STEPS": 1}):
            run = self.start([TEST, REPORT])
            drain()
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        auto = run.steps.get(action="choose")
        self.assertEqual(auto.actor, "system")
        self.assertIn("Step budget used up", auto.note)
        cands = research.candidates(run)
        self.assertEqual(run.report["chosen"]["id"], research.best(run, cands)["id"])
        self.assertEqual(run.report["chosen"]["chosen_by"], "code")
        self.assertEqual(len(self.fake.calls), 2)  # one decision, then the report: no extra model calls

    def test_three_invalid_answers_with_nothing_tested_fail_cleanly(self):
        run = self.start(["not json"])
        drain()
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIn("no candidate met the requirements", run.error_message)
        self.assertEqual(run.model_calls, 3)
        self.assertFalse(Experiment.objects.filter(kind=Experiment.RESEARCH).exists())

    def test_drawdown_constraint_and_objective(self):
        run = self.start([TEST, NEXT, CHOOSE, REPORT], max_drawdown_pct=1, objective="calmar_ratio")
        drain()
        run.refresh_from_db()
        # Nothing trades within a 1% drawdown here, so the agent's choice is refused and code finds nothing eligible.
        self.assertEqual(run.status, "failed")
        self.assertIn("drawdown constraint", run.error_message)
        self.assertEqual(run.max_drawdown, 0.01)
        self.assertTrue(any("isn't eligible" in s.result["errors"].get("candidate", "")
                            for s in run.steps.filter(action="rejected")))

    def test_an_invented_number_falls_back_to_a_plain_report(self):
        made_up = {**REPORT, "summary": "It returned 987.6% with a Sharpe of 9.99."}
        run = self.start([TEST, NEXT, CHOOSE, made_up, made_up])
        drain()
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.report["text_source"], "template")
        self.assertFalse(run.report["checks"]["summary_numbers_grounded"])
        self.assertIn("987.6", run.report["ungrounded_numbers"])
        self.assertIn("These numbers aren't in the facts: 987.6, 9.99", self.fake.calls[-1][-1]["content"])
        self.assertIn("was chosen from 2 candidates", run.report["text"]["summary"])

    def test_waiting_doesnt_hold_a_worker_and_restarts_resume(self):
        run = self.start([TEST, NEXT, CHOOSE, REPORT])
        self.assertTrue(research.work_one("w"))
        run.refresh_from_db()
        self.assertEqual(run.status, "waiting")
        self.assertFalse(research.work_one("w"))  # nothing to do for research while its backtests run
        # A worker that died mid-step: stale recovery puts the step back; it runs again from saved state.
        RR.objects.filter(id=run.id).update(status=RR.RUNNING, worker_id="dead",
                                            started_at=timezone.now() - timedelta(hours=1))
        research.recover()
        run.refresh_from_db()
        self.assertEqual(run.status, "queued")
        self.assertTrue(research.work_one("w"))
        run.refresh_from_db()
        self.assertEqual(run.status, "waiting")  # its round isn't finished: back to waiting, no model call
        self.assertEqual(len(self.fake.calls), 1)
        drain()
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(BacktestRun.objects.filter(experiment=run.holdout_experiment).count(), 1)

    def test_shutdown_requeues_without_using_an_attempt(self):
        run = self.start([TEST])
        self.addCleanup(bt_jobs.SHUTDOWN.reset)
        claimed = research.claim("w")
        bt_jobs.SHUTDOWN.request(0)
        research.step(claimed, "w")
        run.refresh_from_db()
        self.assertEqual((run.status, run.attempts, run.model_calls), ("queued", 0, 0))

    def test_api_rules(self):
        p = mock.patch("assist.research.providers.get_provider", return_value=providers.FakeProvider([TEST]))
        p.start()
        self.addCleanup(p.stop)
        body = {"goal": "Find me a robust trend strategy.", "symbol": "AAPL", "start_date": "2023-05-01",
                "end_date": "2024-12-31"}
        short = self.api.post("/api/research/", {**body, "start_date": "2024-06-01"}, format="json")
        self.assertEqual(short.status_code, 400)
        self.assertIn("at least 365 days", short.data["end_date"][0])
        india = self.api.post("/api/research/", {**body, "cost_model": "india_delivery"}, format="json")
        self.assertEqual(india.status_code, 400)
        first = self.api.post("/api/research/", body, format="json")
        self.assertEqual(first.status_code, 201)
        again = self.api.post("/api/research/", body, format="json")
        self.assertEqual(again.status_code, 429)
        self.assertIn("still going", again.data["detail"])
        other = APIClient()
        other.force_login(User.objects.create_user("other@example.com", email_verified=True))
        self.assertEqual(other.get(f"/api/research/{first.data['id']}/").status_code, 404)
        guest = APIClient()
        guest.force_login(User.objects.create_user("guest@example.com", is_guest=True))
        r = guest.post("/api/research/", body, format="json")
        self.assertEqual(r.status_code, 429)
        self.assertIn("isn't available for guest", r.data["detail"])
        with override_settings(AI={**AI_ON, "GROQ_API_KEY": ""}):
            self.assertEqual(self.api.post("/api/research/", body, format="json").status_code, 503)

    def test_the_daily_ai_budget_covers_research(self):
        with override_settings(AI={**AI_ON, "DAILY_TOKEN_BUDGET": 4_000}):
            run = self.start([TEST, NEXT, CHOOSE, REPORT])
            drain()
        run.refresh_from_db()
        # One decision (2,300 tokens) leaves 1,700 of 4,000; the next exceeds the deployment's budget, so code chooses
        # and the report is written without the AI.
        self.assertEqual(run.status, "completed")
        self.assertIn("daily AI budget", run.steps.get(action="choose").note)
        self.assertEqual(run.report["text_source"], "template")

    def test_the_placeholder_strategy_is_hidden_and_not_runnable(self):
        hidden = Strategy.objects.get(name=research.PLACEHOLDER)
        self.assertTrue(hidden.is_hidden and hidden.is_builtin)
        names = [s["name"] for s in self.api.get("/api/strategies/").data["results"]] \
            if isinstance(self.api.get("/api/strategies/").data, dict) else \
            [s["name"] for s in self.api.get("/api/strategies/").data]
        self.assertNotIn(research.PLACEHOLDER, names)
        r = self.api.post("/api/runs/", {"strategy": hidden.id, "symbol": "AAPL", "start_date": "2024-01-02",
                                         "end_date": "2024-06-01"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.api.get(f"/api/strategies/{hidden.id}/").status_code, 404)


class AgentCheckTests(SimpleTestCase):
    def ctx(self, stage="explore", cands=(), backtests_left=40):
        return {"stage": stage, "backtests_left": backtests_left, "max_round": 6, "max_values": 6,
                "candidates": list(cands), "tested_hashes": [spec.spec_hash(spec.validate(c["spec"])) for c in cands]}

    def done(self, cid="c1", s=SMA_CROSS, eligible=True):
        return {"id": cid, "name": "x", "spec": spec.validate(s), "status": "completed", "eligible": eligible,
                "metrics": {}}

    def errors(self, obj, ctx):
        with self.assertRaises(agent.ActionError) as e:
            agent.check(obj, ctx)
        return e.exception.errors

    def test_actions_are_limited_by_stage(self):
        self.assertIn("action", self.errors({"action": "choose", "candidate": "c1"}, self.ctx("explore")))
        self.assertIn("action", self.errors({"action": "next_stage"}, self.ctx("refine", [self.done()])))
        self.assertIn("action", self.errors({"action": "save_strategy"}, self.ctx("refine")))
        self.assertEqual(self.errors({"action": "next_stage"}, self.ctx()),
                         {"action": "test at least one candidate before moving on"})

    def test_test_action(self):
        ok = agent.check(TEST, self.ctx())
        self.assertEqual([c["name"] for c in ok["candidates"]], ["SMA 5/20 cross", "RSI dip"])
        self.assertEqual(ok["candidates"][0]["spec"], spec.validate(SMA_CROSS))
        dup = self.errors(TEST, self.ctx(cands=[self.done()]))
        self.assertIn("already tested", dup["candidates[0].spec"])
        self.assertIn("at most 1", self.errors(TEST, self.ctx(backtests_left=1))["candidates"])
        self.assertIn("candidates", self.errors({"action": "test", "candidates": []}, self.ctx()))
        bad = {"action": "test", "candidates": [{"name": "same", "spec": S(
            [{"left": ind("sma", period=20), "op": ">", "right": ind("sma", period=20)}],
            [{"left": {"price": "close"}, "op": "<", "right": {"const": 1}}])}]}
        self.assertEqual(self.errors(bad, self.ctx()),
                         {"candidates[0].spec.entry.all[0]": "compares something with itself: the two sides must differ"})

    def test_search_action(self):
        ctx = self.ctx("refine", [self.done()])
        out = agent.check({**SEARCH, "values": [3, 5, 300, 8]}, ctx)
        self.assertEqual(len(out["candidates"]), 2)  # 3 and 8; 5 is c1 itself, 300 is out of range
        self.assertEqual({x["value"] for x in out["skipped"]}, {5, 300})
        self.assertIn("must be one of sma(5).period, sma(20).period",
                      self.errors({**SEARCH, "parameter": "rsi(14).period"}, ctx)["parameter"])
        self.assertIn("at most 6", self.errors({**SEARCH, "values": list(range(2, 10))}, ctx)["values"])
        self.assertIn("none of these values", self.errors({**SEARCH, "values": [5, 500]}, ctx)["values"])
        self.assertIn("values", self.errors({**SEARCH, "values": ["3"]}, ctx))

    def test_choose_action(self):
        ctx = self.ctx("refine", [self.done(), self.done("c2", RSI_DIP, eligible=False)])
        self.assertEqual(agent.check(CHOOSE, ctx)["candidate"], "c1")
        self.assertIn("isn't eligible", self.errors({**CHOOSE, "candidate": "c2"}, ctx)["candidate"])
        self.assertIn("tested candidate", self.errors({**CHOOSE, "candidate": "c9"}, ctx)["candidate"])

    def test_prompt_contents(self):
        system = agent.system_prompt(6, 6)
        self.assertIn('"donchian"', system)  # the same catalog as the assistant
        self.assertIn('"action": "search"', system)
        ctx = {"goal": "trend please", "symbol": "AAPL", "research_start": "2018-01-01", "research_end": "2022-12-31",
               "objective": "sharpe_ratio", "max_drawdown": 0.25, "min_trades": 3, "stage": "refine", "steps_left": 4,
               "backtests_left": 12, "candidates": [{**self.done(), "metrics": {
                   "sharpe_ratio": 0.81234, "calmar_ratio": None, "total_return": 0.3456, "max_drawdown": 0.18,
                   "trade_count": 12, "exposure": 0.55, "buy_and_hold_return": 0.5}}],
               "buy_and_hold": 0.5, "last_error": {"candidate": "c9 isn't a candidate"}}
        msg = agent.state_message(ctx)
        for part in ("<<<\ntrend please\n>>>", "max drawdown at most 25%", "Budget left: 4 steps, 12 backtests",
                     "c1 | x | 0.81 | n/a | 34.6% | 18.0% | 12 | 55.0% | yes", "sma(5).period (int 2-200)",
                     "- candidate: c9 isn't a candidate", "total return 50.0%"):
            self.assertIn(part, msg)


class GroundingTests(SimpleTestCase):
    FACTS = {"chosen": {"name": "EMA 20/50", "rules": "BUY when all: crosses_above(ind.ema(20), ind.ema(50))"},
             "research_period": "2018-01-01 to 2022-12-31",
             "held_out_result": {"total_return": 0.1234, "sharpe_ratio": 0.876, "max_drawdown": 0.2},
             "candidates_tested": 7}

    def test_numbers_from_the_facts_pass_in_any_reasonable_form(self):
        text = ["EMA 20/50 returned 12.3% (12.34%, 0.12) with a Sharpe of 0.88 and a 20% drawdown, from 7 candidates "
                "over 2018 to 2022."]
        self.assertEqual(agent.ungrounded_numbers(text, self.FACTS), [])

    def test_invented_numbers_are_caught(self):
        self.assertEqual(agent.ungrounded_numbers(["Sharpe 1.5, return 40%, 7 candidates"], self.FACTS),
                         ["1.5", "40"])
