"""Jalur paralel Surat Tugas Pimpinan Unor (PDLN Tipe 2: T2P & T2L) — Modul 1: model dan state machine."""

import importlib
from datetime import date, timedelta

from django.apps import apps as django_apps
from django.test import TestCase

from accounts.models import User

from . import surat_tugas
from .models import DokumenUnor, Pengajuan, PermohonanPembatalan, RiwayatPengajuan
from .tests_pdln import _Basis

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
Aksi = RiwayatPengajuan.Aksi
TIPE2 = ("T2P", "T2L")


class _Dasar(_Basis):
    def pengajuan(self, tipe="T2P", status=S.PROSES_BPSDM, jalur="", pegawai=None):
        return Pengajuan.objects.create(
            pegawai=pegawai or self.pegawai, jenis_perjalanan="pdln", tipe_pdln=tipe, unit_organisasi=self.unor,
            tgl_berangkat=date.today() + timedelta(days=30), tgl_kembali=date.today() + timedelta(days=36),
            status=status, status_surat_tugas=jalur, tgl_pengajuan=date.today() - timedelta(days=5),
        )

    def berkas(self, p):
        return DokumenUnor.objects.create(pengajuan=p, jenis="surat_tugas", file="uji.pdf")

    def riwayat(self, p, aksi):
        return RiwayatPengajuan.objects.filter(pengajuan=p, aksi=aksi)


class ModelSuratTugasTests(_Dasar, TestCase):
    def test_hanya_pdln_tipe_2_memakai_jalur_paralel(self):
        for tipe in TIPE2:
            self.assertTrue(self.pengajuan(tipe).pakai_surat_tugas_paralel, tipe)
        self.assertFalse(self.pengajuan("T1").pakai_surat_tugas_paralel)
        self.assertFalse(self.pengajuan("T3").pakai_surat_tugas_paralel)
        nondinas = Pengajuan.objects.create(pegawai=self.pegawai, jenis_perjalanan="nondinas")
        self.assertFalse(nondinas.pakai_surat_tugas_paralel)

    def test_jalur_terbuka_bila_status_terisi(self):
        self.assertFalse(self.pengajuan().track_surat_tugas_terbuka)
        self.assertTrue(self.pengajuan(jalur=SS.MENUNGGU).track_surat_tugas_terbuka)
        self.assertFalse(self.pengajuan("T1", jalur=SS.MENUNGGU).track_surat_tugas_terbuka)


class BukaJalurTests(_Dasar, TestCase):
    def test_izin_prinsip_pertama_membuka_jalur_t2p_dan_t2l(self):
        for tipe in TIPE2:
            p = self.pengajuan(tipe)
            self.assertTrue(surat_tugas.buka_jalur(p), tipe)
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, SS.MENUNGGU)

    def test_tidak_dibuka_dua_kali_dan_tidak_menimpa_status_yang_ada(self):
        p = self.pengajuan(jalur=SS.DIKIRIM)
        self.assertFalse(surat_tugas.buka_jalur(p))
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

    def test_pengajuan_di_luar_tipe_2_tidak_berubah(self):
        for tipe in ("T1", "T3"):
            p = self.pengajuan(tipe)
            self.assertFalse(surat_tugas.buka_jalur(p))
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, "")


class PemeriksaanTests(_Dasar, TestCase):
    def test_tidak_bisa_ubah_sebelum_jalur_dibuka(self):
        self.assertIn("Izin Prinsip", surat_tugas.alasan_tidak_bisa_ubah(self.pengajuan()))

    def test_tidak_bisa_ubah_untuk_tipe_lain(self):
        self.assertIn("PDLN Tipe 2", surat_tugas.alasan_tidak_bisa_ubah(self.pengajuan("T1", jalur=SS.MENUNGGU)))

    def test_hanya_bisa_diubah_di_tahap_bpsdm_atau_biro_pakln(self):
        for status in (S.PROSES_BPSDM, S.PROSES_PAKLN):
            self.assertEqual(surat_tugas.alasan_tidak_bisa_ubah(self.pengajuan(status=status, jalur=SS.MENUNGGU)), "")
        for status in (S.PROSES, S.SELESAI, S.DIBATALKAN):
            self.assertTrue(surat_tugas.alasan_tidak_bisa_ubah(self.pengajuan(status=status, jalur=SS.MENUNGGU)), status)

    def test_dibekukan_saat_pembatalan_terbuka(self):
        p = self.pengajuan(status=S.PROSES_PAKLN, jalur=SS.MENUNGGU)
        PermohonanPembatalan.objects.create(
            pengajuan=p, diajukan_oleh=self.pegawai, diajukan_role="pegawai", alasan="Uji",
            status=PermohonanPembatalan.Status.MENUNGGU_UNOR,
        )
        self.assertIn("pembatalan", surat_tugas.alasan_tidak_bisa_ubah(p))

    def test_berkas_terkunci_setelah_dikirim_dan_terbuka_bila_dikembalikan(self):
        self.assertEqual(surat_tugas.alasan_berkas_terkunci(self.pengajuan(jalur=SS.MENUNGGU)), "")
        self.assertIn("terkunci", surat_tugas.alasan_berkas_terkunci(self.pengajuan(jalur=SS.DIKIRIM)))
        self.assertEqual(surat_tugas.alasan_berkas_terkunci(self.pengajuan(jalur=SS.DIKEMBALIKAN)), "")

    def test_berkas_tidak_bisa_diunggah_sebelum_izin_prinsip(self):
        self.assertTrue(surat_tugas.alasan_berkas_terkunci(self.pengajuan()))

    def test_biro_pakln_menunggu_sampai_surat_tugas_dikirim(self):
        for tipe in TIPE2:
            self.assertIn("Menunggu", surat_tugas.alasan_menunggu_surat_tugas(self.pengajuan(tipe, S.PROSES_PAKLN)))
            self.assertIn("Menunggu", surat_tugas.alasan_menunggu_surat_tugas(
                self.pengajuan(tipe, S.PROSES_PAKLN, SS.MENUNGGU)))
            self.assertEqual(surat_tugas.alasan_menunggu_surat_tugas(self.pengajuan(tipe, S.PROSES_PAKLN, SS.DIKIRIM)), "")

    def test_biro_pakln_terkunci_saat_dikembalikan_dengan_catatan(self):
        p = self.pengajuan(status=S.PROSES_PAKLN, jalur=SS.DIKEMBALIKAN)
        p.catatan_surat_tugas = "Nomor surat salah"
        self.assertIn("Nomor surat salah", surat_tugas.alasan_menunggu_surat_tugas(p))

    def test_tipe_lain_tidak_pernah_menunggu(self):
        for tipe in ("T1", "T3"):
            self.assertEqual(surat_tugas.alasan_menunggu_surat_tugas(self.pengajuan(tipe, S.PROSES_PAKLN)), "")


