from datetime import date, timedelta

from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from assist.models import AssistRequest, ResearchRun, ResearchStep
from backtester import costs
from backtester.serializers import _check_cost_model, _check_dates, _clean_symbol


class AssistCreateSerializer(serializers.Serializer):
    prompt = serializers.CharField(trim_whitespace=True)

    def validate_prompt(self, value):
        limit = settings.AI["MAX_PROMPT_CHARS"]
        if len(value) > limit:
            raise serializers.ValidationError(f"Keep the description under {limit} characters (it has {len(value)}).")
        if len(value) < 10:
            raise serializers.ValidationError("Describe the strategy in a sentence or two.")
        return value


class ResearchCreateSerializer(serializers.Serializer):
    goal = serializers.CharField(trim_whitespace=True)
    symbol = serializers.CharField(max_length=20)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    objective = serializers.ChoiceField(choices=list(ResearchRun.OBJECTIVES), default="sharpe_ratio")
    max_drawdown_pct = serializers.FloatField(required=False, allow_null=True, min_value=1, max_value=100)
    starting_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=100, max_value=10_000_000,
                                             default=10000)
    cost_model = serializers.ChoiceField(choices=list(costs.COST_MODELS), default=costs.FLAT)

    def validate_goal(self, value):
        limit = settings.AI["MAX_PROMPT_CHARS"]
        if len(value) > limit:
            raise serializers.ValidationError(f"Keep the goal under {limit} characters (it has {len(value)}).")
        if len(value) < 10:
            raise serializers.ValidationError("Describe what you're looking for in a sentence or two.")
        return value

    def validate_symbol(self, s):
        return _clean_symbol(s)

    def validate(self, data):
        _check_dates(data)
        _check_cost_model(data["cost_model"], [data["symbol"]])
        days = (data["end_date"] - data["start_date"]).days
        if days < settings.RESEARCH["MIN_DAYS"]:
            raise serializers.ValidationError(
                {"end_date": f"Research needs at least {settings.RESEARCH['MIN_DAYS']} days, so both the research "
                             "and the held-out part have enough data."})
        # The held-out tail is the same share as an optimization's out-of-sample part (OOS_FRACTION, 30%).
        data["split_date"] = data["start_date"] + timedelta(days=round(days * (1 - settings.VAULT["OOS_FRACTION"])))
        return data


class ResearchStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchStep
        fields = ["index", "stage", "actor", "action", "args", "note", "result", "ok", "tokens_in", "tokens_out",
                  "latency_ms", "created_at"]
        read_only_fields = fields


class ResearchCandidateSerializer(serializers.Serializer):
    """Schema only: one candidate the agent tested, with its in-sample result."""
    id = serializers.CharField()
    name = serializers.CharField()
    spec = serializers.JSONField()
    rules = serializers.CharField()
    run_id = serializers.IntegerField()
    round = serializers.IntegerField()
    stage = serializers.CharField()
    status = serializers.CharField()
    metrics = serializers.DictField(allow_null=True)
    eligible = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)


class ResearchRunSerializer(serializers.ModelSerializer):
    research_end = serializers.SerializerMethodField()
    budgets = serializers.SerializerMethodField()

    class Meta:
        model = ResearchRun
        fields = ["id", "goal", "symbol", "start_date", "end_date", "split_date", "research_end", "objective",
                  "max_drawdown", "starting_cash", "cost_model", "status", "stage", "error_message", "steps_used",
                  "model_calls", "backtests_used", "tokens_in", "tokens_out", "budgets", "model", "request_id",
                  "created_at", "completed_at"]
        read_only_fields = fields

    def get_research_end(self, obj) -> date:
        return obj.split_date - timedelta(days=1)

    def get_budgets(self, obj) -> dict:
        c = settings.RESEARCH
        return {"steps": c["MAX_STEPS"], "backtests": c["MAX_BACKTESTS"], "tokens": c["MAX_TOKENS"],
                "model_calls": c["MAX_MODEL_CALLS"]}


class ResearchDetailSerializer(ResearchRunSerializer):
    steps = ResearchStepSerializer(many=True, read_only=True)
    candidates = serializers.SerializerMethodField()
    report = serializers.JSONField(read_only=True)

    class Meta(ResearchRunSerializer.Meta):
        fields = ResearchRunSerializer.Meta.fields + ["steps", "candidates", "report"]
        read_only_fields = fields

    @extend_schema_field(ResearchCandidateSerializer(many=True))
    def get_candidates(self, obj):
        from assist import agent, research
        return [{**c, "rules": agent.describe(c["spec"])} for c in research.candidates(obj)]


class AssistRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistRequest
        fields = ["id", "prompt", "status", "outcome", "result", "error_message", "model", "cached", "llm_calls",
                  "repair_rounds", "latency_ms", "request_id", "created_at", "completed_at"]
        read_only_fields = fields
