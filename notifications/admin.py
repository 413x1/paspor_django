from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "event", "level", "is_read", "created_at")
    list_filter = ("event", "level", "is_read")
    search_fields = ("title", "body", "recipient__username")
    autocomplete_fields = ("recipient", "pengajuan")
    readonly_fields = ("created_at",)
