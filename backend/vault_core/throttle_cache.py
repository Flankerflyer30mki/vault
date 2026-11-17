"""The shared throttle cache (D-073), made cheap enough for every request.

Django's DatabaseCache.set() runs, on every write: SELECT COUNT(*) over the whole table (to decide whether to cull), a
savepoint, a SELECT of the key, then an UPDATE or INSERT, and the savepoint release. A rate-limited request writes its
counter every time, so that's ~5 round trips on the request path; the load test measured +13-18 ms at p50 and ~20% less
throughput at saturation compared with per-process counters.

Here set() is one statement: INSERT ... ON CONFLICT (cache_key) DO UPDATE (Postgres, and SQLite >= 3.24). Expired rows
are deleted by the worker's hourly housekeeping (delete_expired) instead of on the request path. Reads are unchanged
(expired rows already read as missing). Same table, same format, so it's interchangeable with DatabaseCache.
"""
import base64
import pickle
from datetime import UTC, datetime

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.db import DatabaseCache
from django.db import connections, router


class UpsertDatabaseCache(DatabaseCache):
    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        key = self.make_and_validate_key(key, version=version)
        timeout = self.get_backend_timeout(timeout)
        expires = datetime.max.replace(tzinfo=UTC) if timeout is None else datetime.fromtimestamp(timeout, tz=UTC)
        connection = connections[router.db_for_write(self.cache_model_class)]
        q = connection.ops.quote_name
        table, ckey, cval, cexp = q(self._table), q("cache_key"), q("value"), q("expires")
        encoded = base64.b64encode(pickle.dumps(value, self.pickle_protocol)).decode("latin1")
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} ({ckey}, {cval}, {cexp}) VALUES (%s, %s, %s) "
                f"ON CONFLICT ({ckey}) DO UPDATE SET {cval} = EXCLUDED.{cval}, {cexp} = EXCLUDED.{cexp}",
                [key, encoded, connection.ops.adapt_datetimefield_value(expires.replace(microsecond=0))])

    def delete_expired(self):
        """Housekeeping: remove expired rows. Returns how many were deleted."""
        connection = connections[router.db_for_write(self.cache_model_class)]
        q = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {q(self._table)} WHERE {q('expires')} < %s",
                           [connection.ops.adapt_datetimefield_value(datetime.now(UTC).replace(microsecond=0))])
            return cursor.rowcount
