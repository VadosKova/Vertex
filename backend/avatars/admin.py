from django.contrib import admin

from .models import Avatar


@admin.register(Avatar)
class AvatarAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "gender", "is_default", "updated_at")