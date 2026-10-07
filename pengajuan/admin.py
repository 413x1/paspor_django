from django.contrib import admin

from .models import (
    DetailPdln,
    DokumenBpsdm,
    DokumenGenerateLog,
    DokumenPakln,
    DokumenPaklnPendukung,
    DokumenPegawai,
    DokumenTemplate,
    DokumenUnor,
    DokumenUnorPendukung,
    LaporanPdln,
    Pengajuan,
    PermohonanPembatalan,
    RiwayatPengajuan,
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


class DetailPdlnInline(admin.StackedInline):
    model = DetailPdln
    extra = 0


class DokumenBpsdmInline(admin.TabularInline):
    model = DokumenBpsdm
    extra = 0


class LaporanPdlnInline(admin.StackedInline):
    model = LaporanPdln
    extra = 0


class DokumenPaklnInline(admin.TabularInline):
    model = DokumenPakln
    extra = 0


class DokumenPaklnPendukungInline(admin.StackedInline):
    model = DokumenPaklnPendukung
    extra = 0


class _ReadOnlyMixin:
    """Riwayat bersifat append-only — hanya ditulis lewat
    pengajuan.riwayat.catat, tidak dapat diubah dari admin."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RiwayatPengajuanInline(_ReadOnlyMixin, admin.TabularInline):
    model = RiwayatPengajuan
    extra = 0
    fields = ("created_at", "aksi", "status_dari", "status_ke", "aktor_nama", "aktor_role", "catatan")
    readonly_fields = fields


@admin.register(Pengajuan)
class PengajuanAdmin(admin.ModelAdmin):
    list_display = (
        "kode", "pegawai", "jenis_perjalanan", "tipe_pdln", "kategori", "tujuan_negara_display", "kanal",
        "status", "tgl_pengajuan",
    )
    list_filter = ("jenis_perjalanan", "tipe_pdln", "status", "kanal", "unit_organisasi", "kategori")
    search_fields = ("kode", "pegawai__username", "pegawai__profile__nama", "pegawai__profile__nip")
    readonly_fields = ("kode", "created_at", "updated_at")
    filter_horizontal = ("tujuan_negara",)
    inlines = [
        DetailPdlnInline, DokumenPegawaiInline, DokumenUnorInline, DokumenUnorPendukungInline,
        DokumenBpsdmInline, DokumenPaklnInline, DokumenPaklnPendukungInline, LaporanPdlnInline,
        RiwayatPengajuanInline,
    ]

    @admin.display(description="Tujuan Negara")
    def tujuan_negara_display(self, obj):
        return obj.tujuan_negara_display


@admin.register(DokumenTemplate)
class DokumenTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "nama", "untuk_pegawai", "untuk_admin_unor", "untuk_admin_bpsdm", "jenis_perjalanan", "kategori",
        "aktif", "updated_at",
    )
    list_filter = (
        "aktif", "untuk_pegawai", "untuk_admin_unor", "untuk_admin_bpsdm", "jenis_perjalanan", "kategori",
        "unit_organisasi",
    )
    search_fields = ("nama", "keterangan")
    filter_horizontal = ("unit_organisasi",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(DokumenGenerateLog)
class DokumenGenerateLogAdmin(admin.ModelAdmin):
    list_display = ("jenis", "jumlah_pengajuan", "dibuat_oleh", "created_at")
    list_filter = ("jenis",)
    filter_horizontal = ("pengajuan",)
    readonly_fields = ("created_at",)


@admin.register(RiwayatPengajuan)
class RiwayatPengajuanAdmin(_ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("pengajuan", "aksi", "aktor_nama", "aktor_role", "created_at")
    list_filter = ("aksi", "aktor_role")
    search_fields = ("pengajuan__kode", "aktor_nama", "catatan")
    list_select_related = ("pengajuan",)


@admin.register(LaporanPdln)
class LaporanPdlnAdmin(admin.ModelAdmin):
    list_display = ("pengajuan", "status", "uploaded_at", "diverifikasi_oleh", "tgl_disetujui")
    list_filter = ("status",)
    search_fields = ("pengajuan__kode",)
    list_select_related = ("pengajuan", "diverifikasi_oleh")


@admin.register(PermohonanPembatalan)
class PermohonanPembatalanAdmin(admin.ModelAdmin):
    """Permohonan pembatalan diputus lewat aplikasi (persetujuan berjenjang);
    admin Django hanya untuk melihat."""

    list_display = ("pengajuan", "diajukan_role", "status", "status_pengajuan_saat_diajukan", "created_at")
    list_filter = ("status", "diajukan_role")
    search_fields = ("pengajuan__kode", "alasan")
    list_select_related = ("pengajuan",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
