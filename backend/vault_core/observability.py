"""Request IDs, JSON logs and RED metrics (D-069, D-070).

- Every request gets an ID: a well-formed incoming X-Request-ID is kept (a proxy may have set it), anything else is
  replaced. It's returned in the response and attached to every log line written while the request runs. Runs store the
  ID of the request that created them (see current_request_id), and the worker sets it again while executing the run,
  so "this click -> this run -> this worker log" is one search.
- Logs are JSON lines. One access line per request: method, route *pattern* (never the raw URL, so ids and query
  strings don't leak), status, duration, user id.
- RED metrics (rate, errors, duration) per route are kept in memory per process and rendered in Prometheus text format
  by the /metrics view, together with queue health computed from the database (backtester.ops).
"""
import contextvars
import json
import logging
import re
import threading
import time
import uuid
from datetime import UTC, datetime

request_id_var = contextvars.ContextVar("request_id", default=None)
run_id_var = contextvars.ContextVar("run_id", default=None)
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
QUIET_ROUTES = ("health/live", "health/ready", "metrics")  # counted, but no access line (probes every few seconds)

access_log = logging.getLogger("vault.access")


def sentry_options(dsn, environment, traces_sample_rate=0.0):
    """Sentry init options (D-071). Never send personal data: no request bodies, cookies, user emails or IPs."""
    return {"dsn": dsn, "environment": environment, "send_default_pii": False,
            "traces_sample_rate": traces_sample_rate}


def current_request_id():
    """Model field default: the request (or worker run) currently being handled, or ''."""
    return request_id_var.get() or ""


class ContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        record.run_id = run_id_var.get()
        return True


_STANDARD = set(vars(logging.LogRecord("x", 0, "x", 0, "x", (), None))) | {"message", "asctime"}


class JSONFormatter(logging.Formatter):
    """One JSON object per line. Fields passed with extra={...} become top-level keys."""

    def format(self, record):
        out = {"ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
               "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for key, value in record.__dict__.items():
            if key not in _STANDARD and key not in out and not key.startswith("_") and value is not None:
                out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


class Metrics:
    """Counters and a duration histogram per (method, route). Per process: a scraper sums across processes using the
    `pid` label. Queue metrics come from the database instead, so they're global."""
    BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

    def __init__(self):
        self._lock = threading.Lock()
        self.requests = {}   # (method, route, status) -> count
        self.durations = {}  # (method, route) -> [bucket counts..., +Inf count, sum]

    def observe(self, method, route, status, seconds):
        with self._lock:
            key = (method, route, str(status))
            self.requests[key] = self.requests.get(key, 0) + 1
            h = self.durations.setdefault((method, route), [0] * (len(self.BUCKETS) + 1) + [0.0])
            for i, le in enumerate(self.BUCKETS):
                if seconds <= le:
                    h[i] += 1
            h[len(self.BUCKETS)] += 1
            h[-1] += seconds

    def reset(self):
        with self._lock:
            self.requests.clear()
            self.durations.clear()

    def render(self, pid):
        lines = ["# HELP vault_http_requests_total HTTP requests handled by this process.",
                 "# TYPE vault_http_requests_total counter"]
        with self._lock:
            for (method, route, status), n in sorted(self.requests.items()):
                lines.append(f'vault_http_requests_total{{{_labels(pid=pid, method=method, route=route, status=status)}}} {n}')
            lines += ["# HELP vault_http_request_duration_seconds Request duration by route.",
                      "# TYPE vault_http_request_duration_seconds histogram"]
            for (method, route), h in sorted(self.durations.items()):
                base = _labels(pid=pid, method=method, route=route)
                for le, n in zip(self.BUCKETS, h):
                    lines.append(f'vault_http_request_duration_seconds_bucket{{{base},le="{le}"}} {n}')
                lines.append(f'vault_http_request_duration_seconds_bucket{{{base},le="+Inf"}} {h[len(self.BUCKETS)]}')
                lines.append(f"vault_http_request_duration_seconds_sum{{{base}}} {h[-1]:.6f}")
                lines.append(f"vault_http_request_duration_seconds_count{{{base}}} {h[len(self.BUCKETS)]}")
        return lines


def _labels(**kw):
    def esc(v):
        return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return ",".join(f'{k}="{esc(v)}"' for k, v in kw.items())


REGISTRY = Metrics()


class RequestContextMiddleware:
    """Outermost middleware: assigns the request ID, times the request, records metrics and writes the access line."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        request.request_id = rid
        t0 = time.perf_counter()
        try:
            response = self.get_response(request)
            seconds = time.perf_counter() - t0
            match = getattr(request, "resolver_match", None)
            route = match.route if match is not None and match.route else "unmatched"
            REGISTRY.observe(request.method, route, response.status_code, seconds)
            response["X-Request-ID"] = rid
            if route not in QUIET_ROUTES:
                user = getattr(request, "user", None)
                access_log.info("http_request", extra={
                    "method": request.method, "route": route, "status": response.status_code,
                    "duration_ms": round(seconds * 1000, 1),
                    "user_id": user.pk if user is not None and user.is_authenticated else None})
            return response
        finally:
            request_id_var.reset(token)
