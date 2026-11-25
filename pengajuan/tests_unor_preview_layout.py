"""Pratinjau Admin Unor: kolom kanan memuat Direktori Unggahan, Kembalikan ke Pegawai, lalu Timeline Proses.

Sebelumnya kotak Kembalikan dan Timeline ada di baris kedua, sehingga ruang di bawah Direktori Unggahan kosong.
Ukuran piksel diperiksa di browser; tes ini menjaga struktur, urutan, dan aturan CSS."""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase

from .models import Pengajuan
from .tests_pdln import _Basis

S = Pengajuan.Status
KOLOM = '<div class="preview-kolom">'


class PratinjauUnorSusunanTests(_Basis, TestCase):
    def html(self, p):
        return self.get(self.admin_unor, "unor:preview", kode=p.kode).content.decode()

    def pengajuan_proses(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.assertEqual(self.refresh(p).status, S.PROSES)
        return p

    def test_kolom_kanan_berisi_direktori_kembalikan_lalu_timeline_secara_berurutan(self):
        html = self.html(self.pengajuan_proses())
        self.assertEqual(html.count(KOLOM), 1)
        awal = html.index(KOLOM)
        kolom = html[awal:html.index("Kembali ke Dasbor")]
        urutan = [kolom.index(t) for t in ("Direktori Unggahan Pegawai", "Kembalikan ke Pegawai", "Timeline Proses")]
        self.assertEqual(urutan, sorted(urutan))                       # Direktori < Kembalikan < Timeline
        self.assertLess(html.index("Pratinjau Pengajuan dari Pegawai"), awal)   # kotak Pratinjau ada di kolom kiri, di luar .preview-kolom

    def test_hanya_satu_grid_dua_kolom_tanpa_baris_kedua(self):
        html = self.html(self.pengajuan_proses())
        self.assertEqual(html.count('<div class="preview-split">'), 1)

    def test_tombol_lanjutkan_dan_kembalikan_tetap_ada_dan_berfungsi(self):
        p = self.pengajuan_proses()
        html = self.html(p)
        self.assertIn('name="lanjutkan"', html)
        self.assertIn('name="kembalikan"', html)
        self.post(self.admin_unor, "unor:preview", {"kembalikan": "1", "catatan": "Lengkapi dokumen."}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.BELUM)

    def test_status_selain_proses_tanpa_kotak_kembalikan_tetapi_timeline_tetap_di_kolom_kanan(self):
        p = self.pengajuan_proses()
        self.post(self.admin_unor, "unor:preview", {"kembalikan": "1", "catatan": "Lengkapi dokumen."}, kode=p.kode)
        html = self.html(p)
        kolom = html[html.index(KOLOM):html.index("Kembali ke Dasbor")]
        self.assertNotIn("Kembalikan ke Pegawai", kolom)
        self.assertIn("Direktori Unggahan Pegawai", kolom)
        self.assertIn("Timeline Proses", kolom)

    def test_peran_lain_tidak_berubah(self):
        p = self.pengajuan_proses()
        html = self.get(self.admin_pakln, "pakln:preview", kode=p.kode).content.decode()
        self.assertNotIn(KOLOM, html)


class CssPreviewKolomTests(TestCase):
    def test_aturan_kolom_tumpukan(self):
        css = Path(finders.find("css/style.css")).read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertIn(".preview-kolom { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; align-content: start; min-width: 0; }", css)
        self.assertIn(".preview-kolom > .box { margin-bottom: 0; }", css)
