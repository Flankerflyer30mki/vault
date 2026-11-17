"""Per-user quotas by tier. Checked inside the create transaction after locking the user's row, so two
concurrent requests from the same user are serialised and cannot both slip under a limit."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from assist.models import AssistRequest
from backtester.models import BacktestRun, Experiment, Strategy

WINDOW = timedelta(hours=24)


class QuotaExceeded(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "quota_exceeded"


def limits(user):
    return settings.VAULT["QUOTAS"][user.tier]


def usage(user):
    """Current usage for the quotas in limits(). An experiment (comparison or optimization) counts as one active
    job while any of its runs is active; its child runs don't count as single backtests."""
    since = timezone.now() - WINDOW
    active_runs = BacktestRun.objects.filter(owner=user, experiment__isnull=True,
                                             status__in=BacktestRun.ACTIVE).count()
    active_exps = Experiment.objects.filter(owner=user, runs__status__in=BacktestRun.ACTIVE).distinct().count()
    return {
        "active_jobs": active_runs + active_exps,
        "runs_per_day": BacktestRun.objects.filter(owner=user, experiment__isnull=True, created_at__gte=since).count(),
        "experiments_per_day": Experiment.objects.filter(owner=user, created_at__gte=since).count(),
        "strategies": Strategy.objects.filter(owner=user).count(),  # saved, not per day; built-ins don't count
        "ai_requests_per_day": AssistRequest.objects.filter(owner=user, created_at__gte=since).count(),
    }


def check(user, kind):
    """kind: 'run' or 'experiment'. Raises QuotaExceeded naming the limit that was hit."""
    lim, used = limits(user), usage(user)
    per_day = "runs_per_day" if kind == "run" else "experiments_per_day"
    if used["active_jobs"] >= lim["active_jobs"]:
        raise QuotaExceeded(f"You have {used['active_jobs']} jobs running (limit {lim['active_jobs']} for "
                            f"{user.tier} accounts). Wait for one to finish.")
    if used[per_day] >= lim[per_day]:
        noun = "backtests" if kind == "run" else "experiments (comparisons and optimizations)"
        hint = " Verify your email to raise your limits." if user.tier != "verified" else ""
        raise QuotaExceeded(f"Daily limit reached: {lim[per_day]} {noun} per 24 hours for {user.tier} accounts."
                            + hint)


def check_ai(user):
    """AI requests (D-081): one at a time per user, and a daily count by tier. Call with the user's row locked."""
    if AssistRequest.objects.filter(owner=user, status__in=AssistRequest.ACTIVE).exists():
        raise QuotaExceeded("Your previous AI request is still being answered. Wait for it to finish.")
    lim = limits(user)["ai_requests_per_day"]
    since = timezone.now() - WINDOW
    if AssistRequest.objects.filter(owner=user, created_at__gte=since).count() >= lim:
        hint = " Verify your email to raise your limits." if user.tier != "verified" else ""
        raise QuotaExceeded(f"Daily limit reached: {lim} AI requests per 24 hours for {user.tier} accounts." + hint)


def check_strategy(user):
    """Saved-strategy limit. Call with the user's row locked (see StrategyListCreateView)."""
    lim, used = limits(user)["strategies"], Strategy.objects.filter(owner=user).count()
    if used >= lim:
        hint = " Verify your email to raise your limits." if user.tier != "verified" else ""
        raise QuotaExceeded(f"You have {used} saved strategies (limit {lim} for {user.tier} accounts). "
                            "Delete one you no longer need." + hint)


def visible_strategies_q(user):
    return Q(is_builtin=True) | Q(owner=user)
