import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from backtester.models import BacktestRun, OptimizationJob, Strategy, Trade
from backtester.sandbox_runner import check_code

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,20}$")
D = Decimal


def pct(lo, hi, **kw):
    return serializers.DecimalField(max_digits=10, decimal_places=6, min_value=D(lo), max_value=D(hi), **kw)


class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = ["id", "name", "code", "is_builtin", "created_at"]
        read_only_fields = ["is_builtin"]

    def validate_code(self, code):
        if len(code) > settings.VAULT["MAX_CODE_CHARS"]:
            raise serializers.ValidationError(f"Code is limited to {settings.VAULT['MAX_CODE_CHARS']} characters")
        err = check_code(code)
        if err:
            raise serializers.ValidationError(err)
        return code


class TradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = ["id", "side", "ts", "price", "quantity", "commission", "slippage_cost", "cash_after", "reason"]


class _RangeMixin:
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
        if not settings.VAULT["ALLOW_CUSTOM_CODE"] and not data["strategy"].is_builtin:
            raise serializers.ValidationError({"strategy": "Only built-in strategies can run on this deployment"})


class BacktestRunSerializer(_RangeMixin, serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)
    starting_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=D(100), max_value=D(10_000_000))
    max_position_pct = pct("0.01", "1", default=D(1))
    commission_pct = pct("0", "0.05", default=D("0.001"))
    slippage_pct = pct("0", "0.05", default=D("0.0005"))
    stop_loss_pct = pct("0.001", "0.99", required=False, allow_null=True)
    take_profit_pct = pct("0.001", "10", required=False, allow_null=True)

    class Meta:
        model = BacktestRun
        fields = [
            "id", "strategy", "strategy_name", "optimization", "sample", "symbol", "start_date", "end_date",
            "starting_cash", "max_position_pct", "commission_pct", "slippage_pct", "stop_loss_pct", "take_profit_pct",
            "status", "failure_category", "error_message", "attempts", "created_at", "started_at", "completed_at",
            "bars_total", "bars_processed", "execution_time_ms", "strategy_hash", "engine_version", "data_manifest",
            "final_value", "total_commission", "total_slippage", "cagr", "sharpe_ratio", "max_drawdown",
            "win_rate", "buy_and_hold_return",
        ]
        read_only_fields = [f for f in fields if f not in {
            "strategy", "symbol", "start_date", "end_date", "starting_cash", "max_position_pct",
            "commission_pct", "slippage_pct", "stop_loss_pct", "take_profit_pct"}]

    def validate(self, data):
        self._validate_range(data)
        return data


class RunWithCurveSerializer(BacktestRunSerializer):
    class Meta(BacktestRunSerializer.Meta):
        fields = BacktestRunSerializer.Meta.fields + ["equity_curve"]
        read_only_fields = fields


class OptimizationJobSerializer(_RangeMixin, serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)
    starting_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=D(100), max_value=D(10_000_000))
    stop_loss_options = serializers.ListField(child=pct("0.001", "0.99"), min_length=1, max_length=10)
    take_profit_options = serializers.ListField(child=pct("0.001", "10"), min_length=1, max_length=10)
    status = serializers.SerializerMethodField()

    class Meta:
        model = OptimizationJob
        fields = ["id", "strategy", "strategy_name", "symbol", "start_date", "end_date", "split_date",
                  "starting_cash", "stop_loss_options", "take_profit_options", "status", "created_at"]
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
