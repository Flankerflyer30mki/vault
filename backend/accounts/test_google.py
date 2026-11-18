"""Sign in with Google (D-103).

Tokens are signed for real with a throwaway RSA key standing in for Google's, and only the key download is patched,
so google-auth's own checks (signature, audience, issuer, expiry) run exactly as in production.
"""
import time
from datetime import UTC, datetime, timedelta
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from google.auth import crypt
from google.auth import jwt as google_jwt
from rest_framework.test import APIClient

from accounts.models import LEGACY_EMAIL, User
from accounts.tests import FAST_HASHERS, PASSWORD, csrf_client
from backtester.models import Strategy

CLIENT_ID = "test-client.apps.googleusercontent.com"


class FakeGoogleKeys:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-google")])
        now = datetime.now(UTC)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(self.key.public_key())
                .serial_number(1).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                .sign(self.key, hashes.SHA256()))
        self.certs = {"k1": cert.public_bytes(serialization.Encoding.PEM).decode()}
        self.signer = crypt.RSASigner.from_string(
            self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption()), key_id="k1")

    def token(self, email="ada@gmail.com", verified=True, aud=CLIENT_ID, expires_in=600, name="Ada",
              iss="https://accounts.google.com"):
        now = int(time.time())
        claims = {"iss": iss, "aud": aud, "sub": "1234", "email": email, "email_verified": verified,
                  "name": name, "iat": now - 10, "exp": now + expires_in}
        return google_jwt.encode(self.signer, claims).decode()


@override_settings(PASSWORD_HASHERS=FAST_HASHERS, GOOGLE_CLIENT_ID=CLIENT_ID)
class GoogleSignInTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.keys = FakeGoogleKeys()

    def setUp(self):
        cache.clear()
        self.c = csrf_client()
        patcher = mock.patch("google.oauth2.id_token._fetch_certs", return_value=self.keys.certs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def google(self, client=None, **kw):
        return (client or self.c).post("/api/auth/google/", {"credential": self.keys.token(**kw)}, format="json")

    def login_with_password(self, email="ada@gmail.com"):
        return csrf_client().post("/api/auth/login/", {"email": email, "password": PASSWORD}, format="json")

    def test_new_user_is_created_verified_without_password(self):
        r = self.google(email="Ada@Gmail.com")
        self.assertEqual(r.status_code, 201, r.content)
        user = r.json()["user"]
        self.assertEqual((user["email"], user["tier"], user["has_password"], user["display_name"]),
                         ("ada@gmail.com", "verified", False, "Ada"))
        self.assertEqual(self.c.get("/api/auth/me/").json()["user"]["email"], "ada@gmail.com")
        self.assertEqual(len(mail.outbox), 0)  # Google proved the address: nothing to verify, no email

    def test_me_tells_the_frontend_the_client_id(self):
        self.assertEqual(self.c.get("/api/auth/me/").json()["google_client_id"], CLIENT_ID)
        with override_settings(GOOGLE_CLIENT_ID=""):
            self.assertEqual(self.c.get("/api/auth/me/").json()["google_client_id"], "")

    def test_disabled_without_client_id(self):
        with override_settings(GOOGLE_CLIENT_ID=""):
            r = self.google()
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(email="ada@gmail.com").exists())

    def test_csrf_required(self):
        raw = APIClient(enforce_csrf_checks=True)
        r = raw.post("/api/auth/google/", {"credential": self.keys.token()}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_rejects_bad_tokens(self):
        cases = {"another app's token": {"aud": "someone-else.apps.googleusercontent.com"},
                 "expired": {"expires_in": -3600},
                 "not issued by Google": {"iss": "https://evil.example"},
                 "unverified Google email": {"verified": False}}
        for label, kw in cases.items():
            with self.subTest(label):
                self.assertEqual(self.google(**kw).status_code, 400)
        tampered = self.keys.token()[:-6] + "AAAAAA"
        r = self.c.post("/api/auth/google/", {"credential": tampered}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"], "Google sign-in failed. Please try again.")
        self.assertFalse(User.objects.filter(email="ada@gmail.com").exists())
        self.assertIsNone(self.c.get("/api/auth/me/").json()["user"])

    def test_existing_verified_account_signs_in_and_keeps_its_password(self):
        User.objects.create_user("ada@gmail.com", PASSWORD, email_verified=True)
        r = self.google()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["user"]["has_password"])
        self.assertEqual(User.objects.filter(email="ada@gmail.com").count(), 1)
        self.assertEqual(self.login_with_password().status_code, 200)

    def test_existing_unverified_account_loses_the_unproven_password(self):
        # Someone may have registered this address without owning it (account pre-hijacking). Google proves who owns
        # it: the account becomes verified, the old password stops working and its sessions are signed out.
        squatter = csrf_client()
        squatter.post("/api/auth/signup/", {"email": "ada@gmail.com", "password": PASSWORD}, format="json")
        self.assertIsNotNone(squatter.get("/api/auth/me/").json()["user"])
        r = self.google()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["user"]["tier"], r.json()["user"]["has_password"]), ("verified", False))
        self.assertIsNone(squatter.get("/api/auth/me/").json()["user"])
        self.assertEqual(self.login_with_password().status_code, 400)

    def test_guest_keeps_their_data(self):
        self.c.post("/api/auth/guest/")
        guest = User.objects.get(is_guest=True)
        Strategy.objects.create(owner=guest, name="mine", kind="builder", spec={"version": 1})
        r = self.google()
        self.assertEqual(r.status_code, 200, r.content)
        user = User.objects.get(pk=guest.pk)
        self.assertEqual((user.email, user.is_guest, user.tier), ("ada@gmail.com", False, "verified"))
        self.assertEqual(Strategy.objects.filter(owner=user, name="mine").count(), 1)
        self.assertEqual(self.c.get("/api/auth/me/").json()["user"]["id"], guest.pk)

    def test_guest_cannot_take_over_an_existing_account(self):
        User.objects.create_user("ada@gmail.com", PASSWORD, email_verified=True)
        self.c.post("/api/auth/guest/")
        r = self.google()
        self.assertEqual(r.status_code, 400)
        self.assertIn("already exists", r.json()["detail"])
        self.assertTrue(self.c.get("/api/auth/me/").json()["user"]["is_guest"])

    def test_signed_in_user_is_refused(self):
        self.c.post("/api/auth/signup/", {"email": "bob@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(self.google().status_code, 400)

    def test_system_account_cannot_sign_in(self):
        User.objects.get_or_create(email=LEGACY_EMAIL, defaults={"is_system": True, "is_active": False})
        self.assertEqual(self.google(email=LEGACY_EMAIL).status_code, 400)

    def test_google_only_account_settings(self):
        self.google()
        r = self.c.post("/api/auth/password-change/", {"current_password": "a-guess", "new_password": PASSWORD + "x"},
                        format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("signs in with Google", str(r.json()))
        self.assertEqual(self.c.post("/api/auth/delete-account/", {}, format="json").status_code, 204)
        self.assertFalse(User.objects.filter(email="ada@gmail.com").exists())
