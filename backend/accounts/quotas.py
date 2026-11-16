"""Per-user quotas by tier. Checked inside the create transaction after locking the user's row, so two
concurrent requests from the same user are serialised and cannot both slip under a limit."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from backtester.models import BacktestRun, OptimizationJob

WINDOW = timedelta(hours=24)


class QuotaExceeded(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "quota_exceeded"


def limits(user):
    return settings.VAULT["QUOTAS"][user.tier]


def usage(user):
    """Current usage for the quotas in limits(). An optimization counts as one active job while any of its
    runs is active; its child runs don't count as single backtests."""
    since = timezone.now() - WINDOW
    active_runs = BacktestRun.objects.filter(owner=user, optimization__isnull=True,
                                             status__in=BacktestRun.ACTIVE).count()
    active_opts = OptimizationJob.objects.filter(owner=user, runs__status__in=BacktestRun.ACTIVE).distinct().count()
    return {
        "active_jobs": active_runs + active_opts,
        "runs_per_day": BacktestRun.objects.filter(owner=user, optimization__isnull=True, created_at__gte=since).count(),
        "optimizations_per_day": OptimizationJob.objects.filter(owner=user, created_at__gte=since).count(),
    }


def check(user, kind):
    """kind: 'run' or 'optimization'. Raises QuotaExceeded naming the limit that was hit."""
    lim, used = limits(user), usage(user)
    per_day = "runs_per_day" if kind == "run" else "optimizations_per_day"
    if used["active_jobs"] >= lim["active_jobs"]:
        raise QuotaExceeded(f"You have {used['active_jobs']} jobs running (limit {lim['active_jobs']} for "
                            f"{user.tier} accounts). Wait for one to finish.")
    if used[per_day] >= lim[per_day]:
        noun = "backtests" if kind == "run" else "optimizations"
        hint = " Verify your email to raise your limits." if user.tier != "verified" else ""
        raise QuotaExceeded(f"Daily limit reached: {lim[per_day]} {noun} per 24 hours for {user.tier} accounts."
                            + hint)


def visible_strategies_q(user):
    return Q(is_builtin=True) | Q(owner=user)
