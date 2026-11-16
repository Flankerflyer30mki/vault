"""Users. Email is the login. Tier (guest / unverified / verified) drives quotas."""
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

GUEST_DOMAIN = "guest.vault.invalid"  # .invalid is reserved (RFC 2606): these addresses can never receive mail
LEGACY_EMAIL = "legacy@system.vault.invalid"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        return self.create_user(email, password, is_staff=True, is_superuser=True, email_verified=True, **extra)

    def create_guest(self):
        return self.create_user(f"guest-{uuid.uuid4().hex}@{GUEST_DOMAIN}", is_guest=True, display_name="Guest")


class User(AbstractBaseUser, PermissionsMixin):
    GUEST, UNVERIFIED, VERIFIED = "guest", "unverified", "verified"

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=100, blank=True, default="")
    email_verified = models.BooleanField(default=False)
    is_guest = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)  # e.g. the legacy owner of pre-accounts data; never logs in
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    @property
    def tier(self):
        if self.is_guest:
            return self.GUEST
        return self.VERIFIED if self.email_verified else self.UNVERIFIED

    def __str__(self):
        return self.email
