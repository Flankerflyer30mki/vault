"""Transactional email. Development prints to the console; production uses SMTP configured by env vars."""
import logging

from django.conf import settings
from django.core.mail import send_mail

from accounts.tokens import email_verification_token, encode_uid, password_reset_token

log = logging.getLogger(__name__)


def _send(user, subject, body):
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:
        # A mail outage must not fail sign-up or leak whether an address exists; the user can resend.
        log.exception("event=email_failed user=%s subject=%s", user.pk, subject)


def send_verification(user):
    link = f"{settings.FRONTEND_URL}/verify-email?uid={encode_uid(user)}&token={email_verification_token.make_token(user)}"
    _send(user, "Verify your Vault email", f"Confirm this address to raise your Vault limits:\n\n{link}\n")


def send_password_reset(user):
    link = f"{settings.FRONTEND_URL}/reset-password?uid={encode_uid(user)}&token={password_reset_token.make_token(user)}"
    _send(user, "Reset your Vault password",
          f"Use this link to choose a new password. It expires in "
          f"{settings.PASSWORD_RESET_TIMEOUT // 3600} hours.\n\n{link}\n\n"
          "If you didn't ask for this, ignore this email.")
