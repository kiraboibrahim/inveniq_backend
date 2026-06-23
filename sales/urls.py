from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .analytics_views import SalesAnalyticsView, TopProductsView
from .category_analytics import CategoryPerformanceView
from .views import SaleViewSet

router = DefaultRouter()
router.register(r"sales", SaleViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("analytics/sales-trend/", SalesAnalyticsView.as_view(), name="sales-trend"),
    path("analytics/top-products/", TopProductsView.as_view(), name="top-products"),
    path(
        "analytics/category-performance/",
        CategoryPerformanceView.as_view(),
        name="category-performance",
    ),
]
