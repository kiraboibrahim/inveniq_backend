from rest_framework import viewsets

from accounts.permissions import IsStaff

from .models import Sale
from .serializers import SaleSerializer


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [IsStaff]
    filterset_fields = ["branch"]
    pagination_class = None
