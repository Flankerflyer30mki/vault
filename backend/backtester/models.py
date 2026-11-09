from django.db import models

PCT = dict(max_digits=10, decimal_places=6)


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


class Strategy(models.Model):
    name = models.CharField(max_length=100)
    code = models.TextField()
    is_builtin = models.BooleanField(default=False)  # pre-approved; runnable when custom code is disabled
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class OptimizationJob(models.Model):
    """Grid search on the in-sample period; the best combination is then evaluated once
    on the untouched out-of-sample tail. Status is derived from child runs, never stored."""
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="optimization_jobs")
    symbol = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    split_date = models.DateField(null=True)  # in-sample < split_date <= out-of-sample
    starting_cash = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    stop_loss_options = models.JSONField(default=list)
    take_profit_options = models.JSONField(default=list)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Optimization {self.id} - {self.symbol}"


class BacktestRun(models.Model):
    QUEUED, PREPARING, RUNNING, COMPLETED, FAILED = "queued", "preparing_data", "running", "completed", "failed"
    STATUS_CHOICES = [(s, s) for s in (QUEUED, PREPARING, RUNNING, COMPLETED, FAILED)]
    ACTIVE = (QUEUED, PREPARING, RUNNING)
    SAMPLE_CHOICES = [("full", "full"), ("in", "in-sample"), ("out", "out-of-sample")]

    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="runs")
    optimization = models.ForeignKey(OptimizationJob, null=True, blank=True, on_delete=models.CASCADE,
                                     related_name="runs")
    sample = models.CharField(max_length=4, choices=SAMPLE_CHOICES, default="full")
    symbol = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    starting_cash = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    max_position_pct = models.DecimalField(default=1, **PCT)
    commission_pct = models.DecimalField(default="0.001", **PCT)
    slippage_pct = models.DecimalField(default="0.0005", **PCT)
    stop_loss_pct = models.DecimalField(null=True, blank=True, **PCT)
    take_profit_pct = models.DecimalField(null=True, blank=True, **PCT)

    # Reproducibility: exact code, engine and data used.
    strategy_code = models.TextField(blank=True, default="")
    strategy_hash = models.CharField(max_length=64, blank=True, default="")
    engine_version = models.CharField(max_length=20, blank=True, default="")
    data_manifest = models.JSONField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, unique=True)

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
    equity_curve = models.JSONField(null=True, blank=True)  # [[date, value], ...]

    class Meta:
        indexes = [models.Index(fields=["status", "id"], name="idx_run_status_id")]  # queue claim + admission count
        constraints = [models.UniqueConstraint(fields=["optimization"], condition=models.Q(sample="out"),
                                               name="uq_run_one_oos_per_optimization")]

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
