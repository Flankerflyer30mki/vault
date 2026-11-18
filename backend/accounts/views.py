"""Auth API (session cookies). All endpoints live under /api/auth/.

Security notes:
- CSRF: DRF only enforces CSRF for requests that are already session-authenticated. Login, signup and the
  other anonymous POSTs enforce it explicitly (CsrfEnforced), which blocks login CSRF.
- login() rotates the session key (no session fixation). Changing the password changes the session auth hash,
  which signs out every other session; update_session_auth_hash keeps only the current one signed in.
- Password reset always answers the same way, whether or not the email exists (no account enumeration).
- Login, signup and reset share the 'auth' throttle (per IP); guest creation has its own 'guest' throttle.
- Sign in with Google (D-103): Google's signed ID token proves the email, so the account is verified. Linking to an
  existing *unverified* account drops its password and sessions: whoever set them never proved they own the address.
"""
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts import emails, google
from accounts.models import User
from accounts.serializers import (DeleteAccountSerializer, EmailChangeSerializer, EmailSerializer, LoginSerializer,
                                  GoogleCredentialSerializer, NewCredentialsSerializer, PasswordChangeSerializer,
                                  SetPasswordSerializer, TokenSerializer, UserSerializer, check_new_password)
from accounts.tokens import decode_uid, email_verification_token, password_reset_token

INVALID_LINK = "This link is invalid or has expired."

# Response shapes for the OpenAPI schema (D-072).
USER = inline_serializer("UserEnvelope", {"user": UserSerializer(allow_null=True)})
ME = inline_serializer("MeEnvelope", {"user": UserSerializer(allow_null=True),
                                      "google_client_id": serializers.CharField()})
DETAIL = inline_serializer("Detail", {"detail": serializers.CharField()})


class CsrfEnforced:
    def initial(self, request, *args, **kwargs):
        SessionAuthentication().enforce_csrf(request)  # no-op for GET/HEAD/OPTIONS
        super().initial(request, *args, **kwargs)


