"""AI research runs (Phase 5, D-088 to D-095): the agent as a resumable state machine on the job queue.

    queued -> running (one short step) -> queued | waiting (for the backtests it queued) -> ... -> completed | failed

One step = one decision. In explore/refine the agent's action is checked (agent.check) and applied: a `test` or
`search` queues in-sample backtests as one research round (an Experiment of kind "research") and the run waits; the
worker re-queues it when the round's last backtest finishes (on_backtest_finished), so no worker is held while
backtests run. When the agent chooses, or a budget runs out, OUR CODE tests the choice once on the held-out period
(validate) and writes the report with the agent's summary checked against the facts (report).

Model calls happen outside transactions; each step's writes (rounds, runs, state, timeline) happen in one transaction
guarded by the worker's ownership, so a crash between them can't leave half a round.
"""
import logging
import time
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from assist import agent, prompts, providers
from assist.jobs import over_budget
from assist.models import ResearchRun as RR
from assist.models import ResearchStep
from backtester import costs, spec
from backtester.engine import ENGINE_VERSION
from backtester.jobs import SHUTDOWN, frozen_spec
from backtester.models import BacktestRun, Experiment, Strategy
from vault_core.observability import request_id_var

log = logging.getLogger(__name__)
PLACEHOLDER = "AI research candidate"  # hidden built-in, migration 0022
MAX_INVALID_IN_A_ROW = 3


def cfg():
    return settings.RESEARCH


# ---------------------------------------------------------------- reading results

def _metrics(r):
    total = float(r.final_value / r.starting_cash - 1) if r.final_value is not None and r.starting_cash else None
    return {"sharpe_ratio": r.sharpe_ratio, "calmar_ratio": r.calmar_ratio, "total_return": total,
            "max_drawdown": r.max_drawdown, "trade_count": r.trade_count, "exposure": r.exposure,
            "cagr": r.cagr, "buy_and_hold_return": r.buy_and_hold_return}


def _eligible(run, m):
    if m["trade_count"] is None or m["trade_count"] < cfg()["MIN_TRADES"]:
        return False
    return run.max_drawdown is None or (m["max_drawdown"] is not None and m["max_drawdown"] <= run.max_drawdown)


def _score(run, m):
    v = m.get(run.objective)
    return float("-inf") if v is None else v


def candidates(run):
    """The candidates in the run's state, refreshed from their backtests."""
    cands = run.state.get("candidates", [])
    runs = {r.id: r for r in BacktestRun.objects.filter(id__in=[c["run_id"] for c in cands])}
    out = []
    for c in cands:
        r = runs.get(c["run_id"])
        status = r.status if r else "missing"
        m = _metrics(r) if r and status == BacktestRun.COMPLETED else None
        out.append({**c, "status": status, "metrics": m, "eligible": bool(m) and _eligible(run, m),
                    "error": (r.error_message or "")[:120] if r and status == BacktestRun.FAILED else ""})
    return out


def best(run, cands):
    ok = [c for c in cands if c["eligible"]]
    return max(ok, key=lambda c: _score(run, c["metrics"])) if ok else None


# ---------------------------------------------------------------- queueing backtests

def _cost_rates(run):
    buy, sell = costs.rates(run.cost_model, Decimal("0.001") if run.cost_model == costs.FLAT else 0)
    return buy, sell


def _queue_round(run, items, stage, sample, start, end, priority):
    """One research round: an Experiment of kind "research" with one backtest per item (frozen spec each)."""
    placeholder = Strategy.objects.get(name=PLACEHOLDER, is_builtin=True)
    exp = Experiment.objects.create(owner=run.owner, kind=Experiment.RESEARCH, symbol=run.symbol, start_date=start,
                                    end_date=end, starting_cash=run.starting_cash, cost_model=run.cost_model,
                                    config={"research": run.id, "stage": stage}, request_id=run.request_id)
    buy, sell = _cost_rates(run)
    runs = BacktestRun.objects.bulk_create([BacktestRun(
        owner=run.owner, strategy=placeholder, experiment=exp, sample=sample, priority=priority, symbol=run.symbol,
        start_date=start, end_date=end, starting_cash=run.starting_cash, cost_model=run.cost_model,
        commission_pct=buy, sell_commission_pct=sell, request_id=run.request_id, engine_version=ENGINE_VERSION,
        **frozen_spec(item["spec"])) for item in items])
    return exp, runs


