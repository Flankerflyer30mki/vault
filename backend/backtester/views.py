from datetime import timedelta
from decimal import Decimal
from itertools import product

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response

from backtester.engine import ENGINE_VERSION
from backtester.jobs import code_hash
from backtester.models import BacktestRun, OptimizationJob, Strategy, Trade
from backtester.serializers import (BacktestRunSerializer, OptimizationJobSerializer, RunWithCurveSerializer,
                                    StrategySerializer, TradeSerializer)


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
    """Repeat POST with the same Idempotency-Key returns the original resource instead of new work."""

    def create(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key", "")[:64] or None
        model = self.get_serializer_class().Meta.model
        if key and (existing := model.objects.filter(idempotency_key=key).first()):
            return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                obj = self.perform_create(serializer, key)
        except IntegrityError:
            obj = model.objects.get(idempotency_key=key)  # concurrent duplicate won the race
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)


class StrategyListCreateView(Throttled, generics.ListCreateAPIView):
    write_scope = "write"
    queryset = Strategy.objects.order_by("-is_builtin", "-created_at")
    serializer_class = StrategySerializer

    def perform_create(self, serializer):
        if not settings.VAULT["ALLOW_CUSTOM_CODE"]:
            raise PermissionDenied("Custom strategy code is disabled on this deployment; use a built-in strategy.")
        serializer.save()


class BacktestRunListCreateView(Throttled, IdempotentCreate, generics.ListCreateAPIView):
    write_scope = "jobs"
    queryset = BacktestRun.objects.select_related("strategy").order_by("-created_at")
    serializer_class = BacktestRunSerializer

    def perform_create(self, serializer, key):
        admit(1)
        code = serializer.validated_data["strategy"].code
        return serializer.save(strategy_code=code, strategy_hash=code_hash(code), engine_version=ENGINE_VERSION,
                               idempotency_key=key)


class BacktestRunDetailView(Throttled, generics.RetrieveAPIView):
    queryset = BacktestRun.objects.select_related("strategy")
    serializer_class = RunWithCurveSerializer


class TradeListView(Throttled, generics.ListAPIView):
    serializer_class = TradeSerializer
    pagination_class = None  # bounded: at most one trade per bar

    def get_queryset(self):
        return Trade.objects.filter(run_id=self.kwargs["run_id"]).order_by("ts", "id")


class OptimizationJobListCreateView(Throttled, IdempotentCreate, generics.ListCreateAPIView):
    write_scope = "jobs"
    queryset = OptimizationJob.objects.select_related("strategy").prefetch_related("runs").order_by("-created_at")
    serializer_class = OptimizationJobSerializer

    def perform_create(self, serializer, key):
        d = serializer.validated_data
        grid = list(product(d["stop_loss_options"], d["take_profit_options"]))
        admit(len(grid) + 1)  # +1: the out-of-sample run
        job = serializer.save(idempotency_key=key)
        code = job.strategy.code
        BacktestRun.objects.bulk_create([BacktestRun(
            strategy=job.strategy, optimization=job, sample="in", symbol=job.symbol,
            start_date=job.start_date, end_date=job.split_date - timedelta(days=1), starting_cash=job.starting_cash,
            stop_loss_pct=Decimal(sl), take_profit_pct=Decimal(tp),
            strategy_code=code, strategy_hash=code_hash(code), engine_version=ENGINE_VERSION,
        ) for sl, tp in grid])
        return job


class OptimizationJobDetailView(Throttled, generics.RetrieveAPIView):
    """One call returns the job plus every child run with its equity curve (no N+1 polling)."""
    queryset = OptimizationJob.objects.select_related("strategy").prefetch_related("runs__strategy")
    serializer_class = OptimizationJobSerializer

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        data = self.get_serializer(job).data
        data["runs"] = RunWithCurveSerializer(sorted(job.runs.all(), key=lambda r: r.id), many=True).data
        return Response(data)
