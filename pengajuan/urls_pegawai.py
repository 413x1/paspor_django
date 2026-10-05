from django.urls import path

from . import views_pegawai as views

urlpatterns = [
    path("", views.beranda, name="beranda"),
    path("riwayat/data/", views.riwayat_data, name="riwayat_data"),
    path("formulir/", views.formulir_pengajuan, name="formulir_pengajuan"),
    path("hitung-hari/", views.hitung_hari, name="hitung_hari"),
    path("pelaporan/", views.pelaporan, name="pelaporan"),
    path("pembatalan/", views.daftar_pembatalan, name="pembatalan"),
    path("pembatalan/<int:pk>/tarik/", views.tarik_pembatalan, name="tarik_pembatalan"),
    path("<str:kode>/upload/", views.upload_dokumen, name="upload_dokumen"),
    path("<str:kode>/upload/<str:jenis>/hapus/", views.hapus_dokumen, name="hapus_dokumen"),
    path("<str:kode>/monitor/", views.monitor_progres, name="monitor_progres"),
    path("<str:kode>/monitor/unduh-iln/", views.download_iln, name="download_iln"),
    path("<str:kode>/monitor/unduh/<str:jenis>/", views.unduh_hasil, name="unduh_hasil"),
    path("<str:kode>/laporan/", views.unggah_laporan, name="unggah_laporan"),
    path("<str:kode>/batalkan/", views.ajukan_pembatalan, name="ajukan_pembatalan"),
]
