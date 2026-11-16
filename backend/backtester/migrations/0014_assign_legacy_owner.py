"""Step 2 of 3: give every pre-accounts run, optimization and custom strategy to a hidden, inactive legacy
user, so nothing is lost and nobody sees other people's old data. Built-in strategies stay ownerless."""
from django.conf import settings
from django.db import migrations

LEGACY_EMAIL = "legacy@system.vault.invalid"


def assign(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    Strategy = apps.get_model("backtester", "Strategy")
    Run = apps.get_model("backtester", "BacktestRun")
    Opt = apps.get_model("backtester", "OptimizationJob")
    orphans = (Strategy.objects.filter(is_builtin=False, owner__isnull=True).exists()
               or Run.objects.filter(owner__isnull=True).exists()
               or Opt.objects.filter(owner__isnull=True).exists())
    if not orphans:
        return  # fresh database: no legacy user needed
    legacy, _ = User.objects.get_or_create(
        email=LEGACY_EMAIL,
        defaults={"password": "!legacy-no-login", "is_active": False, "is_system": True,
                  "display_name": "Legacy (pre-accounts) data"})
    Strategy.objects.filter(is_builtin=False, owner__isnull=True).update(owner=legacy)
    Opt.objects.filter(owner__isnull=True).update(owner=legacy)
    Run.objects.filter(owner__isnull=True).update(owner=legacy)


class Migration(migrations.Migration):

    dependencies = [
        ("backtester", "0013_owner_fields"),
    ]

    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
