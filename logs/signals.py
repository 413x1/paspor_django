from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import ActivityLog
from .utils import record_activity

A = ActivityLog.Aktivitas


@receiver(user_logged_in)
def _login(sender, request, user, **kwargs):
    record_activity(request, A.LOGIN, "Login berhasil", user=user)


@receiver(user_logged_out)
def _logout(sender, request, user, **kwargs):
    if user is not None:  # logout tanpa sesi login tidak dicatat
        record_activity(request, A.LOGOUT, "Logout", user=user)


@receiver(user_login_failed)
def _login_gagal(sender, credentials, request=None, **kwargs):
    # Hanya username yang dicatat; kata sandi TIDAK PERNAH disimpan.
    username = str(credentials.get("username", ""))
    record_activity(
        request, A.LOGIN_GAGAL, "Login gagal", status=ActivityLog.Status.GAGAL, username=username,
    )
