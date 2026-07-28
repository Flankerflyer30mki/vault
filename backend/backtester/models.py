from django.db import models

class Bar(models.Model):
    symbol = models.CharField(max_length=10, db_index=True)
    ts = models.DateTimeField(db_index=True)
    open = models.DecimalField(max_digits=12, decimal_places=4)
    high = models.DecimalField(max_digits=12, decimal_places=4)
    low = models.DecimalField(max_digits=12, decimal_places=4)
    close = models.DecimalField(max_digits=12, decimal_places=4)
    volume = models.BigIntegerField()

    class Meta:
        unique_together = ('symbol', 'ts')

    def __str__(self):
        return f"{self.symbol} @ {self.ts}"
    
class Strategy(models.Model):
    name = models.CharField(max_length=100)
    code = models.TextField()  # the user's Python function, as text
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BacktestRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='runs')
    symbol = models.CharField(max_length=10)
    start_date = models.DateField()
    end_date = models.DateField()
    starting_cash = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    final_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cagr = models.FloatField(null=True, blank=True)
    sharpe_ratio = models.FloatField(null=True, blank=True)
    max_drawdown = models.FloatField(null=True, blank=True)
    win_rate = models.FloatField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    bars_processed = models.IntegerField(null=True, blank=True)
    max_position_pct = models.FloatField(default=1.0)  # 1.0 = 100% of cash allowed per trade
    commission_pct = models.FloatField(default=0.001)   # 0.1% per trade
    slippage_pct = models.FloatField(default=0.0005)     # 0.05% adverse price movement per trade
    stop_loss_pct = models.FloatField(null=True, blank=True)    # e.g. 0.05 = sell if down 5% from entry
    take_profit_pct = models.FloatField(null=True, blank=True)  # e.g. 0.10 = sell if up 10% from entry
    def __str__(self):
        return f"Run {self.id} - {self.symbol} ({self.status})"


class Trade(models.Model):
    SIDE_CHOICES = [('BUY', 'Buy'), ('SELL', 'Sell')]

    run = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name='trades')
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    ts = models.DateTimeField()
    price = models.DecimalField(max_digits=12, decimal_places=4)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)

    def __str__(self):
        return f"{self.side} {self.quantity} @ {self.price} ({self.ts.date()})"