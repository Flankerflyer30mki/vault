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
        user.delete()  # cascades to the guest's strategies, runs, trades and optimizations
        n += 1
    return n


def run():
    guests = delete_expired_guests()
    sessions, _ = Session.objects.filter(expire_date__lt=timezone.now()).delete()
    if guests or sessions:
        log.info("event=housekeeping guests_deleted=%s sessions_deleted=%s", guests, sessions)
    return guests, sessions
