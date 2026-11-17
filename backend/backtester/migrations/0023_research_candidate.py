"""Phase 5: the hidden built-in strategy "AI research candidate" that research runs point at. Each research run carries
its own frozen spec (like an optimization child), so this row's spec is never run; it's a valid placeholder."""
from django.db import migrations

NAME = "AI research candidate"
SPEC = {
    "version": 1,
    "entry": {"all": [{"left": {"price": "close"}, "op": ">", "right": {"ind": "sma", "params": {"period": 50},
                                                                         "output": "value"}}]},
    "exit": {"any": [{"left": {"price": "close"}, "op": "<", "right": {"ind": "sma", "params": {"period": 50},
                                                                        "output": "value"}}]},
}


def forwards(apps, schema_editor):
    Strategy = apps.get_model("backtester", "Strategy")
    Strategy.objects.get_or_create(name=NAME, is_builtin=True, owner=None,
                                   defaults={"kind": "builder", "spec": SPEC, "code": "", "is_hidden": True})


def backwards(apps, schema_editor):
    Strategy = apps.get_model("backtester", "Strategy")
    Strategy.objects.filter(name=NAME, is_builtin=True, runs__isnull=True, experiments__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("backtester", "0022_research")]
    operations = [migrations.RunPython(forwards, backwards)]
