"""Manajemen Template: tombol Aksi di tabel Daftar Template memakai ikon garis SVG, bukan emoji (perbaikan UI)."""

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase

from .models import DokumenTemplate
from .tests_pdln import _Basis

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2b07\u270e\u2b06]")


class AksiDaftarTemplateTests(_Basis, TestCase):
    def aksi(self, **kolom):
        DokumenTemplate.objects.create(nama="Template Uji", file="t.pdf", **kolom)
        data = self.get(self.admin_pakln, "pakln:templates_data", query="?draw=1&start=0&length=10").json()["data"]
        self.assertEqual(len(data), 1)
        return data[0][-1]

    def test_template_aktif_empat_tombol_berikon_garis_tanpa_emoji(self):
        html = self.aksi(aktif=True)
        self.assertEqual(html.count('<svg class="ikon-aksi"'), 4)
        for label in ("Unduh</a>", "Edit</a>", "Sembunyikan</button>", "Hapus</button>"):
            self.assertIn(label, html)
        self.assertIsNone(EMOJI.search(html))

    def test_template_disembunyikan_menampilkan_tombol_tampilkan(self):
        html = self.aksi(aktif=False)
        self.assertIn("Tampilkan</button>", html)
        self.assertNotIn("Sembunyikan</button>", html)
        self.assertEqual(html.count('<svg class="ikon-aksi"'), 4)
        self.assertIsNone(EMOJI.search(html))

    def test_atribut_untuk_skrip_dan_tautan_tetap_ada(self):
        html = self.aksi(aktif=True)
        self.assertIn("data-template-toggle=", html)                            # dipakai skrip di templates.html
        self.assertIn("data-template-hapus=", html)
        self.assertIn('target="_blank" rel="noopener"', html)                   # Unduh membuka tab baru
        self.assertRegex(html, r'href="/admin-biropakln/templates/\d+/edit/"')
        self.assertIn('class="button is-small is-danger is-light" data-template-hapus', html)   # Hapus: merah lembut

    def test_tooltip_menjelaskan_aksi(self):
        html = self.aksi(aktif=True)
        for judul in ("Unduh berkas template", "Ubah data template", "Sembunyikan dari daftar yang dapat diunduh", "Hapus template"):
            self.assertIn(f'title="{judul}"', html)

    def test_aksi_toggle_dan_hapus_tetap_berfungsi(self):
        t = DokumenTemplate.objects.create(nama="Template Uji", file="t.pdf", aktif=True)
        self.post(self.admin_pakln, "pakln:toggle_template", template_id=t.pk)
        t.refresh_from_db()
        self.assertFalse(t.aktif)
        self.post(self.admin_pakln, "pakln:hapus_template", template_id=t.pk)
        self.assertFalse(DokumenTemplate.objects.filter(pk=t.pk).exists())


class CssIkonAksiTests(TestCase):
    def test_aturan_ikon_aksi(self):
        css = Path(finders.find("css/style.css")).read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertIn(".ikon-aksi {", css)
        self.assertIn("fill: none; stroke: currentColor;", css[css.index(".ikon-aksi {"):])
