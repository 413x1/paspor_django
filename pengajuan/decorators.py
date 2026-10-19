from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Membatasi akses view hanya untuk user dengan `role` tertentu,
    merepresentasikan pemisahan akses antara Pegawai, Admin Unor, dan
    Admin Biro PAKLN pada mockup."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied("Anda tidak memiliki akses ke halaman ini.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


PESAN_PENGAJUAN_SENDIRI = "Anda tidak dapat memproses pengajuan milik sendiri."


def pengajuan_milik_sendiri(user, pengajuan):
    """True bila `user` sedang bertindak sebagai admin atas pengajuan miliknya
    sendiri (AB-12). Sebagai Pegawai, pengajuan sendiri tentu boleh diolah."""
    return pengajuan.pegawai_id == user.pk and user.role != "pegawai"


def tolak_pengajuan_sendiri(request, pengajuan):
    """Panggil di setiap view aksi admin terhadap pengajuan (AB-12)."""
    if pengajuan_milik_sendiri(request.user, pengajuan):
        raise PermissionDenied(PESAN_PENGAJUAN_SENDIRI)
