import math
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import product

from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.quotas import visible_strategies_q
from backtester import costs, spec
from backtester.cache import downsample
from backtester.models import BacktestRun, Experiment, Strategy, Trade
from backtester.sandbox_runner import check_code

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,20}$")
D = Decimal
CURVE_POINTS = 500  # experiment pages: per-child equity curves are downsampled to about this many points


def pct(lo, hi, places=6, **kw):
    return serializers.DecimalField(max_digits=places + 4, decimal_places=places, min_value=D(lo), max_value=D(hi), **kw)


class TunableParamSerializer(serializers.Serializer):
    """Schema-only: one parameter an optimization can search (spec.tunable_params)."""
    label = serializers.CharField()
    indicator = serializers.CharField()
    name = serializers.CharField()
    type = serializers.ChoiceField(choices=["int", "float"])
    min = serializers.FloatField()
    max = serializers.FloatField()
    value = serializers.FloatField()
    paths = serializers.ListField(child=serializers.CharField())


class StrategySerializer(serializers.ModelSerializer):
    kind = serializers.ChoiceField(choices=Strategy.KIND_CHOICES, default=Strategy.CODE)
    code = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    spec = serializers.JSONField(required=False, allow_null=True)
    python = serializers.SerializerMethodField()
    warmup_bars = serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = ["id", "name", "kind", "code", "spec", "is_builtin", "created_at", "python", "warmup_bars",
                  "tunable_params"]
        read_only_fields = ["is_builtin"]

    tunable_params = serializers.SerializerMethodField()

    @extend_schema_field(TunableParamSerializer(many=True))
    def get_tunable_params(self, s):
        """What an optimization can vary (grouped by indicator instance). Empty for code strategies."""
        return spec.tunable_params(s.spec) if s.kind == Strategy.BUILDER and s.spec else []

    def get_python(self, s) -> str | None:
        return spec.render_python(s.spec) if s.kind == Strategy.BUILDER and s.spec else None

    def get_warmup_bars(self, s) -> int | None:
        return spec.warmup_bars(s.spec) if s.kind == Strategy.BUILDER and s.spec else None

    def validate_code(self, code):
        if len(code) > settings.VAULT["MAX_CODE_CHARS"]:
            raise serializers.ValidationError(f"Code is limited to {settings.VAULT['MAX_CODE_CHARS']} characters")
        err = check_code(code) if code else None
        if err:
            raise serializers.ValidationError(err)
        return code

    def validate(self, data):
        inst = self.instance
        kind = data.get("kind", inst.kind if inst else Strategy.CODE)
        if inst and kind != inst.kind:
            raise serializers.ValidationError({"kind": "A strategy's kind can't change; create a new strategy."})
        if kind == Strategy.BUILDER:
            if data.get("code"):
                raise serializers.ValidationError({"code": "Builder strategies are defined by a spec, not code."})
            if "spec" in data or not inst:
                if data.get("spec") is None:
                    raise serializers.ValidationError({"spec": "This field is required for builder strategies."})
                try:
                    data["spec"] = spec.validate(data["spec"])  # stored normalised: defaults filled in
                except spec.SpecError as e:
                    raise serializers.ValidationError({"spec": e.errors}) from None
            data["code"] = ""
        else:
            if data.get("spec") is not None:
                raise serializers.ValidationError({"spec": "Code strategies have no spec."})
            data.pop("spec", None)
            if not data.get("code", inst.code if inst else ""):
                raise serializers.ValidationError({"code": "This field is required for code strategies."})
        return data


class SpecPreviewSerializer(serializers.Serializer):
    spec = serializers.JSONField()

    def validate_spec(self, raw):
        try:
            return spec.validate(raw)
        except spec.SpecError as e:
            raise serializers.ValidationError(e.errors) from None


class TradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = ["id", "side", "ts", "price", "quantity", "commission", "slippage_cost", "cash_after", "reason"]


class _RangeMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only built-ins and the requester's own strategies can be referenced. Anything else fails as
        # "object does not exist", which doesn't reveal that another user's strategy has that id.
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return
        visible = Strategy.objects.filter(visible_strategies_q(request.user))
        field = self.fields.get("strategy")
        if field is not None and not field.read_only:
            field.queryset = visible
        many = self.fields.get("strategies")  # comparisons pick several
        if many is not None:
            many.child_relation.queryset = visible

    def validate_symbol(self, s):
        return _clean_symbol(s)

    def _validate_range(self, data):
        _check_dates(data)
        _check_runnable(data["strategy"], "strategy")
        _check_cost_model(data.get("cost_model", costs.FLAT), [data["symbol"]])


