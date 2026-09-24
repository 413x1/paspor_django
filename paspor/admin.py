from django.contrib import admin

from .models import KategoriPerjalanan, Negara, SumberPembiayaan, UnitOrganisasi


@admin.register(UnitOrganisasi)
class UnitOrganisasiAdmin(admin.ModelAdmin):
    list_display = ("code", "alias", "name")
    search_fields = ("code", "alias", "name")
    ordering = ("code",)


@admin.register(Negara)
class NegaraAdmin(admin.ModelAdmin):
    list_display = ("nama_negara", "kode_negara", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("nama_negara", "kode_negara")
    ordering = ("nama_negara",)


@admin.register(SumberPembiayaan)
class SumberPembiayaanAdmin(admin.ModelAdmin):
    list_display = ("nama", "tipe_perjalanan", "is_active", "updated_at")
    list_filter = ("tipe_perjalanan", "is_active")
    search_fields = ("nama", "keterangan")
    ordering = ("tipe_perjalanan", "nama")


@admin.register(KategoriPerjalanan)
class KategoriPerjalananAdmin(admin.ModelAdmin):
    list_display = ("nama_kategori", "jenis_perjalanan", "is_active", "updated_at")
    list_filter = ("jenis_perjalanan", "is_active")
    search_fields = ("nama_kategori",)
    ordering = ("jenis_perjalanan", "nama_kategori")
