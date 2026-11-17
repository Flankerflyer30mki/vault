from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import quotas
from assist import jobs, prompts, providers
from assist.models import AssistRequest
from assist.serializers import AssistCreateSerializer, AssistRequestSerializer
from backtester.views import Throttled


class AIUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "ai_unavailable"


class AssistStrategyView(Throttled, APIView):
    """Describe a strategy in words; the worker asks the AI for a builder spec (D-077, D-078). Returns the request, which
    the client polls. Nothing is saved as a strategy: the client loads the spec into the builder form for review."""
    write_scope = "jobs"

    @extend_schema(request=AssistCreateSerializer, responses={201: AssistRequestSerializer})
    def post(self, request):
        if not providers.enabled():
            raise AIUnavailable(jobs.NOT_CONFIGURED)
        ser = AssistCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        text = ser.validated_data["prompt"]
        h = jobs.prompt_hash(text, settings.AI["MODEL"])
        with transaction.atomic():
            # Same pattern as job creation: the user's row lock makes the per-user checks exact.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            quotas.check_ai(request.user)
            if (hit := jobs.cached_answer(h)) is not None:
                now = timezone.now()
                req = AssistRequest.objects.create(
                    owner=request.user, prompt=text, prompt_hash=h, status=AssistRequest.COMPLETED,
                    outcome=hit.outcome, result=hit.result, provider=hit.provider, model=hit.model,
                    prompt_version=prompts.PROMPT_VERSION, cached=True, latency_ms=0, started_at=now, completed_at=now)
            else:
                if jobs.over_budget():
                    raise AIUnavailable(jobs.OVER_BUDGET)
                if AssistRequest.objects.filter(status=AssistRequest.QUEUED).count() >= settings.AI["MAX_QUEUED"]:
                    raise AIUnavailable("The AI queue is full. Try again in a minute.")
                req = AssistRequest.objects.create(owner=request.user, prompt=text, prompt_hash=h)
        return Response(AssistRequestSerializer(req).data, status=status.HTTP_201_CREATED)


class AssistDetailView(Throttled, generics.RetrieveAPIView):
    serializer_class = AssistRequestSerializer

    def get_queryset(self):
        return AssistRequest.objects.filter(owner=self.request.user)
