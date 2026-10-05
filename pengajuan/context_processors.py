"""Badge jumlah item "perlu tindakan" pada sidebar (BISNIS_PROSES_PDLN.MD §9)."""

from accounts.models import User

from .models import LaporanPdln, PermohonanPembatalan


def badge_sidebar(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.resolver_match:
        return {}
    from . import report

    badge = {}
    if user.role == User.Role.ADMIN_UNOR:
        badge["pembatalan"] = report.pembatalan_menunggu(user).count()
    elif user.role == User.Role.ADMIN_PAKLN:
        badge["pembatalan"] = PermohonanPembatalan.objects.filter(
            status=PermohonanPembatalan.Status.MENUNGGU_PAKLN
        ).count()
        badge["pelaporan"] = LaporanPdln.objects.filter(status=LaporanPdln.Status.MENUNGGU).count()
    elif user.role == User.Role.PEGAWAI:
        badge["pelaporan"] = LaporanPdln.objects.filter(
            pengajuan__pegawai=user, status=LaporanPdln.Status.DIKEMBALIKAN
        ).count()
    return {"sidebar_badge": badge}
