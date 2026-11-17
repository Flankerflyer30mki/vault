"""AI requests as queued jobs (D-078). The worker loop calls work_one() before backtests: AI requests are interactive
and short. Same mechanics as backtester.jobs: SKIP LOCKED claim, updates conditional on worker_id, request IDs in logs,
graceful shutdown. A request is never retried automatically: the user sees the failure and can ask again.
"""
import hashlib
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from assist import prompts, providers, strategy
from assist.models import AssistRequest as A
from backtester.jobs import SHUTDOWN
from vault_core.observability import request_id_var

log = logging.getLogger(__name__)

NOT_CONFIGURED = "AI assistance isn't configured on this deployment. You can still build the strategy in the form."
OVER_BUDGET = "Today's AI budget is used up. Try again tomorrow, or build the strategy in the form."
PROVIDER_DOWN = "The AI service didn't answer (busy or unavailable). Try again in a minute."
NOT_VALID = ("The AI couldn't produce a valid strategy for that description. Try saying it differently, or build it "
             "in the form.")
TIMED_OUT = "The AI request timed out. Try again."


def normalise(text):
    return " ".join(text.lower().split())


def prompt_hash(text, model):
    return hashlib.sha256(f"{prompts.PROMPT_VERSION}|{model}|{normalise(text)}".encode()).hexdigest()


def cached_answer(h):
    """An earlier completed answer to the same description (same prompt version and model) from the last 7 days.
    Only the description determines the answer, so reusing it across users reveals nothing about anyone."""
    since = timezone.now() - timedelta(days=settings.AI["CACHE_DAYS"])
    return (A.objects.filter(prompt_hash=h, status=A.COMPLETED, outcome__in=(A.SPEC, A.UNSUPPORTED), cached=False,
                             created_at__gte=since).order_by("-id").first())


def tokens_today():
    """Assistant requests plus research steps: one budget for all AI use (D-081, D-093)."""
    from assist.models import ResearchStep
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total = F("tokens_in") + F("tokens_out")
    return ((A.objects.filter(created_at__gte=start).aggregate(t=Sum(total))["t"] or 0)
            + (ResearchStep.objects.filter(created_at__gte=start).aggregate(t=Sum(total))["t"] or 0))


def over_budget():
    return tokens_today() >= settings.AI["DAILY_TOKEN_BUDGET"]


def claim(wid):
    with transaction.atomic():
        req = A.objects.select_for_update(skip_locked=True).filter(status=A.QUEUED).order_by("id").first()
        if req is None:
            return None
        req.status, req.worker_id, req.attempts, req.started_at = A.RUNNING, wid, req.attempts + 1, timezone.now()
        req.save(update_fields=["status", "worker_id", "attempts", "started_at"])
        return req


def _finish(req, wid, **fields):
    return A.objects.filter(id=req.id, worker_id=wid, status=A.RUNNING).update(completed_at=timezone.now(),
                                                                                 **fields) == 1


def _fail(req, wid, outcome, message):
    log.info("event=assist_failed id=%s outcome=%s", req.id, outcome)
    _finish(req, wid, status=A.FAILED, outcome=outcome, error_message=message)


def execute(req, wid):
    cfg = settings.AI
    provider = providers.get_provider()
    if provider is None:
        return _fail(req, wid, A.UNAVAILABLE, NOT_CONFIGURED)
    if over_budget():
        return _fail(req, wid, A.UNAVAILABLE, OVER_BUDGET)
    t0 = time.monotonic()
    try:
        out = strategy.generate(provider, req.prompt, max_repairs=cfg["MAX_REPAIRS"], should_stop=SHUTDOWN.overdue)
    except strategy.Stopped:
        if A.objects.filter(id=req.id, worker_id=wid, status=A.RUNNING).update(
                status=A.QUEUED, worker_id="", attempts=F("attempts") - 1, started_at=None):
            log.info("event=assist_requeued_on_shutdown id=%s", req.id)
        return
    except providers.ProviderError as e:
        log.warning("event=assist_provider_error id=%s error=%s", req.id, e)
        return _fail(req, wid, A.UNAVAILABLE, PROVIDER_DOWN)
    ms = int((time.monotonic() - t0) * 1000)
    ok = out.kind in (A.SPEC, A.UNSUPPORTED)
    _finish(req, wid, status=A.COMPLETED if ok else A.FAILED, outcome=out.kind, result=out.result(),
            error_message="" if ok else NOT_VALID, provider=provider.name, model=provider.model,
            prompt_version=prompts.PROMPT_VERSION, tokens_in=out.tokens_in, tokens_out=out.tokens_out,
            llm_calls=out.calls, repair_rounds=out.repair_rounds, latency_ms=ms)
    # Never log the description or the answer: they are the user's text.
    log.info("event=assist_completed id=%s outcome=%s calls=%s repairs=%s tokens_in=%s tokens_out=%s ms=%s model=%s",
             req.id, out.kind, out.calls, out.repair_rounds, out.tokens_in, out.tokens_out, ms, provider.model)


def recover_stale():
    """A worker that died mid-request leaves it `running`; fail it after STALE_AFTER_S (the user can ask again)."""
    cutoff = timezone.now() - timedelta(seconds=settings.AI["STALE_AFTER_S"])
    n = A.objects.filter(status=A.RUNNING, started_at__lt=cutoff).update(
        status=A.FAILED, outcome=A.UNAVAILABLE, error_message=TIMED_OUT, worker_id="", completed_at=timezone.now())
    if n:
        log.warning("event=assist_stale_failed count=%s", n)
    return n


def delete_old():
    """Housekeeping: requests (and so users' descriptions) are kept RETENTION_DAYS (D-083)."""
    cutoff = timezone.now() - timedelta(days=settings.AI["RETENTION_DAYS"])
    n, _ = A.objects.filter(created_at__lt=cutoff).delete()
    return n


def work_one(wid):
    if SHUTDOWN.requested:
        return False
    req = claim(wid)
    if req is None:
        return False
    token = request_id_var.set(req.request_id or None)
    try:
        try:
            execute(req, wid)
        except Exception:
            log.exception("event=assist_crashed id=%s", req.id)
            _fail(req, wid, A.UNAVAILABLE, PROVIDER_DOWN)
    finally:
        request_id_var.reset(token)
    return True
