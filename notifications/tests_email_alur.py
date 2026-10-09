"""Email terpicu dari alur pengajuan sungguhan, sinkron dengan notifikasi in-app."""

from django.core import mail
from django.test import TestCase, override_settings

from pengajuan.tests import _AlurMixin

from .models import EmailLog, Notification


@override_settings(MAIL_ALLOW_SEND=True)
class EmailAlurPengajuanTests(_AlurMixin, TestCase):
    def setUp(self):
        super().setUp()
        for user, email in ((self.pegawai, "pegawai1@pu.go.id"), (self.admin_unor, "unor1@pu.go.id"),
                            (self.admin_pakln, "pakln1@pu.go.id")):
            user.email = email
            user.save()

    def _email(self):
        """Daftar (peran penerima, event) email yang dibuat, urut dibuat."""
        return [(log.recipient.role, log.event) for log in EmailLog.objects.select_related("recipient").order_by("pk")]

    def test_alur_penuh_memicu_email_ke_pihak_yang_tepat(self):
        self.kirim()
        self.kembalikan_unor()
        self.kirim()
        self.teruskan()
        self.selesaikan()
        self.assertEqual(self._email(), [
            ("admin_unor", "NOTIF_01_SUBMIT_UNOR"),         # pegawai mengajukan
            ("pegawai", "NOTIF_02B_REJECT_UNOR"),           # dikembalikan Admin Unor
            ("admin_unor", "NOTIF_02C_RESUBMIT_UNOR"),      # pegawai memperbaiki
            ("pegawai", "NOTIF_02A_APPROVE_UNOR"),          # diteruskan (salinan pegawai)
            ("admin_pakln", "NOTIF_02A_APPROVE_UNOR"),      # diteruskan ke Admin PAKLN
            ("pegawai", "NOTIF_03A_COMPLETE_PKLN"),         # selesai
        ])

    def test_email_sinkron_dengan_notifikasi_in_app(self):
        self.kirim()
        self.kembalikan_unor()
        self.assertEqual(Notification.objects.filter(recipient=self.admin_unor, event="NOTIF_01_SUBMIT_UNOR").count(), 1)
        in_app = Notification.objects.get(recipient=self.pegawai, event="NOTIF_02B_REJECT_UNOR")
        email = EmailLog.objects.get(recipient=self.pegawai, event="NOTIF_02B_REJECT_UNOR")
        self.assertEqual(email.subject, f"[PASPOR] {in_app.title}")
        self.assertIn(in_app.body.split(". Silakan")[0], email.body_text)

    def test_konten_email_memuat_ringkasan_pengajuan_dan_tautan(self):
        self.kirim()
        log = EmailLog.objects.get(recipient=self.admin_unor)
        kode = self.pengajuan.kode
        self.assertIn(kode, log.body_html)
        self.assertIn("Pegawai Satu", log.body_text)
        self.assertIn(f"/admin-unor/{kode}/preview/", log.body_text)
        self.assertIn("Buka di PASPOR", log.body_html)
        self.assertIn("Tindakan Anda diperlukan", log.body_html)   # template khusus event submit_unor

    def test_email_terkirim_oleh_worker(self):
        from . import email_queue
        self.kirim()
        self.assertEqual(email_queue.proses_antrean(pacing=0)["terkirim"], 1)
        self.assertEqual(mail.outbox[0].to, ["unor1@pu.go.id"])

    def test_akun_tanpa_email_dilewati_tetapi_notifikasi_tetap_ada(self):
        self.admin_unor.email = ""
        self.admin_unor.save()
        self.kirim()
        self.assertEqual(Notification.objects.filter(recipient=self.admin_unor).count(), 1)
        log = EmailLog.objects.get(recipient=self.admin_unor)
        self.assertEqual((log.status, log.status_note), ("skipped", "Penerima belum memiliki email"))
