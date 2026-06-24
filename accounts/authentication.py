"""Custom authentication classes to handle invalid token types gracefully."""

from dj_rest_auth.jwt_auth import JWTCookieAuthentication
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class CustomJWTCookieAuthentication(JWTCookieAuthentication):
    """Custom JWT Cookie Authentication that catches lookup errors."""

    def get_user(self, validated_token):
        try:
            return super().get_user(validated_token)
        except (ValueError, TypeError, ValidationError) as e:
            raise InvalidToken(
                _("User not found or invalid user identification")
            ) from e


class CustomJWTAuthentication(JWTAuthentication):
    """Custom JWT Authentication that catches lookup errors."""

    def get_user(self, validated_token):
        try:
            return super().get_user(validated_token)
        except (ValueError, TypeError, ValidationError) as e:
            raise InvalidToken(
                _("User not found or invalid user identification")
            ) from e
