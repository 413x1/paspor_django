from django.contrib import admin

from .models import (
    DokumenGenerateLog,
    DokumenPakln,
    DokumenPaklnPendukung,
    DokumenPegawai,
    DokumenTemplate,
    DokumenUnor,
    DokumenUnorPendukung,
    Pengajuan,
)


class DokumenPegawaiInline(admin.TabularInline):
    model = DokumenPegawai
    extra = 0


class DokumenUnorInline(admin.TabularInline):
    model = DokumenUnor
    extra = 0


class DokumenUnorPendukungInline(admin.StackedInline):
    model = DokumenUnorPendukung
    extra = 0


class DokumenPaklnInline(admin.TabularInline):
    model = DokumenPakln
    extra = 0


class DokumenPaklnPendukungInline(admin.StackedInline):
    model = DokumenPaklnPendukung
    extra = 0


@admin.register(Pengajuan)
class PengajuanAdmin(admin.ModelAdmin):
    list_display = ("kode", "pegawai", "kategori", "tujuan_negara_display", "kanal", "status", "tgl_pengajuan")
    list_filter = ("status", "kanal", "kategori")
    search_fields = ("kode", "pegawai__username", "pegawai__profile__nama", "pegawai__profile__nip")
    readonly_fields = ("kode", "created_at", "updated_at")
    filter_horizontal = ("tujuan_negara",)
    inlines = [
        DokumenPegawaiInline, DokumenUnorInline, DokumenUnorPendukungInline,
        DokumenPaklnInline, DokumenPaklnPendukungInline,
    ]

    @admin.display(description="Tujuan Negara")
    def tujuan_negara_display(self, obj):
        return obj.tujuan_negara_display


@admin.register(DokumenTemplate)
class DokumenTemplateAdmin(admin.ModelAdmin):
    list_display = ("nama", "untuk_pegawai", "untuk_admin_unor", "kategori", "aktif", "updated_at")
    list_filter = ("aktif", "untuk_pegawai", "untuk_admin_unor", "kategori", "unit_organisasi")
    search_fields = ("nama", "keterangan")
    filter_horizontal = ("unit_organisasi",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(DokumenGenerateLog)
class DokumenGenerateLogAdmin(admin.ModelAdmin):
    list_display = ("jenis", "jumlah_pengajuan", "dibuat_oleh", "created_at")
    list_filter = ("jenis",)
    filter_horizontal = ("pengajuan",)
    readonly_fields = ("created_at",)
