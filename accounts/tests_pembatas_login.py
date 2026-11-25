"""Pembatas login: 5x gagal per IP + username, atau 20x gagal per IP (semua
username) -> diblokir sementara 10 menit."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from logs.models import ActivityLog

from .models import User

LOC = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "uji-pembatas"}}


@override_settings(CACHES=LOC, LOGIN_BATAS_GAGAL=5, LOGIN_BATAS_GAGAL_IP=20, LOGIN_DURASI_BLOKIR=600)
class PembatasLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="budi", password="rahasia-benar-123")
        cls.admin = User.objects.create_superuser(username="root", password="rahasia-admin-123", email="r@x.id")
        cls.penyerang = User.objects.create_user(username="penyerang", password="akun-sendiri-123")

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _login(self, password="salah", username="budi", ip="10.1.1.1", url=None):
        return self.client.post(url or reverse("login"), {"username": username, "password": password},
                                REMOTE_ADDR=ip)

    def test_empat_gagal_belum_diblokir(self):
        for _ in range(4):
            self.assertEqual(self._login().status_code, 200)
        resp = self._login(password="rahasia-benar-123")
        self.assertRedirects(resp, reverse("home"), fetch_redirect_response=False)

    def test_login_berhasil_mereset_hitungan(self):
        for _ in range(4):
            self._login()
        self.assertEqual(self._login(password="rahasia-benar-123").status_code, 302)
        self.client.logout()
        # Hitungan mulai dari nol: 4 gagal lagi belum memblokir, gagal ke-5 baru memblokir.
        for _ in range(4):
            self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self._login().status_code, 429)

    def test_login_admin_berhasil_juga_mereset(self):
        url = reverse("admin:login")
        for _ in range(4):
            self._login(username="root", url=url)
        self.assertEqual(self._login(username="root", password="rahasia-admin-123", url=url).status_code, 302)
        self.client.logout()
        for _ in range(4):
            self.assertEqual(self._login(username="root", url=url).status_code, 200)

    # --- celah penyerang yang punya akun -------------------------------------

    def test_login_akun_sendiri_tidak_mereset_hitungan_akun_korban(self):
        for _ in range(4):
            self._login(username="budi")
        self.assertEqual(self._login(username="penyerang", password="akun-sendiri-123").status_code, 302)
        self.client.logout()
        # Tebakan ke-5 untuk budi tetap memblokir.
        self.assertEqual(self._login(username="budi").status_code, 429)

    def test_login_akun_sendiri_tidak_mereset_hitungan_ip(self):
        # 4 tebakan per korban (di bawah batas per username), diselingi login akun sendiri.
        korban = [f"korban{i}" for i in range(5)]
        for nama in korban[:4]:
            for _ in range(4):
                self.assertEqual(self._login(username=nama).status_code, 200)
            self.assertEqual(self._login(username="penyerang", password="akun-sendiri-123").status_code, 302)
            self.client.logout()
        # 16 gagal sejauh ini; gagal ke-20 memblokir seluruh IP walau ada login berhasil di antaranya.
        for _ in range(3):
            self.assertEqual(self._login(username=korban[4]).status_code, 200)
        self.assertEqual(self._login(username=korban[4]).status_code, 429)
        self.assertEqual(self._login(username="penyerang", password="akun-sendiri-123").status_code, 429)

    def test_login_berhasil_ip_lain_tidak_mereset(self):
        for _ in range(4):
            self._login(ip="10.1.1.1")
        self._login(password="rahasia-benar-123", ip="10.2.2.2")
        self.client.logout()
        self.assertEqual(self._login(ip="10.1.1.1").status_code, 429)

    def test_gagal_kelima_memblokir_ip(self):
        for _ in range(4):
            self._login()
        resp = self._login()
        self.assertEqual(resp.status_code, 429)
        self.assertContains(resp, "Silakan coba lagi dalam 10 menit", status_code=429)

    def test_selama_diblokir_password_benar_pun_ditolak(self):
        for _ in range(5):
            self._login()
        with mock.patch("accounts.views.authenticate") as auth:
            resp = self._login(password="rahasia-benar-123")
        self.assertEqual(resp.status_code, 429)
        self.assertTrue(resp.has_header("Retry-After"))
        auth.assert_not_called()  # kredensial tidak diperiksa sama sekali
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_blokir_username_tidak_mengunci_username_lain_di_ip_sama(self):
        for _ in range(5):
            self._login(username="budi")
        self.assertEqual(self._login(username="budi", password="rahasia-benar-123").status_code, 429)
        self.assertEqual(self._login(username="root", password="rahasia-admin-123").status_code, 302)

    def test_username_beda_huruf_besar_kecil_dihitung_sama(self):
        for nama in ("budi", "BUDI", "Budi", " budi", "bUdI"):
            self._login(username=nama)
        self.assertEqual(self._login(username="budi", password="rahasia-benar-123").status_code, 429)

    def test_password_spraying_banyak_username_memblokir_ip(self):
        for i in range(19):
            self.assertEqual(self._login(username=f"tebakan{i}").status_code, 200)
        self.assertEqual(self._login(username="tebakan19").status_code, 429)
        self.assertEqual(self._login(password="rahasia-benar-123").status_code, 429)
        self.assertTrue(ActivityLog.objects.filter(deskripsi__startswith="IP diblokir sementara").exists())

    def test_ip_lain_tidak_terdampak(self):
        for _ in range(5):
            self._login(ip="10.1.1.1")
        resp = self._login(password="rahasia-benar-123", ip="10.2.2.2")
        self.assertEqual(resp.status_code, 302)

    def test_blokir_berakhir_setelah_10_menit(self):
        import time as _time
        sekarang = _time.time()
        with mock.patch("accounts.pembatas_login.time.time", return_value=sekarang):
            for _ in range(5):
                self._login()
        with mock.patch("accounts.pembatas_login.time.time", return_value=sekarang + 599):
            self.assertEqual(self._login(password="rahasia-benar-123").status_code, 429)
        with mock.patch("accounts.pembatas_login.time.time", return_value=sekarang + 601):
            resp = self._login(password="rahasia-benar-123")
        self.assertEqual(resp.status_code, 302)

    def test_halaman_login_get_tetap_bisa_dibuka(self):
        for _ in range(5):
            self._login()
        self.assertEqual(self.client.get(reverse("login"), REMOTE_ADDR="10.1.1.1").status_code, 200)

    def test_login_admin_ikut_dihitung_dan_diblokir(self):
        url = reverse("admin:login")
        for _ in range(5):
            self._login(username="root", url=url)
        resp = self._login(username="root", password="rahasia-admin-123", url=url)
        self.assertEqual(resp.status_code, 429)

    def test_blokir_dicatat_di_log_sistem(self):
        for _ in range(5):
            self._login()
        self.assertTrue(ActivityLog.objects.filter(
            aktivitas=ActivityLog.Aktivitas.LOGIN_GAGAL, deskripsi__startswith="Username diblokir sementara").exists())

    def test_cache_mati_fail_open(self):
        with mock.patch("accounts.pembatas_login._cache", side_effect=ConnectionError("redis mati")), \
                mock.patch("accounts.pembatas_login.get_usage", side_effect=ConnectionError("redis mati")):
            for _ in range(6):
                self._login()
            resp = self._login(password="rahasia-benar-123")
        self.assertEqual(resp.status_code, 302)
