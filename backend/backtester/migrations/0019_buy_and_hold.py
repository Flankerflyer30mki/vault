"""Built-in "Buy and Hold" builder strategy: enters on the first bar and never exits. Comparisons run it on an index with
zero costs as the benchmark (D-060); users can also pick it like any template."""
from django.db import migrations

NAME = "Buy and Hold"
SPEC = {
    "version": 1,
    "entry": {"all": [{"left": {"price": "close"}, "op": ">", "right": {"const": 0}}]},
    "exit": {"any": [{"left": {"price": "close"}, "op": "<", "right": {"const": 0}}]},
}


def forwards(apps, schema_editor):
    Strategy = apps.get_model("backtester", "Strategy")
    Strategy.objects.get_or_create(name=NAME, is_builtin=True, owner=None,
                                   defaults={"kind": "builder", "spec": SPEC, "code": ""})


def backwards(apps, schema_editor):
    Strategy = apps.get_model("backtester", "Strategy")
    Strategy.objects.filter(name=NAME, is_builtin=True, runs__isnull=True, experiments__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("backtester", "0018_experiments")]
    operations = [migrations.RunPython(forwards, backwards)]
