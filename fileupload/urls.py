from django.urls import path

from . import views

app_name = "fileupload"

urlpatterns = [
    path("", views.upload_view, name="upload"),
    path("<int:pk>/lihat/", views.view_file, name="view"),
    path("<int:pk>/hapus/", views.delete_view, name="delete"),
]
