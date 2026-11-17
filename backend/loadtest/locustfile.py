"""Load test for the API (D-067, D-068). Dev-only: `pip install -r requirements-dev.txt`.

Each simulated user is a guest (one-click account), then browses like the SPA: dashboard, lists, a run page, the builder
catalog and live preview, and occasionally starts a backtest. Run it against production settings (DEBUG=0, gunicorn) with
rate limits and quotas raised through env vars, so the test measures capacity rather than the limits.

    locust -f loadtest/locustfile.py --host http://vault-api:8000 --headless -u 40 -r 20 -t 30s --csv out/u40

Production cookies are `Secure`; over plain HTTP a client won't send them back, so the session and CSRF cookies are
copied into the request headers by hand. Production settings stay untouched.
"""
import random

from locust import HttpUser, between, task

PREVIEW_SPEC = {"version": 1,
                "entry": {"all": [{"left": {"ind": "ema", "params": {"period": 12}}, "op": "crosses_above",
                                   "right": {"ind": "ema", "params": {"period": 26}}}]},
                "exit": {"any": [{"left": {"ind": "rsi", "params": {"period": 14}}, "op": ">", "right": {"const": 70}}]}}


class SpaUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.client.get("/api/auth/csrf/", name="auth/csrf")
        self._sync_headers()
        r = self.client.post("/api/auth/guest/", json={}, name="auth/guest")
        self._sync_headers()
        strategies = self.client.get("/api/strategies/", name="strategies").json()["results"]
        self.hold = next(s["id"] for s in strategies if s["name"] == "Buy and Hold")
        self.run_ids = []
        if r.status_code != 201:
            raise RuntimeError(f"guest creation failed: {r.status_code} {r.text[:200]}")

    def _sync_headers(self):
        jar = self.client.cookies
        cookies = {k: jar.get(k) for k in ("sessionid", "csrftoken") if jar.get(k)}
        self.client.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        if "csrftoken" in cookies:
            self.client.headers["X-CSRFToken"] = cookies["csrftoken"]

    @task(5)
    def dashboard(self):
        self.client.get("/api/dashboard/", name="dashboard")

    @task(2)
    def run_list(self):
        self.client.get("/api/runs/", name="runs (list)")

    @task(2)
    def strategies(self):
        self.client.get("/api/strategies/", name="strategies")

    @task(1)
    def catalog(self):
        self.client.get("/api/strategies/catalog/", name="strategies/catalog")

    @task(2)
    def preview(self):
        self.client.post("/api/strategies/preview/", json={"spec": PREVIEW_SPEC}, name="strategies/preview")

    @task(2)
    def run_detail(self):
        if self.run_ids:
            self.client.get(f"/api/runs/{random.choice(self.run_ids)}/", name="runs/<id>")

    @task(1)
    def create_run(self):
        r = self.client.post("/api/runs/", json={"strategy": self.hold, "symbol": "AAPL", "start_date": "2024-01-01",
                                                 "end_date": "2024-12-31", "starting_cash": "10000"},
                             name="runs (create)")
        if r.status_code == 201:
            self.run_ids.append(r.json()["id"])
