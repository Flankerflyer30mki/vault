"""Accounts, isolation, quotas, guests, dashboard and the legacy-data migration.

Run: DEBUG=1 DATABASE_URL=sqlite:///:memory: python manage.py test accounts
Password hashing uses MD5 in these tests only (FAST_HASHERS) so the suite measures our logic, not PBKDF2.
"""
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import housekeeping
from accounts.models import LEGACY_EMAIL, User
from backtester import jobs
from backtester.models import BacktestRun, Bar, OptimizationJob, Strategy, SymbolCoverage, Trade
from backtester.tests import make_bars

FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
PASSWORD = "correct-horse-battery-9"


class BrowserClient(APIClient):
    """Behaves like the SPA: CSRF enforced, and every request echoes the *current* csrftoken cookie in
    X-CSRFToken (as axios does). Re-reading matters: Django rotates the token on login."""

    def __init__(self):
        super().__init__(enforce_csrf_checks=True)

    def generic(self, method, path, *args, **extra):
        if "csrftoken" in self.cookies:
            extra.setdefault("HTTP_X_CSRFTOKEN", self.cookies["csrftoken"].value)
        return super().generic(method, path, *args, **extra)


def csrf_client():
    c = BrowserClient()
    c.get("/api/auth/csrf/")
    return c


def link_params(message):
    url = re.search(r"https?://\S+", message.body).group(0)
    q = parse_qs(urlparse(url).query)
    return {"uid": q["uid"][0], "token": q["token"][0]}, urlparse(url).path


def seed_market(symbol="AAPL"):
    Bar.objects.bulk_create(make_bars(symbol, date(2023, 9, 1), 500))
    SymbolCoverage.objects.create(symbol=symbol, start=date(2023, 9, 1), until=date(2025, 1, 12),
                                  fetched_at=timezone.now())


