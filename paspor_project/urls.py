from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts import views as account_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth & landing
    path("", account_views.role_redirect, name="home"),
    path("login/", account_views.login_view, name="login"),
    path("logout/", account_views.logout_view, name="logout"),

    # Role-based sections (namespaced, sesuai 3 role pada mockup)
    path("pegawai/", include(("pengajuan.urls_pegawai", "pegawai"), namespace="pegawai")),
    path("admin-unor/", include(("pengajuan.urls_unor", "unor"), namespace="unor")),
    path("admin-biropakln/", include(("pengajuan.urls_pakln", "pakln"), namespace="pakln")),

    # Demo unggah berkas PDF ke MinIO — publik, tanpa login (lihat wiki/UPLOAD_FILE.MD)
    path("upload/", include(("fileupload.urls", "fileupload"), namespace="fileupload")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
