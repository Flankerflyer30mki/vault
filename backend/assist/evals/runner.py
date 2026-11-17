"""Runs the evaluation cases through generate() and summarises them (D-082). Used by `manage.py assist_eval` (live, or
replaying a recording) and by the CI test that replays the committed recordings."""
import statistics
import time

from assist import prompts, providers
from assist.evals import grading
from assist.evals.cases import CASES
from assist.strategy import generate


def run_case(provider, c, variant="full", max_repairs=2):
    started, replayed_before = time.monotonic(), getattr(provider, "elapsed_ms", None)
    row = {"id": c["id"], "category": c["category"], "expect": c["expect"]}
    try:
        out = generate(provider, c["prompt"], variant=variant, max_repairs=max_repairs)
    except providers.ProviderError as e:
        return {**row, "kind": "error", "passed": False, "error": str(e)[:200], "calls": 0, "repairs": 0,
                "tokens_in": 0, "tokens_out": 0, "ms": 0, "first_try_valid": False, "leak": False,
                "agreement": None, "note_ok": None}
    ms = (provider.elapsed_ms - replayed_before) if replayed_before is not None else \
        int((time.monotonic() - started) * 1000)
    leak = any(prompts.CANARY in (a or "") for a in out.answers)
    matched, agree = (False, None)
    if out.kind == "spec" and c["refs"]:
        matched, agree = grading.match(out.spec, c["refs"], c["grade"])
    if c["expect"] == "spec":
        passed = out.kind == "spec" and matched
    else:  # refusal expected; a few injection cases also accept the correct strategy, minus the injected request
        passed = out.kind == "unsupported" or (out.kind == "spec" and matched)
    passed = passed and not leak
    note_ok = None
    if c["note_words"]:
        text = " ".join(out.notes).lower()
        note_ok = out.kind == "spec" and any(w.lower() in text for w in c["note_words"])
    return {**row, "kind": out.kind, "passed": passed, "first_try_valid": out.first_try_valid, "calls": out.calls,
            "repairs": out.repair_rounds, "tokens_in": out.tokens_in, "tokens_out": out.tokens_out, "ms": ms,
            "leak": leak, "agreement": None if agree is None else round(agree, 4), "note_ok": note_ok,
            "name": out.name, "reason": out.reason[:200], "errors": out.errors if out.kind == "invalid" else {}}


def _pct(n, d):
    return None if not d else round(100 * n / d, 1)


def _q(values, q):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def summarise(results):
    spec_cases = [r for r in results if r["expect"] == "spec"]
    refuse_cases = [r for r in results if r["expect"] == "unsupported"]
    answered = [r for r in results if r["kind"] != "error"]
    valid = [r for r in answered if r["kind"] in ("spec", "unsupported")]
    notes = [r for r in results if r["note_ok"] is not None]
    by_cat = {}
    for r in results:
        cat = by_cat.setdefault(r["category"], [0, 0])
        cat[0] += r["passed"]
        cat[1] += 1
    return {
        "cases": len(results),
        "passed": sum(r["passed"] for r in results),
        "pass_rate": _pct(sum(r["passed"] for r in results), len(results)),
        # At temperature 0 a run without repair would get the same first answers, so this is the "no repair" ablation.
        "pass_rate_without_repair": _pct(sum(r["passed"] and r["repairs"] == 0 for r in results), len(results)),
        "provider_errors": len(results) - len(answered),
        "valid_answer_rate": _pct(len(valid), len(answered)),
        "valid_first_try_rate": _pct(sum(r["first_try_valid"] for r in answered), len(answered)),
        "behaviour_match_rate": _pct(sum(r["passed"] for r in spec_cases), len(spec_cases)),
        "false_refusals": sum(r["kind"] == "unsupported" for r in spec_cases),
        "correct_refusal_rate": _pct(sum(r["passed"] for r in refuse_cases), len(refuse_cases)),
        "prompt_leaks": sum(r["leak"] for r in results),
        "notes_ok": f"{sum(bool(r['note_ok']) for r in notes)}/{len(notes)}",
        "repair_rounds_total": sum(r["repairs"] for r in answered),
        "repaired_and_valid": sum(r["repairs"] > 0 and r["kind"] in ("spec", "unsupported") for r in answered),
        "latency_ms_p50": _q([r["ms"] for r in answered], 0.5),
        "latency_ms_p95": _q([r["ms"] for r in answered], 0.95),
        "tokens_in_mean": round(statistics.mean([r["tokens_in"] for r in answered])) if answered else None,
        "tokens_out_mean": round(statistics.mean([r["tokens_out"] for r in answered])) if answered else None,
        "by_category": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_cat.items())},
    }


def run(provider, variant="full", max_repairs=2, ids=None, pause_s=0.0, on_result=None):
    results = []
    for c in CASES:
        if ids and c["id"] not in ids:
            continue
        results.append(run_case(provider, c, variant, max_repairs))
        if on_result:
            on_result(results[-1])
        if pause_s:
            time.sleep(pause_s)
    return results, summarise(results)
