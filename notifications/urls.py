from django.urls import path

from . import views

urlpatterns = [
    path("", views.list_view, name="list"),
    path("<int:pk>/buka/", views.go, name="go"),
    path("<int:pk>/hapus/", views.dismiss, name="dismiss"),
    path("hapus-semua/", views.clear_all, name="clear_all"),
    path("baca-semua/", views.mark_all_read, name="mark_all_read"),
]
