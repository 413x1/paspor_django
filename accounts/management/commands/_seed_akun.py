"""Helper bersama seed akun: kontak dummy & PeranUser eksplisit."""

from accounts.models import PeranUser, User


def isi_kontak(user, *, email, no_hp):
    """Isi email & nomor HP dummy HANYA bila masih kosong — seed tidak menimpa
    kontak yang sudah ada (mis. dikoreksi Admin Biro PAKLN di produksi)."""
    berubah = []
    if not user.email and not User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
        user.email = email
        berubah.append("email")
    if not user.no_hp:
        user.no_hp = no_hp
        berubah.append("no_hp")
    if berubah:
        user.save(update_fields=berubah)


def beri_peran(user, role, unit=None):
    """Pastikan user memiliki PeranUser aktif `role` (Admin Unor: beserta unit)."""
    PeranUser.objects.update_or_create(
        user=user, role=role,
        defaults={"is_active": True, "unit_organisasi": unit if role == User.Role.ADMIN_UNOR else None},
    )
    user.reset_cache_peran()
