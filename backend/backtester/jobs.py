"""Durable job queue on PostgreSQL. A run row IS the job.

queued -> preparing_data -> running -> completed
                \\-------------\\------> failed
Workers claim with SELECT ... FOR UPDATE SKIP LOCKED, heartbeat while running, and finalise
in one transaction guarded by (status, worker_id), so a retried or stolen job cannot
double-write trades. Stale jobs (no heartbeat) are re-queued up to MAX_ATTEMPTS.
At-least-once execution, idempotent finalisation.

Claim order is (priority, id): runs a person starts by hand (priority 0) go before experiment children (priority 1).
Nothing is pre-empted; a running job always finishes. Experiments fan out into child runs and fan in by deriving their
status from them (experiment_status); an optimization's fan-in also queues its single out-of-sample run.
"""
import hashlib
import logging
import os
import socket
import time
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from django.db.models import F

from backtester import cache, engine, spec
from backtester.data_fetch import DataError, load_bars
from backtester.models import BacktestRun, Experiment, SymbolCoverage, Trade
from backtester.sandbox_runner import StrategyProcess
from vault_core.observability import request_id_var, run_id_var

log = logging.getLogger(__name__)
R = BacktestRun


class Shutdown:
    """Graceful stop (D-074). After a request the worker claims nothing new; the run in progress may finish until the
    deadline, after which it's put back in the queue (see ShutdownRequested) instead of waiting for stale recovery."""

    def __init__(self):
        self.requested, self.deadline = False, None

    def request(self, grace_s):
        if not self.requested:
            self.requested, self.deadline = True, time.monotonic() + grace_s
            log.info("event=shutdown_requested grace_s=%s", grace_s)

    def overdue(self):
        return self.requested and time.monotonic() >= self.deadline

    def reset(self):
        self.requested, self.deadline = False, None


SHUTDOWN = Shutdown()


class ShutdownRequested(Exception):
    """Raised from the progress callback when the grace period is over."""
# Heartbeat (and progress) at most once per second. It used to be every 50 bars, sized for slow sandbox runs; with
# interpreted builder strategies a run's simulation takes milliseconds, and those UPDATEs became ~70% of a child run's
# time (profiled in Phase 3). Stale recovery waits STALE_AFTER_S (120 s), so 1 s is far more often than needed.
HEARTBEAT_EVERY_S = 1.0
HOUSEKEEPING_EVERY_S = 3600  # expired guests and sessions


def worker_id():
    return f"{socket.gethostname()}:{os.getpid()}"


def code_hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def frozen_strategy(strategy):
    """The run's own copy of what it will execute. Editing the strategy later never changes this run."""
    if strategy.kind == "builder":
        return frozen_spec(strategy.spec)
    return {"strategy_code": strategy.code, "strategy_spec": None, "strategy_hash": code_hash(strategy.code)}


def frozen_spec(s):
    return {"strategy_code": "", "strategy_spec": s, "strategy_hash": spec.spec_hash(s)}


def claim(wid):
    with transaction.atomic():
        run = (R.objects.select_for_update(skip_locked=True).filter(status=R.QUEUED)
               .order_by("priority", "id").first())
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


def requeue(run, wid):
    """Shutdown overran the grace period: hand the run straight back to the queue. The attempt isn't counted (the
    worker stopped, the run didn't fail), and no other worker has to wait STALE_AFTER_S to notice."""
    if _update(run, wid, status=R.QUEUED, worker_id="", attempts=F("attempts") - 1, heartbeat_at=None,
               bars_processed=None):
        log.info("event=run_requeued_on_shutdown run=%s", run.id)


def fail(run, wid, category, message):
    log.info("event=run_failed run=%s category=%s", run.id, category)
    _update(run, wid, status=R.FAILED, failure_category=category, error_message=message[:500],
            completed_at=timezone.now())


def load_bars_cached(symbol, start, end, warmup_bars):
    """load_bars behind the per-worker cache (D-058). Only spans already covered are cached, and the key includes the
    coverage's fetched_at, so a re-download (which replaces the symbol's bars) can never be served stale."""
    cov = SymbolCoverage.objects.filter(symbol=symbol).values_list("fetched_at", flat=True).first()
    key = (symbol, start, end, warmup_bars, cov)
    hit = cache.BARS.get(key) if cov else None
    if hit is not None:
        return hit
    loaded = load_bars(symbol, start, end, warmup_bars=warmup_bars)
    cov = SymbolCoverage.objects.filter(symbol=symbol).values_list("fetched_at", flat=True).first()
    if cov:
        cache.BARS.put((symbol, start, end, warmup_bars, cov), loaded)
    return loaded


