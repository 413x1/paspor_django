"""Pratinjau Admin Biro PAKLN: kolom kanan memuat Direktori Dokumen, Kembalikan, lalu Timeline Proses.

Sebelumnya kotak Kembalikan dan Timeline ada di baris kedua, sehingga ruang di bawah kotak Direktori kosong.
Ukuran piksel diperiksa di browser; tes ini menjaga struktur dan urutan."""

import re

from django.test import TestCase

from .models import Pengajuan
from .tests_pdln import _Basis

S = Pengajuan.Status
KOLOM = '<div class="preview-kolom">'


class PratinjauPaklnSusunanTests(_Basis, TestCase):
    def pengajuan_di_pakln(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        return p

    def html(self, p):
        return self.get(self.admin_pakln, "pakln:preview", kode=p.kode).content.decode()

    def test_kolom_kanan_berisi_direktori_kembalikan_lalu_timeline_berurutan(self):
        html = self.html(self.pengajuan_di_pakln())
        self.assertEqual(html.count(KOLOM), 1)
        awal = html.index(KOLOM)
        kolom = html[awal:html.index("Kembali ke Dasbor")]
        urutan = [kolom.index(t) for t in ("Direktori Dokumen", "Kembalikan ke Admin Unor", "Timeline Proses")]
        self.assertEqual(urutan, sorted(urutan))
        self.assertLess(html.index("Pratinjau Pengajuan"), awal)               # kotak Pratinjau di kolom kiri, di luar kolom kanan

    def test_hanya_satu_grid_dua_kolom_tanpa_baris_kedua(self):
        html = self.html(self.pengajuan_di_pakln())
        self.assertEqual(html.count('<div class="preview-split">'), 1)

    def test_tag_div_seimbang(self):
        html = self.html(self.pengajuan_di_pakln())
        self.assertEqual(len(re.findall(r"<div[\s>]", html)), len(re.findall(r"</div>", html)))

    def test_tombol_lanjutkan_dan_kembalikan_tetap_berfungsi(self):
        p = self.pengajuan_di_pakln()
        html = self.html(p)
        self.assertIn('name="lanjutkan"', html)
        self.assertIn('name="kembalikan"', html)
        self.post(self.admin_pakln, "pakln:preview", {"kembalikan": "1", "catatan": "Lengkapi dokumen."}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.PROSES)                       # kembali ke Admin Unor

    def test_status_selesai_tanpa_kotak_kembalikan_timeline_tetap_di_kolom(self):
        p = self.pengajuan_di_pakln()
        self.pakln_selesai(p, kecuali=("visa",))
        resp = self.get(self.admin_pakln, "pakln:preview", kode=p.kode)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        kolom = html[html.index(KOLOM):html.index("Kembali ke Dasbor")]
        self.assertNotIn("Kembalikan ke Admin Unor", kolom)
        self.assertIn("Direktori Dokumen", kolom)
        self.assertIn("Timeline Proses", kolom)