def run_body(strategy_id, **kw):
    return {"strategy": strategy_id, "symbol": "AAPL", "start_date": "2024-01-01", "end_date": "2024-12-31",
            "starting_cash": "10000", **kw}


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class AuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = csrf_client()

    def signup(self, email="ada@example.com", password=PASSWORD, client=None):
        return (client or self.c).post("/api/auth/signup/", {"email": email, "password": password}, format="json")

    def test_csrf_is_required_even_for_anonymous_login(self):
        raw = APIClient(enforce_csrf_checks=True)
        r = raw.post("/api/auth/login/", {"email": "a@example.com", "password": "x"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertIn("CSRF", r.json()["detail"])

    def test_signup_signs_in_and_sends_verification(self):
        r = self.signup("Ada@Example.com")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["user"]["email"], "ada@example.com")  # normalised to lower case
        self.assertEqual(r.json()["user"]["tier"], "unverified")
        self.assertEqual(self.c.get("/api/auth/me/").json()["user"]["email"], "ada@example.com")
        self.assertEqual(len(mail.outbox), 1)
        _, path = link_params(mail.outbox[0])
        self.assertEqual(path, "/verify-email")
        cookie = r.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    def test_duplicate_email_is_case_insensitive(self):
        self.signup("ada@example.com")
        r = self.signup("ADA@example.com", client=csrf_client())
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.json())

    def test_weak_passwords_rejected(self):
        for pw in ("short1", "password123", "1234567890123", "ada@example.com"):
            r = self.signup("ada@example.com", pw, client=csrf_client())
            self.assertEqual(r.status_code, 400, pw)
            self.assertIn("password", r.json())

    def test_verification_link_raises_tier_and_works_once(self):
        self.signup()
        params, _ = link_params(mail.outbox[0])
        r = self.c.post("/api/auth/verify-email/", params, format="json")
        self.assertEqual(r.json()["user"]["tier"], "verified")
        again = self.c.post("/api/auth/verify-email/", params, format="json")
        self.assertEqual(again.status_code, 400)  # the token hashes email_verified, so it is now dead
        bad = self.c.post("/api/auth/verify-email/", {**params, "token": "x-y"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_login_generic_error_and_session_rotation(self):
        self.signup()
        self.c.post("/api/auth/logout/")
        wrong = self.c.post("/api/auth/login/", {"email": "ada@example.com", "password": "nope"}, format="json")
        unknown = self.c.post("/api/auth/login/", {"email": "who@example.com", "password": "nope"}, format="json")
        self.assertEqual(wrong.json(), unknown.json())  # no hint whether the account exists
        before = self.c.cookies.get(settings.SESSION_COOKIE_NAME)
        r = self.c.post("/api/auth/login/", {"email": "ADA@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200)
        after = self.c.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertNotEqual(before and before.value, after)  # new session id on login: no session fixation

    def test_csrf_token_rotates_on_login_and_old_token_is_rejected(self):
        self.signup()
        self.c.post("/api/auth/logout/")
        self.c.get("/api/auth/csrf/")
        old = self.c.cookies["csrftoken"].value
        self.c.post("/api/auth/login/", {"email": "ada@example.com", "password": PASSWORD}, format="json")
        new = self.c.cookies["csrftoken"].value
        self.assertNotEqual(old, new)
        stale = self.c.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=old)
        self.assertEqual(stale.status_code, 403)
        self.assertEqual(self.c.post("/api/auth/logout/").status_code, 204)

    def test_logout_ends_session(self):
        self.signup()
        self.assertEqual(self.c.post("/api/auth/logout/").status_code, 204)
        self.assertIsNone(self.c.get("/api/auth/me/").json()["user"])
        self.assertEqual(self.c.get("/api/runs/").status_code, 403)

    def test_password_reset_flow_without_account_enumeration(self):
        self.signup()
        mail.outbox.clear()
        other = csrf_client()
        known = other.post("/api/auth/password-reset/", {"email": "ada@example.com"}, format="json")
        unknown = other.post("/api/auth/password-reset/", {"email": "nobody@example.com"}, format="json")
        self.assertEqual((known.status_code, known.json()), (unknown.status_code, unknown.json()))
        self.assertEqual(len(mail.outbox), 1)  # only the real account got mail
        params, path = link_params(mail.outbox[0])
        self.assertEqual(path, "/reset-password")
        r = other.post("/api/auth/password-reset/confirm/", {**params, "new_password": "brand-new-secret-77"},
                       format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.c.get("/api/runs/").status_code, 403)  # old session signed out
        reuse = other.post("/api/auth/password-reset/confirm/", {**params, "new_password": "another-secret-88"},
                           format="json")
        self.assertEqual(reuse.status_code, 400)  # the link died with the password change
        ok = other.post("/api/auth/login/", {"email": "ada@example.com", "password": "brand-new-secret-77"},
                        format="json")
        self.assertEqual(ok.status_code, 200)

    def test_password_change_keeps_this_session_and_signs_out_others(self):
        self.signup()
        second = csrf_client()
        second.post("/api/auth/login/", {"email": "ada@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(second.get("/api/runs/").status_code, 200)
        wrong = self.c.post("/api/auth/password-change/", {"current_password": "nope", "new_password": "x" * 12},
                            format="json")
        self.assertEqual(wrong.status_code, 400)
        r = self.c.post("/api/auth/password-change/",
                        {"current_password": PASSWORD, "new_password": "brand-new-secret-77"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.c.get("/api/runs/").status_code, 200)
        self.assertEqual(second.get("/api/runs/").status_code, 403)

    def test_email_change_requires_password_and_reverification(self):
        self.signup()
        params, _ = link_params(mail.outbox[0])
        self.c.post("/api/auth/verify-email/", params, format="json")
        mail.outbox.clear()
        bad = self.c.post("/api/auth/email-change/", {"new_email": "new@example.com", "current_password": "x"},
                          format="json")
        self.assertEqual(bad.status_code, 400)
        r = self.c.post("/api/auth/email-change/", {"new_email": "New@Example.com", "current_password": PASSWORD},
                        format="json")
        self.assertEqual(r.json()["user"]["email"], "new@example.com")
        self.assertEqual(r.json()["user"]["tier"], "unverified")
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        self.assertEqual(self.c.post("/api/auth/verify-email/", params, format="json").status_code, 400)

    def test_guest_flow_keeps_data_after_conversion(self):
        seed_market()
        r = self.c.post("/api/auth/guest/")
        self.assertEqual(r.status_code, 201)
        user = r.json()["user"]
        self.assertEqual((user["tier"], user["email"]), ("guest", None))
        self.assertIsNotNone(user["guest_expires_at"])
        builtin = Strategy.objects.get(name__startswith="SMA Crossover")
        run = self.c.post("/api/runs/", run_body(builtin.id), format="json")
        self.assertEqual(run.status_code, 201, run.content)
        conv = self.c.post("/api/auth/guest/convert/", {"email": "grace@example.com", "password": PASSWORD},
                           format="json")
        self.assertEqual(conv.json()["user"]["tier"], "unverified")
        self.assertEqual(self.c.get(f"/api/runs/{run.json()['id']}/").status_code, 200)  # same session, same data
        self.assertEqual(len(mail.outbox), 1)
        self.c.post("/api/auth/logout/")
        login = self.c.post("/api/auth/login/", {"email": "grace@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 200)

    def test_guests_legacy_and_inactive_users_cannot_password_login(self):
        guest = User.objects.create_guest()
        legacy = User.objects.create_user(LEGACY_EMAIL, PASSWORD, is_system=True)
        inactive = User.objects.create_user("gone@example.com", PASSWORD, is_active=False)
        for email, pw in ((guest.email, ""), (legacy.email, PASSWORD), (inactive.email, PASSWORD)):
            r = csrf_client().post("/api/auth/login/", {"email": email, "password": pw or "x"}, format="json")
            self.assertEqual(r.status_code, 400, email)

    def test_delete_account_removes_only_that_users_data(self):
        seed_market()
        self.signup()
        builtin = Strategy.objects.get(name__startswith="SMA Crossover")
        run_id = self.c.post("/api/runs/", run_body(builtin.id), format="json").json()["id"]
        jobs.work_one("w")
        self.assertTrue(Trade.objects.filter(run_id=run_id).exists())
        other = User.objects.create_user("keep@example.com", PASSWORD)
        kept = BacktestRun.objects.create(owner=other, strategy=builtin, symbol="AAPL", start_date=date(2024, 1, 1),
                                          end_date=date(2024, 2, 1))
        self.assertEqual(self.c.post("/api/auth/delete-account/", {"current_password": "x"}, format="json")
                         .status_code, 400)
        r = self.c.post("/api/auth/delete-account/", {"current_password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(User.objects.filter(email="ada@example.com").exists())
        self.assertFalse(BacktestRun.objects.filter(id=run_id).exists())
        self.assertFalse(Trade.objects.filter(run_id=run_id).exists())
        self.assertTrue(BacktestRun.objects.filter(id=kept.id).exists())
        self.assertTrue(Strategy.objects.filter(id=builtin.id).exists())  # shared built-ins survive

    def test_auth_throttle_is_per_ip_and_ignores_spoofed_forwarded_for(self):
        rf = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
        with self.settings(REST_FRAMEWORK=rf):
            codes = [self.c.post("/api/auth/login/", {"email": "a@example.com", "password": "x"}, format="json",
                                 HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.7").status_code for i in range(11)]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[-1], 429)  # 10/min per IP; a fresh fake address per request doesn't help

    def test_guest_creation_is_throttled_per_ip(self):
        codes = []
        for _ in range(6):
            c = csrf_client()
            codes.append(c.post("/api/auth/guest/").status_code)
        self.assertEqual(codes, [201] * 5 + [429])


@override_settings(PASSWORD_HASHERS=FAST_HASHERS, VAULT={**settings.VAULT, "ALLOW_CUSTOM_CODE": True})
class IsolationTests(TestCase):
    """User B must not see, use or even detect anything of user A's."""

    def setUp(self):
        cache.clear()
        seed_market()
        self.a, self.b = (User.objects.create_user(e, email_verified=True) for e in ("a@example.com", "b@example.com"))
        self.ca, self.cb = APIClient(), APIClient()
        self.ca.force_login(self.a)
        self.cb.force_login(self.b)
        self.strategy = self.ca.post("/api/strategies/", {"name": "A's", "code": "def on_bar(b,i,s): return 'HOLD'"},
                                     format="json").json()
        self.run = self.ca.post("/api/runs/", run_body(self.strategy["id"]), format="json",
                                HTTP_IDEMPOTENCY_KEY="shared-key").json()
        self.opt = self.ca.post("/api/optimizations/", run_body(self.strategy["id"], stop_loss_options=["0.05"],
                                                               take_profit_options=["0.2"]), format="json").json()

    def test_other_users_items_are_404_not_403(self):
        for url in (f"/api/runs/{self.run['id']}/", f"/api/runs/{self.run['id']}/trades/",
                    f"/api/optimizations/{self.opt['id']}/"):
            self.assertEqual(self.cb.get(url).status_code, 404, url)
            self.assertEqual(self.ca.get(url).status_code, 200, url)
        self.assertEqual(self.cb.get("/api/runs/999999/trades/").status_code, 404)  # same answer as "missing"

    def test_lists_show_only_own_items_plus_builtins(self):
        self.assertEqual(self.cb.get("/api/runs/").json()["count"], 0)
        self.assertEqual(self.cb.get("/api/optimizations/").json()["count"], 0)
        names = [s["name"] for s in self.cb.get("/api/strategies/").json()["results"]]
        self.assertNotIn("A's", names)
        self.assertTrue(all(s["is_builtin"] for s in self.cb.get("/api/strategies/").json()["results"]))
        self.assertIn("A's", [s["name"] for s in self.ca.get("/api/strategies/").json()["results"]])

    def test_cannot_run_or_optimize_another_users_strategy(self):
        r = self.cb.post("/api/runs/", run_body(self.strategy["id"]), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("does not exist", str(r.json()["strategy"]))
        r = self.cb.post("/api/optimizations/", run_body(self.strategy["id"], stop_loss_options=["0.05"],
                                                         take_profit_options=["0.2"]), format="json")
        self.assertEqual(r.status_code, 400)

    def test_idempotency_keys_are_per_user(self):
        builtin = Strategy.objects.get(name__startswith="SMA Crossover")
        r = self.cb.post("/api/runs/", run_body(builtin.id), format="json", HTTP_IDEMPOTENCY_KEY="shared-key")
        self.assertEqual(r.status_code, 201)  # a new run for B, not A's run
        self.assertNotEqual(r.json()["id"], self.run["id"])
        again = self.ca.post("/api/runs/", run_body(self.strategy["id"]), format="json",
                             HTTP_IDEMPOTENCY_KEY="shared-key")
        self.assertEqual((again.status_code, again.json()["id"]), (200, self.run["id"]))

    def test_dashboard_contains_only_own_data(self):
        jobs.work_one("w")
        d = self.cb.get("/api/dashboard/").json()
        self.assertEqual((d["active_runs"], d["recent_runs"], d["optimizations"]), ([], [], []))
        self.assertEqual(d["quota"]["usage"], {"active_jobs": 0, "runs_per_day": 0, "optimizations_per_day": 0,
                                              "strategies": 0})


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class QuotaTests(TestCase):
    def setUp(self):
        cache.clear()
        seed_market()
        self.builtin = Strategy.objects.get(name__startswith="SMA Crossover")

    def client_for(self, user):
        c = APIClient()
        c.force_login(user)
        return c

    def test_guest_active_job_limit(self):
        c = self.client_for(User.objects.create_guest())
        codes = [c.post("/api/runs/", run_body(self.builtin.id), format="json").status_code for _ in range(3)]
        self.assertEqual(codes, [201, 201, 429])
        r = c.post("/api/runs/", run_body(self.builtin.id), format="json")
        self.assertIn("limit 2 for guest", r.json()["detail"])

    def test_daily_limit_counts_finished_runs_and_suggests_verifying(self):
        user = User.objects.create_user("u@example.com")
        c = self.client_for(user)
        quotas = {**settings.VAULT["QUOTAS"], "unverified": {"active_jobs": 5, "runs_per_day": 2,
                                                             "optimizations_per_day": 1}}
        with self.settings(VAULT={**settings.VAULT, "QUOTAS": quotas}):
            for _ in range(2):
                self.assertEqual(c.post("/api/runs/", run_body(self.builtin.id), format="json").status_code, 201)
                jobs.work_one("w")
            r = c.post("/api/runs/", run_body(self.builtin.id), format="json")
            self.assertEqual(r.status_code, 429)
            self.assertIn("Verify your email", r.json()["detail"])
            # Runs older than 24 hours no longer count.
            BacktestRun.objects.filter(owner=user).update(created_at=timezone.now() - timedelta(hours=25))
            self.assertEqual(c.post("/api/runs/", run_body(self.builtin.id), format="json").status_code, 201)

    def test_optimization_counts_as_one_active_job(self):
        user = User.objects.create_user("v@example.com", email_verified=True)
        c = self.client_for(user)
        r = c.post("/api/optimizations/", run_body(self.builtin.id, stop_loss_options=["0.05", "0.1"],
                                                   take_profit_options=["0.2", "0.3"]), format="json")
        self.assertEqual(r.status_code, 201)
        usage = c.get("/api/dashboard/").json()["quota"]["usage"]
        self.assertEqual(usage, {"active_jobs": 1, "runs_per_day": 0, "optimizations_per_day": 1, "strategies": 0})

    def test_verifying_raises_limits(self):
        user = User.objects.create_user("w@example.com")
        c = self.client_for(user)
        self.assertEqual(c.get("/api/dashboard/").json()["quota"]["limits"]["runs_per_day"], 30)
        user.email_verified = True
        user.save()
        self.assertEqual(c.get("/api/dashboard/").json()["quota"]["limits"]["runs_per_day"], 200)

    def test_quota_values_come_from_env(self):
        from importlib import reload
        from unittest import mock

        import vault_core.settings as s
        with mock.patch.dict("os.environ", {"QUOTA_GUEST_RUNS_PER_DAY": "7", "DEBUG": "1"}):
            reload(s)
            self.assertEqual(s.VAULT["QUOTAS"]["guest"]["runs_per_day"], 7)
        reload(s)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class DashboardTests(TestCase):
    def test_dashboard_contents(self):
        cache.clear()
        seed_market()
        user = User.objects.create_user("d@example.com", email_verified=True)
        c = APIClient()
        c.force_login(user)
        builtin = Strategy.objects.get(name__startswith="SMA Crossover")
        done = c.post("/api/runs/", run_body(builtin.id), format="json").json()
        jobs.work_one("w")
        queued = c.post("/api/runs/", run_body(builtin.id, symbol="AAPL", end_date="2024-06-30"),
                        format="json").json()
        opt = c.post("/api/optimizations/", run_body(builtin.id, stop_loss_options=["0.05"],
                                                     take_profit_options=["0.2"]), format="json").json()
        d = c.get("/api/dashboard/").json()
        self.assertEqual(set(d), {"quota", "active_runs", "recent_runs", "optimizations", "strategies",
                                  "custom_code_enabled"})
        self.assertNotIn("leaderboard", d)  # deliberately absent (D-022)
        self.assertEqual([r["id"] for r in d["active_runs"]], [queued["id"]])
        recent = d["recent_runs"][0]
        run = BacktestRun.objects.get(id=done["id"])
        self.assertEqual(recent["id"], done["id"])
        self.assertAlmostEqual(recent["total_return"], float(run.final_value / run.starting_cash - 1))
        self.assertEqual(recent["buy_and_hold_return"], run.buy_and_hold_return)
        self.assertEqual(d["optimizations"][0]["id"], opt["id"])
        self.assertEqual(d["optimizations"][0]["runs_total"], 1)
        self.assertTrue(any(s["is_builtin"] for s in d["strategies"]))
        self.assertEqual(d["quota"]["usage"]["active_jobs"], 2)  # the queued run + the optimization


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class HousekeepingTests(TestCase):
    def test_expired_guests_and_sessions_are_deleted(self):
        builtin = Strategy.objects.get(name__startswith="SMA Crossover")
        old = User.objects.create_guest()
        User.objects.filter(pk=old.pk).update(date_joined=timezone.now() - timedelta(days=8))
        fresh = User.objects.create_guest()
        member = User.objects.create_user("m@example.com")
        User.objects.filter(pk=member.pk).update(date_joined=timezone.now() - timedelta(days=30))
        old_run = BacktestRun.objects.create(owner=old, strategy=builtin, symbol="AAPL", start_date=date(2024, 1, 1),
                                             end_date=date(2024, 2, 1))
        Session.objects.create(session_key="x" * 32, session_data="", expire_date=timezone.now() - timedelta(days=1))
        guests, sessions = housekeeping.run()
        self.assertEqual((guests, sessions), (1, 1))
        self.assertFalse(User.objects.filter(pk=old.pk).exists())
        self.assertFalse(BacktestRun.objects.filter(pk=old_run.pk).exists())
        self.assertTrue(User.objects.filter(pk=fresh.pk).exists())
        self.assertTrue(User.objects.filter(pk=member.pk).exists())

    def test_worker_finalising_a_deleted_users_run_is_harmless(self):
        seed_market()
        guest = User.objects.create_guest()
        builtin = Strategy.objects.get(name__startswith="SMA Crossover")
        run = BacktestRun.objects.create(owner=guest, strategy=builtin, symbol="AAPL", start_date=date(2024, 1, 1),
                                         end_date=date(2024, 6, 1), strategy_code=builtin.code)
        claimed = jobs.claim("w")
        guest.delete()  # e.g. account deleted while the job was running
        jobs.execute(claimed, "w")  # must neither crash nor resurrect rows
        self.assertFalse(BacktestRun.objects.filter(pk=run.pk).exists())
        self.assertFalse(Trade.objects.filter(run_id=run.pk).exists())


class LegacyMigrationTests(TransactionTestCase):
    """0014 must give pre-accounts rows to an inactive legacy user and leave built-ins ownerless."""
    serialized_rollback = True
    before = [("backtester", "0012_symbolcoverage")]
    after = [("backtester", "0015_owner_required")]

    def _to_latest(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_rows_move_to_legacy_user(self):
        self.addCleanup(self._to_latest)  # leave the schema at the newest migration for the next test
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps
        S, R, O = (old.get_model("backtester", m) for m in ("Strategy", "BacktestRun", "OptimizationJob"))
        custom = S.objects.create(name="old custom", code="def on_bar(b,i,s): return 'HOLD'")
        builtin = S.objects.filter(is_builtin=True).first()
        opt = O.objects.create(strategy=custom, symbol="AAPL", start_date=date(2024, 1, 1), end_date=date(2024, 6, 1))
        run = R.objects.create(strategy=builtin, symbol="AAPL", start_date=date(2024, 1, 1), end_date=date(2024, 2, 1),
                               optimization=opt, idempotency_key="k")

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps
        U = new.get_model("accounts", "User")
        legacy = U.objects.get(email=LEGACY_EMAIL)
        self.assertEqual((legacy.is_active, legacy.is_system), (False, True))
        self.assertEqual(new.get_model("backtester", "Strategy").objects.get(pk=custom.pk).owner_id, legacy.pk)
        self.assertEqual(new.get_model("backtester", "BacktestRun").objects.get(pk=run.pk).owner_id, legacy.pk)
        self.assertEqual(new.get_model("backtester", "OptimizationJob").objects.get(pk=opt.pk).owner_id, legacy.pk)
        self.assertIsNone(new.get_model("backtester", "Strategy").objects.get(pk=builtin.pk).owner_id)

    def test_fresh_database_gets_no_legacy_user(self):
        self.assertFalse(User.objects.filter(email=LEGACY_EMAIL).exists())
