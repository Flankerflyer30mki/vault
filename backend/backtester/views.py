from datetime import timedelta
from decimal import Decimal
from itertools import product

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import quotas
from backtester import costs, spec
from backtester.engine import ENGINE_VERSION
from backtester.jobs import frozen_strategy, optimization_status
from backtester.models import BacktestRun, OptimizationJob, Strategy, Trade
from backtester.serializers import (BacktestRunSerializer, OptimizationJobSerializer, RunWithCurveSerializer,
                                    SpecPreviewSerializer, StrategySerializer, TradeSerializer)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class QueueFull(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The backtest queue is full. Try again shortly."
    default_code = "queue_full"


def admit(n):
    """Global admission control: reject before creating work the queue cannot absorb.
    ponytail: count-then-insert is a soft cap (concurrent requests can overshoot by a few)."""
    active = BacktestRun.objects.filter(status__in=BacktestRun.ACTIVE).count()
    if active + n > settings.VAULT["MAX_ACTIVE_RUNS"]:
        raise QueueFull()


class Throttled:
    def get_throttles(self):
        self.throttle_scope = "read" if self.request.method == "GET" else self.write_scope
        return super().get_throttles()


class IdempotentCreate:
    """Repeat POST with the same Idempotency-Key returns the user's original resource instead of new work.
    Keys are per user, so one user's key can never return another user's job. The user's row is locked for
    the duration of the create, which serialises that user's concurrent creates: quota checks are exact and
    a duplicate key waits for the first request instead of racing it."""

    def create(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key", "")[:64] or None
        model = self.get_serializer_class().Meta.model
        mine = model.objects.filter(owner=request.user)
        if key and (existing := mine.filter(idempotency_key=key).first()):
            return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                if key and (existing := mine.filter(idempotency_key=key).first()):
                    return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
                obj = self.perform_create(serializer, key)
        except IntegrityError:
            if key is None:
                raise
            obj = mine.get(idempotency_key=key)  # concurrent duplicate won the race
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)


class StrategyListCreateView(Throttled, generics.ListCreateAPIView):
    write_scope = "write"
    serializer_class = StrategySerializer

    def get_queryset(self):
        return Strategy.objects.filter(quotas.visible_strategies_q(self.request.user)) \
            .order_by("-is_builtin", "-created_at")

    def perform_create(self, serializer):
        _check_code_allowed(serializer.validated_data.get("kind"))
        with transaction.atomic():
            # Same pattern as job creation: lock the user's row so two concurrent saves can't both pass the limit.
            get_user_model().objects.select_for_update().get(pk=self.request.user.pk)
            quotas.check_strategy(self.request.user)
            serializer.save(owner=self.request.user, is_builtin=False)


def _check_code_allowed(kind):
    if kind == Strategy.CODE and not settings.VAULT["ALLOW_CUSTOM_CODE"]:
        raise PermissionDenied("Custom strategy code is disabled on this deployment; use the strategy builder.")


class StrategyDetailView(Throttled, generics.RetrieveUpdateDestroyAPIView):
    """Read any visible strategy; change or delete only your own. Built-ins are read-only templates."""
    write_scope = "write"
    serializer_class = StrategySerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Strategy.objects.filter(quotas.visible_strategies_q(self.request.user))

    def _own(self):
        obj = self.get_object()
        if obj.owner_id != self.request.user.id:
            raise PermissionDenied("Built-in strategies are read-only. Use one as a template to make your own.")
        return obj

    def perform_update(self, serializer):
        self._own()
        _check_code_allowed(serializer.instance.kind)
        serializer.save()  # past runs keep their frozen copy, so editing never changes old results

    def perform_destroy(self, instance):
        self._own()
        n = instance.runs.count()
        if n:
            raise Conflict(f"This strategy has {n} backtest runs. It's kept so those results stay reproducible.")
        instance.delete()


class StrategyCatalogView(Throttled, APIView):
    """What the builder form offers: indicators, operators, limits, cost models, suggested symbols."""

    def get(self, request):
        return Response({**spec.catalog(),
                         "cost_models": [{"id": k, "label": v} for k, v in costs.COST_MODELS.items()],
                         "india_rates": {k: str(v) for k, v in costs.india_delivery()[2].items()},
                         "suggested_symbols": costs.SUGGESTED_SYMBOLS,
                         "custom_code_enabled": settings.VAULT["ALLOW_CUSTOM_CODE"]})


class SpecPreviewView(Throttled, APIView):
    """Validate a spec without saving it; returns the normalised spec, its Python rendering and warm-up.
    The builder calls this as the user types, so it shares the generous read limit."""
    write_scope = "read"

    def post(self, request):
        ser = SpecPreviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        s = ser.validated_data["spec"]
        return Response({"spec": s, "python": spec.render_python(s), "warmup_bars": spec.warmup_bars(s),
                         "hash": spec.spec_hash(s)})


class BacktestRunListCreateView(Throttled, IdempotentCreate, generics.ListCreateAPIView):
    write_scope = "jobs"
    serializer_class = BacktestRunSerializer

    def get_queryset(self):
        # The list serializer shows neither the curve nor the code; don't load them.
        return (BacktestRun.objects.filter(owner=self.request.user).select_related("strategy")
                .defer("equity_curve", "strategy_code").order_by("-created_at"))

    def perform_create(self, serializer, key):
        quotas.check(self.request.user, "run")
        admit(1)
        return serializer.save(owner=self.request.user, **frozen_strategy(serializer.validated_data["strategy"]),
                               engine_version=ENGINE_VERSION, idempotency_key=key)


class BacktestRunDetailView(Throttled, generics.RetrieveAPIView):
    serializer_class = RunWithCurveSerializer

    def get_queryset(self):
        return BacktestRun.objects.filter(owner=self.request.user).select_related("strategy")


class TradeListView(Throttled, generics.ListAPIView):
    serializer_class = TradeSerializer
    pagination_class = None  # bounded: at most one trade per bar

    def get_queryset(self):
        run = get_object_or_404(BacktestRun.objects.only("id"), id=self.kwargs["run_id"], owner=self.request.user)
        return Trade.objects.filter(run=run).order_by("ts", "id")


class OptimizationJobListCreateView(Throttled, IdempotentCreate, generics.ListCreateAPIView):
    write_scope = "jobs"
    serializer_class = OptimizationJobSerializer

    def get_queryset(self):
        # Status is derived from the child runs; load only what optimization_status reads, never the curves.
        return OptimizationJob.objects.filter(owner=self.request.user).select_related("strategy").prefetch_related(
            Prefetch("runs", queryset=BacktestRun.objects.only("id", "optimization_id", "status", "sample"))
        ).order_by("-created_at")

    def perform_create(self, serializer, key):
        quotas.check(self.request.user, "optimization")
        d = serializer.validated_data
        grid = list(product(d["stop_loss_options"], d["take_profit_options"]))
        admit(len(grid) + 1)  # +1: the out-of-sample run
        job = serializer.save(owner=self.request.user, idempotency_key=key)
        frozen = frozen_strategy(job.strategy)
        # Flat: the model's default fee. India: statutory charges with zero brokerage (a discount broker's delivery).
        buy, sell = costs.rates(job.cost_model, Decimal("0.001") if job.cost_model == costs.FLAT else 0)
        BacktestRun.objects.bulk_create([BacktestRun(
            owner=self.request.user, strategy=job.strategy, optimization=job, sample="in", symbol=job.symbol,
            start_date=job.start_date, end_date=job.split_date - timedelta(days=1), starting_cash=job.starting_cash,
            stop_loss_pct=Decimal(sl), take_profit_pct=Decimal(tp), cost_model=job.cost_model,
            commission_pct=buy, sell_commission_pct=sell, **frozen, engine_version=ENGINE_VERSION,
        ) for sl, tp in grid])
        return job


class OptimizationJobDetailView(Throttled, generics.RetrieveAPIView):
    """One call returns the job plus every child run with its equity curve (no N+1 polling)."""
    serializer_class = OptimizationJobSerializer

    def get_queryset(self):
        return OptimizationJob.objects.filter(owner=self.request.user).select_related("strategy") \
            .prefetch_related("runs__strategy")

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        data = self.get_serializer(job).data
        data["runs"] = RunWithCurveSerializer(sorted(job.runs.all(), key=lambda r: r.id), many=True).data
        return Response(data)


def _run_summary(r):
    total = None
    if r.final_value is not None and r.starting_cash:
        total = float(r.final_value / r.starting_cash - 1)
    return {"id": r.id, "strategy_name": r.strategy.name, "symbol": r.symbol, "currency": costs.currency(r.symbol),
            "status": r.status,
            "start_date": r.start_date, "end_date": r.end_date, "created_at": r.created_at,
            "bars_processed": r.bars_processed, "bars_total": r.bars_total, "total_return": total,
            "buy_and_hold_return": r.buy_and_hold_return, "sharpe_ratio": r.sharpe_ratio,
            "failure_category": r.failure_category}


class DashboardView(Throttled, APIView):
    """Everything the dashboard shows, in one request. Deliberately no 'best by Sharpe' ranking (see D-022)."""

    def get(self, request):
        user = request.user
        runs = (BacktestRun.objects.filter(owner=user).select_related("strategy")
                .only("id", "strategy__name", "symbol", "status", "start_date", "end_date", "created_at",
                      "bars_processed", "bars_total", "final_value", "starting_cash", "buy_and_hold_return",
                      "sharpe_ratio", "failure_category", "optimization_id"))
        active = list(runs.filter(optimization__isnull=True, status__in=BacktestRun.ACTIVE).order_by("-created_at"))
        recent = list(runs.filter(optimization__isnull=True).exclude(status__in=BacktestRun.ACTIVE)
                      .order_by("-created_at")[:10])
        opts = list(OptimizationJob.objects.filter(owner=user).select_related("strategy").prefetch_related(
            Prefetch("runs", queryset=BacktestRun.objects.only(
                "id", "optimization_id", "status", "sample", "sharpe_ratio", "final_value", "starting_cash",
                "buy_and_hold_return", "stop_loss_pct", "take_profit_pct")))
            .order_by("-created_at")[:5])
        optimizations = []
        for job in opts:
            oos = next((r for r in job.runs.all() if r.sample == "out"), None)
            optimizations.append({
                "id": job.id, "strategy_name": job.strategy.name, "symbol": job.symbol,
                "status": optimization_status(job), "created_at": job.created_at,
                "runs_total": sum(1 for r in job.runs.all() if r.sample == "in"),
                "runs_done": sum(1 for r in job.runs.all() if r.sample == "in" and r.status not in BacktestRun.ACTIVE),
                "out_of_sample": None if oos is None else {
                    "status": oos.status, "sharpe_ratio": oos.sharpe_ratio,
                    "total_return": (float(oos.final_value / oos.starting_cash - 1)
                                     if oos.final_value is not None else None),
                    "buy_and_hold_return": oos.buy_and_hold_return,
                    "stop_loss_pct": oos.stop_loss_pct, "take_profit_pct": oos.take_profit_pct},
            })
        strategies = Strategy.objects.filter(quotas.visible_strategies_q(user)).order_by("-is_builtin", "-created_at")
        return Response({
            "quota": {"tier": user.tier, "limits": quotas.limits(user), "usage": quotas.usage(user)},
            "active_runs": [_run_summary(r) for r in active],
            "recent_runs": [_run_summary(r) for r in recent],
            "optimizations": optimizations,
            "strategies": [{"id": s.id, "name": s.name, "kind": s.kind, "is_builtin": s.is_builtin}
                           for s in strategies.only("id", "name", "kind", "is_builtin")[:20]],
            "custom_code_enabled": settings.VAULT["ALLOW_CUSTOM_CODE"],
        })
