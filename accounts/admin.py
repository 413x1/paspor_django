from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import DokumenKepegawaian, PasporPegawai, PegawaiProfile, PeranUser, User


class PegawaiProfileInline(admin.StackedInline):
    model = PegawaiProfile
    can_delete = False
    extra = 0


class PeranUserInline(admin.TabularInline):
    model = PeranUser
    fk_name = "user"
    extra = 0
    fields = ("role", "unit_organisasi", "is_active", "diberikan_oleh", "created_at")
    readonly_fields = ("diberikan_oleh", "created_at")
    autocomplete_fields = ("unit_organisasi",)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [PeranUserInline, PegawaiProfileInline]
    list_display = ("username", "get_full_name", "role", "no_hp", "sumber_akun", "is_active", "is_staff")
    list_filter = ("peran_list__role", "sumber_akun", "is_active", "is_staff")
    search_fields = ("username", "first_name", "last_name", "email", "no_hp", "profile__nip")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Peran PASPOR", {"fields": ("role", "unit_kerja", "unit_organisasi")}),
        ("Kontak & SSO", {"fields": ("no_hp", "email_dikunci", "no_hp_dikunci", "sumber_akun",
                                     "sso_sub", "ehrm_sinkron_at")}),
    )
    readonly_fields = ("sso_sub", "ehrm_sinkron_at")
    autocomplete_fields = ("unit_organisasi",)

    def get_inlines(self, request, obj):
        # Inline profil pegawai hanya relevan untuk user yang memiliki role Pegawai.
        if obj and obj.punya_peran(User.Role.PEGAWAI):
            return [PeranUserInline, PegawaiProfileInline]
        return [PeranUserInline] if obj else []


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
