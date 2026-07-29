import threading
from itertools import product
from backtester.models import OptimizationJob, BacktestRun
from backtester.engine import run_backtest


import os

def run_optimization(job_id, shared_code_path):
    job = OptimizationJob.objects.get(id=job_id)
    job.status = 'running'
    job.save()

    with open(shared_code_path, 'r') as f:
        strategy_code = f.read()

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

        os.makedirs('strategy_temp', exist_ok=True)
        run_code_path = f"strategy_temp/strategy_code_run_{run.id}.py"
        with open(run_code_path, 'w') as f:
            f.write(strategy_code)

        t = threading.Thread(target=run_backtest, args=(run.id, run_code_path))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()  # wait for all runs in this optimization to finish
    if os.path.exists(shared_code_path):
        os.remove(shared_code_path)
    job.status = 'completed'
    from django.utils import timezone
    job.completed_at = timezone.now()
    job.save()