def _check_dates(data):
    start, end = data["start_date"], data["end_date"]
    if end <= start:
        raise serializers.ValidationError({"end_date": "end_date must be after start_date"})
    if end > datetime.now(UTC).date():
        raise serializers.ValidationError({"end_date": "end_date cannot be in the future"})
    if (end - start).days > settings.VAULT["MAX_RANGE_DAYS"]:
        raise serializers.ValidationError({"end_date": f"Range is limited to {settings.VAULT['MAX_RANGE_DAYS']} days"})


def _check_runnable(strategy, field):
    if not settings.VAULT["ALLOW_CUSTOM_CODE"] and strategy.kind == Strategy.CODE and not strategy.is_builtin:
        raise serializers.ValidationError(
            {field: f"Custom code can't run on this deployment ({strategy.name}); use a built-in or a builder strategy"})


def _check_cost_model(cost_model, symbols):
    if cost_model == costs.INDIA_DELIVERY and any(costs.currency(s) != "INR" for s in symbols):
        raise serializers.ValidationError(
            {"cost_model": "The India delivery cost model applies to NSE/BSE symbols (.NS, .BO, Indian indices)"})


def _clean_symbol(s):
    s = str(s).strip().upper()
    if not SYMBOL_RE.match(s):
        raise serializers.ValidationError(f"Invalid ticker format: {s}")
    return s


class CurrencyMixin(serializers.Serializer):
    currency = serializers.SerializerMethodField()

    def get_currency(self, obj) -> str | None:
        return costs.currency(obj.symbol)


class BacktestRunSerializer(_RangeMixin, CurrencyMixin, serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)
    strategy_kind = serializers.CharField(source="strategy.kind", read_only=True)
    starting_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=D(100), max_value=D(10_000_000))
    max_position_pct = pct("0.01", "1", default=D(1))
    # Flat model: the fee per fill. India delivery: the broker's brokerage; statutory charges are added on top.
    commission_pct = pct("0", "0.05", places=9, default=D("0.001"))
    sell_commission_pct = pct("0", "1", places=9, read_only=True)
    cost_model = serializers.ChoiceField(choices=list(costs.COST_MODELS), default=costs.FLAT)
    slippage_pct = pct("0", "0.05", default=D("0.0005"))
    stop_loss_pct = pct("0.001", "0.99", required=False, allow_null=True)
    take_profit_pct = pct("0.001", "10", required=False, allow_null=True)
    cost_drag = serializers.SerializerMethodField()

    class Meta:
        model = BacktestRun
        fields = [
            "id", "strategy", "strategy_name", "strategy_kind", "experiment", "sample", "priority", "grid_params",
            "symbol", "currency", "start_date", "end_date", "starting_cash", "max_position_pct", "cost_model",
            "commission_pct", "sell_commission_pct", "slippage_pct", "stop_loss_pct", "take_profit_pct",
            "status", "failure_category", "error_message", "attempts", "created_at", "started_at", "completed_at",
            "bars_total", "bars_processed", "execution_time_ms", "strategy_hash", "engine_version", "data_manifest",
            "final_value", "total_commission", "total_slippage", "cost_drag", "cagr", "sharpe_ratio", "sortino_ratio",
            "calmar_ratio", "max_drawdown", "win_rate", "exposure", "trade_count", "buy_and_hold_return",
            "request_id",
        ]
        read_only_fields = [f for f in fields if f not in {
            "strategy", "symbol", "start_date", "end_date", "starting_cash", "max_position_pct", "cost_model",
            "commission_pct", "slippage_pct", "stop_loss_pct", "take_profit_pct"}]

    def validate(self, data):
        self._validate_range(data)
        buy, sell = costs.rates(data.get("cost_model", costs.FLAT), data.get("commission_pct", D("0.001")))
        data["commission_pct"], data["sell_commission_pct"] = buy, sell
        sl, slip = data.get("stop_loss_pct"), data.get("slippage_pct", D("0.0005"))
        if sl is not None and sl <= slip:
            # Entry fills at open * (1 + slippage); a stop this tight sits above the open, so every entry
            # would be stopped out on its first bar.
            raise serializers.ValidationError({"stop_loss_pct": "stop_loss_pct must be greater than slippage_pct"})
        return data

    def get_cost_drag(self, run) -> float | None:
        """Commission plus slippage as a share of starting cash: how much return the costs ate."""
        if run.total_commission is None or not run.starting_cash:
            return None
        return float((run.total_commission + (run.total_slippage or 0)) / run.starting_cash)


class RunWithCurveSerializer(BacktestRunSerializer):
    class Meta(BacktestRunSerializer.Meta):
        fields = BacktestRunSerializer.Meta.fields + ["equity_curve"]
        read_only_fields = fields


