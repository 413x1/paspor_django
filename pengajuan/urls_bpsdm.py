from django.urls import path

from . import views_bpsdm as views
from . import views_kegiatan, views_report

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("dashboard/data/", views.dashboard_data, name="dashboard_data"),
    path("pembatalan/", views.daftar_pembatalan, name="pembatalan"),
    path("kegiatan/", views_kegiatan.bpsdm_daftar, name="kegiatan"),
    path("kegiatan/data/", views_kegiatan.bpsdm_data, name="kegiatan_data"),
    path("kegiatan/tambah/", views_kegiatan.bpsdm_tambah, name="tambah_kegiatan"),
    path("kegiatan/<int:pk>/", views_kegiatan.bpsdm_edit, name="edit_kegiatan"),
    path("export/", views_report.export_database, name="export"),
    path("export/data/", views_report.export_data, name="export_data"),
    path("rekap/", views_report.rekap, name="rekap"),
    path("<str:kode>/preview/", views.preview, name="preview"),
    path("<str:kode>/upload/", views.upload_dokumen, name="upload_dokumen"),
    path("<str:kode>/upload/<str:jenis>/hapus/", views.hapus_dokumen, name="hapus_dokumen"),
]
