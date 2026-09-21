from django.urls import path

from . import views_pakln as views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("users/", views.kelola_user, name="kelola_user"),
    path("users/data/", views.users_data, name="users_data"),
    path("users/<int:user_id>/edit/", views.edit_user, name="edit_user"),
    path("templates/", views.kelola_template, name="kelola_template"),
    path("templates/<int:template_id>/edit/", views.edit_template, name="edit_template"),
    path("templates/<int:template_id>/toggle/", views.toggle_template, name="toggle_template"),
    path("templates/<int:template_id>/hapus/", views.hapus_template, name="hapus_template"),
    path("<str:kode>/preview/", views.preview, name="preview"),
    path("<str:kode>/upload/", views.upload_dokumen, name="upload_dokumen"),
    path("<str:kode>/upload/<str:jenis>/hapus/", views.hapus_dokumen, name="hapus_dokumen"),
    path("export/", views.export_database, name="export"),
]
