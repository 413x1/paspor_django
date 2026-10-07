from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import DokumenKepegawaian, PasporPegawai, PegawaiProfile, User


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


@admin.register(PasporPegawai)
class PasporPegawaiAdmin(admin.ModelAdmin):
    list_display = ("nomor", "jenis", "pegawai", "tgl_expired")
    list_filter = ("jenis",)
    search_fields = ("nomor", "pegawai__username", "pegawai__profile__nama")


@admin.register(DokumenKepegawaian)
class DokumenKepegawaianAdmin(admin.ModelAdmin):
    list_display = ("user", "jenis", "uploaded_at")
    list_filter = ("jenis",)
    search_fields = ("user__username",)
