"""Panah dropdown (select) berputar setengah putaran v -> ^ saat daftar terbuka, di semua halaman Pegawai.

Animasi dan status daftar diukur di browser (bukan di tes ini); tes ini menjaga aturan CSS dan opt-in per halaman."""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from .models import User

BASE_DIR = Path(__file__).resolve().parent.parent
HALAMAN_PEGAWAI = (
    "pegawai/beranda.html", "pegawai/formulir.html", "pegawai/formulir_pdln.html", "pegawai/laporan_form.html",
    "pegawai/monitor.html", "pegawai/pelaporan.html", "pegawai/pembatalan.html", "pegawai/upload.html",
    "akun/profil.html",
)


class CssPanahSelectTests(TestCase):
    def setUp(self):
        self.css = Path(finders.find("css/style.css")).read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_dua_keadaan_memakai_daftar_transform_sama_agar_putaran_halus(self):
        self.assertIn("transform: translateY(0) rotate(-45deg);", self.css)
        self.assertIn("transform: translateY(.3375em) rotate(135deg);", self.css)       # -45 -> 135 = 180 derajat searah jarum jam
        self.assertIn("transition: transform var(--duration-slow) var(--ease-apple-in-out);", self.css)

    def test_posisi_tidak_lagi_dianimasikan_lewat_margin_yang_melompat(self):
        self.assertNotIn("margin-top: -.1em", self.css)

    def test_status_dibaca_dari_open_dengan_cadangan_kelas_untuk_browser_lama(self):
        self.assertIn("@supports selector(select:open) and selector(:has(a))", self.css)
        self.assertIn(".select:has(> select:open):not(.is-multiple):not(.is-loading)::after", self.css)
        self.assertIn("@supports not (selector(select:open) and selector(:has(a)))", self.css)
        self.assertIn(".select.is-open:not(.is-multiple):not(.is-loading)::after", self.css)

    def test_gerak_dimatikan_bila_pengguna_meminta_kurangi_animasi(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        self.assertIn(".select:not(.is-multiple):not(.is-loading)::after, .dt-toolbar .dt-length select.dt-input { transition: none; }", self.css)


class MultiSelectTujuanNegaraTests(TestCase):
    """Panah kolom "Tujuan Negara" (multi-select berchip) ikut berputar v -> ^ saat panel dibuka."""

    def setUp(self):
        self.css = Path(finders.find("css/style.css")).read_text(encoding="utf-8").replace("\r\n", "\n")
        self.base = (BASE_DIR / "templates/base.html").read_text(encoding="utf-8")

    def test_css_panah_multiselect_memutar_halus_dengan_daftar_transform_sama(self):
        self.assertIn("transform: translateY(0) rotate(-45deg);", self.css[self.css.index(".multiselect-caret {"):])
        self.assertIn(".multiselect.is-open .multiselect-caret { transform: translateY(.35em) rotate(135deg); }", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce) { .multiselect-caret { transition: none; } }", self.css)

    def test_js_memasang_dan_melepas_is_open_di_semua_jalur_penutupan(self):
        self.assertIn("$wrap.toggleClass('is-open', $panel.hasClass('is-active'));", self.base)          # klik kolom
        self.assertIn("removeClass('is-active').closest('.multiselect').removeClass('is-open');", self.base)   # panel lain / klik luar
        self.assertEqual(self.base.count(".closest('.multiselect').removeClass('is-open')"), 2)

    def test_halaman_formulir_memuat_multiselect_tujuan_negara(self):
        User.objects.create_user("peg1", password="Rahasia-123", role="pegawai", no_hp="6281100000001")
        self.client.login(username="peg1", password="Rahasia-123")
        html = self.client.get(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas").content.decode()
        self.assertIn("data-multiselect=", html)


class OptInHalamanPegawaiTests(TestCase):
    def test_semua_templat_pegawai_mengaktifkan_panah_select(self):
        for nama in HALAMAN_PEGAWAI:
            with self.subTest(templat=nama):
                isi = (BASE_DIR / "templates" / nama).read_text(encoding="utf-8")
                self.assertIn("{% block wrap_extra_class %} medium panah-select{% endblock %}", isi)

    def test_filter_report_ikut_aktif(self):
        isi = (BASE_DIR / "templates/partials/_filter_report.html").read_text(encoding="utf-8")
        self.assertIn('<form method="get" class="box filter-report panah-select">', isi)

    def test_halaman_formulir_pegawai_memuat_kelas_pada_pembungkus_halaman(self):
        User.objects.create_user("peg1", password="Rahasia-123", role="pegawai", no_hp="6281100000001")
        self.client.login(username="peg1", password="Rahasia-123")
        html = self.client.get(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas").content.decode()
        self.assertIn('<main class="page-wrap medium panah-select">', html)
