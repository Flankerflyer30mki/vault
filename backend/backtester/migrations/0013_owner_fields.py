"""Step 1 of 3: add nullable owner columns and per-user idempotency keys. Data is filled in 0014."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backtester", "0012_symbolcoverage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="strategy", name="owner",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="strategies", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(
            model_name="optimizationjob", name="owner",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="optimizations", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(
            model_name="backtestrun", name="owner",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="runs", to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(
            model_name="optimizationjob", name="idempotency_key",
            field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AlterField(
            model_name="backtestrun", name="idempotency_key",
            field=models.CharField(blank=True, max_length=64, null=True)),
    ]
