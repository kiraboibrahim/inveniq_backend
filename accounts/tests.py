"""
Docstring for inveniq_backend.accounts.tests
Tests for accounts app.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from accounts.serializers import UserDetailsSerializer

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Tests for User model."""

    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(
            email="user" + "@" + "example.com", password="testpass123"
        )
        assert user.email == "user" + "@" + "example.com"
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser
        assert user.check_password("testpass123")

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="superuser" + "@" + "example.com", password="testpass123"
        )
        assert user.email == "superuser" + "@" + "example.com"
        assert user.is_active
        assert user.is_staff
        assert user.is_superuser

    def test_user_str(self):
        """Test User __str__ method."""
        user = User.objects.create_user(
            email="user" + "@" + "example.com", password="testpass123"
        )
        assert str(user) == "user" + "@" + "example.com"

    def test_create_user_without_email(self):
        """Test creating user without email raises error."""
        with pytest.raises(ValueError, match="The Email field must be set"):
            User.objects.create_user(email="", password="testpass123")


@pytest.mark.django_db
class TestUserDetailsSerializer:
    """Tests for UserDetailsSerializer email updates."""

    def test_admin_can_update_email(self):
        """Test admin is allowed to update email."""
        admin = User.objects.create_user(
            email="admin" + "@" + "example.com", password="testpass123", role="admin"
        )
        factory = APIRequestFactory()
        request = factory.put("/api/auth/user/")
        request.user = admin
        serializer = UserDetailsSerializer(
            instance=admin,
            data={"email": "newadmin" + "@" + "example.com"},
            context={"request": request},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        assert admin.email == "newadmin" + "@" + "example.com"

    def test_staff_cannot_update_email(self):
        """Test staff is not allowed to update email."""
        staff = User.objects.create_user(
            email="staff" + "@" + "example.com", password="testpass123", role="staff"
        )
        factory = APIRequestFactory()
        request = factory.put("/api/auth/user/")
        request.user = staff
        serializer = UserDetailsSerializer(
            instance=staff,
            data={"email": "newstaff" + "@" + "example.com"},
            context={"request": request},
            partial=True,
        )
        assert not serializer.is_valid()
        assert "email" in serializer.errors
        assert "Only administrators and managers" in str(serializer.errors["email"])

    def test_email_uniqueness_validation(self):
        """Test that updating to an existing email fails validation."""
        admin1 = User.objects.create_user(
            email="admin1" + "@" + "example.com", password="testpass123", role="admin"
        )
        User.objects.create_user(
            email="manager2" + "@" + "example.com",
            password="testpass123",
            role="manager",
        )
        factory = APIRequestFactory()
        request = factory.put("/api/auth/user/")
        request.user = admin1
        serializer = UserDetailsSerializer(
            instance=admin1,
            data={"email": "manager2" + "@" + "example.com"},
            context={"request": request},
            partial=True,
        )
        assert not serializer.is_valid()
        assert "email" in serializer.errors
        assert "already exists" in str(serializer.errors["email"])


@pytest.mark.django_db
class TestCustomJWTAuthentication:
    """Tests for custom JWT authentication classes handling malformed or invalid IDs."""

    def test_custom_jwt_authentication_invalid_user_id(self):
        """Test that a non-integer user_id raises InvalidToken instead of ValueError."""
        from rest_framework_simplejwt.exceptions import InvalidToken

        from accounts.authentication import CustomJWTAuthentication

        auth = CustomJWTAuthentication()
        validated_token = {"user_id": "ygODxO3"}
        with pytest.raises(
            InvalidToken, match="User not found or invalid user identification"
        ):
            auth.get_user(validated_token)

    def test_custom_jwt_cookie_authentication_invalid_user_id(self):
        """Test that a non-integer user_id in cookie auth raises InvalidToken."""
        from rest_framework_simplejwt.exceptions import InvalidToken

        from accounts.authentication import CustomJWTCookieAuthentication

        auth = CustomJWTCookieAuthentication()
        validated_token = {"user_id": "ygODxO3"}
        with pytest.raises(
            InvalidToken, match="User not found or invalid user identification"
        ):
            auth.get_user(validated_token)
