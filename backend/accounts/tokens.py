"""One-time tokens for email links. Django's generator hashes user state into the token, so a token stops
working as soon as that state changes: a reset link dies once the password changes (and after
PASSWORD_RESET_TIMEOUT); a verification link dies once the email is verified or changed."""
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "accounts.tokens.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified}{timestamp}"


password_reset_token = PasswordResetTokenGenerator()
email_verification_token = EmailVerificationTokenGenerator()


def encode_uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def decode_uid(uid):
    try:
        return int(force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, OverflowError):
        return None
