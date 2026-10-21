from django.urls import path

from . import views_report
from . import views_unor as views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("dashboard/data/", views.dashboard_data, name="dashboard_data"),
    path("pembatalan/", views.daftar_pembatalan, name="pembatalan"),
    path("pembatalan/<int:pk>/putuskan/", views.putuskan_pembatalan, name="putuskan_pembatalan"),
    path("pembatalan/<int:pk>/tarik/", views.tarik_pembatalan, name="tarik_pembatalan"),
    path("pelaporan/", views.pelaporan, name="pelaporan"),
    path("export/", views_report.export_database, name="export"),
    path("export/data/", views_report.export_data, name="export_data"),
    path("rekap/", views_report.rekap, name="rekap"),
    path("<str:kode>/preview/", views.preview, name="preview"),
    path("<str:kode>/upload/", views.upload_dokumen, name="upload_dokumen"),
    path("<str:kode>/upload/<str:jenis>/hapus/", views.hapus_dokumen, name="hapus_dokumen"),
    path("<str:kode>/batalkan/", views.ajukan_pembatalan, name="ajukan_pembatalan"),
]
