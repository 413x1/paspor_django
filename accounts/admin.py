from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import PegawaiProfile, User


class PegawaiProfileInline(admin.StackedInline):
    model = PegawaiProfile
    can_delete = False
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [PegawaiProfileInline]
    list_display = ("username", "get_full_name", "role", "unit_organisasi", "is_active", "is_staff")
    list_filter = ("role", "unit_organisasi", "is_active", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Peran PASPOR", {"fields": ("role", "unit_kerja", "unit_organisasi")}),
    )
    autocomplete_fields = ("unit_organisasi",)

    def get_inlines(self, request, obj):
        # Inline profil pegawai hanya relevan untuk role Pegawai.
        if obj and obj.role == User.Role.PEGAWAI:
            return [PegawaiProfileInline]
        return []


@admin.register(PegawaiProfile)
class PegawaiProfileAdmin(admin.ModelAdmin):
    list_display = ("nama", "nip", "jabatan", "unit_kerja", "unit_organisasi")
    list_filter = ("unit_organisasi",)
    search_fields = ("nama", "nip")
    autocomplete_fields = ("user", "unit_organisasi")