def execute(run, wid):
    t0 = time.monotonic()
    log.info("event=run_started run=%s attempt=%s strategy_hash=%s", run.id, run.attempts, run.strategy_hash[:12])
    cfg = settings.VAULT
    builder = run.strategy_spec is not None
    bars_hits, ind_hits = cache.BARS.hits, cache.INDICATORS.hits
    try:
        warmup, bars, manifest = load_bars_cached(run.symbol, run.start_date, run.end_date, (
            spec.warmup_bars(run.strategy_spec) if builder else engine.WARMUP_BARS))
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
        sell_commission_pct=None if run.sell_commission_pct is None else Decimal(run.sell_commission_pct),
    )
    series = [{"ts": b.ts, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
              for b in warmup + bars]

    last_beat = time.monotonic()

    def progress(n):
        nonlocal last_beat
        if SHUTDOWN.overdue():
            raise ShutdownRequested()
        if time.monotonic() - last_beat >= HEARTBEAT_EVERY_S:
            last_beat = time.monotonic()
            _update(run, wid, bars_processed=n, heartbeat_at=timezone.now())

    proc = None
    try:
        if builder:
            # Interpreted in-process: the spec is data validated against an allowlist, so no sandbox is needed.
            # Indicator series are shared with other runs on the same data (same hash) through the worker cache.
            try:
                decide = spec.compile_decide(spec.validate(run.strategy_spec), series,
                                             cache.IndicatorCache(manifest["data_sha256"]))
            except spec.SpecError as e:
                raise engine.StrategyError(f"Invalid strategy spec: {e}") from None
        else:
            proc = StrategyProcess(run.strategy_code, cfg["RUN_TIMEOUT_S"], cfg["RUN_CPU_S"], cfg["RUN_MEMORY_MB"])

            def decide(bar, indicators):
                wire = {"date": bar["ts"].date().isoformat(),
                        **{k: float(bar[k]) for k in ("open", "high", "low", "close")}, "volume": bar["volume"]}
                return proc.decide(wire, indicators)

        result = engine.simulate(series, decide, params, warmup=len(warmup), on_progress=progress)
    except engine.StrategyError as e:
        return fail(run, wid, "strategy", str(e))
    except ShutdownRequested:
        return requeue(run, wid)
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
    log.info("event=run_completed run=%s trades=%s ms=%s bars_cache_hit=%s indicator_cache_hits=%s", run.id,
             len(result.fills), locked.execution_time_ms, cache.BARS.hits > bars_hits, cache.INDICATORS.hits - ind_hits)


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


def finish_pending_optimizations():
    """Queue the out-of-sample run for any optimization whose in-sample runs are all finished but which has
    none yet. work_one does this after each run; this sweep covers runs that ended some other way (failed by
    recover_stale, or a worker killed between finalising a run and calling finish_optimization)."""
    pending = (Experiment.objects.filter(kind=Experiment.OPTIMIZATION, split_date__isnull=False, runs__sample="in",
                                         runs__status=R.COMPLETED)
               .exclude(runs__sample="out").exclude(runs__status__in=R.ACTIVE).distinct())
    for job in pending:
        finish_optimization(job)


def finish_optimization(job):
    """Fan-in for optimizations: once every in-sample run is terminal, queue one out-of-sample run for the best
    (by Sharpe). Comparisons need no fan-in step: their status is derived from the children."""
    if job.kind != Experiment.OPTIMIZATION or job.split_date is None:
        return
    runs = list(job.runs.filter(sample="in"))
    if not runs or any(r.status in R.ACTIVE for r in runs):
        return
    done = [r for r in runs if r.status == R.COMPLETED]
    if not done:
        return
    best = max(done, key=lambda r: (r.sharpe_ratio is not None, r.sharpe_ratio or 0, r.final_value or 0))
    try:
        with transaction.atomic():
            R.objects.create(
                owner_id=job.owner_id, strategy_id=best.strategy_id, experiment=job, sample="out", symbol=best.symbol,
                start_date=job.split_date, end_date=job.end_date, starting_cash=best.starting_cash,
                max_position_pct=best.max_position_pct, commission_pct=best.commission_pct,
                sell_commission_pct=best.sell_commission_pct, cost_model=best.cost_model,
                slippage_pct=best.slippage_pct, stop_loss_pct=best.stop_loss_pct,
                take_profit_pct=best.take_profit_pct, strategy_code=best.strategy_code,
                strategy_spec=best.strategy_spec, strategy_hash=best.strategy_hash, grid_params=best.grid_params,
                priority=R.BATCH, engine_version=engine.ENGINE_VERSION)
    except IntegrityError:
        pass  # another worker already queued it


def experiment_status(job):
    """Derived from the child runs, never stored: running, completed, partially_completed or failed."""
    runs = list(job.runs.all())
    if any(r.status in R.ACTIVE for r in runs):
        return "running"
    if job.kind == Experiment.COMPARISON:
        cells = [r for r in runs if r.sample != "bench"]
        if not any(r.status == R.COMPLETED for r in cells):
            return "failed"
        return "completed" if all(r.status == R.COMPLETED for r in runs) else "partially_completed"
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
    if SHUTDOWN.requested:
        return False  # stopping: claim nothing new
    run = claim(wid)
    if run is None:
        return False
    # Every log line about this run carries its ID and the ID of the request that created it (D-070).
    tokens = (request_id_var.set(run.request_id or None), run_id_var.set(run.id))
    try:
        try:
            execute(run, wid)
        except Exception:
            log.exception("event=run_crashed run=%s", run.id)
            fail(run, wid, "infrastructure", "Internal error while running the backtest")
        if run.experiment_id:
            finish_optimization(run.experiment)
    finally:
        request_id_var.reset(tokens[0])
        run_id_var.reset(tokens[1])
    return True


def work_forever(poll_s=2.0, stop=lambda: False):
    wid = worker_id()
    log.info("event=worker_started worker=%s", wid)
    last_recover = last_housekeeping = 0.0
    while not stop() and not SHUTDOWN.requested:
        # Outside a request Django never recycles connections; without this a worker keeps a dead
        # connection forever after a database restart.
        close_old_connections()
        try:
            if time.monotonic() - last_recover > 30:
                recover_stale()
                finish_pending_optimizations()
                last_recover = time.monotonic()
            if time.monotonic() - last_housekeeping > HOUSEKEEPING_EVERY_S:
                from accounts.housekeeping import run as housekeeping
                housekeeping()
                last_housekeeping = time.monotonic()
            busy = work_one(wid)
        except Exception:
            log.exception("event=worker_loop_error")
            busy = False
        if not busy and not SHUTDOWN.requested:
            time.sleep(poll_s)
    log.info("event=worker_stopped worker=%s", wid)
