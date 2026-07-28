import threading
from itertools import product
from backtester.models import OptimizationJob, BacktestRun
from backtester.engine import run_backtest


def run_optimization(job_id, code_file_path):
    job = OptimizationJob.objects.get(id=job_id)
    job.status = 'running'
    job.save()

    combinations = list(product(job.stop_loss_options, job.take_profit_options))

    threads = []
    for stop_loss, take_profit in combinations:
        run = BacktestRun.objects.create(
            strategy=job.strategy,
            symbol=job.symbol,
            start_date=job.start_date,
            end_date=job.end_date,
            starting_cash=job.starting_cash,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit
        )
        job.runs.add(run)

        t = threading.Thread(target=run_backtest, args=(run.id, code_file_path))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()  # wait for all runs in this optimization to finish

    job.status = 'completed'
    from django.utils import timezone
    job.completed_at = timezone.now()
    job.save()