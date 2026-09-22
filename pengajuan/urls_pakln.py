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
    path("negara/", views.kelola_negara, name="kelola_negara"),
    path("negara/<int:negara_id>/edit/", views.edit_negara, name="edit_negara"),
    path("negara/<int:negara_id>/toggle/", views.toggle_negara, name="toggle_negara"),
    path("negara/<int:negara_id>/hapus/", views.hapus_negara, name="hapus_negara"),
    path("sumber-pembiayaan/", views.kelola_sumber_pembiayaan, name="kelola_sumber_pembiayaan"),
    path("sumber-pembiayaan/<int:sumber_id>/edit/", views.edit_sumber_pembiayaan, name="edit_sumber_pembiayaan"),
    path("sumber-pembiayaan/<int:sumber_id>/toggle/", views.toggle_sumber_pembiayaan, name="toggle_sumber_pembiayaan"),
    path("sumber-pembiayaan/<int:sumber_id>/hapus/", views.hapus_sumber_pembiayaan, name="hapus_sumber_pembiayaan"),
    path("<str:kode>/preview/", views.preview, name="preview"),
    path("<str:kode>/upload/", views.upload_dokumen, name="upload_dokumen"),
    path("<str:kode>/upload/<str:jenis>/hapus/", views.hapus_dokumen, name="hapus_dokumen"),
    path("export/", views.export_database, name="export"),
]
