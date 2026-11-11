"""Surat Tugas Pimpinan Unor (PDLN Tipe 2) — Modul 4: tiga notifikasi (in-app dan email admin)."""

from datetime import date

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from notifications.models import EmailLog, Notification

from . import surat_tugas
from .models import DokumenBpsdm, Pengajuan
from .tests_surat_tugas_pakln import _DasarPakln
from .tests_surat_tugas_unor import _DasarUnor

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
E = Notification.Event
TIPE2 = ("T2P", "T2L")
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
PDF = b"%PDF-1.4\n%uji\n"


class _DasarNotif(_DasarUnor, _DasarPakln):
    def notif(self, event, p=None, **filt):
        qs = Notification.objects.filter(event=event, **filt)
        return qs.filter(pengajuan=p) if p else qs

    def unggah_izin_prinsip(self, p, tanggal=True):
        data = {"jenis": "izin_prinsip", "file": SimpleUploadedFile("ip.pdf", PDF, content_type="application/pdf")}
        if tanggal:
            data["tanggal_surat"] = date.today().isoformat()
        self.login(self.admin_bpsdm)
        return self.client.post(reverse("bpsdm:upload_dokumen", kwargs={"kode": p.kode}), data, follow=True)

    def di_bpsdm(self, tipe):
        p = self.pengajuan(tipe, S.PROSES_BPSDM, "")
        Pengajuan.objects.filter(pk=p.pk).update(preview_bpsdm_agree=True)
        return p


@override_settings(STORAGES=_STORAGES_MEMORI)
class NotifikasiJalurDibukaTests(_DasarNotif, TestCase):
    def test_izin_prinsip_pertama_memberi_tahu_admin_unor_unit_terkait(self):
        for tipe in TIPE2:
            p = self.di_bpsdm(tipe)
            self.unggah_izin_prinsip(p)
            n = self.notif(E.SURAT_TUGAS_DIBUKA, p).get()
            self.assertEqual(n.recipient, self.admin_unor, tipe)
            self.assertEqual(n.untuk_peran, "admin_unor")
            self.assertEqual(n.redirect_url, reverse("unor:surat_tugas", args=[p.kode]))
            self.assertIn(p.kode, n.title)
            self.assertIn("Surat Tugas", n.body)
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_admin_unor_unit_lain_tidak_menerima(self):
        lain = User.objects.create_user("unor2", password="x", role="admin_unor", unit_organisasi=self.unor_lain)
        p = self.di_bpsdm("T2P")
        self.unggah_izin_prinsip(p)
        self.assertFalse(self.notif(E.SURAT_TUGAS_DIBUKA, recipient=lain).exists())

    def test_mengganti_izin_prinsip_tidak_mengirim_notifikasi_lagi(self):
        p = self.di_bpsdm("T2P")
        self.unggah_izin_prinsip(p)
        self.unggah_izin_prinsip(p)
        self.assertEqual(self.notif(E.SURAT_TUGAS_DIBUKA, p).count(), 1)

    def test_izin_prinsip_gagal_tidak_mengirim_notifikasi(self):
        p = self.di_bpsdm("T2P")
        self.unggah_izin_prinsip(p, tanggal=False)                 # tanpa Tanggal Surat ditolak
        self.assertFalse(DokumenBpsdm.objects.filter(pengajuan=p).exists())
        self.assertFalse(self.notif(E.SURAT_TUGAS_DIBUKA, p).exists())

    def test_pengajuan_yang_jalurnya_sudah_terisi_tidak_diberi_notifikasi(self):
        p = self.di_bpsdm("T2P")
        Pengajuan.objects.filter(pk=p.pk).update(status_surat_tugas=SS.DIKIRIM)      # mis. hasil migrasi data
        self.unggah_izin_prinsip(p)
        self.assertFalse(self.notif(E.SURAT_TUGAS_DIBUKA, p).exists())

    def test_notifikasi_membuka_halaman_surat_tugas_dengan_peran_admin_unor(self):
        p = self.di_bpsdm("T2L")
        self.unggah_izin_prinsip(p)
        n = self.notif(E.SURAT_TUGAS_DIBUKA, p).get()
        self.login(self.admin_unor)
        resp = self.client.get(reverse("notifications:go", args=[n.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("unor:surat_tugas", args=[p.kode]))


@override_settings(STORAGES=_STORAGES_MEMORI)
class NotifikasiDikirimTests(_DasarNotif, TestCase):
    def test_kirim_memberi_tahu_admin_biro_pakln(self):
        for tipe in TIPE2:
            p = self.pengajuan(tipe, S.PROSES_BPSDM, SS.MENUNGGU)
            self.unggah(p)
            self.kirim_post(p)
            n = self.notif(E.SURAT_TUGAS_DIKIRIM, p).get()
            self.assertEqual((n.recipient, n.untuk_peran), (self.admin_pakln, "admin_pakln"), tipe)
            self.assertEqual(n.redirect_url, reverse("pakln:preview", args=[p.kode]))
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_hanya_admin_pakln_yang_menerima(self):
        p = self.pengajuan("T2P", S.PROSES_BPSDM, SS.MENUNGGU)
        self.unggah(p)
        self.kirim_post(p)
        penerima = set(self.notif(E.SURAT_TUGAS_DIKIRIM, p).values_list("recipient__username", flat=True))
        self.assertEqual(penerima, {"pakln1"})

    def test_kirim_gagal_tidak_mengirim_notifikasi(self):
        p = self.pengajuan("T2P", jalur=SS.MENUNGGU)
        self.kirim_post(p)                                          # tanpa berkas
        self.kirim_post(p, agree=False)                            # tanpa pernyataan
        self.assertFalse(self.notif(E.SURAT_TUGAS_DIKIRIM, p).exists())

    def test_kirim_ulang_setelah_dikembalikan_memberi_tahu_lagi(self):
        p = self.pengajuan("T2P", S.PROSES_PAKLN, SS.MENUNGGU)
        self.unggah(p)
        self.kirim_post(p)
        surat_tugas.kembalikan(p, self.admin_pakln, "Tanggal tidak sesuai")
        self.kirim_post(p)
        self.assertEqual(self.notif(E.SURAT_TUGAS_DIKIRIM, p).count(), 2)


@override_settings(STORAGES=_STORAGES_MEMORI)
class NotifikasiDikembalikanTests(_DasarNotif, TestCase):
    def test_kembalikan_memberi_tahu_admin_unor_beserta_catatan(self):
        for tipe in TIPE2:
            p = self.di_pakln(tipe, SS.DIKIRIM)
            self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "Nomor surat salah"})
            n = self.notif(E.SURAT_TUGAS_DIKEMBALIKAN, p).get()
            self.assertEqual((n.recipient, n.untuk_peran, n.level), (self.admin_unor, "admin_unor", "warning"), tipe)
            self.assertIn("Nomor surat salah", n.body)
            self.assertEqual(n.redirect_url, reverse("unor:surat_tugas", args=[p.kode]))
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_pegawai_dan_admin_lain_tidak_menerima(self):
        p = self.di_pakln("T2P", SS.DIKIRIM)
        self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "Tidak sesuai"})
        penerima = set(self.notif(E.SURAT_TUGAS_DIKEMBALIKAN, p).values_list("recipient__username", flat=True))
        self.assertEqual(penerima, {"unor1"})

    def test_kembalikan_gagal_tidak_mengirim_notifikasi(self):
        p = self.di_pakln("T2L", SS.DIKIRIM)
        self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "  "})          # catatan kosong
        q = self.di_pakln("T2P", SS.MENUNGGU)
        self.post_pakln(q, {"kembalikan_surat_tugas": "1", "catatan": "Tidak sesuai"})  # belum dikirim
        self.assertFalse(Notification.objects.filter(event=E.SURAT_TUGAS_DIKEMBALIKAN).exists())


