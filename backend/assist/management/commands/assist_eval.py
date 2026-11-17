"""Evaluation of "describe a strategy → spec" (D-082).

Live (needs GROQ_API_KEY; uses the provider's free quota, so it paces itself and retries on rate limits):
    python manage.py assist_eval --model openai/gpt-oss-120b --variant full --record assist/evals/recordings/x.json
Replay a recording (no network; what CI does):
    python manage.py assist_eval --replay assist/evals/recordings/x.json
"""
import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from assist import prompts, providers
from assist.evals import runner


class Command(BaseCommand):
    help = "Run the AI strategy evaluation live or from a recording."

    def add_arguments(self, parser):
        parser.add_argument("--model", default=None, help="provider model (default: AI_MODEL)")
        parser.add_argument("--variant", default="full", choices=prompts.VARIANTS)
        parser.add_argument("--repairs", type=int, default=2, help="max repair rounds")
        parser.add_argument("--reasoning-effort", default=None, help="low|medium|high (reasoning models only)")
        parser.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
        parser.add_argument("--pause", type=float, default=0.0, help="seconds between cases (rate limits)")
        parser.add_argument("--record", default="", help="write the recording (answers, results, summary) here")
        parser.add_argument("--replay", default="", help="replay this recording instead of calling the provider")
        parser.add_argument("--reuse", action="store_true",
                            help="with --record: answer messages already in that recording from it; call the model "
                                 "only for new ones (after a change that affects a few cases)")

    def handle(self, *args, **o):
        ids = {x.strip() for x in o["cases"].split(",") if x.strip()} or None
        if o["replay"]:
            data = json.loads(Path(o["replay"]).read_text(encoding="utf-8"))
            meta = data["meta"]
            provider = providers.ReplayProvider(data["records"], meta["model"])
            recorded_ids = set(meta["cases"]) if meta.get("cases") else None
            results, summary = runner.run(provider, meta["variant"], meta["repairs"], ids or recorded_ids)
            self._print(meta, summary, results)
            if not ids and summary != data["summary"]:
                raise CommandError("replayed summary differs from the recorded one")
            return
        key = settings.AI["GROQ_API_KEY"]
        if not key:
            raise CommandError("GROQ_API_KEY is not set")
        model = o["model"] or settings.AI["MODEL"]
        effort = settings.AI["REASONING_EFFORT"] if o["reasoning_effort"] is None else o["reasoning_effort"]
        # Evaluations wait out rate limits instead of failing: free-tier tokens-per-minute limits are low.
        live = providers.GroqProvider(key, model, timeout_s=60, max_tokens=settings.AI["MAX_OUTPUT_TOKENS"],
                                      reasoning_effort=effort, retries=8, max_wait_s=60)
        reuse, meta_before = {}, None
        if o["reuse"] and o["record"] and Path(o["record"]).exists():
            before = json.loads(Path(o["record"]).read_text(encoding="utf-8"))
            reuse, meta_before = before["records"], before["meta"]
            if (meta_before["model"], meta_before["variant"]) != (model, o["variant"]):
                raise CommandError("--reuse needs the same model and variant as the existing recording")
        provider = providers.RecordingProvider(live, reuse=reuse)
        meta = {"provider": "groq", "model": model, "variant": o["variant"], "repairs": o["repairs"],
                "reasoning_effort": effort, "prompt_version": prompts.PROMPT_VERSION, "date": date.today().isoformat()}
        if meta_before:
            meta["first_recorded"] = meta_before.get("first_recorded", meta_before["date"])
        if ids:
            meta["cases"] = sorted(ids)  # a subset run (e.g. a latency sample); replays use the same cases

        def progress(r):
            mark = "PASS" if r["passed"] else "FAIL"
            self.stdout.write(f"{r['id']:>4} {mark} {r['kind']:<11} calls={r['calls']} ms={r['ms']}")
            self.stdout.flush()

        results, summary = runner.run(provider, o["variant"], o["repairs"], ids, o["pause"], progress)
        self._print(meta, summary, results)
        self.stdout.write(f"model calls: {provider.live_calls} live, {provider.reused} reused from the recording; "
                          f"waited {getattr(live, 'waited_s', 0):.0f} s for rate limits")
        if o["record"]:
            path = Path(o["record"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"meta": meta, "summary": summary, "results": results,
                                        "records": provider.records}, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            self.stdout.write(f"recorded to {path}")

    def _print(self, meta, summary, results):
        self.stdout.write(json.dumps({"meta": meta, "summary": summary}, indent=1, ensure_ascii=False))
        failed = [r for r in results if not r["passed"]]
        for r in failed:
            detail = r.get("error") or r.get("reason") or r.get("errors") or f"agreement={r.get('agreement')}"
            self.stdout.write(f"FAIL {r['id']} expected={r['expect']} got={r['kind']}: {detail}")
