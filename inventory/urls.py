from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .analytics_views import (
    AiInsightsView,
    BranchDetailView,
    BranchKpisView,
    DashboardSummaryView,
    StockDepletionForecastView,
    StockHistoryView,
)
from .views import (
    BranchViewSet,
    CategoryViewSet,
    ProductViewSet,
    PurchaseOrderViewSet,
    StockEntryViewSet,
    StockViewSet,
)

router = DefaultRouter()
router.register(r"branches", BranchViewSet)
router.register(r"categories", CategoryViewSet)
router.register(r"products", ProductViewSet, basename="product")
router.register(r"stock", StockViewSet, basename="stock")
router.register(r"stock-entries", StockEntryViewSet, basename="stockentry")
router.register(r"purchase-orders", PurchaseOrderViewSet, basename="purchaseorder")

urlpatterns = [
    path("", include(router.urls)),
    path("analytics/stock-forecast/", StockDepletionForecastView.as_view()),
    path("analytics/ai-insights/", AiInsightsView.as_view()),
    path("analytics/branches/", BranchKpisView.as_view()),
    path("analytics/branches/<int:pk>/", BranchDetailView.as_view()),
    path("analytics/stock-history/", StockHistoryView.as_view()),
    path("analytics/dashboard-summary/", DashboardSummaryView.as_view()),
]
