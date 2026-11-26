"""Halaman Manajemen Admin PAKLN: tombol kembali bergaya (chip panah + teks "Kembali ke <halaman>") menggantikan
"<- Kembali ke ..." pada halaman daftar (Kembali ke Dasbor) dan halaman edit (Kembali ke Manajemen ...)."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from paspor.models import HariLibur, KategoriPerjalanan, SumberPembiayaan

from .models import DokumenTemplate
from .tests_pdln import _Basis

PANAH_KIRI = "←"
DAFTAR = (
    "pakln:kelola_user", "pakln:kelola_template", "pakln:kelola_negara", "pakln:kelola_sumber_pembiayaan",
    "pakln:kelola_kategori", "pakln:kelola_kalender", "pakln:histori_generate", "pakln:pengaturan_dokumen",
)


class TombolKembaliManajemenTests(_Basis, TestCase):
    def assertTombol(self, html, url, label):
        self.assertIn(f'<a href="{url}" class="tombol-kembali" title="Kembali ke {label}"', html)
        self.assertIn(f"<small>Kembali ke</small><strong>{label}</strong>", html)
        self.assertNotIn(PANAH_KIRI + " Kembali ke", html)

    def test_halaman_daftar_manajemen_kembali_ke_dasbor_bergaya(self):
        for nama in DAFTAR:
            with self.subTest(halaman=nama):
                resp = self.get(self.admin_pakln, nama)
                self.assertEqual(resp.status_code, 200)
                self.assertTombol(resp.content.decode(), reverse("pakln:dashboard"), "Dasbor")

    def test_halaman_edit_manajemen_kembali_ke_daftarnya_bergaya(self):
        template = DokumenTemplate.objects.create(nama="Template Uji", file="t.pdf")
        kasus = (
            ("pakln:edit_user", {"user_id": self.pegawai.pk}, "pakln:kelola_user", "Manajemen User"),
            ("pakln:edit_template", {"template_id": template.pk}, "pakln:kelola_template", "Manajemen Template"),
            ("pakln:edit_negara", {"negara_id": self.jepang.pk}, "pakln:kelola_negara", "Manajemen Negara"),
            ("pakln:edit_sumber_pembiayaan", {"sumber_id": SumberPembiayaan.objects.first().pk},
             "pakln:kelola_sumber_pembiayaan", "Manajemen Sumber Pembiayaan"),
            ("pakln:edit_kategori", {"kategori_id": KategoriPerjalanan.objects.first().pk},
             "pakln:kelola_kategori", "Manajemen Kategori Perjalanan"),
        )
        for rute, kwargs, tujuan, label in kasus:
            with self.subTest(halaman=rute):
                resp = self.get(self.admin_pakln, rute, **kwargs)
                self.assertEqual(resp.status_code, 200)
                self.assertTombol(resp.content.decode(), reverse(tujuan), label)

    def test_edit_hari_libur_kembali_ke_kalender_pada_tahun_yang_sama(self):
        libur = HariLibur.objects.create(tanggal=date(2027, 2, 3), keterangan="Libur Uji")
        resp = self.get(self.admin_pakln, "pakln:edit_hari_libur", libur_id=libur.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertTombol(resp.content.decode(), reverse("pakln:kelola_kalender") + "?tahun=2027", "Setting Kalender")

    def test_halaman_generate_nd_kembali_ke_dasbor_bergaya(self):
        for rute in ("pakln:generate_nd_kabag", "pakln:generate_nd_karo"):
            with self.subTest(halaman=rute):
                resp = self.get(self.admin_pakln, rute)
                self.assertEqual(resp.status_code, 200)
                self.assertTombol(resp.content.decode(), reverse("pakln:dashboard"), "Dasbor")
