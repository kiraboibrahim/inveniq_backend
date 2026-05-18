"""User model for InvenIQ Backend."""
from typing import Any

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""

    def create_user(
        self, 
        email: str, 
        password: str | None = None, 
        **extra_fields: Any
    ) -> "User":
        """
        Create and save a regular user.
        
        Args:
            email: User's email address (used for authentication)
            password: User's password (will be hashed)
            **extra_fields: Additional fields for the user model
            
        Returns:
            The created User instance
            
        Raises:
            ValueError: If email is not provided
        """
        if not email:
            raise ValueError(_("The Email field must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, 
        email: str, 
        password: str | None = None, 
        **extra_fields: Any
    ) -> "User":
        """
        Create and save a superuser.
        
        Args:
            email: Superuser's email address
            password: Superuser's password (will be hashed)
            **extra_fields: Additional fields for the user model
            
        Returns:
            The created superuser instance
            
        Raises:
            ValueError: If is_staff or is_superuser are not True
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model that uses email instead of username for authentication."""

    username = None
    email = models.EmailField(_("email address"), unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        """Return user's full name or email as fallback."""
        if self.first_name or self.last_name:
            return self.get_full_name()
        return self.email
