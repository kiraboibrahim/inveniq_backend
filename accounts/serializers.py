from dj_rest_auth.serializers import LoginSerializer as DJRestAuthLoginSerializer
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

User = get_user_model()


from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token["role"] = user.role
        token["email"] = user.email
        token["name"] = user.display_name
        return token


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

    name = serializers.CharField(source="display_name", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "avatar",
            "bio",
            "role",
            "display_name",
            "name",
        )
        read_only_fields = ("id", "email", "role", "display_name", "name")
