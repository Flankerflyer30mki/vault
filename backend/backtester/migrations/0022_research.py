"""Phase 5 (AI research agent), schema: `Strategy.is_hidden` and the `research` experiment kind. The hidden strategy
itself is seeded by 0023: on Postgres, a data change and an ALTER TABLE in one migration can't be rolled back together
("pending trigger events"), so schema and data are separate migrations."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backtester', '0021_cache_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='strategy',
            name='is_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='experiment',
            name='kind',
            field=models.CharField(choices=[('optimization', 'optimization'), ('comparison', 'comparison'),
                                            ('research', 'research')], default='optimization', max_length=20),
        ),
    ]
