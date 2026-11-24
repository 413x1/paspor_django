"""Penahan "Tambah Usulan Baru" (kewajiban lapor): aturan tetap, pesan di Beranda diperjelas.

Konfirmasi Ketua Tim (24 Nov 2026): pengajuan yang belum selesai tetap diselesaikan admin dan tidak dianggap selesai;
usulan baru boleh berjalan bersamaan (paralel); penahan kewajiban lapor tetap berlaku (BISNIS_PROSES_PDLN.MD §2.1, §4.4)."""

from django.urls import reverse

from . import alur
from .models import LaporanPdln, Pengajuan
from .tests_pengajuan_paralel import ParalelBase

S = Pengajuan.Status
CATATAN = "tetap wajib dilaporkan dan laporannya disetujui Admin Biro PAKLN"
TIDAK_MENGHALANGI = "yang masih diproses admin tidak menghalangi usulan baru"


class PenahanPesanTests(ParalelBase):
    def selesaikan(self, p):
        self.kirim(p)
        self.unor_teruskan(p)
        self.pakln_selesai(p, kecuali=("visa",))
        self.assertEqual(self.refresh(p).status, S.SELESAI)

    def test_satu_penahan_menampilkan_alasan_dan_catatan_tanpa_hitungan_lain(self):
        p = self.isi_formulir("T1")
        self.selesaikan(p)
        html = self.beranda().content.decode()
        self.assertIn("belum dapat mengajukan perjalanan baru", html)
        self.assertIn(f"Laporan PDLN untuk {p.kode} belum diunggah.", html)
        self.assertIn(CATATAN, html)
        self.assertIn(TIDAK_MENGHALANGI, html)
        self.assertNotIn("PDLN selesai lainnya", html)

    def test_dua_penahan_menyebut_jumlah_yang_lain_dan_alasan_untuk_yang_terbaru(self):
        a = self.isi_formulir("T1")
        b = self.isi_formulir("T1")                                  # dua draft sekaligus (paralel), lalu keduanya selesai
        self.selesaikan(a)
        self.selesaikan(b)
        daftar = alur.daftar_penahan(self.pegawai)
        self.assertEqual({p.pk for p in daftar}, {a.pk, b.pk})
        self.assertEqual(alur.penahan_pengajuan_baru(self.pegawai), daftar[0])
        html = self.beranda().content.decode()
        self.assertIn("Masih ada 1 PDLN selesai lainnya yang laporannya belum disetujui.", html)
        self.assertIn(daftar[0].kode, html.split("belum dapat mengajukan perjalanan baru")[1])

    def test_laporan_dikembalikan_pesannya_jelas(self):
        p = self.isi_formulir("T1")
        self.selesaikan(p)
        LaporanPdln.objects.update_or_create(pengajuan=p, defaults={"status": LaporanPdln.Status.DIKEMBALIKAN})
        html = self.beranda().content.decode()
        self.assertIn(f"Laporan PDLN {p.kode} dikembalikan Biro PAKLN dan perlu diunggah ulang.", html)
        self.assertIn(CATATAN, html)

    def test_pengajuan_yang_masih_diproses_tidak_menahan_dan_tanpa_banner(self):
        a = self.isi_formulir("T1")
        self.kirim(a)                                                # menunggu Admin Unor, belum selesai
        self.assertEqual(self.refresh(a).status, S.PROSES)
        self.assertIsNone(alur.penahan_pengajuan_baru(self.pegawai))
        self.assertEqual(alur.daftar_penahan(self.pegawai), [])
        html = self.beranda().content.decode()
        self.assertNotIn("belum dapat mengajukan perjalanan baru", html)
        self.assertNotIn(CATATAN, html)
        self.assertIn('data-modal-open="jenisModal"', html)
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query="?jenis=nondinas")
        self.assertEqual(resp.status_code, 200)                      # usulan baru bisa dibuat bersamaan

    def test_laporan_disetujui_semua_membuka_kembali_dan_banner_hilang(self):
        a = self.isi_formulir("T1")
        self.selesaikan(a)
        LaporanPdln.objects.create(pengajuan=a, status=LaporanPdln.Status.DISETUJUI)
        self.assertEqual(alur.daftar_penahan(self.pegawai), [])
        html = self.beranda().content.decode()
        self.assertNotIn(CATATAN, html)
        self.assertIn('data-modal-open="jenisModal"', html)
