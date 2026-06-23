from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomerViewSet, SupplierViewSet

router = DefaultRouter()
router.register(r"suppliers", SupplierViewSet)
router.register(r"customers", CustomerViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
