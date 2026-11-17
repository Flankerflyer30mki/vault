"""Periodic cleanup, run by the worker loop (no cron needed): expired guest accounts and expired sessions."""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone

from accounts.models import User

log = logging.getLogger(__name__)


def delete_expired_guests():
    cutoff = timezone.now() - timedelta(days=settings.VAULT["GUEST_TTL_DAYS"])
    n = 0
    for user in User.objects.filter(is_guest=True, date_joined__lt=cutoff).iterator():
        user.delete()  # cascades to the guest's strategies, runs, trades and experiments
        n += 1
    return n


def delete_expired_cache_rows():
    """Throttle-cache rows past their expiry. The upsert cache never culls on the request path (vault_core/throttle_cache)."""
    from django.core.cache import cache
    return cache.delete_expired() if hasattr(cache, "delete_expired") else 0


def run():
    guests = delete_expired_guests()
    sessions, _ = Session.objects.filter(expire_date__lt=timezone.now()).delete()
    cache_rows = delete_expired_cache_rows()
    if guests or sessions or cache_rows:
        log.info("event=housekeeping guests_deleted=%s sessions_deleted=%s cache_rows_deleted=%s",
                 guests, sessions, cache_rows)
    return guests, sessions
