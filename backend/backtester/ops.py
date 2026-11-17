"""Queue health from the queue table itself (D-069). Because the queue is Postgres, these numbers are global: the
same whichever API process serves /metrics, and they include every worker."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Min
from django.utils import timezone

from backtester.models import BacktestRun

R = BacktestRun


def _percentile(sorted_values, q):
    if not sorted_values:
        return None
    i = min(len(sorted_values) - 1, max(0, round(q * (len(sorted_values) - 1))))
    return sorted_values[i]


def queue_snapshot(now=None):
    now = now or timezone.now()
    hour_ago = now - timedelta(hours=1)
    queued = R.objects.filter(status=R.QUEUED)
    depth = {p: 0 for p in (R.INTERACTIVE, R.BATCH)}
    depth.update({row["priority"]: row["n"] for row in queued.values("priority").annotate(n=Count("id"))})
    oldest = queued.aggregate(t=Min("created_at"))["t"]
    active = {s: 0 for s in R.ACTIVE}
    active.update({row["status"]: row["n"] for row in
                   R.objects.filter(status__in=R.ACTIVE).values("status").annotate(n=Count("id"))})
    finished = R.objects.filter(completed_at__gte=hour_ago)
    failed = {row["failure_category"] or "unknown": row["n"] for row in
              finished.filter(status=R.FAILED).values("failure_category").annotate(n=Count("id"))}
    # Bounded sample: the most recent 5,000 completions in the hour are plenty for p50/p95.
    times = sorted(finished.filter(status=R.COMPLETED, execution_time_ms__isnull=False)
                   .order_by("-completed_at").values_list("execution_time_ms", flat=True)[:5000])
    stale_cutoff = now - timedelta(seconds=settings.VAULT["STALE_AFTER_S"])
    return {
        "queue_depth": depth,
        "oldest_queued_age_seconds": (now - oldest).total_seconds() if oldest else 0.0,
        "active_runs": active,
        "completed_last_hour": finished.filter(status=R.COMPLETED).count(),
        "failed_last_hour": failed,
        "run_seconds_p50": None if not times else _percentile(times, 0.5) / 1000,
        "run_seconds_p95": None if not times else _percentile(times, 0.95) / 1000,
        "stale_runs": R.objects.filter(status__in=(R.PREPARING, R.RUNNING), heartbeat_at__lt=stale_cutoff).count(),
    }


def render_queue_metrics(snap):
    lane = {R.INTERACTIVE: "interactive", R.BATCH: "batch"}
    lines = ["# HELP vault_queue_depth Runs waiting to be claimed, by priority lane.", "# TYPE vault_queue_depth gauge"]
    lines += [f'vault_queue_depth{{lane="{lane[p]}"}} {n}' for p, n in sorted(snap["queue_depth"].items())]
    lines += ["# HELP vault_queue_oldest_age_seconds Age of the oldest queued run.",
              "# TYPE vault_queue_oldest_age_seconds gauge",
              f"vault_queue_oldest_age_seconds {snap['oldest_queued_age_seconds']:.3f}",
              "# HELP vault_runs_active Runs in each active state.", "# TYPE vault_runs_active gauge"]
    lines += [f'vault_runs_active{{status="{s}"}} {n}' for s, n in sorted(snap["active_runs"].items())]
    lines += ["# HELP vault_runs_completed_last_hour Runs completed in the last hour.",
              "# TYPE vault_runs_completed_last_hour gauge",
              f"vault_runs_completed_last_hour {snap['completed_last_hour']}",
              "# HELP vault_runs_failed_last_hour Runs failed in the last hour, by failure category.",
              "# TYPE vault_runs_failed_last_hour gauge"]
    lines += [f'vault_runs_failed_last_hour{{category="{c}"}} {n}' for c, n in sorted(snap["failed_last_hour"].items())]
    lines += ["# HELP vault_run_duration_seconds Run time of runs completed in the last hour.",
              "# TYPE vault_run_duration_seconds gauge"]
    for q, label in (("p50", "0.5"), ("p95", "0.95")):
        v = snap[f"run_seconds_{q}"]
        if v is not None:
            lines.append(f'vault_run_duration_seconds{{quantile="{label}"}} {v:.3f}')
    lines += ["# HELP vault_runs_stale Running runs with no heartbeat for STALE_AFTER_S (should be 0).",
              "# TYPE vault_runs_stale gauge", f"vault_runs_stale {snap['stale_runs']}"]
    return lines
