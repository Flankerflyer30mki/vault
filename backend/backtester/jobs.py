"""Durable job queue on PostgreSQL. A run row IS the job.

queued -> preparing_data -> running -> completed
                \\-------------\\------> failed
Workers claim with SELECT ... FOR UPDATE SKIP LOCKED, heartbeat while running, and finalise
in one transaction guarded by (status, worker_id), so a retried or stolen job cannot
double-write trades. Stale jobs (no heartbeat) are re-queued up to MAX_ATTEMPTS.
At-least-once execution, idempotent finalisation.
"""
import hashlib
import logging
import os
import socket
import time
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from backtester import engine
from backtester.data_fetch import DataError, load_bars
from backtester.models import BacktestRun, Trade
from backtester.sandbox_runner import StrategyProcess

log = logging.getLogger(__name__)
R = BacktestRun
HEARTBEAT_EVERY = 50  # bars


def worker_id():
    return f"{socket.gethostname()}:{os.getpid()}"


def code_hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def claim(wid):
    with transaction.atomic():
        run = R.objects.select_for_update(skip_locked=True).filter(status=R.QUEUED).order_by("id").first()
        if run is None:
            return None
        now = timezone.now()
        run.status, run.worker_id, run.attempts = R.PREPARING, wid, run.attempts + 1
        run.started_at = run.heartbeat_at = now
        run.save(update_fields=["status", "worker_id", "attempts", "started_at", "heartbeat_at"])
        return run


def _update(run, wid, **fields):
    """Conditional update: only the worker that owns an active run may touch it. Returns True if applied."""
    return R.objects.filter(id=run.id, worker_id=wid, status__in=R.ACTIVE).update(**fields) == 1


def fail(run, wid, category, message):
    log.info("event=run_failed run=%s category=%s", run.id, category)
    _update(run, wid, status=R.FAILED, failure_category=category, error_message=message[:500],
            completed_at=timezone.now())


