"""Fase 2 — Akun mandiri di Profil (SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD §4.5)."""

from django.test import TestCase
from django.urls import reverse

from logs.models import ActivityLog

from .models import PegawaiProfile, User
from .views import PESAN_TANPA_PASSWORD

PASSWORD_BARU = "SandiBaru#2026xyz"


class _ProfilBasis:
    def setUp(self):
        self.pegawai = User.objects.create_user(
            "peg1", password="lama-Rahasia#1", role="pegawai", email="peg@pu.go.id", no_hp="6281100000001",
        )
        PegawaiProfile.objects.create(
            user=self.pegawai, nip="198701012010011001", nama="Pegawai Satu", jabatan="Staf",
            pangkat_golongan="III-a", unit_kerja="Dit. A",
        )
        self.pakln = User.objects.create_user(
            "pakln1", password="lama-Rahasia#1", role="admin_pakln", email="pakln@pu.go.id",
            no_hp="6281100000099",
        )

    def post_profil(self, user, data):
        self.client.force_login(user)
        return self.client.post(reverse("profil"), data)


class WhitelistProfilTests(_ProfilBasis, TestCase):
    def test_ubah_username_mengabaikan_field_lain(self):
        resp = self.post_profil(self.pegawai, {
            "aksi": "ubah_username", "username": "peg.baru",
            "email": "lain@pu.go.id", "no_hp": "081299998888", "nama": "Diganti", "role": "admin_pakln",
        })
        self.assertEqual(resp.status_code, 302)
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.username, "peg.baru")
        self.assertEqual(self.pegawai.email, "peg@pu.go.id")
        self.assertEqual(self.pegawai.no_hp, "6281100000001")
        self.assertEqual(self.pegawai.role, "pegawai")
        self.assertEqual(self.pegawai.profile.nama, "Pegawai Satu")
        log = ActivityLog.objects.get(aktivitas=ActivityLog.Aktivitas.UBAH_USERNAME)
        self.assertIn("peg1 → peg.baru", log.deskripsi)

    def test_pegawai_ubah_kontak_ditolak(self):
        self.post_profil(self.pegawai, {"aksi": "ubah_kontak", "email": "lain@pu.go.id", "no_hp": "081299998888"})
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.email, "peg@pu.go.id")
        self.assertEqual(self.pegawai.no_hp, "6281100000001")

    def test_pakln_ubah_kontak_sendiri(self):
        resp = self.post_profil(self.pakln, {
            "aksi": "ubah_kontak", "email": "pakln.baru@pu.go.id", "no_hp": "081299998888", "role": "pegawai",
        })
        self.assertEqual(resp.status_code, 302)
        self.pakln.refresh_from_db()
        self.assertEqual(self.pakln.email, "pakln.baru@pu.go.id")
        self.assertEqual(self.pakln.no_hp, "6281299998888")
        self.assertEqual(self.pakln.role, "admin_pakln")
        self.assertFalse(self.pakln.no_hp_dikunci)  # akun lokal tidak dikunci

    def test_role_ganda_ubah_kontak_hanya_saat_peran_pakln(self):
        from .models import PeranUser

        PeranUser.objects.create(user=self.pegawai, role="admin_pakln")
        self.client.force_login(self.pegawai)
        self.client.post(reverse("ganti_peran"), {"peran": "pegawai"})
        self.client.post(reverse("profil"), {"aksi": "ubah_kontak", "email": "x@pu.go.id", "no_hp": "081299998888"})
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.email, "peg@pu.go.id")
        self.client.post(reverse("ganti_peran"), {"peran": "admin_pakln"})
        self.client.post(reverse("profil"), {"aksi": "ubah_kontak", "email": "x@pu.go.id", "no_hp": "081299998888"})
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.email, "x@pu.go.id")

    def test_username_duplikat_beda_huruf_ditolak(self):
        resp = self.post_profil(self.pegawai, {"aksi": "ubah_username", "username": "PAKLN1"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Username sudah digunakan.")
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.username, "peg1")

    def test_username_nip_orang_lain_ditolak(self):
        resp = self.post_profil(self.pakln, {"aksi": "ubah_username", "username": "198701012010011001"})
        self.assertEqual(resp.status_code, 200)
        self.pakln.refresh_from_db()
        self.assertEqual(self.pakln.username, "pakln1")


class PasswordProfilTests(_ProfilBasis, TestCase):
    def test_atur_password_tanpa_password_lama(self):
        self.pegawai.set_unusable_password()
        self.pegawai.save()
        resp = self.post_profil(self.pegawai, {
            "aksi": "atur_password", "new_password1": PASSWORD_BARU, "new_password2": PASSWORD_BARU,
        })
        self.assertEqual(resp.status_code, 302)
        self.pegawai.refresh_from_db()
        self.assertTrue(self.pegawai.check_password(PASSWORD_BARU))
        self.assertEqual(self.client.get(reverse("profil")).status_code, 200)

    def test_atur_password_ditolak_bila_sudah_berpassword(self):
        self.post_profil(self.pegawai, {
            "aksi": "atur_password", "new_password1": PASSWORD_BARU, "new_password2": PASSWORD_BARU,
        })
        self.pegawai.refresh_from_db()
        self.assertFalse(self.pegawai.check_password(PASSWORD_BARU))

    def test_ganti_password_tanpa_password_lama_benar_ditolak(self):
        resp = self.post_profil(self.pegawai, {
            "aksi": "ganti_password", "old_password": "salah",
            "new_password1": PASSWORD_BARU, "new_password2": PASSWORD_BARU,
        })
        self.assertEqual(resp.status_code, 200)
        self.pegawai.refresh_from_db()
        self.assertTrue(self.pegawai.check_password("lama-Rahasia#1"))

    def test_ganti_password_sesi_tetap_login(self):
        resp = self.post_profil(self.pegawai, {
            "aksi": "ganti_password", "old_password": "lama-Rahasia#1",
            "new_password1": PASSWORD_BARU, "new_password2": PASSWORD_BARU,
        })
        self.assertEqual(resp.status_code, 302)
        self.pegawai.refresh_from_db()
        self.assertTrue(self.pegawai.check_password(PASSWORD_BARU))
        self.assertEqual(self.client.get(reverse("profil")).status_code, 200)

    def test_hapus_password_akun_lokal_ditolak(self):
        self.post_profil(self.pegawai, {"aksi": "hapus_password", "password_lama": "lama-Rahasia#1"})
        self.pegawai.refresh_from_db()
        self.assertTrue(self.pegawai.has_usable_password())

    def test_hapus_password_akun_sso_lalu_login_form_gagal(self):
        self.pegawai.sso_sub = "sub-peg1"
        self.pegawai.save()
        resp = self.post_profil(self.pegawai, {"aksi": "hapus_password", "password_lama": "lama-Rahasia#1"})
        self.assertEqual(resp.status_code, 302)
        self.pegawai.refresh_from_db()
        self.assertFalse(self.pegawai.has_usable_password())

        self.client.logout()
        resp = self.client.post(reverse("login"), {"username": "peg1", "password": "lama-Rahasia#1"})
        self.assertContains(resp, PESAN_TANPA_PASSWORD)

    def test_log_password_tanpa_nilai(self):
        self.post_profil(self.pegawai, {
            "aksi": "ganti_password", "old_password": "lama-Rahasia#1",
            "new_password1": PASSWORD_BARU, "new_password2": PASSWORD_BARU,
        })
        log = ActivityLog.objects.get(aktivitas=ActivityLog.Aktivitas.GANTI_PASSWORD)
        for teks in (log.deskripsi, log.detail):
            self.assertNotIn(PASSWORD_BARU, teks)
            self.assertNotIn("lama-Rahasia#1", teks)


class LoginFormTests(_ProfilBasis, TestCase):
    def test_login_gagal_pesan_generik(self):
        resp = self.client.post(reverse("login"), {"username": "peg1", "password": "salah"})
        self.assertContains(resp, "Username atau password salah.")

    def test_user_nonaktif_ditolak(self):
        User.objects.filter(pk=self.pegawai.pk).update(is_active=False)
        resp = self.client.post(reverse("login"), {"username": "peg1", "password": "lama-Rahasia#1"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