class KirimTests(_Dasar, TestCase):
    def test_kirim_mengubah_status_dan_mencatat_riwayat(self):
        for tipe in TIPE2:
            p = self.pengajuan(tipe, jalur=SS.MENUNGGU)
            self.berkas(p)
            surat_tugas.kirim(p, self.admin_unor)
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, SS.DIKIRIM, tipe)
            self.assertEqual(p.status, S.PROSES_BPSDM)          # status utama tidak berubah
            r = self.riwayat(p, Aksi.SURAT_TUGAS_DIKIRIM).get()
            self.assertEqual((r.status_dari, r.status_ke, r.aktor_role), (S.PROSES_BPSDM, S.PROSES_BPSDM, "admin_unor"))

    def test_kirim_butuh_berkas_surat_tugas(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        with self.assertRaisesMessage(surat_tugas.SuratTugasError, "Unggah berkas"):
            surat_tugas.kirim(p, self.admin_unor)
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.MENUNGGU)

    def test_hanya_admin_unor_yang_boleh_mengirim(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.berkas(p)
        for user in (self.pegawai, self.admin_bpsdm, self.admin_pakln, self.admin_bko):
            with self.assertRaises(surat_tugas.SuratTugasError, msg=user.role):
                surat_tugas.kirim(p, user)

    def test_kirim_dua_kali_ditolak(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.berkas(p)
        surat_tugas.kirim(p, self.admin_unor)
        with self.assertRaisesMessage(surat_tugas.SuratTugasError, "sudah berubah"):
            surat_tugas.kirim(p, self.admin_unor)
        self.assertEqual(self.riwayat(p, Aksi.SURAT_TUGAS_DIKIRIM).count(), 1)

    def test_kirim_ditolak_sebelum_jalur_dibuka(self):
        p = self.pengajuan()
        self.berkas(p)
        with self.assertRaises(surat_tugas.SuratTugasError):
            surat_tugas.kirim(p, self.admin_unor)

    def test_admin_unor_tidak_boleh_mengirim_pengajuan_milik_sendiri(self):
        p = self.pengajuan(jalur=SS.MENUNGGU, pegawai=self.admin_unor)
        self.berkas(p)
        with self.assertRaisesMessage(surat_tugas.SuratTugasError, "milik sendiri"):
            surat_tugas.kirim(p, self.admin_unor)

    def test_kirim_ditolak_saat_pembatalan_terbuka(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.berkas(p)
        PermohonanPembatalan.objects.create(
            pengajuan=p, diajukan_oleh=self.pegawai, diajukan_role="pegawai", alasan="Uji",
            status=PermohonanPembatalan.Status.MENUNGGU_UNOR,
        )
        with self.assertRaisesMessage(surat_tugas.SuratTugasError, "pembatalan"):
            surat_tugas.kirim(p, self.admin_unor)


class KembalikanTests(_Dasar, TestCase):
    def dikirim(self, tipe="T2P", status=S.PROSES_PAKLN):
        p = self.pengajuan(tipe, status, SS.DIKIRIM)
        self.berkas(p)
        return p

    def test_kembalikan_tanpa_mengubah_status_pengajuan(self):
        for tipe in TIPE2:
            p = self.dikirim(tipe)
            surat_tugas.kembalikan(p, self.admin_pakln, "Nomor surat tidak sesuai")
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, SS.DIKEMBALIKAN, tipe)
            self.assertEqual(p.catatan_surat_tugas, "Nomor surat tidak sesuai")
            self.assertEqual(p.status, S.PROSES_PAKLN)
            r = self.riwayat(p, Aksi.SURAT_TUGAS_DIKEMBALIKAN).get()
            self.assertEqual((r.catatan, r.aktor_role), ("Nomor surat tidak sesuai", "admin_pakln"))

    def test_catatan_wajib(self):
        p = self.dikirim()
        for kosong in ("", "   ", None):
            with self.assertRaisesMessage(surat_tugas.SuratTugasError, "catatan"):
                surat_tugas.kembalikan(p, self.admin_pakln, kosong)
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

    def test_hanya_admin_biro_pakln(self):
        p = self.dikirim()
        for user in (self.pegawai, self.admin_unor, self.admin_bpsdm, self.admin_bko):
            with self.assertRaises(surat_tugas.SuratTugasError, msg=user.role):
                surat_tugas.kembalikan(p, user, "Tidak sesuai")

    def test_hanya_bisa_saat_pengajuan_sudah_di_biro_pakln(self):
        p = self.dikirim(status=S.PROSES_BPSDM)
        with self.assertRaisesMessage(surat_tugas.SuratTugasError, "Biro PAKLN"):
            surat_tugas.kembalikan(p, self.admin_pakln, "Tidak sesuai")

    def test_hanya_surat_tugas_yang_sudah_dikirim_bisa_dikembalikan(self):
        for jalur in (SS.MENUNGGU, SS.DIKEMBALIKAN):
            p = self.pengajuan(status=S.PROSES_PAKLN, jalur=jalur)
            with self.assertRaises(surat_tugas.SuratTugasError, msg=jalur):
                surat_tugas.kembalikan(p, self.admin_pakln, "Tidak sesuai")

    def test_admin_pakln_tidak_boleh_mengembalikan_pengajuan_milik_sendiri(self):
        p = self.pengajuan(status=S.PROSES_PAKLN, jalur=SS.DIKIRIM, pegawai=self.admin_pakln)
        self.berkas(p)
        with self.assertRaisesMessage(surat_tugas.SuratTugasError, "milik sendiri"):
            surat_tugas.kembalikan(p, self.admin_pakln, "Tidak sesuai")

    def test_kirim_ulang_setelah_dikembalikan_mengosongkan_catatan(self):
        p = self.dikirim()
        surat_tugas.kembalikan(p, self.admin_pakln, "Perbaiki tanggal")
        surat_tugas.kirim(p, self.admin_unor)
        p.refresh_from_db()
        self.assertEqual((p.status_surat_tugas, p.catatan_surat_tugas), (SS.DIKIRIM, ""))
        self.assertEqual(self.riwayat(p, Aksi.SURAT_TUGAS_DIKIRIM).count(), 1)
        self.assertEqual(self.riwayat(p, Aksi.SURAT_TUGAS_DIKEMBALIKAN).get().catatan, "Perbaiki tanggal")

    def test_kembalikan_ditolak_saat_pembatalan_terbuka(self):
        p = self.dikirim()
        PermohonanPembatalan.objects.create(
            pengajuan=p, diajukan_oleh=self.pegawai, diajukan_role="pegawai", alasan="Uji",
            status=PermohonanPembatalan.Status.MENUNGGU_PAKLN,
        )
        with self.assertRaisesMessage(surat_tugas.SuratTugasError, "pembatalan"):
            surat_tugas.kembalikan(p, self.admin_pakln, "Tidak sesuai")


class MigrasiDataTests(_Dasar, TestCase):
    """Migrasi 0032: Surat Tugas yang sudah diunggah di tahap Unor (aturan lama) ditandai `dikirim`."""

    def jalankan(self):
        modul = importlib.import_module("pengajuan.migrations.0032_surat_tugas_data")
        modul.tandai_dikirim(django_apps, None)

    def test_pengajuan_tipe_2_dengan_surat_tugas_ditandai_dikirim(self):
        a = self.pengajuan("T2P", S.PROSES_BPSDM)
        b = self.pengajuan("T2L", S.PROSES_PAKLN)
        self.berkas(a)
        self.berkas(b)
        self.jalankan()
        for p in (a, b):
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

    def test_tanpa_surat_tugas_atau_tipe_lain_tidak_berubah_dan_updated_at_tetap(self):
        tanpa = self.pengajuan("T2P", S.PROSES)
        t1 = self.pengajuan("T1", S.PROSES_PAKLN)
        self.berkas(t1)
        sebelum = {p.pk: p.updated_at for p in (tanpa, t1)}
        self.jalankan()
        for p in (tanpa, t1):
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, "")
            self.assertEqual(p.updated_at, sebelum[p.pk])

    def test_tidak_menimpa_status_yang_sudah_ada(self):
        p = self.pengajuan("T2P", S.PROSES_PAKLN, SS.DIKEMBALIKAN)
        self.berkas(p)
        self.jalankan()
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKEMBALIKAN)
