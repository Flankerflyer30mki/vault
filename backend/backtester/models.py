from django.conf import settings
from django.db import models

from vault_core.observability import current_request_id

PCT = dict(max_digits=10, decimal_places=6)
FEE = dict(max_digits=12, decimal_places=9)  # India's statutory charges need 9 places (0.001186226)
COST_MODEL_CHOICES = [("flat", "flat"), ("india_delivery", "india_delivery")]


class Bar(models.Model):
    """Daily OHLCV, adjusted (yfinance auto_adjust=True). ts = midnight UTC of the trading date."""
    symbol = models.CharField(max_length=20, db_index=True)
    ts = models.DateTimeField(db_index=True)
    open = models.DecimalField(max_digits=12, decimal_places=4)
    high = models.DecimalField(max_digits=12, decimal_places=4)
    low = models.DecimalField(max_digits=12, decimal_places=4)
    close = models.DecimalField(max_digits=12, decimal_places=4)
    volume = models.BigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["symbol", "ts"], name="uq_bar_symbol_ts")]

    def __str__(self):
        return f"{self.symbol} @ {self.ts}"


class SymbolCoverage(models.Model):
    """Date span already requested from the provider for a symbol. Within this span the stored bars are
    whatever the provider has (late listings and market closures included), so they are not fetched again."""
    symbol = models.CharField(max_length=20, unique=True)
    start = models.DateField()
    until = models.DateField()  # last date that was complete when fetched (before the fetch day)
    fetched_at = models.DateTimeField()

    def __str__(self):
        return f"{self.symbol} {self.start}..{self.until}"


class Strategy(models.Model):
    CODE, BUILDER = "code", "builder"
    KIND_CHOICES = [(CODE, "code"), (BUILDER, "builder")]

    # Built-ins are shared and have no owner; every other strategy belongs to exactly one user.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                              related_name="strategies")
    name = models.CharField(max_length=100)
    # A code strategy has Python run in the sandbox; a builder strategy has a JSON spec interpreted by spec.py.
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=CODE)
    code = models.TextField(blank=True, default="")
    spec = models.JSONField(null=True, blank=True)
    is_builtin = models.BooleanField(default=False)  # pre-approved; runnable when custom code is disabled
    # Hidden built-ins never appear in lists or accept runs from users. The one in use is "AI research candidate"
    # (migration 0022): the strategy row behind research runs, each of which carries its own frozen spec.
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(is_builtin=True, owner__isnull=True) | models.Q(is_builtin=False, owner__isnull=False),
                name="ck_strategy_builtin_xor_owner"),
            models.CheckConstraint(
                condition=(models.Q(kind="code", spec__isnull=True) & ~models.Q(code=""))
                | models.Q(kind="builder", spec__isnull=False, code=""),
                name="ck_strategy_kind_body"),
        ]

    def __str__(self):
        return self.name


class Experiment(models.Model):
    """A batch of child runs (fan-out) whose result is read from all of them together (fan-in).
    Status is derived from the child runs, never stored.

    - optimization: one strategy on one symbol; a grid (spec parameters × stop-loss × take-profit) runs on the in-sample
      period, then the best combination runs once on the untouched out-of-sample tail.
    - comparison: strategies × symbols over the same period and costs, plus an index benchmark per currency.
    - research: one round of an AI research run (Phase 5): the agent's candidates on the in-sample period, or the
      single held-out run. Shown on the research page, not in experiment lists.
    """
    OPTIMIZATION, COMPARISON, RESEARCH = "optimization", "comparison", "research"
    KIND_CHOICES = [(OPTIMIZATION, "optimization"), (COMPARISON, "comparison"), (RESEARCH, "research")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="experiments")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=OPTIMIZATION)
    # Optimization only: the strategy and symbol searched. A comparison lists its own in `config`.
    strategy = models.ForeignKey(Strategy, null=True, blank=True, on_delete=models.CASCADE, related_name="experiments")
    symbol = models.CharField(max_length=20, blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField()
    split_date = models.DateField(null=True)  # optimization: in-sample < split_date <= out-of-sample
    starting_cash = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    stop_loss_options = models.JSONField(default=list)
    take_profit_options = models.JSONField(default=list)
    cost_model = models.CharField(max_length=20, choices=COST_MODEL_CHOICES, default="flat")
    # comparison: {"strategies": [ids], "symbols": [...]}; optimization: {"param_grid": {path: [values]},
    # "skipped": [{"params": {...}, "reason": "..."}]}
    config = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True, default=current_request_id)  # the request that created it
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Keys are scoped per user: one user's key must never match (and return) another user's job.
        constraints = [models.UniqueConstraint(fields=["owner", "idempotency_key"], name="uq_opt_owner_idem_key")]
        indexes = [models.Index(fields=["owner", "-created_at"], name="idx_opt_owner_created")]

    def __str__(self):
        return f"Experiment {self.id} ({self.kind})"


