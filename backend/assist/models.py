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


class ResearchRun(models.Model):
    """An AI research run (Phase 5, D-088): a goal on one symbol, researched by the agent on the in-sample part of the
    period and tested once by our code on the held-out part. It is a resumable state machine on the job queue: each
    `queued → running` turn is one short step; after queueing backtests it waits (`waiting`) and the worker re-queues
    it when they finish, so no worker is held while backtests run.

    stage: explore → refine → validate → report → done. `state` holds the agent's memory: the candidates tested
    (spec, run ID, in-sample metrics) and the last error it must fix."""
    QUEUED, RUNNING, WAITING, COMPLETED, FAILED = "queued", "running", "waiting", "completed", "failed"
    STATUS_CHOICES = [(s, s) for s in (QUEUED, RUNNING, WAITING, COMPLETED, FAILED)]
    ACTIVE = (QUEUED, RUNNING, WAITING)
    EXPLORE, REFINE, VALIDATE, REPORT, DONE = "explore", "refine", "validate", "report", "done"
    STAGE_CHOICES = [(s, s) for s in (EXPLORE, REFINE, VALIDATE, REPORT, DONE)]
    OBJECTIVES = ("sharpe_ratio", "calmar_ratio", "total_return")

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="research_runs")
    goal = models.TextField()
    symbol = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    # Research (in-sample): start_date .. split_date - 1 day. Held out: split_date .. end_date, run once by code.
    split_date = models.DateField()
    objective = models.CharField(max_length=20, default="sharpe_ratio")
    max_drawdown = models.FloatField(null=True, blank=True)  # constraint, as a fraction (0.25 = 25%)
    starting_cash = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    cost_model = models.CharField(max_length=20, default="flat")

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=QUEUED)
    stage = models.CharField(max_length=16, choices=STAGE_CHOICES, default=EXPLORE)
    state = models.JSONField(default=dict, blank=True)
    # The round being waited for, and the one held-out round (OneToOne: a research run can't test twice).
    current_experiment = models.ForeignKey("backtester.Experiment", null=True, blank=True, on_delete=models.SET_NULL,
                                           related_name="+")
    holdout_experiment = models.OneToOneField("backtester.Experiment", null=True, blank=True,
                                              on_delete=models.SET_NULL, related_name="+")
    report = models.JSONField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")

    steps_used = models.PositiveSmallIntegerField(default=0)
    model_calls = models.PositiveSmallIntegerField(default=0)
    backtests_used = models.PositiveSmallIntegerField(default=0)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    model = models.CharField(max_length=100, blank=True, default="")

    attempts = models.PositiveSmallIntegerField(default=0)
    worker_id = models.CharField(max_length=100, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default=current_request_id)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)  # of the current step
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "id"], name="idx_research_claim")]

    def __str__(self):
        return f"ResearchRun {self.id} ({self.status}/{self.stage})"


class ResearchStep(models.Model):
    """One entry in a research run's timeline: an agent decision (with its reason), a rejected action, or something
    our code did (holdout test, report). What the UI shows and what the process checks read."""
    run = models.ForeignKey(ResearchRun, on_delete=models.CASCADE, related_name="steps")
    index = models.PositiveSmallIntegerField()
    stage = models.CharField(max_length=16)
    actor = models.CharField(max_length=8)  # "agent" or "system"
    action = models.CharField(max_length=32)
    args = models.JSONField(null=True, blank=True)
    note = models.CharField(max_length=600, blank=True, default="")  # the agent's reason, or what the system did
    result = models.JSONField(null=True, blank=True)
    ok = models.BooleanField(default=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run_id", "index"]
        constraints = [models.UniqueConstraint(fields=["run", "index"], name="uq_research_step_index")]
