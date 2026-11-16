"""Built-in builder strategies. Users start from these as templates; Phases 3 and 5 use them as seeds.
Specs are literal (already normalised) so later code changes can't alter what was seeded."""
from django.db import migrations


def ind(name, output="value", **params):
    return {"ind": name, "params": params, "output": output}


def const(v):
    return {"const": v}


CLOSE = {"price": "close"}


def cond(left, op, right):
    return {"left": left, "op": op, "right": right}


TEMPLATES = {
    "EMA Crossover (12/26)": {
        "version": 1,
        "entry": {"all": [cond(ind("ema", period=12), "crosses_above", ind("ema", period=26))]},
        "exit": {"any": [cond(ind("ema", period=12), "crosses_below", ind("ema", period=26))]},
    },
    "RSI Mean Reversion (14: buy < 30, sell > 50)": {
        "version": 1,
        "entry": {"all": [cond(ind("rsi", period=14), "<", const(30))]},
        "exit": {"any": [cond(ind("rsi", period=14), ">", const(50))]},
    },
    "MACD Signal Cross (12/26/9)": {
        "version": 1,
        "entry": {"all": [cond(ind("macd", "line", fast=12, slow=26, signal=9), "crosses_above",
                               ind("macd", "signal", fast=12, slow=26, signal=9))]},
        "exit": {"any": [cond(ind("macd", "line", fast=12, slow=26, signal=9), "crosses_below",
                              ind("macd", "signal", fast=12, slow=26, signal=9))]},
    },
    "Bollinger Breakout (20, 2)": {
        "version": 1,
        "entry": {"all": [cond(CLOSE, "crosses_above", ind("bbands", "upper", period=20, std=2.0))]},
        "exit": {"any": [cond(CLOSE, "crosses_below", ind("bbands", "middle", period=20, std=2.0))]},
    },
    "Donchian Breakout (20/10)": {
        "version": 1,
        "entry": {"all": [cond(CLOSE, ">", ind("donchian", "upper", period=20))]},
        "exit": {"any": [cond(CLOSE, "<", ind("donchian", "lower", period=10))]},
    },
    "Trend-Filtered RSI (SMA 200, RSI 14)": {
        "version": 1,
        "entry": {"all": [cond(CLOSE, ">", ind("sma", period=200)), cond(ind("rsi", period=14), "<", const(35))]},
        "exit": {"any": [cond(ind("rsi", period=14), ">", const(60)), cond(CLOSE, "<", ind("sma", period=200))]},
    },
}


def forwards(apps, schema_editor):
    Strategy = apps.get_model("backtester", "Strategy")
    for name, spec in TEMPLATES.items():
        Strategy.objects.get_or_create(name=name, is_builtin=True, owner=None,
                                       defaults={"kind": "builder", "spec": spec, "code": ""})


def backwards(apps, schema_editor):
    # Only remove templates nothing has run against; runs keep their own frozen spec either way.
    Strategy = apps.get_model("backtester", "Strategy")
    Strategy.objects.filter(name__in=TEMPLATES, is_builtin=True, kind="builder", runs__isnull=True,
                            optimization_jobs__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("backtester", "0016_builder_and_costs")]
    operations = [migrations.RunPython(forwards, backwards)]