class BacktestRun(models.Model):
    QUEUED, PREPARING, RUNNING, COMPLETED, FAILED = "queued", "preparing_data", "running", "completed", "failed"
    STATUS_CHOICES = [(s, s) for s in (QUEUED, PREPARING, RUNNING, COMPLETED, FAILED)]
    ACTIVE = (QUEUED, PREPARING, RUNNING)
    SAMPLE_CHOICES = [("full", "full"), ("in", "in-sample"), ("out", "out-of-sample"), ("bench", "benchmark")]
    # Claim order is (priority, id): runs a person starts by hand go before batch children (D-059).
    INTERACTIVE, BATCH = 0, 1

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="runs")
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="runs")
    experiment = models.ForeignKey(Experiment, null=True, blank=True, on_delete=models.CASCADE, related_name="runs")
    sample = models.CharField(max_length=10, choices=SAMPLE_CHOICES, default="full")
    priority = models.PositiveSmallIntegerField(default=INTERACTIVE)
    grid_params = models.JSONField(null=True, blank=True)  # optimization child: the values this run tried
    # The API request that created this run (D-070); the worker logs the run under the same ID. Runs the worker itself
    # creates (an optimization's out-of-sample run) inherit the ID of the run being processed.
    request_id = models.CharField(max_length=64, blank=True, default=current_request_id)
    symbol = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    starting_cash = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    max_position_pct = models.DecimalField(default=1, **PCT)
    commission_pct = models.DecimalField(default="0.001", **FEE)  # buy side (and sell side unless set below)
    sell_commission_pct = models.DecimalField(null=True, blank=True, **FEE)
    cost_model = models.CharField(max_length=20, choices=COST_MODEL_CHOICES, default="flat")
    slippage_pct = models.DecimalField(default="0.0005", **PCT)
    stop_loss_pct = models.DecimalField(null=True, blank=True, **PCT)
    take_profit_pct = models.DecimalField(null=True, blank=True, **PCT)

    # Reproducibility: exact code or spec, engine and data used.
    strategy_code = models.TextField(blank=True, default="")
    strategy_spec = models.JSONField(null=True, blank=True)  # set for builder strategies, frozen at creation
    strategy_hash = models.CharField(max_length=64, blank=True, default="")
    engine_version = models.CharField(max_length=20, blank=True, default="")
    data_manifest = models.JSONField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)

    # Durable job state. The table is the queue (SELECT ... FOR UPDATE SKIP LOCKED).
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=QUEUED)
    failure_category = models.CharField(max_length=20, blank=True, default="")  # data|strategy|infrastructure
    error_message = models.TextField(blank=True, null=True)
    attempts = models.IntegerField(default=0)
    worker_id = models.CharField(max_length=64, blank=True, default="")
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    bars_total = models.IntegerField(null=True, blank=True)
    bars_processed = models.IntegerField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)

    # Results, all derived from the simulation ledger.
    final_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_commission = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    total_slippage = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    cagr = models.FloatField(null=True, blank=True)
    sharpe_ratio = models.FloatField(null=True, blank=True)
    max_drawdown = models.FloatField(null=True, blank=True)
    win_rate = models.FloatField(null=True, blank=True)
    buy_and_hold_return = models.FloatField(null=True, blank=True)
    sortino_ratio = models.FloatField(null=True, blank=True)
    calmar_ratio = models.FloatField(null=True, blank=True)
    exposure = models.FloatField(null=True, blank=True)  # share of bars ending in the market
    trade_count = models.IntegerField(null=True, blank=True)  # closed round trips
    equity_curve = models.JSONField(null=True, blank=True)  # [[date, value], ...]

    class Meta:
        indexes = [models.Index(fields=["status", "priority", "id"], name="idx_run_claim"),  # claim + admission count
                   models.Index(fields=["owner", "-created_at"], name="idx_run_owner_created")]  # lists + quotas
        constraints = [models.UniqueConstraint(fields=["experiment"], condition=models.Q(sample="out"),
                                               name="uq_run_one_oos_per_experiment"),
                       models.UniqueConstraint(fields=["owner", "idempotency_key"], name="uq_run_owner_idem_key")]

    def __str__(self):
        return f"Run {self.id} - {self.symbol} ({self.status})"


class Trade(models.Model):
    SIDE_CHOICES = [("BUY", "Buy"), ("SELL", "Sell")]

    run = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name="trades")
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    ts = models.DateTimeField()
    price = models.DecimalField(max_digits=16, decimal_places=6)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    commission = models.DecimalField(max_digits=16, decimal_places=6, default=0)
    slippage_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0)
    cash_after = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    reason = models.CharField(max_length=20, blank=True, default="")

    def __str__(self):
        return f"{self.side} {self.quantity} @ {self.price} ({self.ts.date()})"
