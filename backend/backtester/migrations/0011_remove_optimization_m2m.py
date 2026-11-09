from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("backtester", "0010_engine_v2_data")]
    operations = [
        migrations.RemoveField(
            model_name='optimizationjob',
            name='completed_at',
        ),
        migrations.RemoveField(
            model_name='optimizationjob',
            name='runs',
        ),
        migrations.RemoveField(
            model_name='optimizationjob',
            name='status',
        ),
    ]
