"""
Peran aktif untuk user ber-role ganda (IMPROVEMENT_PLAN_19102026.MD §6).

Peran yang dipilih di sesi (`session["peran_aktif"]`) ditimpakan ke
`request.user.role` DI MEMORI, sehingga `role_required`, sidebar,
`role_redirect`, context processor, dan snapshot `role` di Log Sistem otomatis
mengikuti peran aktif. `User.save()` menjaga agar nilai ini tidak tersimpan
ke database (lihat `_role_db`).
"""

SESSION_KEY = "peran_aktif"


def tentukan_peran(user, peran_sesi):
    """Peran aktif yang sah: peran di sesi bila masih dimiliki; bila tidak,
    peran terakhir (`User.role`) bila dimiliki; bila tidak, prioritas
    `URUTAN_PERAN`."""
    dimiliki = user.daftar_peran()
    if peran_sesi in dimiliki:
        return peran_sesi
    if user.role in dimiliki:
        return user.role
    return dimiliki[0] if dimiliki else user.role


class PeranAktifMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user  # SimpleLazyObject; dievaluasi hanya bila diakses
        if user.is_authenticated:
            peran = tentukan_peran(user, request.session.get(SESSION_KEY))
            if request.session.get(SESSION_KEY) != peran:
                request.session[SESSION_KEY] = peran
            user._role_db = user.role
            user.role = peran
        return self.get_response(request)
