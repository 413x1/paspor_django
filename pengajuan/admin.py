from django.contrib import admin

from .models import (
    DokumenPakln,
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


@admin.register(Pengajuan)
class PengajuanAdmin(admin.ModelAdmin):
    list_display = ("kode", "pegawai", "kategori", "tujuan_negara", "kanal", "status", "tgl_pengajuan")
    list_filter = ("status", "kanal", "kategori")
    search_fields = ("kode", "pegawai__username", "pegawai__profile__nama", "pegawai__profile__nip")
    readonly_fields = ("kode", "created_at", "updated_at")
    inlines = [DokumenPegawaiInline, DokumenUnorInline, DokumenUnorPendukungInline, DokumenPaklnInline]


@admin.register(DokumenTemplate)
class DokumenTemplateAdmin(admin.ModelAdmin):
    list_display = ("nama", "untuk_pegawai", "untuk_admin_unor", "kategori", "aktif", "updated_at")
    list_filter = ("aktif", "untuk_pegawai", "untuk_admin_unor", "kategori", "unit_organisasi")
    search_fields = ("nama", "keterangan")
    filter_horizontal = ("unit_organisasi",)
    readonly_fields = ("created_at", "updated_at")
