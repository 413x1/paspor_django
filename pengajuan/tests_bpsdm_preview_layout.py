"""Pratinjau Admin BPSDM: kolom kanan memuat Unggahan, Kembalikan ke Admin Unor, lalu Timeline Proses.

Sebelumnya kotak Kembalikan dan Timeline ada di baris kedua, sehingga ruang di bawah kotak Unggahan kosong.
Ukuran piksel diperiksa di browser; tes ini menjaga struktur dan urutan."""

import re

from django.test import TestCase

from .models import Pengajuan
from .tests_pdln import _Basis

S = Pengajuan.Status
KOLOM = '<div class="preview-kolom">'


class PratinjauBpsdmSusunanTests(_Basis, TestCase):
    def pengajuan_di_bpsdm(self):
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.kirim(p)
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_BPSDM)
        return p

    def html(self, p):
        return self.get(self.admin_bpsdm, "bpsdm:preview", kode=p.kode).content.decode()

    def test_kolom_kanan_berisi_unggahan_kembalikan_lalu_timeline_berurutan(self):
        html = self.html(self.pengajuan_di_bpsdm())
        self.assertEqual(html.count(KOLOM), 1)
        awal = html.index(KOLOM)
        kolom = html[awal:html.index("Kembali ke Dasbor")]
        urutan = [kolom.index(t) for t in ("Unggahan Pegawai &amp; Admin Unor", "Kembalikan ke Admin Unor", "Timeline Proses")]
        self.assertEqual(urutan, sorted(urutan))
        self.assertLess(html.index("Pratinjau Pengajuan"), awal)               # kotak Pratinjau di kolom kiri, di luar kolom kanan

    def test_hanya_satu_grid_dua_kolom_tanpa_baris_kedua(self):
        html = self.html(self.pengajuan_di_bpsdm())
        self.assertEqual(html.count('<div class="preview-split">'), 1)

    def test_tag_div_seimbang(self):
        html = self.html(self.pengajuan_di_bpsdm())
        self.assertEqual(len(re.findall(r"<div[\s>]", html)), len(re.findall(r"</div>", html)))

    def test_tombol_lanjutkan_dan_kembalikan_tetap_berfungsi(self):
        p = self.pengajuan_di_bpsdm()
        html = self.html(p)
        self.assertIn('name="lanjutkan"', html)
        self.assertIn('name="kembalikan"', html)
        self.post(self.admin_bpsdm, "bpsdm:preview", {"kembalikan": "1", "catatan": "Lengkapi dokumen."}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.PROSES)                       # kembali ke Admin Unor

    def test_status_selain_proses_bpsdm_tanpa_kotak_kembalikan_timeline_tetap_di_kolom(self):
        p = self.pengajuan_di_bpsdm()
        self.bpsdm_teruskan(p)                                                   # sudah diteruskan ke Biro PAKLN
        resp = self.get(self.admin_bpsdm, "bpsdm:preview", kode=p.kode)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        kolom = html[html.index(KOLOM):html.index("Kembali ke Dasbor")]
        self.assertNotIn("Kembalikan ke Admin Unor", kolom)
        self.assertIn("Unggahan Pegawai &amp; Admin Unor", kolom)
        self.assertIn("Timeline Proses", kolom)

    def test_pratinjau_biro_pakln_tidak_berubah(self):
        p = self.pengajuan_di_bpsdm()
        self.bpsdm_teruskan(p)
        html = self.get(self.admin_pakln, "pakln:preview", kode=p.kode).content.decode()
        self.assertNotIn(KOLOM, html)
