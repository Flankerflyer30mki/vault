"""OptimizationJob becomes Experiment (D-055); runs gain priority lanes (D-059), grid params and new metrics (D-060).
Hand-written: an auto-generated migration can't tell a rename from "drop table, create table", which would lose data."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backtester", "0017_builder_templates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Constraints and indexes that name the old field are dropped first and recreated at the end.
        migrations.RemoveConstraint(model_name="backtestrun", name="uq_run_one_oos_per_optimization"),
        migrations.RemoveIndex(model_name="backtestrun", name="idx_run_status_id"),

        migrations.RenameModel(old_name="OptimizationJob", new_name="Experiment"),
        migrations.RenameField(model_name="backtestrun", old_name="optimization", new_name="experiment"),

        migrations.AddField(
            model_name="experiment", name="kind",
            field=models.CharField(choices=[("optimization", "optimization"), ("comparison", "comparison")],
                                   default="optimization", max_length=20)),
        migrations.AddField(model_name="experiment", name="config",
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AlterField(
            model_name="experiment", name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="experiments",
                                    to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(
            model_name="experiment", name="strategy",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="experiments", to="backtester.strategy")),
        migrations.AlterField(model_name="experiment", name="symbol",
                              field=models.CharField(blank=True, default="", max_length=20)),

        migrations.AlterField(
            model_name="backtestrun", name="sample",
            field=models.CharField(choices=[("full", "full"), ("in", "in-sample"), ("out", "out-of-sample"),
                                            ("bench", "benchmark")], default="full", max_length=10)),
        migrations.AddField(model_name="backtestrun", name="priority",
                            field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="backtestrun", name="grid_params",
                            field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name="backtestrun", name="sortino_ratio",
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="backtestrun", name="calmar_ratio",
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="backtestrun", name="exposure",
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="backtestrun", name="trade_count",
                            field=models.IntegerField(blank=True, null=True)),

        migrations.AddIndex(model_name="backtestrun",
                            index=models.Index(fields=["status", "priority", "id"], name="idx_run_claim")),
        migrations.AddConstraint(
            model_name="backtestrun",
            constraint=models.UniqueConstraint(condition=models.Q(sample="out"), fields=("experiment",),
                                               name="uq_run_one_oos_per_experiment")),
    ]
