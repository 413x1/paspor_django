"""Kegiatan Admin PAKLN: tombol Tinjau tanpa panah dan tombol kembali ke Daftar Kegiatan bergaya (perbaikan UI).

Tombol kembali (chip bulat berisi panah + teks "Kembali ke <halaman>") hanya dipakai halaman Admin PAKLN (Tambah dan
Detail/Edit Kegiatan). Halaman Kegiatan milik BPSDM dan Pegawai tetap memakai tombol lama sampai disetujui."""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from paspor.models import Kegiatan

from .tests_kegiatan import _KegiatanBasis

PANAH = "→"
PANAH_KIRI = "←"


class TombolKegiatanPaklnTests(_KegiatanBasis, TestCase):
    def buat_kegiatan(self, status=Kegiatan.Status.DISETUJUI):
        data = self.data_kegiatan([self.kat("Workshop")])
        self.assertEqual(self.post(self.admin_pakln, "pakln:tambah_kegiatan", data).status_code, 302)
        k = Kegiatan.objects.get(nama="Workshop Uji")
        Kegiatan.objects.filter(pk=k.pk).update(status=status)
        return Kegiatan.objects.get(pk=k.pk)

    def baris_aksi(self):
        data = self.get(self.admin_pakln, "pakln:kegiatan_data", query="?draw=1&start=0&length=10").json()["data"]
        return str(data)

    # ---- tabel Daftar Kegiatan ----
    def test_tombol_tinjau_tanpa_panah_untuk_usulan_menunggu(self):
        self.buat_kegiatan(Kegiatan.Status.MENUNGGU)
        isi = self.baris_aksi()
        self.assertIn('class="button is-small is-warning">Tinjau</a>', isi)
        self.assertNotIn("Tinjau " + PANAH, isi)

    def test_tombol_edit_kegiatan_disetujui_tidak_berubah(self):
        self.buat_kegiatan(Kegiatan.Status.DISETUJUI)
        self.assertIn("✎ Edit", self.baris_aksi())

    # ---- halaman Tambah dan Detail ----
    def assertTombolKembali(self, html, url):
        self.assertIn('class="tombol-kembali"', html)
        self.assertIn(f'href="{url}"', html)
        self.assertIn('title="Kembali ke Daftar Kegiatan"', html)
        self.assertIn('aria-label="Kembali ke Daftar Kegiatan"', html)
        self.assertIn("<small>Kembali ke</small><strong>Daftar Kegiatan</strong>", html)
        self.assertIn('<svg viewBox="0 0 24 24">', html.split('class="tombol-kembali"')[1].split("</a>")[0])
        self.assertNotIn(PANAH_KIRI + " Daftar Kegiatan", html)                       # tombol lama sudah diganti

    def test_halaman_tambah_kegiatan_memakai_tombol_kembali_bergaya(self):
        html = self.get(self.admin_pakln, "pakln:tambah_kegiatan").content.decode()
        self.assertTombolKembali(html, reverse("pakln:kelola_kegiatan"))

    def test_halaman_detail_kegiatan_disetujui_memakai_tombol_kembali_bergaya(self):
        k = self.buat_kegiatan(Kegiatan.Status.DISETUJUI)
        html = self.get(self.admin_pakln, "pakln:edit_kegiatan", pk=k.pk).content.decode()
        self.assertTombolKembali(html, reverse("pakln:kelola_kegiatan"))

    def test_halaman_tinjau_usulan_kembali_ke_tab_menunggu(self):
        k = self.buat_kegiatan(Kegiatan.Status.MENUNGGU)
        html = self.get(self.admin_pakln, "pakln:edit_kegiatan", pk=k.pk).content.decode()
        self.assertTombolKembali(html, reverse("pakln:kelola_kegiatan") + "?tab=menunggu")

    # ---- halaman peran lain tidak berubah ----
    def test_halaman_kegiatan_bpsdm_tetap_memakai_tombol_lama(self):
        resp = self.get(self.admin_bpsdm, "bpsdm:tambah_kegiatan")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn('class="tombol-kembali"', html)
        self.assertIn(PANAH_KIRI + " Daftar Kegiatan", html)


class CssTombolKembaliTests(TestCase):
    def test_aturan_css_chip_hover_dan_gerak_dikurangi(self):
        css = Path(finders.find("css/style.css")).read_text(encoding="utf-8").replace("\r\n", "\n")
        for potongan in (
            ".tombol-kembali {", ".tombol-kembali-ikon {", ".tombol-kembali-ikon svg {", ".tombol-kembali-teks small",
            ".tombol-kembali:hover .tombol-kembali-ikon svg, .tombol-kembali:focus-visible .tombol-kembali-ikon svg { transform: translateX(-2px); }",
            ".tombol-kembali:focus-visible { outline: 2px solid var(--teal); outline-offset: 2px; }",
        ):
            self.assertIn(potongan, css)
        reduced = css[css.index("@media (prefers-reduced-motion: reduce) {\n  .tombol-kembali,"):]
        self.assertIn("transition: none;", reduced.split("}\n}")[0])
