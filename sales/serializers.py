from rest_framework import serializers

from .models import Sale, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")

    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "quantity", "unit_price", "subtotal"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    branch_name = serializers.ReadOnlyField(source="branch.name")
    customer_name = serializers.ReadOnlyField(source="customer.company_name")

    class Meta:
        model = Sale
        fields = [
            "id",
            "branch",
            "branch_name",
            "customer",
            "customer_name",
            "total_amount",
            "payment_method",
            "timestamp",
            "items",
        ]

    def create(self, validated_data):
        import datetime

        from inventory.models import Stock, StockEntry

        items_data = validated_data.pop("items")
        branch = validated_data.get("branch")
        customer = validated_data.get("customer")
        payment_method = validated_data.get("payment_method", "cash")
        total_amount = validated_data.get("total_amount", 0)

        # 1. Pre-validate stock availability for all items to guarantee transaction atomicity
        for item_data in items_data:
            product = item_data.get("product")
            qty = item_data.get("quantity")

            try:
                stock = Stock.objects.get(product=product, branch=branch)
            except Stock.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "items": f"Product '{product.name}' has no stock record at branch '{branch.name}'."
                    }
                )

            if stock.quantity < qty:
                raise serializers.ValidationError(
                    {
                        "items": f"Insufficient stock for product '{product.name}' at branch '{branch.name}'. Available: {stock.quantity}, requested: {qty}."
                    }
                )

        # 2. If valid, commit sale and adjust inventory levels
        sale = Sale.objects.create(**validated_data)

        for item_data in items_data:
            product = item_data.get("product")
            qty = item_data.get("quantity")

            # Create SaleItem
            SaleItem.objects.create(sale=sale, **item_data)

            # Decrement Stock
            stock = Stock.objects.get(product=product, branch=branch)
            stock.quantity -= qty
            stock.save()

            # Create a corresponding negative StockEntry as audit log
            StockEntry.objects.create(
                product=product,
                branch=branch,
                quantity=-qty,
                note=f"Sale #{sale.id} checkout",
            )

        # 3. Update customer stats
        if customer:
            customer.last_order_date = datetime.date.today()
            if payment_method == "credit":
                customer.outstanding_balance += total_amount
            else:
                customer.lifetime_value += total_amount
            customer.save()

        return sale
