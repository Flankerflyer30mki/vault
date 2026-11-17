from django.conf import settings
from rest_framework import serializers

from assist.models import AssistRequest


class AssistCreateSerializer(serializers.Serializer):
    prompt = serializers.CharField(trim_whitespace=True)

    def validate_prompt(self, value):
        limit = settings.AI["MAX_PROMPT_CHARS"]
        if len(value) > limit:
            raise serializers.ValidationError(f"Keep the description under {limit} characters (it has {len(value)}).")
        if len(value) < 10:
            raise serializers.ValidationError("Describe the strategy in a sentence or two.")
        return value


class AssistRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistRequest
        fields = ["id", "prompt", "status", "outcome", "result", "error_message", "model", "cached", "llm_calls",
                  "repair_rounds", "latency_ms", "request_id", "created_at", "completed_at"]
        read_only_fields = fields
