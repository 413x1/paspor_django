"""Dialog "Konfirmasi Keluar" memakai ikon pintu keluar yang sama dengan tombol Keluar di sidebar (bukan tempat sampah).

Tipe 'danger' (konfirmasi hapus dan sejenisnya) tetap memakai tempat sampah; hanya dialog keluar yang memakai tipe 'keluar'."""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from .models import User

BASE_DIR = Path(__file__).resolve().parent.parent
IKON_KELUAR = (
    '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/>'
    '<line x1="21" y1="12" x2="9" y2="12"/>'
)
IKON_SAMPAH = '<path d="M6 7l1 13h10l1-13"/>'


class DialogKeluarTests(TestCase):
    def setUp(self):
        User.objects.create_user("peg1", password="Rahasia-123", role="pegawai", no_hp="6281100000001")
        self.client.login(username="peg1", password="Rahasia-123")
        self.html = self.client.get(reverse("pegawai:beranda")).content.decode()

    def test_ikon_dialog_keluar_sama_persis_dengan_ikon_tombol_keluar_sidebar(self):
        sidebar = self.html[self.html.index("logout-sidebar-link"):]
        self.assertIn(IKON_KELUAR, sidebar.split("</svg>")[0])                       # ikon di sidebar
        self.assertIn("keluar: '<svg viewBox=\"0 0 24 24\">" + IKON_KELUAR + "</svg>'", self.html)           # ikon di dialog

    def test_dialog_konfirmasi_keluar_memakai_tipe_keluar_bukan_danger(self):
        self.assertIn("type: 'keluar', title: 'Konfirmasi Keluar',", self.html)
        self.assertNotIn("type: 'danger', title: 'Konfirmasi Keluar',", self.html)
        self.assertIn("var TYPES = 'is-warning is-danger is-success is-error is-info is-keluar';", self.html)

    def test_tipe_danger_tetap_memakai_ikon_tempat_sampah(self):
        self.assertIn("danger: '<svg viewBox=\"0 0 24 24\"><polyline points=\"4 7 20 7\"/>" + IKON_SAMPAH, self.html)

    def test_css_tipe_keluar_berwarna_merah_seperti_danger(self):
        css = Path(finders.find("css/style.css")).read_text(encoding="utf-8")
        self.assertIn(".paspor-dialog.is-keluar .dialog-icon {", css)
        self.assertIn("#pasporDialog.is-keluar .dialog-ok {", css)

    def test_form_keluar_tetap_post_ke_logout(self):
        self.assertIn(f'<form method="post" action="{reverse("logout")}">', self.html)
        resp = self.client.post(reverse("logout"))
        self.assertEqual(resp.status_code, 302)
