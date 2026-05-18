from dj_rest_auth.serializers import LoginSerializer as DJRestAuthLoginSerializer
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

User = get_user_model()


class LoginSerializer(DJRestAuthLoginSerializer):
    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": _("Email is required"),
            "blank": _("Email is required"),
        },
    )

    password = serializers.CharField(
        style={"input_type": "password"},
        required=True,
        error_messages={
            "required": _("Password is required"),
            "blank": _("Password is required"),
        },
    )

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except serializers.ValidationError:
            raise serializers.ValidationError(
                _("Invalid email or password"),
            ) from None


class UserDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer for the user detail view (e.g., /api/v1/auth/user/).
    """

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name")
        read_only_fields = ("id", "email")
