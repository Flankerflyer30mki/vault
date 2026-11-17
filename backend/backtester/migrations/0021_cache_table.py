"""The shared throttle-cache table (D-073). Created by a migration so a deploy needs only `migrate`, not a separate
`createcachetable` step. Idempotent: createcachetable skips a table that already exists (the test runner also calls it)."""
from django.core.management import call_command
from django.db import migrations

TABLE = "vault_cache"


def create(apps, schema_editor):
    call_command("createcachetable", TABLE, database=schema_editor.connection.alias, verbosity=0)


def drop(apps, schema_editor):
    schema_editor.execute(f"DROP TABLE IF EXISTS {schema_editor.quote_name(TABLE)}")


class Migration(migrations.Migration):
    dependencies = [("backtester", "0020_request_ids")]
    operations = [migrations.RunPython(create, drop)]
