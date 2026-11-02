from django.contrib import admin
from .models import Brand, Category, Product, ProductSize

class SizeInline(admin.TabularInline):
    model = ProductSize
    extra = 0

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "brand", "category", "gender", "is_template")
    list_filter = ("category", "is_template")
    inlines = [SizeInline]

admin.site.register(Brand)
admin.site.register(Category)