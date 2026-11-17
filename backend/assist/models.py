from django.conf import settings
from django.db import models

from vault_core.observability import current_request_id


class AssistRequest(models.Model):
    """One AI request, and also its job (D-078): the API inserts it as `queued`, a worker claims it with SKIP LOCKED,
    calls the model and stores the outcome. Same pattern as BacktestRun."""
    QUEUED, RUNNING, COMPLETED, FAILED = "queued", "running", "completed", "failed"
    STATUS_CHOICES = [(s, s) for s in (QUEUED, RUNNING, COMPLETED, FAILED)]
    ACTIVE = (QUEUED, RUNNING)
    # Outcome of a completed or failed request.
    SPEC, UNSUPPORTED, INVALID, UNAVAILABLE = "spec", "unsupported", "invalid", "unavailable"
    OUTCOME_CHOICES = [("", "")] + [(o, o) for o in (SPEC, UNSUPPORTED, INVALID, UNAVAILABLE)]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assist_requests")
    prompt = models.TextField()
    # sha256 of the normalised prompt + prompt version + model: identical descriptions reuse an earlier answer (D-081).
    prompt_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=QUEUED)
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES, blank=True, default="")
    # spec outcome: {"spec", "name", "notes"}; unsupported: {"reason"}; invalid: {"errors"}.
    result = models.JSONField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")
    provider = models.CharField(max_length=32, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.CharField(max_length=16, blank=True, default="")
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    llm_calls = models.PositiveSmallIntegerField(default=0)
    repair_rounds = models.PositiveSmallIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    cached = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    worker_id = models.CharField(max_length=100, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default=current_request_id)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "id"], name="idx_assist_claim")]

    def __str__(self):
        return f"AssistRequest {self.id} ({self.status})"
