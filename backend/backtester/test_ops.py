"""Phase 3.5: request IDs and JSON logs, /metrics, queue health, shared throttle cache, OpenAPI, graceful shutdown.
Run: DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test backtester.test_ops"""
import importlib
import json
import logging
import re
from datetime import date, timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache as django_cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from backtester import jobs, ops
from backtester.models import BacktestRun, Experiment, Strategy
from backtester.test_experiments import seed
from vault_core import observability as obs

R = BacktestRun


class LoggingTests(SimpleTestCase):
    def record(self, msg="hello", **extra):
        r = logging.LogRecord("vault.test", logging.INFO, __file__, 1, msg, (), None)
        for k, v in extra.items():
            setattr(r, k, v)
        return r

    def test_json_line_carries_context_and_extra_fields(self):
        tokens = obs.request_id_var.set("req-12345678"), obs.run_id_var.set(42)
        try:
            r = self.record("event=x", route="api/runs/<int:pk>/", status=200)
            obs.ContextFilter().filter(r)
        finally:
            obs.request_id_var.reset(tokens[0])
            obs.run_id_var.reset(tokens[1])
        line = json.loads(obs.JSONFormatter().format(r))
        self.assertEqual({k: line[k] for k in ("level", "logger", "msg", "request_id", "run_id", "route", "status")},
                         {"level": "INFO", "logger": "vault.test", "msg": "event=x", "request_id": "req-12345678",
                          "run_id": 42, "route": "api/runs/<int:pk>/", "status": 200})
        self.assertRegex(line["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$")

    def test_empty_context_is_omitted(self):
        r = self.record()
        obs.ContextFilter().filter(r)
        self.assertNotIn("request_id", json.loads(obs.JSONFormatter().format(r)))

    def test_exceptions_are_included(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            r = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
        self.assertIn("ValueError: boom", json.loads(obs.JSONFormatter().format(r))["exc"])

    def test_sentry_never_sends_personal_data(self):
        opts = obs.sentry_options("https://key@example.invalid/1", "staging")
        self.assertIs(opts["send_default_pii"], False)
        self.assertEqual(settings.SENTRY_DSN, "")  # off in tests: nothing is initialised or sent


class RequestContextTests(TestCase):
    def setUp(self):
        django_cache.clear()
        self.user = User.objects.create_user("ops@example.com", email_verified=True)
        self.api = APIClient()
        self.api.force_login(self.user)

    def test_request_id_generated_kept_or_replaced(self):
        new = self.client.get("/health/live")["X-Request-ID"]
        self.assertRegex(new, r"^[0-9a-f]{32}$")
        self.assertEqual(self.client.get("/health/live", HTTP_X_REQUEST_ID="proxy-abc-123")["X-Request-ID"],
                         "proxy-abc-123")
        for bad in ("short", "has space in it", "x" * 65, "quote\"inside1"):
            got = self.client.get("/health/live", HTTP_X_REQUEST_ID=bad)["X-Request-ID"]
            self.assertNotEqual(got, bad)
            self.assertRegex(got, r"^[0-9a-f]{32}$")

    def test_access_line_uses_route_pattern_not_raw_url(self):
        hold = Strategy.objects.get(name="Buy and Hold")
        with self.assertLogs("vault.access", "INFO") as logs:
            self.api.get(f"/api/strategies/{hold.id}/?secret=1")
        rec = logs.records[0]
        self.assertEqual((rec.method, rec.route, rec.status, rec.user_id),
                         ("GET", "api/strategies/<int:pk>/", 200, self.user.id))
        self.assertGreaterEqual(rec.duration_ms, 0)
        self.assertNotIn("secret", json.dumps(rec.__dict__, default=str))
        self.assertNotIn("ops@example.com", json.dumps(rec.__dict__, default=str))  # no emails in access logs
        self.assertEqual((rec.xff_hops, rec.via_vercel), (0, False))

    def test_access_line_counts_proxy_hops_without_addresses(self):
        # NUM_PROXIES must equal the hops a real request passed; the log shows the count, never the addresses.
        with self.assertLogs("vault.access", "INFO") as logs:
            self.api.get("/api/strategies/", HTTP_X_FORWARDED_FOR="203.0.113.9, 76.76.21.1",
                         HTTP_X_VERCEL_FORWARDED_FOR="203.0.113.9")
        rec = logs.records[0]
        self.assertEqual((rec.xff_hops, rec.via_vercel), (2, True))
        self.assertNotIn("203.0.113.9", json.dumps(rec.__dict__, default=str))

    def test_probes_are_counted_but_not_logged(self):
        with self.assertNoLogs("vault.access", "INFO"):
            self.client.get("/health/live")
            self.client.get("/health/ready")

    def test_run_records_its_request_and_the_worker_logs_under_it(self):
        seed(("AAPL",))
        body = {"strategy": Strategy.objects.get(name="Buy and Hold").id, "symbol": "AAPL",
                "start_date": "2024-01-01", "end_date": "2024-03-01", "starting_cash": "10000"}
        r = self.api.post("/api/runs/", body, format="json", HTTP_X_REQUEST_ID="click-0001-abcdef")
        self.assertEqual(r["X-Request-ID"], "click-0001-abcdef")
        run = R.objects.get(id=r.json()["id"])
        self.assertEqual((run.request_id, r.json()["request_id"]), ("click-0001-abcdef", "click-0001-abcdef"))
        seen = []
        real = jobs.execute

        def spy(run_, wid):
            seen.append((obs.request_id_var.get(), obs.run_id_var.get()))
            return real(run_, wid)

        with mock.patch.object(jobs, "execute", spy):
            jobs.work_one("w")
        self.assertEqual(seen, [("click-0001-abcdef", run.id)])
        self.assertIsNone(obs.request_id_var.get())  # context cleared after the run

    def test_out_of_sample_run_inherits_the_experiment_request_id(self):
        seed(("AAPL",))
        r = self.api.post("/api/experiments/", {
            "kind": "optimization", "strategy": Strategy.objects.get(name="Buy and Hold").id, "symbol": "AAPL",
            "start_date": "2024-01-01", "end_date": "2024-12-31", "starting_cash": "10000",
            "stop_loss_options": ["0.05"], "take_profit_options": ["0.2"]}, format="json",
            HTTP_X_REQUEST_ID="opt-click-000001")
        job = Experiment.objects.get(id=r.json()["id"])
        while jobs.work_one("w"):
            pass
        self.assertEqual(set(job.runs.values_list("request_id", flat=True)), {"opt-click-000001"})
        self.assertEqual(job.runs.filter(sample="out").count(), 1)


@override_settings(METRICS_TOKEN="test-token-123")
class MetricsTests(TestCase):
    def setUp(self):
        django_cache.clear()
        obs.REGISTRY.reset()
        self.user = User.objects.create_user("metrics@example.com", email_verified=True)
        self.hold = Strategy.objects.get(name="Buy and Hold")

    def scrape(self, token="test-token-123"):
        return self.client.get("/metrics", HTTP_AUTHORIZATION=f"Bearer {token}")

    def make(self, **kw):
        defaults = dict(owner=self.user, strategy=self.hold, symbol="AAPL", start_date=date(2024, 1, 1),
                        end_date=date(2024, 2, 1))
        return R.objects.create(**{**defaults, **kw})

    def test_token_required_and_off_without_one(self):
        self.assertEqual(self.scrape("wrong").status_code, 401)
        self.assertEqual(self.client.get("/metrics").status_code, 401)
        with override_settings(METRICS_TOKEN=""):
            self.assertEqual(self.scrape().status_code, 404)

    def test_red_metrics_by_route_pattern(self):
        api = APIClient()
        api.force_login(self.user)
        api.get(f"/api/strategies/{self.hold.id}/")
        api.get(f"/api/strategies/{self.hold.id + 100000}/")  # 404
        body = self.scrape().content.decode()
        self.assertIn('vault_http_requests_total{pid="', body)
        self.assertRegex(body, r'route="api/strategies/<int:pk>/",status="200"\} 1')
        self.assertRegex(body, r'route="api/strategies/<int:pk>/",status="404"\} 1')
        self.assertRegex(body, r'vault_http_request_duration_seconds_count\{[^}]*route="api/strategies/<int:pk>/"\} 2')
        self.assertNotIn(str(self.hold.id + 100000), body)  # raw ids never become labels

    def test_queue_health_matches_the_table(self):
        now = timezone.now()
        old = self.make(priority=R.BATCH)
        R.objects.filter(id=old.id).update(created_at=now - timedelta(seconds=90))
        self.make(priority=R.BATCH)
        self.make(priority=R.INTERACTIVE)
        self.make(status=R.RUNNING, heartbeat_at=now - timedelta(seconds=settings.VAULT["STALE_AFTER_S"] + 5))
        for ms in (100, 200, 300, 400, 1000):
            self.make(status=R.COMPLETED, completed_at=now - timedelta(minutes=5), execution_time_ms=ms)
        self.make(status=R.COMPLETED, completed_at=now - timedelta(hours=2), execution_time_ms=99999)  # outside hour
        self.make(status=R.FAILED, failure_category="data", completed_at=now - timedelta(minutes=1))
        snap = ops.queue_snapshot(now)
        self.assertEqual(snap["queue_depth"], {R.INTERACTIVE: 1, R.BATCH: 2})
        self.assertAlmostEqual(snap["oldest_queued_age_seconds"], 90, delta=1)
        self.assertEqual((snap["completed_last_hour"], snap["failed_last_hour"], snap["stale_runs"]), (5, {"data": 1}, 1))
        self.assertEqual((snap["run_seconds_p50"], snap["run_seconds_p95"]), (0.3, 1.0))
        body = self.scrape().content.decode()
        for line in ('vault_queue_depth{lane="interactive"} 1', 'vault_queue_depth{lane="batch"} 2',
                     'vault_runs_failed_last_hour{category="data"} 1', "vault_runs_stale 1",
                     'vault_run_duration_seconds{quantile="0.95"} 1.000', "vault_runs_completed_last_hour 5"):
            self.assertIn(line, body)
        self.assertTrue(body.endswith("\n"))
        for row in body.splitlines():  # valid exposition: comments, or `name{labels} value`
            self.assertRegex(row, r'^(# (HELP|TYPE) .+|[a-z_]+(\{[^}]*\})? [-0-9.e+]+)$')


class ThrottleCacheTests(TestCase):
    def test_counters_live_in_the_shared_table_not_the_process(self):
        from django.core.cache.backends.db import DatabaseCache
        from django.core.cache.backends.locmem import LocMemCache
        from django.db import connection

        django_cache.clear()
        self.assertEqual(settings.CACHES["default"]["BACKEND"], "vault_core.throttle_cache.UpsertDatabaseCache")
        for _ in range(3):
            self.client.post("/api/auth/login/", {"email": "x@example.com", "password": "nope"},
                             content_type="application/json")
        with connection.cursor() as c:
            c.execute("SELECT COUNT(*) FROM vault_cache")
            self.assertGreaterEqual(c.fetchone()[0], 1)
        key = "throttle_auth_127.0.0.1"
        # A brand-new cache object (what another gunicorn process would have) sees the same history...
        self.assertEqual(len(DatabaseCache("vault_cache", {}).get(key)), 3)
        # ...whereas a separate per-process cache starts from zero: the limit would be multiplied by the processes.
        self.assertIsNone(LocMemCache("another-process", {}).get(key))

    def test_upsert_write_is_one_statement_and_behaves_like_the_stock_cache(self):
        from django.core.cache.backends.db import DatabaseCache
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from vault_core.throttle_cache import UpsertDatabaseCache

        mine, stock = UpsertDatabaseCache("vault_cache", {}), DatabaseCache("vault_cache", {})
        mine.clear()
        with CaptureQueriesContext(connection) as q:
            mine.set("k", [1, 2, 3], 60)
        self.assertEqual(len(q), 1)
        with CaptureQueriesContext(connection) as q:
            stock.set("k2", [1], 60)
        self.assertGreaterEqual(len(q), 3)  # COUNT(*), SELECT, INSERT (+ savepoint statements)
        mine.set("k", [9], 60)  # overwrite
        self.assertEqual((mine.get("k"), stock.get("k")), ([9], [9]))  # same table, same format
        mine.set("old", "x", -1)  # already expired
        self.assertEqual(mine.delete_expired(), 1)  # (a get() would also drop it: expired rows read as missing)
        self.assertIsNone(mine.get("old"))
        self.assertEqual(mine.get("k"), [9])

    def test_housekeeping_removes_expired_throttle_rows(self):
        from accounts import housekeeping
        django_cache.set("expired", 1, -1)
        django_cache.set("live", 1, 60)
        self.assertEqual(housekeeping.delete_expired_cache_rows(), 1)
        self.assertEqual(django_cache.get("live"), 1)


class OpenApiTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_login(User.objects.create_user("docs@example.com", email_verified=True))

    def test_schema_documents_every_api_and_docs_page_serves_locally(self):
        schema = self.api.get("/api/schema/?format=json")
        self.assertEqual(schema.status_code, 200)
        paths = schema.json()["paths"]
        for p in ("/api/experiments/", "/api/experiments/{id}/", "/api/runs/", "/api/strategies/preview/",
                  "/api/strategies/catalog/", "/api/dashboard/", "/api/auth/login/", "/api/auth/me/"):
            self.assertIn(p, paths)
        ops_count = sum(len(v) for v in paths.values())
        self.assertGreaterEqual(ops_count, 30)
        page = self.api.get("/api/docs/")
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertNotIn("cdn.jsdelivr", html)  # assets bundled, not from a CDN
        asset = re.search(r'src="(/static/drf_spectacular_sidecar/[^"]+\.js)"', html).group(1)
        served = self.api.get(asset)
        self.assertEqual(served.status_code, 200)  # served even with DEBUG off (tests run with DEBUG off)
        served.close()

    def test_docs_off_unless_enabled(self):
        import vault_core.urls
        try:
            with override_settings(API_DOCS=False):
                clear_url_caches()
                importlib.reload(vault_core.urls)
                with override_settings(ROOT_URLCONF="vault_core.urls"):
                    self.assertEqual(self.api.get("/api/schema/").status_code, 404)
                    self.assertEqual(self.api.get("/api/docs/").status_code, 404)
        finally:
            clear_url_caches()
            importlib.reload(vault_core.urls)


class GracefulShutdownTests(TestCase):
    def setUp(self):
        seed(("AAPL",))
        self.addCleanup(jobs.SHUTDOWN.reset)
        user = User.objects.create_user("stop@example.com", email_verified=True)
        hold = Strategy.objects.get(name="Buy and Hold")
        self.runs = [R.objects.create(owner=user, strategy=hold, symbol="AAPL", start_date=date(2023, 6, 1),
                                      end_date=date(2024, 12, 31), **jobs.frozen_strategy(hold)) for _ in range(2)]

    def test_overdue_run_is_requeued_without_spending_an_attempt(self):
        jobs.SHUTDOWN.request(grace_s=0)  # the platform is about to kill us
        run = jobs.claim("w")  # claimed just before the signal
        with self.assertLogs("backtester.jobs", "INFO") as logs:
            jobs.execute(run, "w")
        run.refresh_from_db()
        self.assertEqual((run.status, run.worker_id, run.attempts), ("queued", "", 0))
        self.assertTrue(any("run_requeued_on_shutdown" in m for m in logs.output))
        self.assertFalse(jobs.work_one("w"))  # and nothing new is claimed

    def test_run_within_grace_finishes_then_nothing_new_is_claimed(self):
        run = jobs.claim("w")
        jobs.SHUTDOWN.request(grace_s=60)
        jobs.execute(run, "w")
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertFalse(jobs.work_one("w"))
        self.assertEqual(R.objects.get(id=self.runs[1].id).status, "queued")  # left for the next worker

    def test_work_loop_exits_once_shutdown_is_requested(self):
        jobs.SHUTDOWN.request(grace_s=5)
        with self.assertLogs("backtester.jobs", "INFO") as logs:
            jobs.work_forever(poll_s=0.01)  # returns instead of looping forever
        self.assertTrue(any("worker_stopped" in m for m in logs.output))
        self.assertEqual(R.objects.filter(status="queued").count(), 2)

    def test_signal_handler_requests_shutdown_with_configured_grace(self):
        import signal
        from backtester.management.commands import run_worker
        handlers = {}
        with mock.patch.object(signal, "signal", lambda sig, fn: handlers.setdefault(sig, fn)), \
                mock.patch.object(run_worker, "work_forever"):
            run_worker.Command().handle()
        self.assertEqual(set(handlers), {signal.SIGTERM, signal.SIGINT})
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        self.assertTrue(jobs.SHUTDOWN.requested)
        self.assertTrue(re.match(r"\d", str(settings.VAULT["WORKER_GRACE_S"])))
