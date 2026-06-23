from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """Allows access only to admin users."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsManager(permissions.BasePermission):
    """Allows access to managers and admins."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ["admin", "manager"]
        )


class IsStaff(permissions.BasePermission):
    """Allows access to all authenticated staff, managers, and admins."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ["admin", "manager", "staff"]
        )


class IsManagerOrReadOnly(permissions.BasePermission):
    """
    Allows write operations only to admin and manager roles.
    Allows read-only requests to staff role.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(
                request.user
                and request.user.is_authenticated
                and request.user.role in ["admin", "manager", "staff"]
            )
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ["admin", "manager"]
        )


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allows write operations only to admin role.
    Allows read-only requests to manager and staff roles.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(
                request.user
                and request.user.is_authenticated
                and request.user.role in ["admin", "manager", "staff"]
            )
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )
