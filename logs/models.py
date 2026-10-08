from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """
    Satu baris = satu aktivitas pengguna pada sistem (siapa, melakukan apa,
    hasilnya, kapan, dan memakai apa). Lihat wiki/instructions/SYSTEM_LOGGING.MD.

    Baris log tidak pernah diedit; hanya ditambah (lewat `logs.utils.record_activity`)
    dan dihapus lewat fitur Reset Log (hapus permanen).
    """

    class Aktivitas(models.TextChoices):
        """Katalog kode aktivitas (untuk dropdown filter). Sengaja tidak dipasang
        sebagai `choices` pada field, agar menambah kode baru tidak perlu migrasi."""

        LOGIN = "auth.login", "Login"
        LOGIN_GAGAL = "auth.login_failed", "Login gagal"
        LOGOUT = "auth.logout", "Logout"
        SIMPAN_FORMULIR = "pengajuan.simpan_formulir", "Menyimpan formulir pengajuan"
        KIRIM_PENGAJUAN = "pengajuan.kirim", "Mengirim pengajuan"
        TERUSKAN_PENGAJUAN = "pengajuan.teruskan", "Meneruskan pengajuan"
        KEMBALIKAN_PENGAJUAN = "pengajuan.kembalikan", "Mengembalikan pengajuan"
        SELESAI_PENGAJUAN = "pengajuan.selesai", "Menyelesaikan pengajuan"
        PROSES_PENGAJUAN = "pengajuan.proses", "Memproses pengajuan"
        UNGGAH_DOKUMEN = "dokumen.unggah", "Mengunggah dokumen"
        HAPUS_DOKUMEN = "dokumen.hapus", "Menghapus dokumen"
        GENERATE_ND = "dokumen.generate_nd", "Generate/unduh Nota Dinas"
        UBAH_MASTER = "master.ubah", "Mengubah data master"
        RESET_LOG = "log.reset", "Reset Log"

    class Status(models.TextChoices):
        BERHASIL = "success", "Berhasil"
        GAGAL = "failed", "Gagal"

    # Siapa. FK kosong untuk pengguna anonim (mis. login gagal); `username` dan
    # `role` adalah snapshot agar log tetap terbaca bila akun kemudian dihapus.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="activity_logs",
    )
    username = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=30, blank=True)

    # Melakukan apa, pada objek apa.
    aktivitas = models.CharField(max_length=50)
    deskripsi = models.CharField(max_length=255, blank=True)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=100, blank=True)

    # Hasil aktivitas.
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BERHASIL)
    detail = models.TextField(blank=True)

    # Kapan dan memakai apa.
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"], name="log_timestamp_idx"),
            models.Index(fields=["aktivitas", "timestamp"], name="log_aktivitas_ts_idx"),
            models.Index(fields=["status", "timestamp"], name="log_status_ts_idx"),
            models.Index(fields=["user", "timestamp"], name="log_user_ts_idx"),
        ]
        verbose_name = "Log Aktivitas"
        verbose_name_plural = "Log Aktivitas"

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} {self.username or 'anonim'} — {self.aktivitas} ({self.status})"
