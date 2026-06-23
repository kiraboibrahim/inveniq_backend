from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Branch, Category, Product, Stock


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "location", "manager", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "code", "location", "manager")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "code")}),
        (_("Details"), {"fields": ("location", "manager")}),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "product_count", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("Products"))
    def product_count(self, obj):
        return obj.products.count()


class StockInline(admin.TabularInline):
    model = Stock
    extra = 0
    fields = ("branch", "quantity", "updated_at")
    readonly_fields = ("updated_at",)
    autocomplete_fields = ("branch",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "price",
        "threshold",
        "expiry_date",
        "created_at",
    )
    list_filter = ("category", "expiry_date", "created_at")
    search_fields = ("name", "sku")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("category",)
    inlines = (StockInline,)
    fieldsets = (
        (None, {"fields": ("sku", "name", "category")}),
        (_("Pricing & Stock"), {"fields": ("price", "threshold", "expiry_date")}),
        (_("Details"), {"fields": ("description",)}),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("product", "branch", "quantity", "updated_at")
    list_filter = ("branch",)
    search_fields = ("product__name", "product__sku", "branch__name")
    readonly_fields = ("updated_at",)
    autocomplete_fields = ("product", "branch")
