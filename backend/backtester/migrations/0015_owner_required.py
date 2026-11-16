"""Step 3 of 3: owners are now required (built-in strategies excepted) and idempotency keys are per user."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backtester", "0014_assign_legacy_owner"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="optimizationjob", name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="optimizations",
                                    to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(
            model_name="backtestrun", name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="runs",
                                    to=settings.AUTH_USER_MODEL)),
        migrations.AddConstraint(
            model_name="strategy",
            constraint=models.CheckConstraint(
                condition=models.Q(models.Q(("is_builtin", True), ("owner__isnull", True)),
                                   models.Q(("is_builtin", False), ("owner__isnull", False)), _connector="OR"),
                name="ck_strategy_builtin_xor_owner")),
        migrations.AddConstraint(
            model_name="optimizationjob",
            constraint=models.UniqueConstraint(fields=("owner", "idempotency_key"), name="uq_opt_owner_idem_key")),
        migrations.AddConstraint(
            model_name="backtestrun",
            constraint=models.UniqueConstraint(fields=("owner", "idempotency_key"), name="uq_run_owner_idem_key")),
        migrations.AddIndex(
            model_name="optimizationjob",
            index=models.Index(fields=["owner", "-created_at"], name="idx_opt_owner_created")),
        migrations.AddIndex(
            model_name="backtestrun",
            index=models.Index(fields=["owner", "-created_at"], name="idx_run_owner_created")),
    ]