class ExperimentRunSerializer(BacktestRunSerializer):
    """A child run inside an experiment page: every metric, plus the equity curve downsampled for charts (D-062)."""
    curve = serializers.SerializerMethodField()

    class Meta(BacktestRunSerializer.Meta):
        fields = BacktestRunSerializer.Meta.fields + ["curve"]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.ListField(), help_text="[[date, equity], ...]"))
    def get_curve(self, run):
        c = run.equity_curve or []
        if c and not isinstance(c[0], list):  # legacy v1 runs stored bare floats
            c = [[i, v] for i, v in enumerate(c)]
        return downsample(c, CURVE_POINTS)


class ExperimentSerializer(serializers.ModelSerializer):
    """Read view of an experiment, for lists and the detail page."""
    strategy_name = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Experiment
        fields = ["id", "kind", "strategy", "strategy_name", "symbol", "currency", "start_date", "end_date",
                  "split_date", "starting_cash", "cost_model", "stop_loss_options", "take_profit_options", "config",
                  "status", "request_id", "created_at"]
        read_only_fields = fields

    def get_strategy_name(self, job) -> str | None:
        return job.strategy.name if job.strategy_id else None

    def get_currency(self, job) -> str | None:
        found = {costs.currency(s) for s in ([job.symbol] if job.symbol else job.config.get("symbols", []))}
        return found.pop() if len(found) == 1 else None  # mixed or unknown: no single currency to show

    @extend_schema_field(serializers.ChoiceField(choices=["running", "completed", "partially_completed", "failed"]))
    def get_status(self, job):
        from backtester.jobs import experiment_status
        return experiment_status(job)


def _unique(values, field):
    if len(set(values)) != len(values):
        raise serializers.ValidationError({field: "Values must be unique"})


class ParamGridEntry(serializers.Serializer):
    """One searched parameter: every path where that indicator instance's parameter appears, and values to try."""
    paths = serializers.ListField(child=serializers.CharField(max_length=80), min_length=1, max_length=20)
    values = serializers.ListField(child=serializers.FloatField(), min_length=1, max_length=10)


class OptimizationCreateSerializer(_RangeMixin, serializers.Serializer):
    """POST /api/experiments/ with kind=optimization (also POST /api/optimizations/)."""
    kind = serializers.ChoiceField(choices=[Experiment.OPTIMIZATION], default=Experiment.OPTIMIZATION)
    strategy = serializers.PrimaryKeyRelatedField(queryset=Strategy.objects.none())
    symbol = serializers.CharField(max_length=20)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    starting_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=D(100), max_value=D(10_000_000))
    cost_model = serializers.ChoiceField(choices=list(costs.COST_MODELS), default=costs.FLAT)
    stop_loss_options = serializers.ListField(child=pct("0.001", "0.99"), min_length=1, max_length=10)
    take_profit_options = serializers.ListField(child=pct("0.001", "10"), min_length=1, max_length=10)
    param_grid = ParamGridEntry(many=True, required=False)

    def validate_symbol(self, s):
        return _clean_symbol(s)

    def validate(self, data):
        cfg = settings.VAULT
        self._validate_range(data)
        for f in ("stop_loss_options", "take_profit_options"):
            _unique(data[f], f)
        groups = self._param_groups(data["strategy"], data.get("param_grid") or [])
        n_params = math.prod(len(g["values"]) for g in groups)
        grid = n_params * len(data["stop_loss_options"]) * len(data["take_profit_options"])
        if grid > cfg["MAX_GRID"]:
            raise serializers.ValidationError(
                {"non_field_errors": [f"{grid} combinations requested; the limit is {cfg['MAX_GRID']}"]})
        days = (data["end_date"] - data["start_date"]).days
        if days < 120:
            raise serializers.ValidationError({"end_date": "Optimization needs at least 120 days for a train/test split"})
        data["split_date"] = data["start_date"] + timedelta(days=round(days * (1 - cfg["OOS_FRACTION"])))

        # Every parameter combination becomes its own spec, validated on its own. Combinations that are only invalid
        # together (MACD fast >= slow) are skipped and reported, not failed (D-057).
        combos, skipped = [], []
        for values in product(*[g["values"] for g in groups]):
            assigned = {g["label"]: v for g, v in zip(groups, values)}
            frozen = None
            if groups:
                try:
                    frozen = spec.validate(spec.with_params(
                        data["strategy"].spec, [(g["paths"], v) for g, v in zip(groups, values)]))
                except spec.SpecError as e:
                    # Linked paths report the same problem once each; say it once.
                    skipped.append({"params": assigned, "reason": "; ".join(dict.fromkeys(e.errors.values()))})
                    continue
            combos.append((assigned, frozen))
        if not combos:
            raise serializers.ValidationError({"param_grid": "Every combination is invalid; see the parameter limits"})
        data["param_grid"], data["combos"], data["skipped"] = groups, combos, skipped
        for f in ("stop_loss_options", "take_profit_options"):
            data[f] = [str(x) for x in data[f]]  # JSONField cannot hold Decimal; strings keep exact values
        return data

    def _param_groups(self, strategy, entries):
        if not entries:
            return []
        if strategy.kind != Strategy.BUILDER:
            raise serializers.ValidationError(
                {"param_grid": "Only builder strategies have parameters to search; code strategies search stop-loss "
                               "and take-profit only"})
        if len(entries) > settings.VAULT["MAX_GRID_PARAMS"]:
            raise serializers.ValidationError(
                {"param_grid": f"At most {settings.VAULT['MAX_GRID_PARAMS']} parameters can be searched at once"})
        tunable = {tuple(g["paths"]): g for g in spec.tunable_params(strategy.spec)}
        groups, errors = [], {}
        for entry in entries:
            g = tunable.get(tuple(entry["paths"]))
            if g is None:
                raise serializers.ValidationError(
                    {"param_grid": f"{entry['paths']} isn't one parameter of this strategy (use its tunable_params)"})
            if any(x["label"] == g["label"] for x in groups):
                raise serializers.ValidationError({"param_grid": f"{g['label']} is listed twice"})
            values = entry["values"]
            if g["type"] == "int":
                if any(not float(v).is_integer() for v in values):
                    errors[g["label"]] = "must be whole numbers"
                    continue
                values = [int(v) for v in values]
            if len(set(values)) != len(values):
                errors[g["label"]] = "values must be unique"
                continue
            for v in values:  # a value out of range is the request's mistake: reject, with the parameter named
                try:
                    spec.validate(spec.with_params(strategy.spec, [(g["paths"], v)]))
                except spec.SpecError as e:
                    own = [m for p, m in e.errors.items() if p in g["paths"]]
                    if own:
                        errors[g["label"]] = f"{v}: {own[0]}"
                        break
            groups.append({"label": g["label"], "paths": g["paths"], "values": values})
        if errors:
            raise serializers.ValidationError({"param_grid": errors})
        return groups


