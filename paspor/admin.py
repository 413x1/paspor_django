from django.contrib import admin

from .models import (
    DasarKegiatan, HariLibur, KategoriPerjalanan, Kegiatan, Negara, SumberPembiayaan, UnitOrganisasi,
)


class DasarKegiatanInline(admin.TabularInline):
    model = DasarKegiatan
    extra = 0


@admin.register(Kegiatan)
class KegiatanAdmin(admin.ModelAdmin):
    list_display = ("nama", "penyelenggara", "tahun_pelaksanaan", "status", "is_active", "sumber_data")
    list_filter = ("status", "is_active", "sumber_data", "tahun_pelaksanaan")
    search_fields = ("nama", "penyelenggara", "kota", "kode_pintar")
    filter_horizontal = ("negara", "kategori", "skema_pendanaan")
    inlines = [DasarKegiatanInline]


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


@admin.register(HariLibur)
class HariLiburAdmin(admin.ModelAdmin):
    list_display = ("tanggal", "keterangan", "jenis", "is_active")
    list_filter = ("jenis", "is_active")
    search_fields = ("keterangan",)
    date_hierarchy = "tanggal"
    ordering = ("tanggal",)
