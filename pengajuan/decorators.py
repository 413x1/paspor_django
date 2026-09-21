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
