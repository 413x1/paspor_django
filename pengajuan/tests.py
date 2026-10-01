"""Riwayat Pemrosesan Pengajuan — wiki/instructions/RIWAYAT_PEMROSESAN_PENGAJUAN.MD §9."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import PegawaiProfile, User
from paspor.models import UnitOrganisasi

from . import riwayat
from .models import (
    DokumenPakln, DokumenPegawai, DokumenUnor, DokumenUnorPendukung, Pengajuan, RiwayatPengajuan,
)

Aksi = RiwayatPengajuan.Aksi

PESAN_UNOR = "Formulir ILN belum ditandatangani pimpinan."
PESAN_PAKLN = "Nota Dinas ke Biro PAKLN belum sesuai format."


class _AlurMixin:
    def setUp(self):
        # org_units sudah terisi lewat migrasi data.
        self.unor, self.unor_lain = UnitOrganisasi.objects.all()[:2]
        self.pegawai = User.objects.create_user("pegawai1", password="x", role="pegawai")
        PegawaiProfile.objects.create(
            user=self.pegawai, nip="1990", nama="Pegawai Satu", jabatan="Staf",
            pangkat_golongan="III-a", unit_kerja="Biro", unit_organisasi=self.unor,
        )
        self.admin_unor = User.objects.create_user(
            "unor1", password="x", role="admin_unor", first_name="Admin", last_name="Unor",
            unit_organisasi=self.unor,
        )
        self.admin_pakln = User.objects.create_user(
            "pakln1", password="x", role="admin_pakln", first_name="Admin", last_name="PAKLN",
        )
        self.pengajuan = Pengajuan.objects.create(pegawai=self.pegawai, form_saved=True)
        for jenis, _ in DokumenPegawai.Jenis.choices:
            DokumenPegawai.objects.create(pengajuan=self.pengajuan, jenis=jenis, file="x.pdf")
        for jenis, _ in DokumenUnor.Jenis.choices:
            DokumenUnor.objects.create(pengajuan=self.pengajuan, jenis=jenis, file="x.pdf")
        DokumenUnorPendukung.objects.create(pengajuan=self.pengajuan, file="x.pdf", nd_sekunor=True)
        DokumenPakln.objects.create(
            pengajuan=self.pengajuan, jenis=DokumenPakln.Jenis.ILN_SEKJEN, file="x.pdf",
        )

    def _post(self, user, url_name, data):
        self.client.force_login(user)
        return self.client.post(reverse(url_name, args=[self.pengajuan.kode]), data)

    def kirim(self):
        self._post(self.pegawai, "pegawai:upload_dokumen", {"kirim": "1", "agree": "on"})

    def kembalikan_unor(self, catatan=PESAN_UNOR):
        self._post(self.admin_unor, "unor:preview", {"kembalikan": "1", "catatan": catatan})

    def teruskan(self):
        self._post(self.admin_unor, "unor:preview", {"lanjutkan": "1"})
        self._post(self.admin_unor, "unor:upload_dokumen", {"teruskan": "1", "agree": "on"})

    def kembalikan_pakln(self, catatan=PESAN_PAKLN):
        self._post(self.admin_pakln, "pakln:preview", {"kembalikan": "1", "catatan": catatan})

    def selesaikan(self):
        self._post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1"})
        self._post(self.admin_pakln, "pakln:upload_dokumen", {"selesaikan": "1", "agree": "on"})

    def alur_penuh(self):
        self.kirim()
        self.kembalikan_unor()
        self.kirim()
        self.teruskan()
        self.kembalikan_pakln()
        self.teruskan()
        self.selesaikan()

    def aksi_list(self):
        return list(self.pengajuan.riwayat.values_list("aksi", flat=True))


class PencatatanRiwayatTests(_AlurMixin, TestCase):
    def test_kirim_pertama(self):
        self.kirim()
        r = self.pengajuan.riwayat.get()
        self.assertEqual(r.aksi, Aksi.DIKIRIM)
        self.assertEqual((r.status_dari, r.status_ke), ("belum", "proses"))
        self.assertEqual(r.aktor, self.pegawai)
        self.assertEqual(r.aktor_role, "pegawai")
        self.assertEqual(r.aktor_nama, "Pegawai Satu")

    def test_alur_penuh_tercatat_berurutan(self):
        self.alur_penuh()
        self.pengajuan.refresh_from_db()
        self.assertEqual(self.pengajuan.status, Pengajuan.Status.SELESAI)
        self.assertEqual(self.aksi_list(), [
            Aksi.DIKIRIM, Aksi.DIKEMBALIKAN_UNOR, Aksi.DIKIRIM_ULANG, Aksi.DITERUSKAN_PAKLN,
            Aksi.DIKEMBALIKAN_PAKLN, Aksi.DITERUSKAN_PAKLN, Aksi.SELESAI,
        ])
        kembali_unor = self.pengajuan.riwayat.get(aksi=Aksi.DIKEMBALIKAN_UNOR)
        self.assertEqual(kembali_unor.catatan, PESAN_UNOR)
        self.assertEqual((kembali_unor.status_dari, kembali_unor.status_ke), ("proses", "belum"))
        kembali_pakln = self.pengajuan.riwayat.get(aksi=Aksi.DIKEMBALIKAN_PAKLN)
        self.assertEqual(kembali_pakln.catatan, PESAN_PAKLN)
        self.assertEqual(kembali_pakln.aktor_role, "admin_pakln")

    def test_pengembalian_berulang_tidak_saling_menimpa(self):
        self.kirim()
        self.kembalikan_unor("Pesan pertama")
        self.kirim()
        self.kembalikan_unor("Pesan kedua")
        pesan = list(
            self.pengajuan.riwayat.filter(aksi=Aksi.DIKEMBALIKAN_UNOR).values_list("catatan", flat=True)
        )
        self.assertEqual(pesan, ["Pesan pertama", "Pesan kedua"])

    def test_kembalikan_tanpa_catatan_tidak_dicatat(self):
        self.kirim()
        self.kembalikan_unor(catatan="  ")
        self.assertEqual(self.aksi_list(), [Aksi.DIKIRIM])


class VisibilitasRiwayatTests(_AlurMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.alur_penuh()

    def _get(self, user, url_name):
        self.client.force_login(user)
        return self.client.get(reverse(url_name, args=[self.pengajuan.kode]))

    def test_pegawai_hanya_melihat_pesan_unor(self):
        resp = self._get(self.pegawai, "pegawai:monitor_progres")
        self.assertContains(resp, PESAN_UNOR)
        self.assertNotContains(resp, PESAN_PAKLN)
        self.assertContains(resp, "Dikembalikan ke Admin Unor untuk perbaikan")
        # Pegawai tidak melihat nama pribadi admin.
        self.assertNotContains(resp, "Admin PAKLN (Biro PAKLN)")

    def test_admin_unor_melihat_pesan_pakln_dan_pesannya_sendiri(self):
        resp = self._get(self.admin_unor, "unor:preview")
        self.assertContains(resp, PESAN_PAKLN)
        self.assertContains(resp, PESAN_UNOR)

    def test_admin_pakln_melihat_semua_pesan(self):
        resp = self._get(self.admin_pakln, "pakln:preview")
        self.assertContains(resp, PESAN_UNOR)
        self.assertContains(resp, PESAN_PAKLN)

    def test_riwayat_untuk_mengosongkan_pesan_tidak_berhak(self):
        def pesan(user):
            return {e["aksi"]: e["catatan"] for e in riwayat.riwayat_untuk(self.pengajuan, user)}

        self.assertEqual(pesan(self.pegawai)[Aksi.DIKEMBALIKAN_PAKLN], "")
        self.assertEqual(pesan(self.pegawai)[Aksi.DIKEMBALIKAN_UNOR], PESAN_UNOR)
        self.assertEqual(pesan(self.admin_unor)[Aksi.DIKEMBALIKAN_UNOR], PESAN_UNOR)
        self.assertEqual(pesan(self.admin_unor)[Aksi.DIKEMBALIKAN_PAKLN], PESAN_PAKLN)
        self.assertEqual(pesan(self.admin_pakln)[Aksi.DIKEMBALIKAN_UNOR], PESAN_UNOR)
        self.assertEqual(pesan(self.admin_pakln)[Aksi.DIKEMBALIKAN_PAKLN], PESAN_PAKLN)

    def test_peta_alur_menghitung_pengembalian(self):
        self.pengajuan.refresh_from_db()
        peta = riwayat.peta_alur(self.pengajuan)
        self.assertEqual(peta["kembali_ke_pegawai"], 1)
        self.assertEqual(peta["kembali_ke_unor"], 1)
        self.assertEqual([s["state"] for s in peta["simpul"]], ["done"] * 4)

    def test_akses_pengajuan_orang_lain_tetap_ditolak(self):
        pegawai_lain = User.objects.create_user("pegawai2", password="x", role="pegawai")
        self.assertEqual(self._get(pegawai_lain, "pegawai:monitor_progres").status_code, 404)

        admin_unor_lain = User.objects.create_user(
            "unor2", password="x", role="admin_unor", unit_organisasi=self.unor_lain,
        )
        self.assertEqual(self._get(admin_unor_lain, "unor:preview").status_code, 404)


class RegresiCatatanTests(_AlurMixin, TestCase):
    def test_banner_catatan_dan_notifikasi_tetap_berjalan(self):
        from notifications.models import Notification

        self.kirim()
        self.kembalikan_unor()
        self.pengajuan.refresh_from_db()
        self.assertEqual(self.pengajuan.catatan_unor, PESAN_UNOR)
        self.assertTrue(Notification.objects.filter(
            recipient=self.pegawai, event=Notification.Event.REJECT_UNOR,
        ).exists())

        self.kirim()
        self.pengajuan.refresh_from_db()
        self.assertEqual(self.pengajuan.catatan_unor, "")
        self.assertTrue(Notification.objects.filter(event=Notification.Event.RESUBMIT_UNOR).exists())
