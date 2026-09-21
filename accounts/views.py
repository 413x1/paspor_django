from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import User


def login_view(request):
    """Halaman login tunggal untuk seluruh role (Pegawai, Admin Unor,
    Admin Biro PAKLN). Setelah berhasil login, pengguna diarahkan otomatis
    ke beranda/dasbor sesuai role masing-masing oleh `role_redirect`."""
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            login(request, user)
            return redirect("home")
        error = "Username atau password salah. Silakan coba lagi."

    return render(request, "registration/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def role_redirect(request):
    """Landing page "/" mengarahkan pengguna ke halaman utama sesuai role,
    meniru perilaku role switcher pada mockup."""
    role = request.user.role
    if role == User.Role.PEGAWAI:
        return redirect("pegawai:beranda")
    if role == User.Role.ADMIN_UNOR:
        return redirect("unor:dashboard")
    if role == User.Role.ADMIN_PAKLN:
        return redirect("pakln:dashboard")
    return redirect("login")