def _research_end(run):
    return run.split_date - timedelta(days=1)


# ---------------------------------------------------------------- the step

def _log(run, stage, actor, action, note="", args=None, result=None, ok=True, tokens=(0, 0), ms=None):
    n = run.steps.count()
    ResearchStep.objects.create(run=run, index=n, stage=stage, actor=actor, action=action, args=args, note=note[:600],
                                result=result, ok=ok, tokens_in=tokens[0], tokens_out=tokens[1], latency_ms=ms)


def _owned(run, wid):
    return RR.objects.select_for_update().filter(id=run.id, worker_id=wid, status=RR.RUNNING).first()


def _ctx(run, cands):
    c = cfg()
    steps_left = max(0, c["MAX_STEPS"] - run.steps_used)
    in_sample = [x for x in cands if x["status"] == "completed"]
    return {"goal": run.goal, "symbol": run.symbol, "research_start": run.start_date.isoformat(),
            "research_end": _research_end(run).isoformat(), "objective": run.objective,
            "max_drawdown": run.max_drawdown, "min_trades": c["MIN_TRADES"], "stage": run.stage,
            "steps_left": steps_left, "backtests_left": max(0, c["MAX_BACKTESTS"] - run.backtests_used),
            "candidates": cands, "last_error": run.state.get("last_error"),
            "buy_and_hold": in_sample[0]["metrics"]["buy_and_hold_return"] if in_sample else None,
            "tested_hashes": [spec.spec_hash(x["spec"]) for x in cands], "max_round": c["MAX_CANDIDATES_PER_ROUND"],
            "max_values": c["MAX_SEARCH_VALUES"]}


def _out_of_budget(run, ctx):
    c = cfg()
    if run.steps_used >= c["MAX_STEPS"]:
        return "step budget used up"
    if run.model_calls >= c["MAX_MODEL_CALLS"]:
        return "model-call budget used up"
    if run.tokens_in + run.tokens_out >= c["MAX_TOKENS"]:
        return "token budget used up"
    if ctx["backtests_left"] == 0 and run.stage == RR.EXPLORE and not any(x["status"] == "completed"
                                                                            for x in ctx["candidates"]):
        return "backtest budget used up"
    if ctx["backtests_left"] == 0 and run.stage == RR.REFINE:
        # Choosing is still possible without backtests; let the agent choose once more, then decide for it.
        return "backtest budget used up" if run.state.get("asked_to_choose") else None
    if over_budget():
        return "the deployment's daily AI budget is used up"
    return None


