from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation
from rest_framework import serializers

from accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()
    tier = serializers.CharField(read_only=True)
    guest_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "tier", "email_verified", "is_guest", "date_joined",
                  "guest_expires_at"]

    def get_email(self, user):
        return None if user.is_guest else user.email  # guests have a synthetic address; don't show it

    def get_guest_expires_at(self, user):
        return user.date_joined + timedelta(days=settings.VAULT["GUEST_TTL_DAYS"]) if user.is_guest else None


def _email(value):
    return value.strip().lower()


class NewCredentialsSerializer(serializers.Serializer):
    """Signup and guest conversion: a new email plus a password that passes the configured validators."""
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    display_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        value = _email(value)
        if value.endswith(".invalid"):
            raise serializers.ValidationError("Enter a real email address.")
        existing = User.objects.filter(email=value)
        if self.context.get("user") is not None:
            existing = existing.exclude(pk=self.context["user"].pk)
        if existing.exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, data):
        candidate = User(email=data["email"], display_name=data.get("display_name", ""))
        try:
            password_validation.validate_password(data["password"], user=candidate)
        except Exception as e:  # django.core.exceptions.ValidationError
            raise serializers.ValidationError({"password": list(getattr(e, "messages", [str(e)]))})
        return data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate_email(self, value):
        return _email(value)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return _email(value)


class TokenSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)


class SetPasswordSerializer(TokenSerializer):
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)


class EmailChangeSerializer(serializers.Serializer):
    new_email = serializers.EmailField(max_length=254)
    current_password = serializers.CharField(max_length=128, trim_whitespace=False)


class DeleteAccountSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, trim_whitespace=False, required=False, default="")


def check_new_password(password, user):
    try:
        password_validation.validate_password(password, user=user)
    except Exception as e:
        raise serializers.ValidationError({"new_password": list(getattr(e, "messages", [str(e)]))})
