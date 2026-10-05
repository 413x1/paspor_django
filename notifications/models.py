from django.conf import settings
from django.db import models


class Notification(models.Model):
    """
    Notifikasi in-app (Toast Pop-up + Notification Center) untuk modul
    Pengajuan Surat, mengikuti wiki/instructions/SKENARIO_NOTIFIKASI_SURAT.md.

    Satu baris = satu notifikasi untuk satu penerima. Event dengan beberapa
    penerima (mis. NOTIF_02A ke Pegawai sekaligus seluruh Admin PKLN)
    menghasilkan beberapa baris dengan `event` yang sama.
    """

    class Event(models.TextChoices):
        SUBMIT_UNOR = "NOTIF_01_SUBMIT_UNOR", "Pengajuan Surat Baru"
        APPROVE_UNOR = "NOTIF_02A_APPROVE_UNOR", "Disetujui Unor / Diteruskan ke PKLN"
        REJECT_UNOR = "NOTIF_02B_REJECT_UNOR", "Dikembalikan oleh Admin Unor"
        RESUBMIT_UNOR = "NOTIF_02C_RESUBMIT_UNOR", "Pengajuan Ulang ke Admin Unor"
        COMPLETE_PKLN = "NOTIF_03A_COMPLETE_PKLN", "Selesai & Terbit oleh Admin PKLN"
        REJECT_PKLN_UNOR = "NOTIF_03B_REJECT_PKLN_TO_UNOR", "Dikembalikan Admin PKLN ke Admin Unor"
        # PDLN Tipe 2 — tahap BPSDM
        FORWARD_BPSDM = "NOTIF_04A_FORWARD_BPSDM", "Diteruskan Unor ke Admin BPSDM"
        RESUBMIT_BPSDM = "NOTIF_04B_RESUBMIT_BPSDM", "Perbaikan diteruskan ke Admin BPSDM"
        REJECT_BPSDM_UNOR = "NOTIF_04C_REJECT_BPSDM_TO_UNOR", "Dikembalikan Admin BPSDM ke Admin Unor"
        # Pelaporan PDLN
        LAPORAN_DIUNGGAH = "NOTIF_05A_LAPORAN_DIUNGGAH", "Laporan PDLN diunggah"
        LAPORAN_DIKEMBALIKAN = "NOTIF_05B_LAPORAN_DIKEMBALIKAN", "Laporan PDLN dikembalikan"
        LAPORAN_DISETUJUI = "NOTIF_05C_LAPORAN_DISETUJUI", "Laporan PDLN disetujui"
        # Pembatalan
        PEMBATALAN_DIAJUKAN = "NOTIF_06A_PEMBATALAN_DIAJUKAN", "Permohonan pembatalan diajukan"
        PEMBATALAN_MENUNGGU_PAKLN = "NOTIF_06B_PEMBATALAN_MENUNGGU_PAKLN", "Pembatalan menunggu Biro PAKLN"
        PEMBATALAN_DITOLAK = "NOTIF_06C_PEMBATALAN_DITOLAK", "Permohonan pembatalan ditolak"
        PEMBATALAN_DISETUJUI = "NOTIF_06D_PEMBATALAN_DISETUJUI", "Perjalanan dibatalkan"
        PEMBATALAN_DITARIK = "NOTIF_06E_PEMBATALAN_DITARIK", "Permohonan pembatalan ditarik"

    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        DANGER = "danger", "Danger"
        SUCCESS = "success", "Success"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    pengajuan = models.ForeignKey(
        "pengajuan.Pengajuan", on_delete=models.CASCADE, related_name="notifications",
        null=True, blank=True,
    )
    event = models.CharField(max_length=40, choices=Event.choices)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=200)
    body = models.TextField()
    redirect_url = models.CharField(max_length=255, blank=True)

    is_read = models.BooleanField(default=False)
    is_toasted = models.BooleanField(default=False)
    # Ditutup ("x") oleh user dari panel Notification Center — hilang dari
    # panel cepat, tapi baris tetap tersimpan untuk jejak audit dan masih
    # tampil pada halaman "Lihat Semua".
    is_dismissed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "is_toasted"]),
            models.Index(fields=["recipient", "is_dismissed"]),
        ]
        verbose_name = "Notifikasi"
        verbose_name_plural = "Notifikasi"

    def __str__(self):
        return f"[{self.event}] {self.title} -> {self.recipient}"
