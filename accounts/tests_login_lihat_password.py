"""Halaman login: tombol mata untuk melihat atau menyembunyikan password (perbaikan UI inisiatif sendiri)."""

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from .models import User

EMOJI = re.compile("[\U0001F300-\U0001FAFF⬀-⯿➕-➗✅❌⚠]")


class TombolLihatPasswordTests(TestCase):
    def setUp(self):
        self.html = self.client.get(reverse("login")).content.decode()

    def kolom_password(self):
        return self.html[self.html.index('<div class="control password-control">'):self.html.index("</button>")]

    def test_password_tersembunyi_secara_bawaan(self):
        self.assertIn('<input class="input" type="password" id="password" name="password"', self.html)
        self.assertNotIn('id="password" name="password" value=', self.html)

    def test_tombol_mata_ada_dengan_label_dan_status_yang_benar(self):
        kolom = self.kolom_password()
        self.assertIn('type="button"', kolom)                       # tidak menyubmit form
        self.assertIn('data-toggle-password="#password"', kolom)
        self.assertIn('aria-controls="password"', kolom)
        self.assertIn('aria-pressed="false"', kolom)
        self.assertIn('aria-label="Tampilkan password"', kolom)
        self.assertIn('title="Tampilkan password"', kolom)

    def test_dua_ikon_mata_dan_mata_dicoret_tanpa_ikon_kunci(self):
        kolom = self.kolom_password()
        self.assertEqual(kolom.count("<svg"), 2)
        self.assertIn('class="ikon-tampil"', kolom)
        self.assertIn('class="ikon-sembunyi"', kolom)
        self.assertIn('<line x1="3" y1="3" x2="21" y2="21"/>', kolom)      # garis coret hanya pada ikon "sembunyikan"
        self.assertNotIn("lock", self.html.lower())
        self.assertNotIn('rect x="3" y="11"', self.html)

    def test_skrip_mengalihkan_tipe_menjaga_kursor_dan_fokus_keyboard(self):
        self.assertIn("input.type = tampil ? 'text' : 'password';", self.html)
        self.assertIn("'aria-pressed': String(tampil)", self.html)
        self.assertIn("'Sembunyikan password'", self.html)
        self.assertIn("setSelectionRange(s.awal, s.akhir)", self.html)
        self.assertIn("e.originalEvent.detail > 0", self.html)               # fokus pindah ke kolom hanya untuk klik mouse

    def test_kembali_bertipe_password_saat_submit_dan_saat_dipulihkan_dari_cache(self):
        self.assertIn("$('form').on('submit', sembunyikanSemua);", self.html)
        self.assertIn("window.addEventListener('pageshow'", self.html)
        self.assertIn("e.persisted", self.html)

    def test_tanpa_emoji(self):
        self.assertIsNone(EMOJI.search(self.html))

    def test_css_menyembunyikan_tombol_mata_bawaan_edge_dan_versi_cache_naik(self):
        css = Path(finders.find("css/style.css")).read_text(encoding="utf-8")
        self.assertIn(".password-control .input::-ms-reveal, .password-control .input::-ms-clear { display: none; }", css)
        self.assertIn(".password-toggle .ikon-sembunyi, .password-toggle.is-aktif .ikon-tampil { display: none; }", css)
        self.assertIn(".password-toggle.is-aktif .ikon-sembunyi { display: block; }", css)
        self.assertIn("css/style.css?v=20261124a", self.html)


class LoginTetapBerfungsiTests(TestCase):
    def setUp(self):
        User.objects.create_user("peg1", password="Rahasia-123", role="pegawai", no_hp="6281100000001")

    def test_login_benar_masuk(self):
        resp = self.client.post(reverse("login"), {"username": "peg1", "password": "Rahasia-123"})
        self.assertEqual(resp.status_code, 302)

    def test_login_salah_menampilkan_pesan_dan_kolom_tetap_tersembunyi(self):
        resp = self.client.post(reverse("login"), {"username": "peg1", "password": "salah"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Username atau password salah")
        self.assertContains(resp, '<input class="input" type="password" id="password" name="password"')