def agent_step(run, wid, provider):
    cands = candidates(run)
    ctx = _ctx(run, cands)
    reason = _out_of_budget(run, ctx)
    if reason:
        return _auto_choose(run, wid, cands, reason)
    if ctx["backtests_left"] == 0 and run.stage == RR.REFINE:
        ctx["last_error"] = {**(ctx["last_error"] or {}), "budget": "no backtests left: choose a candidate now"}
        run.state["asked_to_choose"] = True
    if SHUTDOWN.overdue():
        return _requeue(run, wid)

    system = agent.system_prompt(ctx["max_round"], ctx["max_values"])
    user = agent.state_message(ctx)
    # Process check (D-091): the agent's prompt never carries the held-out period.
    leaked = run.split_date.isoformat() in user or run.end_date.isoformat() in user
    t0 = time.monotonic()
    try:
        completion = provider.complete([{"role": "system", "content": system}, {"role": "user", "content": user}])
    except providers.ProviderError as e:
        log.warning("event=research_provider_error id=%s error=%s", run.id, e)
        with transaction.atomic():
            locked = _owned(run, wid)
            if locked is None:
                return
            locked.state["provider_errors"] = locked.state.get("provider_errors", 0) + 1
            if locked.state["provider_errors"] >= MAX_INVALID_IN_A_ROW:
                return _fail(locked, "The AI service didn't answer. Try again later.")
            locked.status, locked.worker_id = RR.QUEUED, ""
            locked.save(update_fields=["state", "status", "worker_id"])
        return
    ms = int((time.monotonic() - t0) * 1000)
    tokens = (completion.tokens_in, completion.tokens_out)

    with transaction.atomic():
        locked = _owned(run, wid)
        if locked is None:
            return
        locked.model_calls += 1
        locked.tokens_in += tokens[0]
        locked.tokens_out += tokens[1]
        locked.model = getattr(provider, "model", "")
        locked.state["provider_errors"] = 0
        locked.state["holdout_in_prompt"] = locked.state.get("holdout_in_prompt", False) or leaked
        if run.state.get("asked_to_choose"):
            locked.state["asked_to_choose"] = True
        try:
            action = agent.check(agent.parse(completion.text), ctx)
        except agent.ActionError as e:
            locked.state["last_error"] = e.errors
            locked.state["invalid_in_a_row"] = locked.state.get("invalid_in_a_row", 0) + 1
            _log(locked, locked.stage, "agent", "rejected", "The action was rejected and sent back to the agent.",
                 result={"errors": e.errors}, ok=False, tokens=tokens, ms=ms)
            if locked.state["invalid_in_a_row"] >= MAX_INVALID_IN_A_ROW:
                locked.save()
                return _auto_choose(locked, wid, cands, "the agent's last 3 actions were invalid", locked=True)
            locked.status, locked.worker_id = RR.QUEUED, ""
            locked.save()
            return
        locked.state["last_error"], locked.state["invalid_in_a_row"] = None, 0
        locked.steps_used += 1
        _apply(locked, action, tokens, ms)


def _apply(run, action, tokens, ms):
    kind = action["action"]
    if kind in ("test", "search"):
        items = action["candidates"]
        start, end = run.start_date, _research_end(run)
        exp, runs = _queue_round(run, items, run.stage, "in", start, end, BacktestRun.BATCH)
        known = run.state.setdefault("candidates", [])
        ids = []
        for item, r in zip(items, runs):
            cid = f"c{len(known) + 1}"
            known.append({"id": cid, "name": item["name"], "spec": item["spec"], "run_id": r.id,
                          "round": run.state.get("rounds", 0) + 1, "stage": run.stage})
            ids.append(cid)
        run.state["rounds"] = run.state.get("rounds", 0) + 1
        run.backtests_used += len(items)
        run.current_experiment = exp
        run.status, run.worker_id = RR.WAITING, ""
        args = {"candidates": [{"id": i, "name": x["name"]} for i, x in zip(ids, items)]}
        if kind == "search":
            args.update({"of": action["of"], "parameter": action["parameter"], "skipped": action["skipped"]})
        _log(run, run.stage, "agent", kind, action["why"], args=args, tokens=tokens, ms=ms)
    elif kind == "next_stage":
        _log(run, run.stage, "agent", kind, action["why"], tokens=tokens, ms=ms)
        run.stage, run.status, run.worker_id = RR.REFINE, RR.QUEUED, ""
    else:  # choose
        run.state["chosen"] = action["candidate"]
        run.state["chosen_by"] = "agent"
        _log(run, run.stage, "agent", "choose", action["why"], args={"candidate": action["candidate"]},
             tokens=tokens, ms=ms)
        run.stage, run.status, run.worker_id = RR.VALIDATE, RR.QUEUED, ""
    run.save()


