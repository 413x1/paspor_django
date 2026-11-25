"""Pembatas percobaan login (anti password guessing online).

Setiap login gagal dihitung memakai django-ratelimit pada dua lapis:

1. **IP + username** — ``LOGIN_BATAS_GAGAL`` kali gagal (bawaan 5) untuk satu
   username dari satu IP memblokir kombinasi tersebut. Login yang berhasil
   mereset hitungan ini, hanya untuk username yang berhasil login.
2. **IP** (semua username) — ``LOGIN_BATAS_GAGAL_IP`` kali gagal (bawaan 20)
   dari satu IP memblokir seluruh IP. Hitungan ini TIDAK direset oleh login
   berhasil, sehingga penyerang yang punya akun tidak bisa menghapus jejak
   tebakannya ke akun lain dengan login memakai akunnya sendiri, dan menyebar
   tebakan ke banyak username (password spraying) tetap tertahan.

Hitungan berlaku dalam jendela ``LOGIN_DURASI_BLOKIR`` detik; blokir berlaku
``LOGIN_DURASI_BLOKIR`` detik (bawaan 600 = 10 menit) sejak kegagalan yang
memicunya. Selama diblokir, POST ke halaman login (aplikasi maupun /admin/)
ditolak dengan status 429 tanpa memeriksa kredensial.

Penghitung & daftar blokir disimpan di cache ``RATELIMIT_USE_CACHE`` (Redis di
produksi) agar berlaku lintas worker Gunicorn. Bila cache tidak dapat
dihubungi, pembatas *fail open* (login tetap jalan) dan kejadiannya dicatat
di log teknis, supaya gangguan Redis tidak mengunci seluruh pengguna.
"""

import hashlib
import logging
import math
import time

from django.conf import settings
from django.core.cache import caches
from django_ratelimit.core import get_usage

from logs.utils import _ambil_ip

logger = logging.getLogger(__name__)

GRUP_IP_USERNAME = "accounts.login-gagal.ip-username"
GRUP_IP = "accounts.login-gagal.ip"
_PREFIX_BLOKIR = "login-blokir:"


def batas_gagal():
    """Batas kegagalan per kombinasi IP + username."""
    return int(getattr(settings, "LOGIN_BATAS_GAGAL", 5))


def batas_gagal_ip():
    """Batas kegagalan per IP untuk semua username."""
    return int(getattr(settings, "LOGIN_BATAS_GAGAL_IP", 20))


def durasi_blokir():
    return int(getattr(settings, "LOGIN_DURASI_BLOKIR", 600))


def _cache():
    return caches[getattr(settings, "RATELIMIT_USE_CACHE", "default")]


def ip_klien(request):
    return _ambil_ip(request) or "tanpa-ip"


def _normal(username):
    """Username dinormalkan (huruf kecil, tanpa spasi tepi) agar variasi huruf
    besar/kecil tidak menjadi hitungan terpisah."""
    return str(username or "").strip().lower()


def _nilai_ip_username(ip, username):
    return f"{ip}|{_normal(username)}"


def _lapis(request, username):
    """(grup, nilai kunci, batas) untuk tiap lapis penghitung."""
    ip = ip_klien(request)
    return (
        (GRUP_IP_USERNAME, _nilai_ip_username(ip, username), batas_gagal()),
        (GRUP_IP, ip, batas_gagal_ip()),
    )


def _kunci_blokir(grup, nilai):
    return _PREFIX_BLOKIR + grup + ":" + hashlib.sha256(nilai.encode("utf-8")).hexdigest()


def sisa_blokir(request, username=""):
    """Sisa detik blokir untuk IP peminta (atau kombinasi IP + username);
    0 bila tidak diblokir."""
    try:
        cache = _cache()
        sampai = [cache.get(_kunci_blokir(grup, nilai)) for grup, nilai, _ in _lapis(request, username)]
    except Exception:  # cache (Redis) tidak tersedia -> fail open
        logger.exception("Pembatas login: cache tidak dapat dibaca")
        return 0
    sampai = max((s for s in sampai if s), default=0)
    return max(0, math.ceil(sampai - time.time())) if sampai else 0


def catat_gagal(request, username=""):
    """Hitung satu kegagalan login pada kedua lapis; blokir lapis yang
    mencapai batas. Mengembalikan True bila kini ada blokir baru."""
    diblokir = []
    try:
        for grup, nilai, batas in _lapis(request, username):
            usage = get_usage(
                request, group=grup, key=lambda g, r, v=nilai: v,
                rate=(batas, durasi_blokir()), increment=True,
            )
            # count = jumlah kegagalan dalam jendela, termasuk yang barusan.
            if usage is not None and usage["count"] >= batas:
                _cache().set(_kunci_blokir(grup, nilai), time.time() + durasi_blokir(), durasi_blokir())
                diblokir.append((grup, batas))
    except Exception:  # cache (Redis) tidak tersedia -> fail open
        logger.exception("Pembatas login: cache tidak dapat ditulis")
        return False
    if not diblokir:
        return False

    from logs.models import ActivityLog
    from logs.utils import record_activity
    ip = ip_klien(request)
    menit = durasi_blokir() // 60
    for grup, batas in diblokir:
        if grup == GRUP_IP:
            deskripsi = f"IP diblokir sementara {menit} menit setelah {batas} kali login gagal"
        else:
            deskripsi = f"Username diblokir sementara {menit} menit dari IP ini setelah {batas} kali login gagal"
        logger.warning("Pembatas login: %s (IP %s, username %r)", deskripsi, ip, username)
        record_activity(request, ActivityLog.Aktivitas.LOGIN_GAGAL, deskripsi,
                        status=ActivityLog.Status.GAGAL, username=username)
    return True


def reset_gagal(request, username):
    """Login berhasil: hitungan kegagalan kombinasi IP + username tersebut
    dimulai lagi dari nol. Hitungan per IP sengaja TIDAK direset.
    Kunci dibentuk persis seperti `get_usage` django-ratelimit (versi dipin di
    requirements.txt) agar penghitung yang sama yang dihapus."""
    from django_ratelimit import ALL
    from django_ratelimit.core import _get_window, _make_cache_key

    nilai = _nilai_ip_username(ip_klien(request), username)
    rate = (batas_gagal(), durasi_blokir())
    kunci = _make_cache_key(GRUP_IP_USERNAME, _get_window(nilai, durasi_blokir()), rate, nilai, ALL)
    try:
        _cache().delete(kunci)
    except Exception:  # cache (Redis) tidak tersedia
        logger.exception("Pembatas login: penghitung tidak dapat direset")


def pesan_blokir(detik):
    menit = max(1, math.ceil(detik / 60))
    return (f"Terlalu banyak percobaan login yang gagal dari perangkat/jaringan Anda. "
            f"Silakan coba lagi dalam {menit} menit.")
