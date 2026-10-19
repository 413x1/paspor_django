"""Fase 1 — Nomor HP & kontak (SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD §3.9)."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from logs.models import ActivityLog
from paspor.models import UnitOrganisasi
from pengajuan.templatetags.pengajuan_extras import format_hp, wa_link

from .models import PegawaiProfile, User
from .validators import normalisasi_no_hp


class NormalisasiNoHpTests(SimpleTestCase):
    def test_format_umum_dinormalisasi(self):
        for masukan in ("0812-3456-7890", "+62 812 3456 7890", "6281234567890", "(0812) 3456.7890"):
            with self.subTest(masukan=masukan):
                self.assertEqual(normalisasi_no_hp(masukan), "6281234567890")

    def test_kosong_tetap_kosong(self):
        self.assertEqual(normalisasi_no_hp(""), "")
        self.assertEqual(normalisasi_no_hp(None), "")

    def test_input_tidak_valid_ditolak(self):
        for masukan in ("812345", "0812abc", "6281234567890123", "1234567890", "+62+812345678"):
            with self.subTest(masukan=masukan), self.assertRaises(ValidationError):
                normalisasi_no_hp(masukan)


class FilterHpTests(SimpleTestCase):
    def test_format_hp(self):
        self.assertEqual(format_hp("6281234567890"), "+62 812-3456-7890")
        self.assertEqual(format_hp(""), "")
        self.assertEqual(format_hp(None), "")

    def test_wa_link(self):
        self.assertEqual(wa_link("6281234567890"), "https://wa.me/6281234567890")
        self.assertEqual(wa_link(""), "")


class _KontakBasis:
    def setUp(self):
        self.unit = UnitOrganisasi.objects.first()
        self.pakln = User.objects.create_user(
            "pakln1", password="x", role="admin_pakln", email="pakln@pu.go.id", no_hp="6281100000099",
        )
        self.pegawai = User.objects.create_user(
            "peg1", password="x", role="pegawai", email="peg@pu.go.id", no_hp="6281100000001",
        )
        PegawaiProfile.objects.create(
            user=self.pegawai, nip="198701012010011001", nama="Pegawai Satu", jabatan="Staf",
            pangkat_golongan="III-a", unit_kerja="Dit. A", unit_organisasi=self.unit,
        )

    def data_edit(self, user, **ubah):
        profile = getattr(user, "profile", None)
        data = {
            "aksi": "simpan",
            "username": user.username,
            "nama": profile.nama if profile else (user.get_full_name() or user.username),
            "is_active": "on",
            "unit_organisasi": self.unit.pk,
            "unit_kerja": "Dit. A",
            "email": user.email,
            "no_hp": user.no_hp,
            "nip": profile.nip if profile else "",
            "jabatan": profile.jabatan if profile else "",
            "pangkat_golongan": profile.pangkat_golongan if profile else "",
            "sisa_cuti_tahun_berjalan": 12,
        }
        data.update(ubah)
        return data


class KelolaKontakTests(_KontakBasis, TestCase):
    def test_tambah_user_lokal_tanpa_no_hp_ditolak(self):
        self.client.force_login(self.pakln)
        resp = self.client.post(reverse("pakln:kelola_user"), {
            "aksi": "tambah", "role": "admin_bko", "username": "bko.darurat", "nama": "Admin Darurat",
            "email": "bko.darurat@pu.go.id", "no_hp": "", "password": "RahasiaKuat#2026",
            "password_konfirmasi": "RahasiaKuat#2026", "unit_kerja": "Biro BKO",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="bko.darurat").exists())

    def test_tambah_user_lokal_menormalisasi_no_hp(self):
        self.client.force_login(self.pakln)
        resp = self.client.post(reverse("pakln:kelola_user"), {
            "aksi": "tambah", "role": "admin_unor", "username": "unor.darurat", "nama": "Admin Darurat",
            "email": "unor.darurat@pu.go.id", "no_hp": "0812-1111-2222", "password": "RahasiaKuat#2026",
            "password_konfirmasi": "RahasiaKuat#2026", "unit_kerja": "Setditjen", "unit_organisasi": self.unit.pk,
        })
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username="unor.darurat")
        self.assertEqual(user.no_hp, "6281211112222")
        self.assertEqual(user.sumber_akun, User.SumberAkun.LOKAL)
        # Akun admin darurat tidak memiliki role Pegawai (Q6).
        self.assertEqual(user.daftar_peran(), [User.Role.ADMIN_UNOR])
        self.assertEqual(user.unit_admin_id(), self.unit.pk)

    def test_edit_no_hp_user_sso_mengunci_field(self):
        self.pegawai.sso_sub = "sub-peg1"
        self.pegawai.save()
        self.client.force_login(self.pakln)
        resp = self.client.post(
            reverse("pakln:edit_user", args=[self.pegawai.pk]), self.data_edit(self.pegawai, no_hp="081299998888"),
        )
        self.assertEqual(resp.status_code, 302)
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.no_hp, "6281299998888")
        self.assertTrue(self.pegawai.no_hp_dikunci)
        self.assertFalse(self.pegawai.email_dikunci)
        log = ActivityLog.objects.get(aktivitas=ActivityLog.Aktivitas.UBAH_KONTAK)
        self.assertIn("6281100000001", log.detail)
        self.assertIn("6281299998888", log.detail)

    def test_edit_user_lokal_tidak_mengunci(self):
        self.client.force_login(self.pakln)
        self.client.post(
            reverse("pakln:edit_user", args=[self.pegawai.pk]), self.data_edit(self.pegawai, no_hp="081299998888"),
        )
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.no_hp, "6281299998888")
        self.assertFalse(self.pegawai.no_hp_dikunci)

    def test_buka_kunci(self):
        self.pegawai.sso_sub = "sub-peg1"
        self.pegawai.no_hp_dikunci = True
        self.pegawai.save()
        self.client.force_login(self.pakln)
        self.client.post(
            reverse("pakln:edit_user", args=[self.pegawai.pk]),
            self.data_edit(self.pegawai, buka_kunci_no_hp="on"),
        )
        self.pegawai.refresh_from_db()
        self.assertFalse(self.pegawai.no_hp_dikunci)
        self.assertTrue(ActivityLog.objects.filter(aktivitas=ActivityLog.Aktivitas.BUKA_KUNCI_KONTAK).exists())

    def test_email_duplikat_ditolak(self):
        self.client.force_login(self.pakln)
        resp = self.client.post(
            reverse("pakln:edit_user", args=[self.pegawai.pk]), self.data_edit(self.pegawai, email="PAKLN@pu.go.id"),
        )
        self.assertEqual(resp.status_code, 200)
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.email, "peg@pu.go.id")

    def test_non_pakln_tidak_bisa_edit_user(self):
        self.client.force_login(self.pegawai)
        resp = self.client.post(
            reverse("pakln:edit_user", args=[self.pegawai.pk]), self.data_edit(self.pegawai, no_hp="081299998888"),
        )
        self.assertEqual(resp.status_code, 403)
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.no_hp, "6281100000001")


class BannerDanFilterTests(_KontakBasis, TestCase):
    def test_banner_tampil_bila_no_hp_kosong(self):
        User.objects.filter(pk=self.pegawai.pk).update(no_hp="")
        self.client.force_login(self.pegawai)
        resp = self.client.get(reverse("profil"))
        self.assertContains(resp, "Nomor HP belum tercatat — hubungi Admin Biro PAKLN.")

    def test_banner_tidak_tampil_bila_terisi(self):
        self.client.force_login(self.pegawai)
        resp = self.client.get(reverse("profil"))
        self.assertNotContains(resp, "banner-no-hp")

    def test_banner_pakln_menautkan_profil(self):
        User.objects.filter(pk=self.pakln.pk).update(no_hp="")
        self.client.force_login(self.pakln)
        resp = self.client.get(reverse("pakln:dashboard"))
        self.assertContains(resp, "Lengkapi di menu Profil")

    def test_filter_tanpa_hp(self):
        User.objects.filter(pk=self.pegawai.pk).update(no_hp="")
        self.client.force_login(self.pakln)
        resp = self.client.get(reverse("pakln:users_data"), {"tanpa_hp": "1"})
        usernames = [baris[0] for baris in resp.json()["data"]]
        self.assertEqual(len(usernames), 1)
        self.assertIn("peg1", usernames[0])

    def test_kolom_no_hp_berupa_tautan_wa(self):
        self.client.force_login(self.pakln)
        resp = self.client.get(reverse("pakln:users_data"))
        self.assertIn("https://wa.me/6281100000001", str(resp.json()["data"]))
