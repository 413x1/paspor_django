from django.contrib import admin

from .models import UnitOrganisasi


@admin.register(UnitOrganisasi)
class UnitOrganisasiAdmin(admin.ModelAdmin):
    list_display = ("code", "alias", "name")
    search_fields = ("code", "alias", "name")
    ordering = ("code",)
