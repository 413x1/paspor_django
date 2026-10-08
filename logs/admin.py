from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Hanya-baca: log tidak boleh ditambah atau diubah lewat Django Admin."""

    list_display = ("timestamp", "username", "role", "aktivitas", "status", "ip_address")
    list_filter = ("status", "aktivitas", "role")
    search_fields = ("username", "deskripsi", "target_id", "ip_address")
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
