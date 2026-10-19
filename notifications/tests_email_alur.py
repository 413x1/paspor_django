"""Email terpicu dari alur pengajuan sungguhan, sinkron dengan notifikasi in-app."""

from django.core import mail
from django.test import TestCase, override_settings

from accounts.models import PeranUser, User
from pengajuan.tests import _AlurMixin
from pengajuan.tests_pdln import _Basis

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
            ("admin_unor", "NOTIF_03A_COMPLETE_PKLN"),      # selesai (info untuk Admin Unor; semua admin diemailkan)
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


@override_settings(MAIL_ALLOW_SEND=True)
class EmailSemuaAdminTests(_Basis, TestCase):
    """Instruksi mentor: begitu pegawai melanjutkan proses, SEMUA admin pada rantai (Unor, BPSDM,
    BKO, Biro PAKLN) menerima email, bukan hanya notifikasi di website."""

    def setUp(self):
        super().setUp()
        for user in (self.pegawai, self.admin_unor, self.admin_bpsdm, self.admin_pakln, self.admin_bko):
            user.email = f"{user.username}@pu.go.id"
            user.save()

    def _email(self):
        return {(log.recipient.role, log.event) for log in EmailLog.objects.select_related("recipient")}

    def test_alur_tipe2_mengirim_email_ke_unor_bpsdm_bko_dan_pakln(self):
        p = self.isi_formulir("T2P")
        self.kirim(p)
        self.unor_teruskan(p)
        self.bpsdm_teruskan(p)
        email = self._email()
        for harapan in (("admin_unor", "NOTIF_01_SUBMIT_UNOR"), ("admin_bpsdm", "NOTIF_04A_FORWARD_BPSDM"),
                        ("admin_pakln", "NOTIF_02A_APPROVE_UNOR"), ("admin_bko", "NOTIF_07A_FORWARD_BKO")):
            self.assertIn(harapan, email)
        self.assertTrue(EmailLog.objects.filter(status=EmailLog.Status.PENDING).exists())

    def test_laporan_pdln_diemailkan_ke_admin_pakln(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.unor_teruskan(p)
        self.pakln_selesai(p)
        self.unggah_laporan(p)
        self.assertIn(("admin_pakln", "NOTIF_05A_LAPORAN_DIUNGGAH"), self._email())

    def test_pembatalan_diajukan_diemailkan_ke_admin_unor(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.post(self.pegawai, "pegawai:ajukan_pembatalan", {"alasan": "Agenda diundur"}, kode=p.kode)
        self.assertIn(("admin_unor", "NOTIF_06A_PEMBATALAN_DIAJUKAN"), self._email())

    def test_email_pegawai_tetap_memakai_daftar_putih(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.unor_teruskan(p)
        self.pakln_selesai(p)
        self.unggah_laporan(p)
        pegawai = {e for r, e in self._email() if r == "pegawai"}
        self.assertIn("NOTIF_03A_COMPLETE_PKLN", pegawai)
        self.assertNotIn("NOTIF_05A_LAPORAN_DIUNGGAH", pegawai)

    def test_admin_tanpa_email_tidak_membuat_alur_gagal(self):
        User.objects.filter(pk=self.admin_unor.pk).update(email="")
        p = self.isi_formulir("T1")
        resp = self.kirim(p)
        self.assertEqual(resp.status_code, 302)
        log = EmailLog.objects.get(recipient=self.admin_unor, event="NOTIF_01_SUBMIT_UNOR")
        self.assertEqual(log.status, EmailLog.Status.SKIPPED)
        self.assertIn("belum memiliki email", log.status_note)
        self.assertTrue(Notification.objects.filter(recipient=self.admin_unor, event="NOTIF_01_SUBMIT_UNOR").exists())

    def test_user_role_ganda_menerima_email_sesuai_peran_yang_dituju(self):
        ganda = User.objects.create_user("ganda", password="x", role="pegawai", email="ganda@pu.go.id",
                                         unit_organisasi=self.unor)
        PeranUser.objects.update_or_create(user=ganda, role="admin_unor", defaults={"unit_organisasi": self.unor})
        p = self.isi_formulir("T1")
        self.kirim(p)
        # Peran aktif ganda = pegawai, tetapi notifikasi ini ditujukan ke peran Admin Unor.
        self.assertTrue(EmailLog.objects.filter(recipient=ganda, event="NOTIF_01_SUBMIT_UNOR").exists())

    def test_template_admin_memuat_ringkasan_tindak_lanjut_dan_tautan(self):
        p = self.isi_formulir("T2P")
        self.kirim(p)
        self.unor_teruskan(p)
        log = EmailLog.objects.get(recipient=self.admin_bpsdm, event="NOTIF_04A_FORWARD_BPSDM")
        self.assertIn("Tindak lanjut diperlukan", log.body_html)
        self.assertIn("TINDAK LANJUT DIPERLUKAN", log.body_text)
        self.assertIn(p.kode, log.body_html)
        self.assertIn(f"/admin-bpsdm/{p.kode}/preview/", log.body_text)