class AuthView(CsrfEnforced, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class SignedInView(CsrfEnforced, APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


def _user(user, code=status.HTTP_200_OK):
    return Response({"user": UserSerializer(user).data}, status=code)


def _user_from_token(data, generator):
    uid = decode_uid(data["uid"])
    user = User.objects.filter(pk=uid, is_active=True, is_system=False).first() if uid else None
    if user is None or not generator.check_token(user, data["token"]):
        raise ValidationError({"detail": INVALID_LINK})
    return user


def _require_password(user, password):
    if not user.has_usable_password():
        raise ValidationError({"current_password": ["This account has no password: it signs in with Google."]})
    if not user.check_password(password):
        raise ValidationError({"current_password": ["Incorrect password."]})


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the csrftoken cookie. The SPA calls this once on load, before any POST."""
    permission_classes = [AllowAny]

    @extend_schema(responses=DETAIL)
    def get(self, request):
        return Response({"detail": "ok"})


@method_decorator(ensure_csrf_cookie, name="get")
class MeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=ME)
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        return Response({"user": UserSerializer(user).data if user else None,
                         "google_client_id": settings.GOOGLE_CLIENT_ID})


class SignupView(AuthView):
    @extend_schema(request=NewCredentialsSerializer, responses={201: USER})
    def post(self, request):
        if request.user.is_authenticated:
            raise ValidationError({"detail": "Already signed in. Guests can save their account instead."})
        s = NewCredentialsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = User.objects.create_user(s.validated_data["email"], s.validated_data["password"],
                                        display_name=s.validated_data.get("display_name", ""))
        login(request, user)
        emails.send_verification(user)
        return _user(user, status.HTTP_201_CREATED)


class LoginView(AuthView):
    @extend_schema(request=LoginSerializer, responses=USER)
    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(request, email=s.validated_data["email"], password=s.validated_data["password"])
        if user is None or user.is_system:
            raise ValidationError({"detail": "Invalid email or password."})
        login(request, user)
        return _user(user)


class LogoutView(CsrfEnforced, APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GuestView(AuthView):
    throttle_scope = "guest"

    @extend_schema(request=None, responses={201: USER})
    def post(self, request):
        if request.user.is_authenticated:
            raise ValidationError({"detail": "Already signed in."})
        user = User.objects.create_guest()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return _user(user, status.HTTP_201_CREATED)


class ConvertGuestView(SignedInView):
    """A guest keeps all their data and becomes a normal (unverified) account."""

    @extend_schema(request=NewCredentialsSerializer, responses=USER)
    def post(self, request):
        user = request.user
        if not user.is_guest:
            raise ValidationError({"detail": "Only guest accounts can be converted."})
        s = NewCredentialsSerializer(data=request.data, context={"user": user})
        s.is_valid(raise_exception=True)
        user.email = s.validated_data["email"]
        user.display_name = s.validated_data.get("display_name", "")
        user.is_guest = False
        user.set_password(s.validated_data["password"])
        user.save()
        update_session_auth_hash(request, user)
        emails.send_verification(user)
        return _user(user)


class GoogleSignInView(AuthView):
    """Sign in or sign up with a Google ID token. A signed-in guest keeps their data (like ConvertGuestView)."""

    @extend_schema(request=GoogleCredentialSerializer, responses={200: USER, 201: USER})
    def post(self, request):
        if not google.enabled():
            raise ValidationError({"detail": "Sign in with Google isn't enabled."})
        current = request.user if request.user.is_authenticated else None
        if current is not None and not current.is_guest:
            raise ValidationError({"detail": "Already signed in."})
        s = GoogleCredentialSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            info = google.verify(s.validated_data["credential"])
        except google.GoogleTokenError as e:
            raise ValidationError({"detail": str(e)}) from None
        try:
            with transaction.atomic():
                user, code = self._account_for(current, info)
        except IntegrityError:  # the same email created concurrently
            raise ValidationError({"detail": "Please try again."}) from None
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return _user(user, code)

    @staticmethod
    def _account_for(current, info):
        email = info["email"]
        existing = User.objects.select_for_update().filter(email=email).first()
        if existing is not None:
            if current is not None:
                raise ValidationError({"detail": "An account with this email already exists. Sign out of the guest "
                                                 "workspace, then sign in with Google."})
            if existing.is_system or not existing.is_active or existing.is_guest:
                raise ValidationError({"detail": "This account can't sign in."})
            if not existing.email_verified:
                existing.email_verified = True
                existing.set_unusable_password()  # also signs out every existing session
                existing.save(update_fields=["email_verified", "password"])
            return existing, status.HTTP_200_OK
        if current is not None:  # guest -> account, keeping their strategies and runs
            current.email, current.display_name = email, info["name"]
            current.is_guest, current.email_verified = False, True
            current.set_unusable_password()
            current.save()
            return current, status.HTTP_200_OK
        return User.objects.create_user(email, display_name=info["name"], email_verified=True), status.HTTP_201_CREATED


class VerifyEmailView(AuthView):
    @extend_schema(request=TokenSerializer, responses=USER)
    def post(self, request):
        s = TokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = _user_from_token(s.validated_data, email_verification_token)
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
        return _user(user)


class ResendVerificationView(SignedInView):
    @extend_schema(request=None, responses=DETAIL)
    def post(self, request):
        user = request.user
        if user.is_guest or user.email_verified:
            raise ValidationError({"detail": "Nothing to verify."})
        emails.send_verification(user)
        return Response({"detail": "Verification email sent."})


class PasswordResetView(AuthView):
    @extend_schema(request=EmailSerializer, responses=DETAIL)
    def post(self, request):
        s = EmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = User.objects.filter(email=s.validated_data["email"], is_active=True, is_guest=False,
                                   is_system=False).first()
        if user is not None and user.has_usable_password():
            emails.send_password_reset(user)
        return Response({"detail": "If an account exists for that email, a reset link has been sent."})


class PasswordResetConfirmView(AuthView):
    @extend_schema(request=SetPasswordSerializer, responses=DETAIL)
    def post(self, request):
        s = SetPasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = _user_from_token(s.validated_data, password_reset_token)
        check_new_password(s.validated_data["new_password"], user)
        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password"])  # also invalidates the link and every existing session
        return Response({"detail": "Password updated. You can sign in now."})


class PasswordChangeView(SignedInView):
    @extend_schema(request=PasswordChangeSerializer, responses=USER)
    def post(self, request):
        s = PasswordChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = request.user
        _require_password(user, s.validated_data["current_password"])
        check_new_password(s.validated_data["new_password"], user)
        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)  # stay signed in here; other sessions are signed out
        return _user(user)


class EmailChangeView(SignedInView):
    @extend_schema(request=EmailChangeSerializer, responses=USER)
    def post(self, request):
        s = EmailChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = request.user
        _require_password(user, s.validated_data["current_password"])
        try:
            email = NewCredentialsSerializer(context={"user": user}).validate_email(s.validated_data["new_email"])
        except ValidationError as e:
            raise ValidationError({"new_email": e.detail}) from None
        user.email, user.email_verified = email, False
        user.save(update_fields=["email", "email_verified"])
        emails.send_verification(user)
        return _user(user)


class DeleteAccountView(SignedInView):
    @extend_schema(request=DeleteAccountSerializer, responses={204: None})
    def post(self, request):
        s = DeleteAccountSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = request.user
        if user.has_usable_password():  # guests and Google-only accounts have none
            _require_password(user, s.validated_data["current_password"])
        logout(request)
        user.delete()  # cascades to strategies, runs, trades and experiments
        return Response(status=status.HTTP_204_NO_CONTENT)
