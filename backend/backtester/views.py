from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import quotas
from backtester import costs, spec
from backtester.engine import ENGINE_VERSION
from backtester.jobs import experiment_status, frozen_spec, frozen_strategy
from backtester.models import BacktestRun, Experiment, Strategy, Trade
from backtester.serializers import (BacktestRunSerializer, ComparisonCreateSerializer, ExperimentRunSerializer,
                                    ExperimentSerializer, OptimizationCreateSerializer, RunWithCurveSerializer,
                                    SpecPreviewSerializer, StrategySerializer, TradeSerializer)

BENCHMARK_STRATEGY = "Buy and Hold"  # seeded by migration 0019

# Response shapes for the OpenAPI schema (D-072). Nested parts are described loosely (objects/lists) where their exact
# shape is documented in the README rather than duplicated here.
_any_list = serializers.ListField(child=serializers.DictField())
CATALOG = inline_serializer("Catalog", {
    "version": serializers.IntegerField(), "max_conditions": serializers.IntegerField(), "operators": _any_list,
    "price_fields": serializers.ListField(child=serializers.CharField()), "indicators": _any_list,
    "cost_models": _any_list, "india_rates": serializers.DictField(), "suggested_symbols": _any_list,
    "custom_code_enabled": serializers.BooleanField(), "limits": serializers.DictField(),
    "benchmarks": serializers.DictField()})
PREVIEW = inline_serializer("SpecPreview", {
    "spec": serializers.JSONField(), "python": serializers.CharField(), "warmup_bars": serializers.IntegerField(),
    "hash": serializers.CharField(), "tunable_params": _any_list})
DASHBOARD = inline_serializer("Dashboard", {
    "quota": serializers.DictField(), "active_runs": _any_list, "recent_runs": _any_list, "experiments": _any_list,
    "strategies": _any_list, "custom_code_enabled": serializers.BooleanField()})
