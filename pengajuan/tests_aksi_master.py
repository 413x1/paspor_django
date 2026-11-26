"""Tabel Manajemen Admin PAKLN (Negara, Sumber Pembiayaan, Kategori Perjalanan, Setting Kalender, User, Histori Generate):
tombol Aksi memakai ikon garis SVG dari komponen `partials/_aksi_master.html`, bukan emoji (perbaikan UI)."""

import re
from datetime import date
from urllib.parse import quote

from django.test import TestCase

from paspor.models import HariLibur, Kegiatan, KategoriPerjalanan, Negara, SumberPembiayaan

from .models import DokumenGenerateLog
from .views_kegiatan import status_kegiatan_html
from .tests_pdln import _Basis

EMOJI = re.compile("[\U0001F300-\U0001FAFF⬇✎]")


class AksiTabelMasterTests(_Basis, TestCase):
    def aksi(self, rute, cari, query=""):
        """Kolom Aksi (kolom terakhir) dari baris tabel yang memuat teks `cari`."""
        url_query = f"?draw=1&start=0&length=50&search%5Bvalue%5D={quote(cari)}{query}"
        data = self.get(self.admin_pakln, rute, query=url_query).json()["data"]
        baris = [b for b in data if cari in str(b)]
        self.assertTrue(baris, f"baris '{cari}' tidak ditemukan")
        return baris[0][-1]

    def assertTombolMaster(self, html, prefix, aktif=True):
        self.assertEqual(html.count('<svg class="ikon-aksi"'), 3)
        self.assertIn("Edit</a>", html)
        self.assertIn("Nonaktifkan</button>" if aktif else "Aktifkan</button>", html)
        self.assertNotIn("Aktifkan</button>" if aktif else "Nonaktifkan</button>", html.replace("Nonaktifkan", "N") if aktif else html)
        self.assertIn(f"data-{prefix}-toggle=", html)
        self.assertIn(f'class="button is-small is-danger is-light" data-{prefix}-hapus=', html)
        self.assertIn("Hapus</button>", html)
        self.assertIsNone(EMOJI.search(html))

    def test_negara_aktif_dan_nonaktif(self):
        for aktif in (True, False):
            with self.subTest(aktif=aktif):
                type(self.jepang).objects.filter(pk=self.jepang.pk).update(is_active=aktif)
                self.assertTombolMaster(self.aksi("pakln:negara_data", self.jepang.nama_negara), "negara", aktif)

    def test_sumber_pembiayaan(self):
        s = SumberPembiayaan.objects.first()
        self.assertTombolMaster(self.aksi("pakln:sumber_pembiayaan_data", s.nama), "sumber", s.is_active)

    def test_kategori_perjalanan(self):
        k = KategoriPerjalanan.objects.first()
        self.assertTombolMaster(self.aksi("pakln:kategori_data", k.nama_kategori), "kategori", k.is_active)

    def test_hari_libur_aktif_dan_nonaktif(self):
        for aktif in (True, False):
            with self.subTest(aktif=aktif):
                HariLibur.objects.all().delete()
                HariLibur.objects.create(tanggal=date(2027, 2, 3), keterangan="Libur Uji", is_active=aktif)
                self.assertTombolMaster(self.aksi("pakln:kalender_data", "Libur Uji", "&tahun=2027"), "libur", aktif)

    def test_manajemen_user_hanya_tombol_edit(self):
        html = self.aksi("pakln:users_data", self.pegawai.username)
        self.assertEqual(html.count('<svg class="ikon-aksi"'), 1)
        self.assertIn("Edit</a>", html)
        self.assertNotIn("data-", html)                                           # tanpa toggle dan hapus
        self.assertIn('title="Ubah data user"', html)
        self.assertIsNone(EMOJI.search(html))

    def test_histori_generate_unduh_berikon_dan_tanpa_berkas(self):
        DokumenGenerateLog.objects.create(jenis="nd_karo", file="uji.pdf", dibuat_oleh=self.admin_pakln)
        DokumenGenerateLog.objects.create(jenis="nd_kabag", file="", dibuat_oleh=self.admin_pakln)
        data = self.get(self.admin_pakln, "pakln:histori_generate_data", query="?draw=1&start=0&length=10").json()["data"]
        kolom_aksi = [b[-1] for b in data]
        ada = [h for h in kolom_aksi if "download" in h]
        self.assertEqual(len(ada), 1)
        self.assertEqual(ada[0].count('<svg class="ikon-aksi"'), 1)
        self.assertIn("Unduh</a>", ada[0])
        self.assertIsNone(EMOJI.search(ada[0]))
        self.assertTrue(any("Berkas tidak tersedia" in h for h in kolom_aksi))


class FormatHtmlTanpaArgumenTests(_Basis, TestCase):
    """Django 6 menolak `format_html()` tanpa argumen (TypeError). Dua tempat memakainya untuk potongan HTML tetap, sehingga tabel
    Manajemen Negara gagal dimuat bila ada negara "Perlu Visa", dan status Kegiatan nonaktif gagal dirender."""

    def test_tabel_negara_memuat_negara_perlu_visa(self):
        Negara.objects.filter(pk=self.jepang.pk).update(perlu_visa=True)
        resp = self.get(
            self.admin_pakln, "pakln:negara_data",
            query=f"?draw=1&start=0&length=50&search%5Bvalue%5D={quote(self.jepang.nama_negara)}",
        )
        self.assertEqual(resp.status_code, 200)
        baris = [b for b in resp.json()["data"] if self.jepang.nama_negara in str(b)]
        self.assertTrue(baris)
        self.assertIn("Perlu Visa", str(baris[0]))

    def test_status_kegiatan_nonaktif_dirender(self):
        k = Kegiatan(status=Kegiatan.Status.DISETUJUI, is_active=False)
        self.assertIn(">Nonaktif</span>", status_kegiatan_html(k))
