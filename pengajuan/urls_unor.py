from django.urls import path

from . import views_unor as views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("dashboard/data/", views.dashboard_data, name="dashboard_data"),
    path("<str:kode>/preview/", views.preview, name="preview"),
    path("<str:kode>/upload/", views.upload_dokumen, name="upload_dokumen"),
    path("<str:kode>/upload/<str:jenis>/hapus/", views.hapus_dokumen, name="hapus_dokumen"),
    path("export/", views.export_database, name="export"),
    path("export/data/", views.export_data, name="export_data"),
]
