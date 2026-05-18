"""
Docstring for inveniq_backend.accounts.tests
Tests for accounts app.
"""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Tests for User model."""

    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(
            email="[email protected]",
            password="testpass123"
        )
        assert user.email == "[email protected]"
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser
        assert user.check_password("testpass123")

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="[email protected]",
            password="testpass123"
        )
        assert user.email == "[email protected]"
        assert user.is_active
        assert user.is_staff
        assert user.is_superuser

    def test_user_str(self):
        """Test User __str__ method."""
        user = User.objects.create_user(
            email="[email protected]",
            password="testpass123"
        )
        assert str(user) == "[email protected]"

    def test_create_user_without_email(self):
        """Test creating user without email raises error."""
        with pytest.raises(ValueError, match="The Email field must be set"):
            User.objects.create_user(email="", password="testpass123")
