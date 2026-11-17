"""AI request health for /metrics (D-081): queue, outcomes in the last hour, tokens used today against the budget."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from assist.jobs import tokens_today
from assist.models import AssistRequest as A


def ai_snapshot(now=None):
    now = now or timezone.now()
    recent = A.objects.filter(completed_at__gte=now - timedelta(hours=1))
    outcomes = {o: 0 for o in (A.SPEC, A.UNSUPPORTED, A.INVALID, A.UNAVAILABLE)}
    outcomes.update({row["outcome"]: row["n"] for row in recent.values("outcome").annotate(n=Count("id"))
                     if row["outcome"]})
    return {"queued": A.objects.filter(status=A.QUEUED).count(), "outcomes_last_hour": outcomes,
            "cached_last_hour": recent.filter(cached=True).count(), "tokens_today": tokens_today(),
            "token_budget": settings.AI["DAILY_TOKEN_BUDGET"]}


def render_ai_metrics(snap):
    lines = ["# HELP vault_ai_queue_depth AI requests waiting for a worker.", "# TYPE vault_ai_queue_depth gauge",
             f"vault_ai_queue_depth {snap['queued']}",
             "# HELP vault_ai_requests_last_hour AI requests finished in the last hour, by outcome.",
             "# TYPE vault_ai_requests_last_hour gauge"]
    lines += [f'vault_ai_requests_last_hour{{outcome="{o}"}} {n}' for o, n in sorted(snap["outcomes_last_hour"].items())]
    lines += ["# HELP vault_ai_cached_last_hour AI requests answered from the cache in the last hour.",
              "# TYPE vault_ai_cached_last_hour gauge", f"vault_ai_cached_last_hour {snap['cached_last_hour']}",
              "# HELP vault_ai_tokens_today Tokens used today (UTC), whole deployment.",
              "# TYPE vault_ai_tokens_today gauge", f"vault_ai_tokens_today {snap['tokens_today']}",
              "# HELP vault_ai_token_budget Daily token budget (AI_DAILY_TOKEN_BUDGET).",
              "# TYPE vault_ai_token_budget gauge", f"vault_ai_token_budget {snap['token_budget']}"]
    return lines