@override_settings(STORAGES=_STORAGES_MEMORI, MAIL_ALLOW_SEND=True, MAIL_DEV_REDIRECT_TO="")
class EmailAdminTests(_DasarNotif, TestCase):
    """Admin menerima email untuk SEMUA notifikasi yang ditujukan kepadanya, termasuk tiga event baru."""

    def setUp(self):
        super().setUp()
        for user, email in ((self.admin_unor, "unor1@pu.go.id"), (self.admin_pakln, "pakln1@pu.go.id")):
            user.email = email
            user.save()

    def test_email_untuk_ketiga_event(self):
        p = self.di_bpsdm("T2P")
        self.unggah_izin_prinsip(p)                                                   # 9A -> Admin Unor
        self.unggah(p)
        self.kirim_post(p)                                                            # 9B -> Admin PAKLN
        Pengajuan.objects.filter(pk=p.pk).update(status=S.PROSES_PAKLN)
        surat_tugas.kembalikan(p, self.admin_pakln, "Perbaiki tanggal")               # 9C -> Admin Unor
        email = {
            (log.recipient.username, log.event)
            for log in EmailLog.objects.filter(pengajuan=p).select_related("recipient")
        }
        self.assertIn(("unor1", E.SURAT_TUGAS_DIBUKA), email)
        self.assertIn(("pakln1", E.SURAT_TUGAS_DIKIRIM), email)
        self.assertIn(("unor1", E.SURAT_TUGAS_DIKEMBALIKAN), email)

    def test_isi_email_dikembalikan_memuat_catatan_dan_tautan(self):
        p = self.di_pakln("T2L", SS.DIKIRIM)
        surat_tugas.kembalikan(p, self.admin_pakln, "Nomor surat salah")
        log = EmailLog.objects.get(recipient=self.admin_unor, event=E.SURAT_TUGAS_DIKEMBALIKAN)
        self.assertIn("Nomor surat salah", log.body_text)
        self.assertIn(f"/admin-unor/{p.kode}/surat-tugas/", log.body_text)
        self.assertIn(p.kode, log.subject)
