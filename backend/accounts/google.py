"""Verifies a "Sign in with Google" ID token (D-103). The only module that knows about Google.

The browser gets the token from Google's own button (Google Identity Services) and posts it to /api/auth/google/.
google-auth checks the signature against Google's published keys, the expiry, the issuer and that the token was issued
for *this* client ID. We additionally require Google to say the email is verified: that is what lets a Google sign-in
mark a Vault account verified without sending an email.
"""
from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

KEYS_TIMEOUT_S = 5  # fetching Google's public keys must never hang a login


class GoogleTokenError(Exception):
    pass


class _Request(google_requests.Request):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = min(kwargs.get("timeout") or KEYS_TIMEOUT_S, KEYS_TIMEOUT_S)
        return super().__call__(*args, **kwargs)


def enabled():
    return bool(settings.GOOGLE_CLIENT_ID)


def verify(credential):
    """Return {"email", "name"} for a valid token, else raise GoogleTokenError (message safe to show)."""
    try:
        claims = id_token.verify_oauth2_token(credential, _Request(), settings.GOOGLE_CLIENT_ID)
    except Exception as e:  # bad signature, expired, wrong audience or issuer, keys unreachable
        raise GoogleTokenError("Google sign-in failed. Please try again.") from e
    email = (claims.get("email") or "").strip().lower()
    if not email or claims.get("email_verified") is not True:
        raise GoogleTokenError("Your Google account's email isn't verified.")
    return {"email": email, "name": (claims.get("name") or "")[:100]}