EXPERIMENT_CREATE = PolymorphicProxySerializer(
    component_name="ExperimentCreate", resource_type_field_name="kind",
    serializers={"optimization": OptimizationCreateSerializer, "comparison": ComparisonCreateSerializer})


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
    model = None

    def output(self, obj):
        return self.get_serializer(obj).data

    def create(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key", "")[:64] or None
        mine = self.model.objects.filter(owner=request.user)
        if key and (existing := mine.filter(idempotency_key=key).first()):
            return Response(self.output(existing), status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                if key and (existing := mine.filter(idempotency_key=key).first()):
                    return Response(self.output(existing), status=status.HTTP_200_OK)
                obj = self.perform_create(serializer, key)
        except IntegrityError:
            if key is None:
                raise
            obj = mine.get(idempotency_key=key)  # concurrent duplicate won the race
        return Response(self.output(obj), status=status.HTTP_201_CREATED)


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

    @extend_schema(responses=CATALOG)
    def get(self, request):
        cfg = settings.VAULT
        return Response({**spec.catalog(),
                         "cost_models": [{"id": k, "label": v} for k, v in costs.COST_MODELS.items()],
                         "india_rates": {k: str(v) for k, v in costs.india_delivery()[2].items()},
                         "suggested_symbols": costs.SUGGESTED_SYMBOLS,
                         "custom_code_enabled": cfg["ALLOW_CUSTOM_CODE"],
                         "limits": {"max_grid": cfg["MAX_GRID"], "max_grid_params": cfg["MAX_GRID_PARAMS"],
                                    "max_compare_strategies": cfg["MAX_COMPARE_STRATEGIES"],
                                    "max_compare_symbols": cfg["MAX_COMPARE_SYMBOLS"]},
                         "benchmarks": cfg["BENCHMARKS"]})


class SpecPreviewView(Throttled, APIView):
    """Validate a spec without saving it; returns the normalised spec, its Python rendering and warm-up.
    The builder calls this as the user types, so it shares the generous read limit."""
    write_scope = "read"

    @extend_schema(request=SpecPreviewSerializer, responses=PREVIEW)
    def post(self, request):
        ser = SpecPreviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        s = ser.validated_data["spec"]
        return Response({"spec": s, "python": spec.render_python(s), "warmup_bars": spec.warmup_bars(s),
                         "hash": spec.spec_hash(s), "tunable_params": spec.tunable_params(s)})


class BacktestRunListCreateView(Throttled, IdempotentCreate, generics.ListCreateAPIView):
    write_scope = "jobs"
    serializer_class = BacktestRunSerializer
    model = BacktestRun

    def get_queryset(self):
        # The list serializer shows neither the curve nor the code; don't load them.
        return (BacktestRun.objects.filter(owner=self.request.user).select_related("strategy")
                .defer("equity_curve", "strategy_code").order_by("-created_at"))

    def perform_create(self, serializer, key):
        quotas.check(self.request.user, "run")
        admit(1)
        # Started by hand: priority 0, so it's claimed before any queued experiment children (D-059).
        return serializer.save(owner=self.request.user, **frozen_strategy(serializer.validated_data["strategy"]),
                               priority=BacktestRun.INTERACTIVE, engine_version=ENGINE_VERSION, idempotency_key=key)


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


@extend_schema_view(post=extend_schema(request=EXPERIMENT_CREATE, responses={201: ExperimentSerializer,
                                                                           200: ExperimentSerializer}))
class ExperimentListCreateView(Throttled, IdempotentCreate, generics.ListCreateAPIView):
    """POST fans out one child run per combination or cell (priority 1); GET lists the user's experiments.
    Also mounted at /api/optimizations/ (default_kind="optimization") so earlier clients keep working."""
    write_scope = "jobs"
    model = Experiment
    default_kind = None

    def get_serializer_class(self):
        if self.request.method == "POST":
            kind = self.default_kind or self.request.data.get("kind") or Experiment.OPTIMIZATION
            return ComparisonCreateSerializer if kind == Experiment.COMPARISON else OptimizationCreateSerializer
        return ExperimentSerializer

    def output(self, obj):
        return ExperimentSerializer(obj, context=self.get_serializer_context()).data

    def get_queryset(self):
        # Status is derived from the child runs; load only what experiment_status reads, never the curves.
        qs = Experiment.objects.filter(owner=self.request.user).select_related("strategy").prefetch_related(
            Prefetch("runs", queryset=BacktestRun.objects.only("id", "experiment_id", "status", "sample"))
        ).order_by("-created_at")
        return qs.filter(kind=self.default_kind) if self.default_kind else qs

    def perform_create(self, serializer, key):
        quotas.check(self.request.user, "experiment")
        if isinstance(serializer, ComparisonCreateSerializer):
            return self._create_comparison(serializer.validated_data, key)
        return self._create_optimization(serializer.validated_data, key)

    def _create_optimization(self, d, key):
        grid = [(params, frozen, sl, tp) for params, frozen in d["combos"]
                for sl in d["stop_loss_options"] for tp in d["take_profit_options"]]
        admit(len(grid) + 1)  # +1: the out-of-sample run
        strategy = d["strategy"]
        job = Experiment.objects.create(
            owner=self.request.user, kind=Experiment.OPTIMIZATION, strategy=strategy, symbol=d["symbol"],
            start_date=d["start_date"], end_date=d["end_date"], split_date=d["split_date"],
            starting_cash=d["starting_cash"], cost_model=d["cost_model"], stop_loss_options=d["stop_loss_options"],
            take_profit_options=d["take_profit_options"], idempotency_key=key,
            config={"param_grid": d["param_grid"], "skipped": d["skipped"]})
        base = frozen_strategy(strategy)
        # Flat: the model's default fee. India: statutory charges with zero brokerage (a discount broker's delivery).
        buy, sell = costs.rates(job.cost_model, Decimal("0.001") if job.cost_model == costs.FLAT else 0)
        BacktestRun.objects.bulk_create([BacktestRun(
            owner=self.request.user, strategy=strategy, experiment=job, sample="in", priority=BacktestRun.BATCH,
            symbol=job.symbol, start_date=job.start_date, end_date=job.split_date - timedelta(days=1),
            starting_cash=job.starting_cash, stop_loss_pct=Decimal(sl), take_profit_pct=Decimal(tp),
            cost_model=job.cost_model, commission_pct=buy, sell_commission_pct=sell,
            grid_params={**params, "stop_loss_pct": sl, "take_profit_pct": tp},
            **(frozen_spec(frozen) if frozen is not None else base), engine_version=ENGINE_VERSION,
        ) for params, frozen, sl, tp in grid])
        return job

    def _create_comparison(self, d, key):
        strategies, symbols = d["strategies"], d["symbols"]
        benchmarks = {}
        for sym in symbols:  # one index per currency present; unknown currencies get none
            cur = costs.currency(sym)
            if cur in settings.VAULT["BENCHMARKS"]:
                benchmarks.setdefault(cur, settings.VAULT["BENCHMARKS"][cur])
        admit(len(strategies) * len(symbols) + len(benchmarks))
        fmt = lambda v: None if v is None else str(v)  # noqa: E731  (JSON can't hold Decimal)
        job = Experiment.objects.create(
            owner=self.request.user, kind=Experiment.COMPARISON, start_date=d["start_date"], end_date=d["end_date"],
            starting_cash=d["starting_cash"], cost_model=d["cost_model"], idempotency_key=key,
            config={"strategies": [s.id for s in strategies], "symbols": symbols, "benchmarks": benchmarks,
                    "commission_pct": fmt(d["commission_pct"]), "sell_commission_pct": fmt(d["sell_commission_pct"]),
                    "slippage_pct": fmt(d["slippage_pct"]), "stop_loss_pct": fmt(d.get("stop_loss_pct")),
                    "take_profit_pct": fmt(d.get("take_profit_pct"))})
        common = dict(owner=self.request.user, experiment=job, priority=BacktestRun.BATCH, start_date=job.start_date,
                      end_date=job.end_date, starting_cash=job.starting_cash, engine_version=ENGINE_VERSION)
        runs = [BacktestRun(**common, strategy=s, sample="full", symbol=sym, cost_model=d["cost_model"],
                            commission_pct=d["commission_pct"], sell_commission_pct=d["sell_commission_pct"],
                            slippage_pct=d["slippage_pct"], stop_loss_pct=d.get("stop_loss_pct"),
                            take_profit_pct=d.get("take_profit_pct"), **frozen_strategy(s))
                for s in strategies for sym in symbols]
        if benchmarks:
            # The benchmark is just another child: buy-and-hold on the index, no costs. Same queue, same data path.
            hold = Strategy.objects.get(name=BENCHMARK_STRATEGY, is_builtin=True)
            runs += [BacktestRun(**common, strategy=hold, sample="bench", symbol=index, commission_pct=0,
                                 sell_commission_pct=0, slippage_pct=0, **frozen_strategy(hold))
                     for index in benchmarks.values()]
        BacktestRun.objects.bulk_create(runs)
        return job


class ExperimentDetailSerializer(ExperimentSerializer):
    """Schema-only: the detail response is the experiment plus its child runs."""
    runs = ExperimentRunSerializer(many=True, read_only=True)

    class Meta(ExperimentSerializer.Meta):
        fields = ExperimentSerializer.Meta.fields + ["runs"]
        read_only_fields = fields


@extend_schema_view(get=extend_schema(responses=ExperimentDetailSerializer))
class ExperimentDetailView(Throttled, generics.RetrieveAPIView):
    """One call returns the experiment plus every child run with a downsampled curve (no N+1 polling)."""
    serializer_class = ExperimentSerializer

    def get_queryset(self):
        return Experiment.objects.filter(owner=self.request.user).select_related("strategy") \
            .prefetch_related("runs__strategy")

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        data = self.get_serializer(job).data
        data["runs"] = ExperimentRunSerializer(sorted(job.runs.all(), key=lambda r: r.id), many=True).data
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


def _experiment_summary(job):
    runs = list(job.runs.all())
    children = [r for r in runs if r.sample in ("in", "full")]
    out = {"id": job.id, "kind": job.kind, "status": experiment_status(job), "created_at": job.created_at,
           "runs_total": len(children), "runs_done": sum(r.status not in BacktestRun.ACTIVE for r in children)}
    if job.kind == Experiment.COMPARISON:
        n_strat, n_sym = len(job.config.get("strategies", [])), len(job.config.get("symbols", []))
        out["title"] = f"{n_strat} strateg{'y' if n_strat == 1 else 'ies'} × {n_sym} symbol{'s' if n_sym != 1 else ''}"
        out["symbols"] = job.config.get("symbols", [])
        return out
    oos = next((r for r in runs if r.sample == "out"), None)
    out.update({
        "title": job.strategy.name if job.strategy_id else "Optimization", "symbol": job.symbol,
        "strategy_name": job.strategy.name if job.strategy_id else None,
        "out_of_sample": None if oos is None else {
            "status": oos.status, "sharpe_ratio": oos.sharpe_ratio,
            "total_return": float(oos.final_value / oos.starting_cash - 1) if oos.final_value is not None else None,
            "buy_and_hold_return": oos.buy_and_hold_return, "grid_params": oos.grid_params,
            "stop_loss_pct": oos.stop_loss_pct, "take_profit_pct": oos.take_profit_pct}})
    return out


class DashboardView(Throttled, APIView):
    """Everything the dashboard shows, in one request. Deliberately no 'best by Sharpe' ranking (see D-022)."""

    @extend_schema(responses=DASHBOARD)
    def get(self, request):
        user = request.user
        runs = (BacktestRun.objects.filter(owner=user).select_related("strategy")
                .only("id", "strategy__name", "symbol", "status", "start_date", "end_date", "created_at",
                      "bars_processed", "bars_total", "final_value", "starting_cash", "buy_and_hold_return",
                      "sharpe_ratio", "failure_category", "experiment_id"))
        active = list(runs.filter(experiment__isnull=True, status__in=BacktestRun.ACTIVE).order_by("-created_at"))
        recent = list(runs.filter(experiment__isnull=True).exclude(status__in=BacktestRun.ACTIVE)
                      .order_by("-created_at")[:10])
        exps = list(Experiment.objects.filter(owner=user).select_related("strategy").prefetch_related(
            Prefetch("runs", queryset=BacktestRun.objects.only(
                "id", "experiment_id", "status", "sample", "sharpe_ratio", "final_value", "starting_cash",
                "buy_and_hold_return", "stop_loss_pct", "take_profit_pct", "grid_params")))
            .order_by("-created_at")[:5])
        strategies = Strategy.objects.filter(quotas.visible_strategies_q(user)).order_by("-is_builtin", "-created_at")
        return Response({
            "quota": {"tier": user.tier, "limits": quotas.limits(user), "usage": quotas.usage(user)},
            "active_runs": [_run_summary(r) for r in active],
            "recent_runs": [_run_summary(r) for r in recent],
            "experiments": [_experiment_summary(job) for job in exps],
            "strategies": [{"id": s.id, "name": s.name, "kind": s.kind, "is_builtin": s.is_builtin}
                           for s in strategies.only("id", "name", "kind", "is_builtin")[:20]],
            "custom_code_enabled": settings.VAULT["ALLOW_CUSTOM_CODE"],
        })
