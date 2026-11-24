"""Badge angka pada lonceng notifikasi di navbar (perbaikan UI inisiatif sendiri).

Angka sebelumnya tampak condong ke bawah karena `line-height` lebih besar dari ruang isi badge. Posisi piksel
diukur di browser (bukan di tes ini); tes di sini menjaga markup, batas "99+", dan aturan CSS pemusatan."""

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import Notification


class BadgeLoncengTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("peg1", password="Rahasia-123", role="pegawai", no_hp="6281100000001")
        self.client.force_login(self.user)

    def buat(self, jumlah):
        Notification.objects.bulk_create([
            Notification(
                recipient=self.user, event=Notification.Event.SUBMIT_UNOR, title=f"N{i}", body="Isi",
                redirect_url="/", is_toasted=True,
            )
            for i in range(jumlah)
        ])

    def badge(self):
        html = self.client.get(reverse("pegawai:beranda")).content.decode()
        # Isi tidak boleh kosong: skrip di base.html memuat templat badge kosong untuk dibuat lewat JS.
        cocok = re.search(r'<span class="notif-badge" id="notifBadge">([^<]+)</span>', html)
        return html, cocok.group(1) if cocok else None

    def test_tanpa_notifikasi_belum_dibaca_badge_tidak_dicetak_server(self):
        self.assertIsNone(self.badge()[1])

    def test_angka_kecil_dicetak_apa_adanya(self):
        self.buat(5)
        self.assertEqual(self.badge()[1], "5")

    def test_batas_99_tepat_masih_angka(self):
        self.buat(99)
        self.assertEqual(self.badge()[1], "99")

    def test_lebih_dari_99_dicetak_99_plus_sama_dengan_skrip_klien(self):
        self.buat(100)
        html, isi = self.badge()
        self.assertEqual(isi, "99+")
        self.assertIn("$badge.text(count > 99 ? '99+' : count);", html)       # JS dan server satu aturan


class CssBadgeLoncengTests(TestCase):
    def setUp(self):
        css = Path(finders.find("css/style.css")).read_text(encoding="utf-8")
        awal = css.index(".notif-badge {")
        self.blok = css[awal:css.index("/* Avatar ikon bulat per level")]

    def test_angka_dipusatkan_dengan_flex_dan_tanpa_line_height_besar(self):
        utama = self.blok[:self.blok.index("}")]
        self.assertIn("display: flex; align-items: center; justify-content: center;", utama)
        self.assertIn("line-height: 1;", utama)
        self.assertNotRegex(utama, r"line-height:\s*(18|20)px")             # penyebab angka turun
        self.assertIn("min-width: 20px; height: 20px;", utama)

    def test_pusat_badge_tepat_di_tepi_lingkaran_lonceng(self):
        self.assertIn("top: -4px; right: -4px;", self.blok)

    def test_browser_yang_mendukung_text_box_memusatkan_menurut_tinggi_angka(self):
        self.assertIn("@supports (text-box: trim-both cap alphabetic)", self.blok)
        self.assertIn("text-box: trim-both cap alphabetic;", self.blok)
        self.assertIn("padding: calc((16px - 1cap) / 2) 5px 0;", self.blok)

    def test_versi_cache_css_dinaikkan(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertIn("css/style.css?v=20261124a", html)