def _auto_choose(run, wid, cands, reason, locked=False):
    """A budget ran out (or the agent kept failing): our code picks the best eligible candidate by the objective."""
    with transaction.atomic():
        run = run if locked else _owned(run, wid)
        if run is None:
            return
        pick = best(run, cands)
        if pick is None:
            return _fail(run, f"Stopped: {reason}, and no candidate met the requirements "
                              f"(at least {cfg()['MIN_TRADES']} round trips"
                              + (" and the drawdown constraint" if run.max_drawdown else "") + ").")
        run.state["chosen"], run.state["chosen_by"] = pick["id"], "code"
        _log(run, run.stage, "system", "choose", f"{reason[0].upper()}{reason[1:]}: picked {pick['id']}, the best eligible "
             f"candidate by {agent.OBJECTIVE_LABEL[run.objective]}.", args={"candidate": pick["id"]})
        run.stage, run.status, run.worker_id = RR.VALIDATE, RR.QUEUED, ""
        run.save()


def validate(run, wid):
    """Our code, not the agent: run the chosen candidate once on the held-out period (D-091)."""
    with transaction.atomic():
        run = _owned(run, wid)
        if run is None:
            return
        if run.holdout_experiment_id is not None:  # resumed after the held-out backtest finished
            run.stage, run.status, run.worker_id = RR.REPORT, RR.QUEUED, ""
            run.save()
            return
        chosen = next(c for c in run.state["candidates"] if c["id"] == run.state["chosen"])
        exp, _ = _queue_round(run, [chosen], RR.VALIDATE, "out", run.split_date, run.end_date, BacktestRun.INTERACTIVE)
        run.holdout_experiment = exp  # one-to-one: a second held-out round can't be created
        run.current_experiment = exp
        _log(run, RR.VALIDATE, "system", "holdout", f"Testing {chosen['id']} once on the held-out period "
             f"({run.split_date.isoformat()} to {run.end_date.isoformat()}).", args={"candidate": chosen["id"]})
        run.status, run.worker_id = RR.WAITING, ""
        run.save()


def facts(run, cands):
    chosen = next(c for c in cands if c["id"] == run.state["chosen"])
    hold = run.holdout_experiment.runs.get(sample="out")
    hm = _metrics(hold) if hold.status == BacktestRun.COMPLETED else None
    research = chosen["metrics"]
    return {
        "goal": run.goal, "symbol": run.symbol, "objective": agent.OBJECTIVE_LABEL[run.objective],
        "max_drawdown_constraint": run.max_drawdown,
        "research_period": f"{run.start_date.isoformat()} to {_research_end(run).isoformat()}",
        "held_out_period": f"{run.split_date.isoformat()} to {run.end_date.isoformat()}",
        "candidates_tested": len(cands), "backtests_used": run.backtests_used,
        "chosen": {"id": chosen["id"], "name": chosen["name"], "rules": agent.describe(chosen["spec"]),
                   "chosen_by": run.state.get("chosen_by", "agent")},
        "research_result": {k: research.get(k) for k in ("sharpe_ratio", "calmar_ratio", "total_return", "max_drawdown",
                                                         "trade_count", "buy_and_hold_return")},
        "held_out_result": None if hm is None else {k: hm.get(k) for k in (
            "sharpe_ratio", "calmar_ratio", "total_return", "max_drawdown", "trade_count", "buy_and_hold_return")},
        "held_out_error": None if hm else (hold.error_message or hold.status),
    }


def _template_text(f):
    """Used when the AI's summary isn't available or isn't grounded: plain facts, nothing invented."""
    h = f["held_out_result"]
    if h is None:
        return {"summary": f"{f['chosen']['name']} was chosen from {f['candidates_tested']} candidates, but its "
                           f"held-out backtest didn't complete ({f['held_out_error']}).", "why": "", "caveats": []}
    vs = "beat" if (h["total_return"] or 0) > (h["buy_and_hold_return"] or 0) else "did not beat"
    return {"summary": f"{f['chosen']['name']} was chosen from {f['candidates_tested']} candidates tested on the "
                       f"research period. On the held-out period it {vs} buy and hold.",
            "why": "", "caveats": ["Chosen from several candidates on the same data, so the research result is "
                                   "optimistic; the held-out result is the fairer one."]}


