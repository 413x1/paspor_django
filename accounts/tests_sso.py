"""Fase 5 — Alur inti login SSO (SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD §7.3).
Memakai stub e-HRM, tanpa jaringan."""

from unittest import mock

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from logs.models import ActivityLog
from paspor.integrasi import ehrm

from .models import PegawaiProfile, User
from .sso import SsoGagal, masuk_dari_sso

NIP_BARU = "199001012015031001"
NIP_LAMA = "198703142011011007"


@override_settings(DEBUG=True, SSO_ENABLED=False)
class AlurSsoTests(TestCase):
    def setUp(self):
        self.lama = User.objects.create_user("andra", password="lama-Rahasia#1", role="pegawai")
        PegawaiProfile.objects.create(
            user=self.lama, nip=NIP_LAMA, nama="Andra", jabatan="Lama", pangkat_golongan="III-d",
            unit_kerja="Dit. Bina Teknik",
        )

    def test_nip_baru_membuat_user_dan_login_sebagai_pegawai(self):
        resp = self.client.post(reverse("sso_login"), {"nip": NIP_BARU})
        self.assertRedirects(resp, reverse("home"), fetch_redirect_response=False)
        user = User.objects.get(profile__nip=NIP_BARU)
        self.assertEqual(user.sso_sub, f"stub-{NIP_BARU}")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(self.client.get(reverse("pegawai:beranda")).status_code, 200)
        self.assertEqual(self.client.session["peran_aktif"], "pegawai")
        self.assertTrue(ActivityLog.objects.filter(aktivitas=ActivityLog.Aktivitas.LOGIN_SSO, user=user).exists())

    def test_nip_lama_ditautkan_tanpa_user_baru(self):
        jumlah = User.objects.count()
        self.client.post(reverse("sso_login"), {"nip": NIP_LAMA})
        self.assertEqual(User.objects.count(), jumlah)
        self.lama.refresh_from_db()
        self.assertEqual(self.lama.sso_sub, f"stub-{NIP_LAMA}")
        self.assertEqual(self.lama.sumber_akun, User.SumberAkun.SSO)
        self.assertEqual(self.lama.profile.jabatan, "Kepala Seksi Perencanaan Teknis")  # tersinkron e-HRM
        self.assertTrue(self.lama.check_password("lama-Rahasia#1"))  # password lama tetap berlaku

    def test_login_kedua_lewat_sso_sub_meski_username_diganti(self):
        self.client.post(reverse("sso_login"), {"nip": NIP_BARU})
        user = User.objects.get(profile__nip=NIP_BARU)
        User.objects.filter(pk=user.pk).update(username="citra.baru")
        self.client.logout()
        self.client.post(reverse("sso_login"), {"nip": NIP_BARU})
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(User.objects.filter(profile__nip=NIP_BARU).count(), 1)

    def test_user_nonaktif_ditolak(self):
        User.objects.filter(pk=self.lama.pk).update(is_active=False)
        resp = self.client.post(reverse("sso_login"), {"nip": NIP_LAMA}, follow=True)
        self.assertContains(resp, "dinonaktifkan")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ehrm_down_user_lama_tetap_login(self):
        with mock.patch.object(ehrm, "ambil_pegawai", side_effect=ehrm.EhrmTidakTersedia("down")):
            self.client.post(reverse("sso_login"), {"nip": NIP_LAMA})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.lama.pk)
        self.assertTrue(ActivityLog.objects.filter(aktivitas=ActivityLog.Aktivitas.SINKRON_EHRM_GAGAL).exists())

    def test_ehrm_down_user_baru_gagal_dengan_pesan_ramah(self):
        with mock.patch.object(ehrm, "ambil_pegawai", side_effect=ehrm.EhrmTidakTersedia("down")):
            resp = self.client.post(reverse("sso_login"), {"nip": NIP_BARU}, follow=True)
        self.assertContains(resp, "Data kepegawaian tidak dapat diambil, coba lagi nanti.")
        self.assertFalse(User.objects.filter(profile__nip=NIP_BARU).exists())

    def test_nip_tidak_dikenal_ditolak(self):
        request = RequestFactory().get("/")
        with self.assertRaises(SsoGagal):
            masuk_dari_sso(request, sub="sub-x", nip="000", klaim={})

    def test_halaman_login_menampilkan_tombol_sso(self):
        self.assertContains(self.client.get(reverse("login")), "Masuk dengan SSO")

    def test_halaman_stub_menampilkan_daftar_nip(self):
        self.assertContains(self.client.get(reverse("sso_login")), NIP_BARU)


class StubProduksiTests(TestCase):
    @override_settings(DEBUG=False, SSO_ENABLED=False)
    def test_stub_404_saat_debug_false(self):
        self.assertEqual(self.client.get(reverse("sso_login")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("login")), "Masuk dengan SSO")