class ComparisonCreateSerializer(_RangeMixin, serializers.Serializer):
    """POST /api/experiments/ with kind=comparison: strategies × symbols over one period and cost setup (D-056)."""
    kind = serializers.ChoiceField(choices=[Experiment.COMPARISON])
    strategies = serializers.PrimaryKeyRelatedField(many=True, queryset=Strategy.objects.none(), allow_empty=False)
    symbols = serializers.ListField(child=serializers.CharField(max_length=20), min_length=1)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    starting_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=D(100), max_value=D(10_000_000))
    cost_model = serializers.ChoiceField(choices=list(costs.COST_MODELS), default=costs.FLAT)
    commission_pct = pct("0", "0.05", places=9, default=D("0.001"))
    slippage_pct = pct("0", "0.05", default=D("0.0005"))
    stop_loss_pct = pct("0.001", "0.99", required=False, allow_null=True)
    take_profit_pct = pct("0.001", "10", required=False, allow_null=True)

    def validate_symbols(self, symbols):
        out = [_clean_symbol(s) for s in symbols]
        if len(out) > settings.VAULT["MAX_COMPARE_SYMBOLS"]:
            raise serializers.ValidationError(f"At most {settings.VAULT['MAX_COMPARE_SYMBOLS']} symbols")
        if len(set(out)) != len(out):
            raise serializers.ValidationError("Symbols must be unique")
        return out

    def validate_strategies(self, strategies):
        if len(strategies) > settings.VAULT["MAX_COMPARE_STRATEGIES"]:
            raise serializers.ValidationError(f"At most {settings.VAULT['MAX_COMPARE_STRATEGIES']} strategies")
        if len({s.id for s in strategies}) != len(strategies):
            raise serializers.ValidationError("Strategies must be unique")
        return strategies

    def validate(self, data):
        _check_dates(data)
        for s in data["strategies"]:
            _check_runnable(s, "strategies")
        _check_cost_model(data["cost_model"], data["symbols"])
        cells = len(data["strategies"]) * len(data["symbols"])
        if cells > settings.VAULT["MAX_GRID"]:
            raise serializers.ValidationError(
                {"non_field_errors": [f"{cells} strategy × symbol cells requested; the limit is "
                                      f"{settings.VAULT['MAX_GRID']}"]})
        sl, slip = data.get("stop_loss_pct"), data["slippage_pct"]
        if sl is not None and sl <= slip:
            raise serializers.ValidationError({"stop_loss_pct": "stop_loss_pct must be greater than slippage_pct"})
        data["commission_pct"], data["sell_commission_pct"] = costs.rates(data["cost_model"], data["commission_pct"])
        return data
