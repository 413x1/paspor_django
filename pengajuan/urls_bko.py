from django.urls import path

from . import views_bko as views
from . import views_report

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("dashboard/data/", views.dashboard_data, name="dashboard_data"),
    path("pembatalan/", views.daftar_pembatalan, name="pembatalan"),
    path("export/", views_report.export_database, name="export"),
    path("export/data/", views_report.export_data, name="export_data"),
    path("rekap/", views_report.rekap, name="rekap"),
    path("<str:kode>/", views.proses, name="proses"),
    path("<str:kode>/hapus/<str:jenis>/", views.hapus_dokumen, name="hapus_dokumen"),
]
