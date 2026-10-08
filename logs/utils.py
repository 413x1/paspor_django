import logging
from functools import wraps

from django.conf import settings
from django.db import transaction

from .models import ActivityLog

logger = logging.getLogger(__name__)

# Batas panjang agar baris log tidak membengkak (input ini berasal dari pengguna).
_MAKS_DESKRIPSI = 255
_MAKS_DETAIL = 1000
_MAKS_USER_AGENT = 512
_MAKS_PATH = 255


def _ambil_ip(request):
    """IP klien. `X-Forwarded-For` hanya dipercaya bila
    `ACTIVITY_LOG_TRUST_PROXY = True` di settings (aplikasi di belakang reverse
    proxy tepercaya); selain itu header ini bisa dipalsukan pengguna."""
    if getattr(settings, "ACTIVITY_LOG_TRUST_PROXY", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def record_activity(request, aktivitas, deskripsi="", *, status=ActivityLog.Status.BERHASIL,
                    target_type="", target_id="", detail="", username="", user=None):
    """Catat satu aktivitas pengguna. Contoh di dalam view:

        record_activity(request, ActivityLog.Aktivitas.KIRIM_PENGAJUAN,
                        f"Mengirim pengajuan {p.kode}", target_type="pengajuan", target_id=p.kode)

    - `request` boleh None (mis. dari management command); IP/UA/path lalu kosong.
    - `username` dipakai bila belum ada pengguna login (mis. login gagal).
    - `user` menyebut pengguna secara eksplisit (mis. dari signal login/logout,
      saat `request.user` belum/tidak lagi menunjuk akun tersebut). Bila kosong,
      dipakai `request.user`.
    - JANGAN mengisi `deskripsi`/`detail` dengan kata sandi, token, atau isi berkas.

    Pencatatan TIDAK PERNAH menggagalkan request: kegagalan hanya ditulis ke log
    teknis dan fungsi mengembalikan None. Penyimpanan memakai savepoint sehingga
    error database tidak merusak transaksi (`atomic`) milik pemanggil.
    """
    try:
        if user is None:
            user = getattr(request, "user", None)
        if user is not None and not user.is_authenticated:
            user = None

        data = {
            "user": user,
            "username": (user.get_username() if user else username)[:150],
            "role": (getattr(user, "role", "") or "")[:30] if user else "",
            "aktivitas": str(aktivitas)[:50],
            "deskripsi": str(deskripsi)[:_MAKS_DESKRIPSI],
            "target_type": str(target_type)[:50],
            "target_id": str(target_id)[:100],
            "status": status,
            "detail": str(detail)[:_MAKS_DETAIL],
        }
        if request is not None:
            data.update(
                ip_address=_ambil_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:_MAKS_USER_AGENT],
                request_method=(request.method or "")[:10],
                request_path=request.path[:_MAKS_PATH],
            )
        with transaction.atomic():
            return ActivityLog.objects.create(**data)
    except Exception:
        logger.exception("Gagal mencatat aktivitas %r", aktivitas)
        return None


def log_aktivitas(aktivitas, deskripsi, *, methods=("POST",), target_type="", target_kwarg="",
                  sukses_redirect=False):
    """Dekorator view: catat aktivitas otomatis dari hasil response.

        @role_required("admin_pakln")
        @log_aktivitas("master.ubah", "Menghapus negara", target_type="negara", target_kwarg="negara_id")
        def hapus_negara(request, negara_id): ...

    - Hanya request ber-method `methods` (bawaan POST) yang dicatat; GET (menampilkan halaman) tidak.
    - Berhasil: status HTTP di bawah 400. Dengan `sukses_redirect=True` (view form yang
      menampilkan ulang halaman bila validasi gagal), berhasil HANYA bila response berupa
      redirect (3xx); response 200 dicatat gagal ("Validasi formulir gagal").
    - Status 400 ke atas, atau exception (dicatat lalu dilempar ulang), dicatat gagal.
    - Letakkan DI BAWAH `@role_required` / `@require_POST`, agar hanya akses yang sah yang dicatat.
    - Untuk view dengan beberapa hasil berbeda, panggil `record_activity` langsung di dalam view.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return view(request, *args, **kwargs)
            target_id = str(kwargs.get(target_kwarg, "")) if target_kwarg else ""
            try:
                response = view(request, *args, **kwargs)
            except Exception as exc:
                record_activity(
                    request, aktivitas, deskripsi, status=ActivityLog.Status.GAGAL,
                    target_type=target_type, target_id=target_id, detail=f"Exception: {type(exc).__name__}",
                )
                raise
            kode = response.status_code
            berhasil = 300 <= kode < 400 if sukses_redirect else kode < 400
            detail = "" if berhasil else (f"HTTP {kode}" if kode >= 400 else "Validasi formulir gagal")
            record_activity(
                request, aktivitas, deskripsi,
                status=ActivityLog.Status.BERHASIL if berhasil else ActivityLog.Status.GAGAL,
                target_type=target_type, target_id=target_id, detail=detail,
            )
            return response
        return wrapper
    return decorator


def _aktivitas_riwayat():
    A = ActivityLog.Aktivitas
    return {
        "dikirim": A.KIRIM_PENGAJUAN, "dikirim_ulang": A.KIRIM_PENGAJUAN,
        "diteruskan_pakln": A.TERUSKAN_PENGAJUAN, "diteruskan_ulang": A.TERUSKAN_PENGAJUAN,
        "diteruskan_bpsdm": A.TERUSKAN_PENGAJUAN, "diteruskan_ulang_bpsdm": A.TERUSKAN_PENGAJUAN,
        "dikembalikan_unor": A.KEMBALIKAN_PENGAJUAN, "dikembalikan_pakln": A.KEMBALIKAN_PENGAJUAN,
        "dikembalikan_bpsdm": A.KEMBALIKAN_PENGAJUAN, "laporan_dikembalikan": A.KEMBALIKAN_PENGAJUAN,
        "selesai": A.SELESAI_PENGAJUAN, "laporan_disetujui": A.SELESAI_PENGAJUAN,
        "laporan_diunggah": A.UNGGAH_DOKUMEN,
    }


def catat_riwayat(request, pengajuan, aksi):
    """Catat transisi status pengajuan ke Log Sistem. Dipanggil tepat setelah
    `riwayat.catat(...)` dengan `aksi` yang sama (mis. `RiwayatPengajuan.Aksi.DIKIRIM`).
    Catatan/alasan penolakan tidak ikut disalin ke log (cukup di Riwayat Pemrosesan)."""
    from pengajuan.models import RiwayatPengajuan  # impor lazy: hindari impor melingkar

    try:
        label = RiwayatPengajuan.Aksi(aksi).label
    except ValueError:
        label = str(aksi)
    return record_activity(
        request, _aktivitas_riwayat().get(str(aksi), ActivityLog.Aktivitas.PROSES_PENGAJUAN),
        f"{label} — {pengajuan.kode}", target_type="pengajuan", target_id=pengajuan.kode,
    )
