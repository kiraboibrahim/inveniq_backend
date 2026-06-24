from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """Allows access only to admin users and superusers."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role == "admin" or request.user.is_superuser)
        )


class IsManager(permissions.BasePermission):
    """Allows access to managers, admins, and superusers."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role in ["admin", "manager"] or request.user.is_superuser)
        )


class IsStaff(permissions.BasePermission):
    """Allows access to all authenticated staff, managers, admins, and superusers."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.role in ["admin", "manager", "staff"]
                or request.user.is_superuser
            )
        )


class IsManagerOrReadOnly(permissions.BasePermission):
    """
    Allows write operations only to admin, manager roles, and superusers.
    Allows read-only requests to staff role.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(
                request.user
                and request.user.is_authenticated
                and (
                    request.user.role in ["admin", "manager", "staff"]
                    or request.user.is_superuser
                )
            )
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role in ["admin", "manager"] or request.user.is_superuser)
        )


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allows write operations only to admin role and superusers.
    Allows read-only requests to manager and staff roles.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(
                request.user
                and request.user.is_authenticated
                and (
                    request.user.role in ["admin", "manager", "staff"]
                    or request.user.is_superuser
                )
            )
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role == "admin" or request.user.is_superuser)
        )