def execute(run, wid):
    t0 = time.monotonic()
    log.info("event=run_started run=%s attempt=%s strategy_hash=%s", run.id, run.attempts, run.strategy_hash[:12])
    cfg = settings.VAULT
    try:
        warmup, bars, manifest = load_bars(run.symbol, run.start_date, run.end_date)
    except DataError as e:
        return fail(run, wid, "data", str(e))
    if not _update(run, wid, status=R.RUNNING, bars_total=len(bars), bars_processed=0,
                   data_manifest=manifest, heartbeat_at=timezone.now()):
        return  # lost ownership (recovered as stale by someone else)

    params = engine.Params(
        starting_cash=Decimal(run.starting_cash), max_position_pct=Decimal(run.max_position_pct),
        commission_pct=Decimal(run.commission_pct), slippage_pct=Decimal(run.slippage_pct),
        stop_loss_pct=run.stop_loss_pct and Decimal(run.stop_loss_pct),
        take_profit_pct=run.take_profit_pct and Decimal(run.take_profit_pct),
    )
    series = [{"ts": b.ts, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
              for b in warmup + bars]

    def progress(n):
        if n % HEARTBEAT_EVERY == 0:
            _update(run, wid, bars_processed=n, heartbeat_at=timezone.now())

    proc = None
    try:
        proc = StrategyProcess(run.strategy_code, cfg["RUN_TIMEOUT_S"], cfg["RUN_CPU_S"], cfg["RUN_MEMORY_MB"])

        def decide(bar, indicators):
            wire = {"date": bar["ts"].date().isoformat(), **{k: float(bar[k]) for k in ("open", "high", "low", "close")},
                    "volume": bar["volume"]}
            return proc.decide(wire, indicators)

        result = engine.simulate(series, decide, params, warmup=len(warmup), on_progress=progress)
    except engine.StrategyError as e:
        return fail(run, wid, "strategy", str(e))
    finally:
        if proc:
            proc.close()

    m = engine.metrics(result, params, series[len(warmup):])
    curve = [[ts.date().isoformat(), float(v)] for ts, v in result.equity_curve]
    with transaction.atomic():
        locked = R.objects.select_for_update().filter(id=run.id, worker_id=wid, status=R.RUNNING).first()
        if locked is None:
            return
        Trade.objects.filter(run_id=run.id).delete()  # a retry replaces, never appends
        Trade.objects.bulk_create([Trade(run_id=run.id, side=f.side, ts=f.ts, price=f.price, quantity=f.quantity,
                                         commission=f.commission, slippage_cost=f.slippage_cost,
                                         cash_after=f.cash_after, reason=f.reason) for f in result.fills])
        for k, v in m.items():
            setattr(locked, k, v)
        locked.equity_curve = curve
        locked.bars_processed = len(bars)
        locked.status, locked.completed_at = R.COMPLETED, timezone.now()
        locked.execution_time_ms = int((time.monotonic() - t0) * 1000)
        locked.save()
    log.info("event=run_completed run=%s trades=%s ms=%s", run.id, len(result.fills), locked.execution_time_ms)


def recover_stale():
    cfg = settings.VAULT
    cutoff = timezone.now() - timedelta(seconds=cfg["STALE_AFTER_S"])
    stale = R.objects.filter(status__in=(R.PREPARING, R.RUNNING), heartbeat_at__lt=cutoff)
    failed = stale.filter(attempts__gte=cfg["MAX_ATTEMPTS"]).update(
        status=R.FAILED, failure_category="infrastructure", worker_id="",
        error_message="Worker stopped responding; retries exhausted", completed_at=timezone.now())
    requeued = stale.filter(attempts__lt=cfg["MAX_ATTEMPTS"]).update(status=R.QUEUED, worker_id="")
    if failed or requeued:
        log.warning("event=stale_recovered requeued=%s failed=%s", requeued, failed)


def finish_optimization(job):
    """Once every in-sample run is terminal, queue one out-of-sample run for the best (by Sharpe)."""
    runs = list(job.runs.filter(sample="in"))
    if not runs or any(r.status in R.ACTIVE for r in runs) or job.split_date is None:
        return
    done = [r for r in runs if r.status == R.COMPLETED]
    if not done:
        return
    best = max(done, key=lambda r: (r.sharpe_ratio is not None, r.sharpe_ratio or 0, r.final_value or 0))
    try:
        with transaction.atomic():
            R.objects.create(
                strategy_id=best.strategy_id, optimization=job, sample="out", symbol=best.symbol,
                start_date=job.split_date, end_date=job.end_date, starting_cash=best.starting_cash,
                max_position_pct=best.max_position_pct, commission_pct=best.commission_pct,
                slippage_pct=best.slippage_pct, stop_loss_pct=best.stop_loss_pct,
                take_profit_pct=best.take_profit_pct, strategy_code=best.strategy_code,
                strategy_hash=best.strategy_hash, engine_version=engine.ENGINE_VERSION)
    except IntegrityError:
        pass  # another worker already queued it


def optimization_status(job):
    runs = list(job.runs.all())
    if any(r.status in R.ACTIVE for r in runs):
        return "running"
    ins = [r for r in runs if r.sample != "out"]  # legacy jobs (no split) have "full" runs
    ok = sum(r.status == R.COMPLETED for r in ins)
    oos = next((r for r in runs if r.sample == "out"), None)
    if ok == 0:
        return "failed"
    if job.split_date and oos is None:
        return "running"  # out-of-sample run not yet queued
    if ok < len(ins) or (oos and oos.status != R.COMPLETED):
        return "partially_completed"
    return "completed"


def work_one(wid):
    """Process one job if available. Returns True if a job was processed."""
    run = claim(wid)
    if run is None:
        return False
    try:
        execute(run, wid)
    except Exception:
        log.exception("event=run_crashed run=%s", run.id)
        fail(run, wid, "infrastructure", "Internal error while running the backtest")
    if run.optimization_id:
        finish_optimization(run.optimization)
    return True


def work_forever(poll_s=2.0, stop=lambda: False):
    wid = worker_id()
    log.info("event=worker_started worker=%s", wid)
    last_recover = 0.0
    while not stop():
        if time.monotonic() - last_recover > 30:
            recover_stale()
            last_recover = time.monotonic()
        try:
            busy = work_one(wid)
        except Exception:
            log.exception("event=worker_loop_error")
            busy = False
        if not busy:
            time.sleep(poll_s)
