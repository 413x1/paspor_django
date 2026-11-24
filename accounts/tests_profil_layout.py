"""Halaman Profil Pegawai: dua kolom di layar lebar (kiri Data Personal + Keamanan, kanan Akun + Data Paspor,
Dokumen selebar penuh di bawahnya). Peran lain tetap satu kolom dengan urutan semula.

Ukuran piksel diperiksa di browser (Edge, Chrome, Firefox, WebKit); tes ini menjaga struktur, urutan, dan aturan CSS."""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from .models import User


def _judul(html):
    """Urutan judul kotak pada halaman, sesuai kemunculan di HTML."""
    hasil, sisa = [], html
    for nama in ("Data Personal", "Akun", "Keamanan", "Data Paspor", "Dokumen Kepegawaian", "Dokumen Penugasan"):
        pos = html.find(f'<div class="section-title is-small">{nama}')
        if pos >= 0:
            hasil.append((pos, nama))
    return [nama for _, nama in sorted(hasil)]


class ProfilPegawaiDuaKolomTests(TestCase):
    def setUp(self):
        User.objects.create_user("peg1", password="Rahasia-123", role="pegawai", no_hp="6281100000001")
        self.client.login(username="peg1", password="Rahasia-123")
        self.resp = self.client.get(reverse("profil"))
        self.html = self.resp.content.decode()

    def test_halaman_terbuka_dan_pembungkus_dua_kolom_dipasang(self):
        self.assertEqual(self.resp.status_code, 200)
        self.assertIn('<div class="profil-grid is-dua-kolom">', self.html)
        self.assertEqual(self.html.count('<div class="profil-kolom">'), 2)

    def test_kolom_kiri_data_personal_dan_keamanan_kolom_kanan_akun_dan_data_paspor(self):
        kiri, kanan = self.html.split('<div class="profil-kolom">')[1:3]
        self.assertIn("Data Personal", kiri.split('<div class="profil-kolom">')[0])
        self.assertIn("Keamanan", kiri)
        self.assertNotIn(">Akun<", kiri)
        self.assertIn(">Akun</div>", kanan)
        self.assertIn("Data Paspor", kanan)
        self.assertNotIn("Keamanan", kanan.split("Data Paspor")[0].split(">Akun</div>")[1])

    def test_dokumen_selebar_penuh_setelah_kedua_kolom(self):
        self.assertIn('<div class="box profil-penuh">', self.html)
        self.assertEqual(_judul(self.html), ["Data Personal", "Keamanan", "Akun", "Data Paspor", "Dokumen Kepegawaian"])

    def test_isi_semua_kotak_masih_lengkap(self):
        for teks in ("Ubah Username", "Ganti Password", "Tambah Paspor", "Nomor Paspor", "name=\"aksi\" value=\"unggah_dokumen\""):
            self.assertIn(teks, self.html)
        self.assertEqual(self.html.count('class="box'), 5)

    def test_tanpa_sisa_komentar_templat_pada_halaman(self):
        self.assertNotIn("{#", self.html)
        self.assertNotIn("{% comment", self.html)
        self.assertNotIn("_profil_", self.html)


class ProfilPeranLainTetapSatuKolomTests(TestCase):
    def setUp(self):
        User.objects.create_user("adm1", password="Rahasia-123", role="admin_pakln", no_hp="6281100000002")
        self.client.login(username="adm1", password="Rahasia-123")
        self.html = self.client.get(reverse("profil")).content.decode()

    def test_tanpa_kelas_dua_kolom_dan_urutan_semula(self):
        self.assertIn('<div class="profil-grid">', self.html)
        self.assertNotIn("is-dua-kolom", self.html)
        self.assertNotIn("profil-kolom", self.html)
        self.assertEqual(_judul(self.html), ["Data Personal", "Akun", "Keamanan", "Dokumen Penugasan"])

    def test_data_paspor_hanya_untuk_pegawai(self):
        self.assertNotIn("Data Paspor", self.html)


class CssProfilTests(TestCase):
    def setUp(self):
        css = Path(finders.find("css/style.css")).read_text(encoding="utf-8").replace("\r\n", "\n")
        self.blok = css[css.index("@media (min-width: 1280px) {\n  .profil-grid"):]
        self.blok = self.blok[:self.blok.index("\n}\n") + 3]

    def test_dua_kolom_hanya_di_layar_lebar_dan_hanya_untuk_pegawai(self):
        self.assertIn(".profil-grid.is-dua-kolom {", self.blok)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start;", self.blok)

    def test_kolom_ditumpuk_mandiri_dan_dokumen_selebar_penuh(self):
        self.assertIn(".profil-grid.is-dua-kolom .profil-kolom { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; }", self.blok)
        self.assertIn(".profil-grid.is-dua-kolom > .profil-penuh { grid-column: 1 / -1; }", self.blok)

    def test_tanpa_fitur_css_baru_yang_tidak_didukung_safari_lama(self):
        for terlarang in (":has(", "@container", "subgrid", "masonry"):
            self.assertNotIn(terlarang, self.blok)