def write_report(run, wid, provider):
    cands = candidates(run)
    f = facts(run, cands)
    text, source, bad = None, "template", []
    tokens, calls = [0, 0], 0
    if provider is not None and not over_budget():
        msgs = [{"role": "system", "content": agent.report_system()},
                {"role": "user", "content": agent.report_message(f)}]
        for attempt in range(2):  # one repair if a number isn't grounded
            try:
                c = provider.complete(msgs)
            except providers.ProviderError as e:
                log.warning("event=research_report_provider_error id=%s error=%s", run.id, e)
                break
            calls += 1
            tokens[0] += c.tokens_in
            tokens[1] += c.tokens_out
            try:
                candidate = agent.check_report(agent.parse(c.text))
            except agent.ActionError:
                bad = ["(not a JSON summary)"]
                msgs = msgs + [{"role": "assistant", "content": c.text},
                               {"role": "user", "content": "Answer with the JSON object described."}]
                continue
            bad = agent.ungrounded_numbers([candidate["summary"], candidate["why"], *candidate["caveats"]], f)
            if not bad and prompts_canary_absent(c.text):
                text, source = candidate, "agent"
                break
            msgs = msgs + [{"role": "assistant", "content": c.text},
                           {"role": "user", "content": "These numbers aren't in the facts: " + ", ".join(bad) +
                            ". Rewrite using only numbers from the facts."}]
    if text is None:
        text = _template_text(f)
    with transaction.atomic():
        run = _owned(run, wid)
        if run is None:
            return
        run.model_calls += calls
        run.tokens_in += tokens[0]
        run.tokens_out += tokens[1]
        h = f["held_out_result"]
        holdout_runs = BacktestRun.objects.filter(experiment__kind=Experiment.RESEARCH,
                                                  experiment__config__research=run.id, sample="out").count()
        candidate_ids = [c["run_id"] for c in cands]
        c = cfg()
        checks = {
            "held_out_tested_once": holdout_runs == 1,
            "agent_never_saw_held_out_period": (
                not run.state.get("holdout_in_prompt")
                and not BacktestRun.objects.filter(id__in=candidate_ids, end_date__gte=run.split_date).exists()),
            "budgets_respected": run.steps_used <= c["MAX_STEPS"] and run.backtests_used <= c["MAX_BACKTESTS"],
            "summary_numbers_grounded": source == "agent",
            "drawdown_constraint_met_held_out": None if run.max_drawdown is None or h is None
            else h["max_drawdown"] is not None and h["max_drawdown"] <= run.max_drawdown,
        }
        run.report = {**f, "text": text, "text_source": source, "ungrounded_numbers": bad, "checks": checks,
                      "beat_buy_and_hold_held_out": None if h is None else
                      (h["total_return"] or 0) > (h["buy_and_hold_return"] or 0)}
        _log(run, RR.REPORT, "system", "report", "Report written" + (" (summary by the agent, numbers checked)."
                                                                     if source == "agent" else
                                                                     " (plain summary: the agent's wasn't usable)."),
             result={"checks": checks}, tokens=tuple(tokens))
        run.stage, run.status, run.worker_id, run.completed_at = RR.DONE, RR.COMPLETED, "", timezone.now()
        run.save()
    log.info("event=research_completed id=%s candidates=%s backtests=%s steps=%s tokens=%s text=%s", run.id,
             len(cands), run.backtests_used, run.steps_used, run.tokens_in + run.tokens_out, source)


def prompts_canary_absent(text):
    return prompts.CANARY not in (text or "")


def _fail(run, message):
    run.status, run.worker_id, run.error_message, run.completed_at = RR.FAILED, "", message[:500], timezone.now()
    _log(run, run.stage, "system", "failed", message, ok=False)
    run.save()
    log.info("event=research_failed id=%s", run.id)


