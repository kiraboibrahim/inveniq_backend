from rest_framework import serializers

from stakeholders.models import Supplier

from .models import (
    Branch,
    Category,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Stock,
    StockEntry,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = "__all__"


class StockSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.ReadOnlyField(source="product.name")
    branch_name = serializers.ReadOnlyField(source="branch.name")

    class Meta:
        model = Stock
        fields = [
            "id",
            "product",
            "product_name",
            "branch",
            "branch_name",
            "quantity",
            "updated_at",
        ]


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.ReadOnlyField(source="category.name")
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=Category.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )
    costPrice = serializers.DecimalField(
        source="cost_price", max_digits=12, decimal_places=2, required=False
    )
    primarySupplierId = serializers.PrimaryKeyRelatedField(
        source="primary_supplier",
        queryset=Supplier.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )
    primarySupplier = serializers.ReadOnlyField(source="primary_supplier.name")
    stocks = StockSerializer(many=True, read_only=True)
    stockQty = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    expiryDate = serializers.DateField(source="expiry_date")

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "category",
            "category_id",
            "description",
            "price",
            "costPrice",
            "primarySupplier",
            "primarySupplierId",
            "threshold",
            "expiryDate",
            "stocks",
            "stockQty",
            "status",
            "created_at",
            "updated_at",
        ]

    def get_stockQty(self, obj):
        return sum(stock.quantity for stock in obj.stocks.all())

    def get_status(self, obj):
        total = self.get_stockQty(obj)
        if total <= 0:
            return "Out of stock"
        if total <= obj.threshold:
            return "Low stock"
        return "In stock"


class StockEntrySerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")
    branch_name = serializers.ReadOnlyField(source="branch.name")

    class Meta:
        model = StockEntry
        fields = [
            "id",
            "product",
            "product_name",
            "branch",
            "branch_name",
            "quantity",
            "note",
            "created_at",
        ]


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")
    product_sku = serializers.ReadOnlyField(source="product.sku")

    class Meta:
        model = PurchaseOrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "quantity",
            "unit_cost",
        ]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.ReadOnlyField(source="supplier.name")
    branch_name = serializers.ReadOnlyField(source="branch.name")
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "branch",
            "branch_name",
            "status",
            "total_value",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "created_at", "updated_at"]

    def get_total_value(self, obj):
        return float(sum(item.quantity * item.unit_cost for item in obj.items.all()))

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        po = PurchaseOrder.objects.create(**validated_data)
        for item in items_data:
            PurchaseOrderItem.objects.create(purchase_order=po, **item)
        return po
