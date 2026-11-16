import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from accounts.quotas import visible_strategies_q
from backtester import costs, spec
from backtester.models import BacktestRun, OptimizationJob, Strategy, Trade
from backtester.sandbox_runner import check_code

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,20}$")
D = Decimal


def pct(lo, hi, places=6, **kw):
    return serializers.DecimalField(max_digits=places + 4, decimal_places=places, min_value=D(lo), max_value=D(hi), **kw)


class StrategySerializer(serializers.ModelSerializer):
    kind = serializers.ChoiceField(choices=Strategy.KIND_CHOICES, default=Strategy.CODE)
    code = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    spec = serializers.JSONField(required=False, allow_null=True)
    python = serializers.SerializerMethodField()
    warmup_bars = serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = ["id", "name", "kind", "code", "spec", "is_builtin", "created_at", "python", "warmup_bars"]
        read_only_fields = ["is_builtin"]

    def get_python(self, s):
        return spec.render_python(s.spec) if s.kind == Strategy.BUILDER and s.spec else None

    def get_warmup_bars(self, s):
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
        field = self.fields.get("strategy")
        if request is not None and field is not None and not field.read_only and request.user.is_authenticated:
            field.queryset = Strategy.objects.filter(visible_strategies_q(request.user))

    def validate_symbol(self, s):
        s = s.strip().upper()
        if not SYMBOL_RE.match(s):
            raise serializers.ValidationError("Invalid ticker format")
        return s

    def _validate_range(self, data):
        start, end = data["start_date"], data["end_date"]
        if end <= start:
            raise serializers.ValidationError({"end_date": "end_date must be after start_date"})
        if end > datetime.now(UTC).date():
            raise serializers.ValidationError({"end_date": "end_date cannot be in the future"})
        if (end - start).days > settings.VAULT["MAX_RANGE_DAYS"]:
            raise serializers.ValidationError({"end_date": f"Range is limited to {settings.VAULT['MAX_RANGE_DAYS']} days"})
        strategy = data["strategy"]
        if (not settings.VAULT["ALLOW_CUSTOM_CODE"] and strategy.kind == Strategy.CODE
                and not strategy.is_builtin):
            raise serializers.ValidationError(
                {"strategy": "Custom code can't run on this deployment; use a built-in or a builder strategy"})
        if data.get("cost_model", costs.FLAT) == costs.INDIA_DELIVERY and costs.currency(data["symbol"]) != "INR":
            raise serializers.ValidationError(
                {"cost_model": "The India delivery cost model applies to NSE/BSE symbols (.NS, .BO, Indian indices)"})


class CurrencyMixin(serializers.Serializer):
    currency = serializers.SerializerMethodField()

    def get_currency(self, obj):
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

    class Meta:
        model = BacktestRun
        fields = [
            "id", "strategy", "strategy_name", "strategy_kind", "optimization", "sample", "symbol", "currency",
            "start_date", "end_date", "starting_cash", "max_position_pct", "cost_model", "commission_pct",
            "sell_commission_pct", "slippage_pct", "stop_loss_pct", "take_profit_pct", "status", "failure_category", "error_message", "attempts", "created_at", "started_at", "completed_at",
            "bars_total", "bars_processed", "execution_time_ms", "strategy_hash", "engine_version", "data_manifest",
            "final_value", "total_commission", "total_slippage", "cagr", "sharpe_ratio", "max_drawdown",
            "win_rate", "buy_and_hold_return",
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


class RunWithCurveSerializer(BacktestRunSerializer):
    class Meta(BacktestRunSerializer.Meta):
        fields = BacktestRunSerializer.Meta.fields + ["equity_curve"]
        read_only_fields = fields


class OptimizationJobSerializer(_RangeMixin, CurrencyMixin, serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)
    cost_model = serializers.ChoiceField(choices=list(costs.COST_MODELS), default=costs.FLAT)
    starting_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=D(100), max_value=D(10_000_000))
    stop_loss_options = serializers.ListField(child=pct("0.001", "0.99"), min_length=1, max_length=10)
    take_profit_options = serializers.ListField(child=pct("0.001", "10"), min_length=1, max_length=10)
    status = serializers.SerializerMethodField()

    class Meta:
        model = OptimizationJob
        fields = ["id", "strategy", "strategy_name", "symbol", "currency", "start_date", "end_date", "split_date",
                  "starting_cash", "cost_model", "stop_loss_options", "take_profit_options", "status", "created_at"]
        read_only_fields = ["split_date"]

    def get_status(self, job):
        from backtester.jobs import optimization_status
        return optimization_status(job)

    def validate(self, data):
        self._validate_range(data)
        for f in ("stop_loss_options", "take_profit_options"):
            if len(set(data[f])) != len(data[f]):
                raise serializers.ValidationError({f: "Values must be unique"})
        grid = len(data["stop_loss_options"]) * len(data["take_profit_options"])
        if grid > settings.VAULT["MAX_GRID"]:
            raise serializers.ValidationError(
                {"non_field_errors": [f"{grid} combinations requested; the limit is {settings.VAULT['MAX_GRID']}"]})
        days = (data["end_date"] - data["start_date"]).days
        if days < 120:
            raise serializers.ValidationError({"end_date": "Optimization needs at least 120 days for a train/test split"})
        data["split_date"] = data["start_date"] + timedelta(days=round(days * (1 - settings.VAULT["OOS_FRACTION"])))
        for f in ("stop_loss_options", "take_profit_options"):
            data[f] = [str(x) for x in data[f]]  # JSONField cannot hold Decimal; strings keep exact values
        return data
