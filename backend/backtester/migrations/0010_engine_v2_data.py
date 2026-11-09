"""Data step in its own migration: Postgres refuses DDL on tables with pending trigger events."""
from django.db import migrations

BUILTINS = {
    "SMA Crossover (10/50)": """def on_bar(bar, indicators, state):
    fast, slow = indicators.get('sma_10'), indicators.get('sma_50')
    if fast is None or slow is None:
        return "HOLD"
    if fast > slow:
        return "BUY"
    if fast < slow:
        return "SELL"
    return "HOLD"
""",
    "Momentum Threshold (2%)": """def on_bar(bar, indicators, state):
    fast, slow = indicators.get('sma_10'), indicators.get('sma_50')
    if fast is None or slow is None:
        return "HOLD"
    diff = (fast - slow) / slow
    if diff > 0.02:
        return "BUY"
    if diff < -0.02:
        return "SELL"
    return "HOLD"
""",
    "Always Hold (benchmark: cash)": """def on_bar(bar, indicators, state):
    return "HOLD"
""",
}


def forwards(apps, schema_editor):
    import hashlib
    Strategy = apps.get_model("backtester", "Strategy")
    Run = apps.get_model("backtester", "BacktestRun")
    Job = apps.get_model("backtester", "OptimizationJob")

    for name, code in BUILTINS.items():
        Strategy.objects.get_or_create(name=name, is_builtin=True, defaults={"code": code})

    # M2M -> FK: an old run belonged to at most one optimization.
    # Use the through table directly: job.runs is ambiguous while both the M2M and the new FK exist.
    for link in Job._meta.get_field("runs").remote_field.through.objects.all():
        Run.objects.filter(id=link.backtestrun_id).update(optimization_id=link.optimizationjob_id, sample="full")

    # Freeze the code each existing run used (best effort: the strategy's current code).
    for run in Run.objects.select_related("strategy").filter(strategy_code=""):
        run.strategy_code = run.strategy.code
        run.strategy_hash = hashlib.sha256(run.strategy.code.encode()).hexdigest()
        run.save(update_fields=["strategy_code", "strategy_hash"])

    # Old thread-based jobs cannot be resumed: pending ones re-enter the queue, running ones are dead.
    Run.objects.filter(status="pending").update(status="queued")
    Run.objects.filter(status="running").update(
        status="failed", failure_category="infrastructure",
        error_message="Interrupted by the engine v2 upgrade; please re-run")


class Migration(migrations.Migration):
    dependencies = [("backtester", "0009_refactor_engine_v2")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