def _requeue(run, wid):
    if RR.objects.filter(id=run.id, worker_id=wid, status=RR.RUNNING).update(
            status=RR.QUEUED, worker_id="", attempts=F("attempts") - 1):
        log.info("event=research_requeued_on_shutdown id=%s", run.id)


def _round_active(run):
    return run.current_experiment_id is not None and BacktestRun.objects.filter(
        experiment_id=run.current_experiment_id, status__in=BacktestRun.ACTIVE).exists()


def step(run, wid):
    if _round_active(run):
        # Re-queued (e.g. after a crash) while its backtests are still running: go back to waiting. The agent must
        # never be asked to decide on unfinished results.
        RR.objects.filter(id=run.id, worker_id=wid, status=RR.RUNNING).update(status=RR.WAITING, worker_id="")
        return
    provider = providers.get_provider()
    if run.stage in (RR.EXPLORE, RR.REFINE):
        if provider is None:
            with transaction.atomic():
                locked = _owned(run, wid)
                if locked:
                    _fail(locked, "AI assistance isn't configured on this deployment.")
            return
        agent_step(run, wid, provider)
    elif run.stage == RR.VALIDATE:
        validate(run, wid)
    elif run.stage == RR.REPORT:
        write_report(run, wid, provider)


# ---------------------------------------------------------------- queue mechanics

def claim(wid):
    with transaction.atomic():
        run = RR.objects.select_for_update(skip_locked=True).filter(status=RR.QUEUED).order_by("id").first()
        if run is None:
            return None
        run.status, run.worker_id, run.attempts, run.started_at = RR.RUNNING, wid, run.attempts + 1, timezone.now()
        run.save(update_fields=["status", "worker_id", "attempts", "started_at"])
        return run


def work_one(wid):
    if SHUTDOWN.requested:
        return False
    run = claim(wid)
    if run is None:
        return False
    token = request_id_var.set(run.request_id or None)
    try:
        try:
            step(run, wid)
        except Exception:
            log.exception("event=research_crashed id=%s", run.id)
            with transaction.atomic():
                locked = _owned(run, wid)
                if locked:
                    _fail(locked, "Internal error during research.")
    finally:
        request_id_var.reset(token)
    return True


def _wake(exp_ids):
    """Re-queue research runs whose round has no active backtests left."""
    for r in RR.objects.filter(status=RR.WAITING, current_experiment_id__in=exp_ids):
        if not BacktestRun.objects.filter(experiment_id=r.current_experiment_id, status__in=BacktestRun.ACTIVE).exists():
            if RR.objects.filter(id=r.id, status=RR.WAITING).update(status=RR.QUEUED):
                # A round finishing is progress: the attempts budget is for crashes, not for waiting.
                RR.objects.filter(id=r.id).update(attempts=0)


def on_backtest_finished(run):
    """Called by the worker after each backtest (backtester.jobs.work_one)."""
    if run.experiment_id and Experiment.objects.filter(id=run.experiment_id, kind=Experiment.RESEARCH).exists():
        _wake([run.experiment_id])


def recover():
    """Worker sweep: wake runs whose round finished some other way (e.g. a backtest failed by stale recovery), and
    re-queue (or fail) steps whose worker died mid-step. Steps are small and their writes atomic, so re-running is safe."""
    _wake(RR.objects.filter(status=RR.WAITING).values_list("current_experiment_id", flat=True))
    cutoff = timezone.now() - timedelta(seconds=cfg()["STALE_AFTER_S"])
    stale = RR.objects.filter(status=RR.RUNNING, started_at__lt=cutoff)
    failed = stale.filter(attempts__gte=cfg()["MAX_ATTEMPTS"]).update(
        status=RR.FAILED, worker_id="", error_message="The research worker stopped responding.",
        completed_at=timezone.now())
    requeued = stale.filter(attempts__lt=cfg()["MAX_ATTEMPTS"]).update(status=RR.QUEUED, worker_id="")
    if failed or requeued:
        log.warning("event=research_stale_recovered requeued=%s failed=%s", requeued, failed)
