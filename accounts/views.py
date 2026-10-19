from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from logs.models import ActivityLog
from logs.utils import record_activity
from paspor.integrasi import ehrm

from . import sso
from .middleware import SESSION_KEY
from .models import User

PESAN_LOGIN_GAGAL = "Username atau password salah. Silakan coba lagi."
PESAN_TANPA_PASSWORD = "Akun ini belum memiliki password. Masuk dengan SSO, lalu atur password di menu Profil."


def sso_tersedia():
    """Tombol "Masuk dengan SSO" tampil bila SSO aktif, atau stub saat DEBUG."""
    return settings.SSO_ENABLED or settings.DEBUG


def login_view(request):
    """Halaman login tunggal untuk seluruh role. Setelah berhasil login,
    pengguna diarahkan otomatis ke beranda/dasbor sesuai peran aktif oleh
    `role_redirect`."""
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("home")
        error = PESAN_LOGIN_GAGAL
        # AB-04: akun tanpa password (SSO saja) diarahkan ke SSO.
        akun = User.objects.filter(username__iexact=username).first() if username else None
        if akun is not None and akun.is_active and not akun.has_usable_password():
            error = PESAN_TANPA_PASSWORD

    return render(request, "registration/login.html", {"error": error, "sso_tersedia": sso_tersedia()})


def logout_view(request):
    logout(request)
    return redirect("login")


def sso_login(request):
    """`/login/sso/` — adaptor protokol SSO (menunggu Q1), atau stub pilih-NIP
    saat `DEBUG=True` dan `SSO_ENABLED=False`."""
    if settings.SSO_ENABLED:
        # Adaptor protokol belum diimplementasikan (Q1 terbuka): lihat
        # SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD §7.4.
        messages.error(request, "Login SSO belum tersedia. Silakan masuk dengan username & password.")
        return redirect("login")
    if not settings.DEBUG:
        raise Http404
    return sso_stub(request)


def sso_stub(request):
    """Stub pengembangan: pilih NIP dari data stub e-HRM lalu jalankan alur
    `masuk_dari_sso` seolah penyedia SSO mengembalikan identitas tersebut."""
    if not settings.DEBUG or settings.SSO_ENABLED:
        raise Http404
    if request.method == "POST":
        nip = request.POST.get("nip", "").strip()
        try:
            sso.masuk_dari_sso(request, sub=f"stub-{nip}", nip=nip, klaim={})
        except sso.SsoGagal as exc:
            messages.error(request, str(exc))
            return redirect("sso_login")
        return redirect("home")
    return render(request, "registration/sso_stub.html", {"daftar_nip": ehrm.daftar_stub()})


@login_required
@require_POST
def ganti_peran(request):
    """Ganti peran aktif user ber-role ganda (AB-10) tanpa login ulang."""
    user = request.user
    peran = request.POST.get("peran", "")
    if not user.punya_peran(peran):
        messages.error(request, "Peran tidak tersedia untuk akun Anda.")
        return redirect("home")
    request.session[SESSION_KEY] = peran
    # Peran ini menjadi default pada login berikutnya.
    User.objects.filter(pk=user.pk).update(role=peran)
    user._role_db = peran
    sebelumnya, user.role = user.role, peran
    record_activity(
        request, ActivityLog.Aktivitas.GANTI_PERAN,
        f"Ganti peran: {User.Role(sebelumnya).label} → {User.Role(peran).label}",
        target_type="user", target_id=user.pk,
    )
    return redirect("home")


@login_required
def role_redirect(request):
    """Landing page "/" mengarahkan pengguna ke halaman utama sesuai peran
    aktif."""
    role = request.user.role
    if role == User.Role.PEGAWAI:
        return redirect("pegawai:beranda")
    if role == User.Role.ADMIN_UNOR:
        return redirect("unor:dashboard")
    if role == User.Role.ADMIN_BPSDM:
        return redirect("bpsdm:dashboard")
    if role == User.Role.ADMIN_PAKLN:
        return redirect("pakln:dashboard")
    if role == User.Role.ADMIN_BKO:
        return redirect("bko:dashboard")
    return redirect("login")
