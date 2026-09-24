from django.urls import path

from . import views_pegawai as views

urlpatterns = [
    path("", views.beranda, name="beranda"),
    path("riwayat/data/", views.riwayat_data, name="riwayat_data"),
    path("formulir/", views.formulir_pengajuan, name="formulir_pengajuan"),
    path("<str:kode>/upload/", views.upload_dokumen, name="upload_dokumen"),
    path("<str:kode>/upload/<str:jenis>/hapus/", views.hapus_dokumen, name="hapus_dokumen"),
    path("<str:kode>/monitor/", views.monitor_progres, name="monitor_progres"),
    path("<str:kode>/monitor/unduh-iln/", views.download_iln, name="download_iln"),
]
