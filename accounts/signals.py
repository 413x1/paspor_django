from django.db.models.signals import post_save
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .models import PeranUser, User


@receiver(post_save, sender=User)
def _pastikan_peranuser(sender, instance, raw=False, update_fields=None, **kwargs):
    """KOMPATIBILITAS SEMENTARA (dihapus di Fase 6): user yang disimpan dengan
    `role` yang belum tercatat di PeranUser (seed/test lama yang hanya mengisi
    `User.role`) otomatis mendapat baris PeranUser untuk role tersebut. Peran
    yang pernah dicabut (`is_active=False`) tidak diaktifkan ulang."""
    if raw or not instance.role:
        return
    if update_fields is not None and "role" not in update_fields:
        return
    if PeranUser.objects.filter(user=instance, role=instance.role).exists():
        return
    PeranUser.objects.create(
        user=instance,
        role=instance.role,
        unit_organisasi_id=instance.unit_organisasi_id if instance.role == User.Role.ADMIN_UNOR else None,
    )
    instance.reset_cache_peran()


@receiver(user_login_failed)
def _hitung_login_gagal(sender, credentials, request=None, **kwargs):
    """Pembatas login: setiap kegagalan autentikasi (halaman login aplikasi
    maupun /admin/) dihitung per IP; lihat accounts/pembatas_login.py."""
    if request is None:
        return
    from . import pembatas_login
    pembatas_login.catat_gagal(request, username=str(credentials.get("username", "")))


@receiver(user_logged_in)
def _reset_login_gagal(sender, request=None, user=None, **kwargs):
    """Login berhasil (password, /admin/, maupun SSO): hitungan login gagal kombinasi
    IP + username tersebut direset ke nol (hitungan per IP tidak)."""
    if request is None:
        return
    from . import pembatas_login
    pembatas_login.reset_gagal(request, user.get_username() if user is not None else "")
