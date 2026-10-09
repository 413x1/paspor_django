from django.contrib import admin

from .models import EmailLog, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "event", "level", "is_read", "created_at")
    list_filter = ("event", "level", "is_read")
    search_fields = ("title", "body", "recipient__username")
    autocomplete_fields = ("recipient", "pengajuan")
    readonly_fields = ("created_at",)


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Hanya-baca: antrean/riwayat email tidak boleh ditambah, diubah, atau
    dihapus dari Django Admin (pemantauan lewat menu Monitor Email Admin PAKLN)."""

    list_display = ("created_at", "to_email", "subject", "event", "status", "attempts", "sent_at")
    list_filter = ("status", "event")
    search_fields = ("to_email", "to_name", "subject")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
