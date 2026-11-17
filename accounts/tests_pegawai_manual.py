"""Tambah Pegawai Manual — Manajemen User (selama integrasi e-HRM belum berfungsi)."""

from django.test import TestCase
from django.urls import reverse

from logs.models import ActivityLog
from paspor.models import UnitOrganisasi

from .forms import TambahPegawaiForm, TambahUserForm
from .models import PegawaiProfile, PeranUser, User

NIP = "199001012015031001"


class PegawaiManualBase(TestCase):
    def setUp(self):
        self.pakln = User.objects.create_user("pakln1", password="x", role="admin_pakln", no_hp="6281100000099")
        self.client.force_login(self.pakln)
        self.unit = UnitOrganisasi.objects.first()
        self.url = reverse("pakln:kelola_user")

    def data(self, **ubah):
        data = {
            "aksi": "tambah_pegawai",
            "nip": NIP,
            "nama_lengkap": "Budi Santoso, S.T.",
            "jabatan": "Analis Kebijakan",
            "pangkat_golongan": "Penata Muda (III/a)",
            "unit_kerja": "Direktorat Bina Teknik Sumber Daya Air",
            "unit_organisasi": self.unit.pk,
            "email": "budi.santoso@example.go.id",
            "no_hp": "0812-3456-7890",
            "username": NIP,
            "password": "KataSandi-Kuat-123",
            "password_confirm": "KataSandi-Kuat-123",
        }
        data.update(ubah)
        return data


class TambahPegawaiManualBerhasilTests(PegawaiManualBase):
    def test_pegawai_dibuat_lengkap(self):
        resp = self.client.post(self.url, self.data())
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)

        user = User.objects.get(username=NIP)
        self.assertEqual(user.role, User.Role.PEGAWAI)
        self.assertEqual(user.sumber_akun, User.SumberAkun.LOKAL)
        self.assertIsNone(user.sso_sub)
        self.assertTrue(user.check_password("KataSandi-Kuat-123"))
        self.assertEqual(user.email, "budi.santoso@example.go.id")
        self.assertEqual(user.no_hp, "6281234567890")
        self.assertEqual((user.first_name, user.last_name), ("Budi", "Santoso, S.T."))
        self.assertEqual(user.unit_organisasi, self.unit)

        profil = user.profile
        self.assertEqual(profil.nip, NIP)
        self.assertEqual(profil.nama, "Budi Santoso, S.T.")
        self.assertEqual(profil.jabatan, "Analis Kebijakan")
        self.assertEqual(profil.pangkat_golongan, "Penata Muda (III/a)")
        self.assertEqual(profil.unit_kerja, "Direktorat Bina Teknik Sumber Daya Air")
        self.assertEqual(profil.unit_organisasi, self.unit)

    def test_sisa_cuti_default_12(self):
        self.client.post(self.url, self.data())
        self.assertEqual(User.objects.get(username=NIP).profile.sisa_cuti_tahun_berjalan, 12)

    def test_sisa_cuti_boleh_diisi(self):
        self.client.post(self.url, self.data(sisa_cuti="7"))
        self.assertEqual(User.objects.get(username=NIP).profile.sisa_cuti_tahun_berjalan, 7)

    def test_sisa_cuti_nol_tidak_menjadi_default(self):
        self.client.post(self.url, self.data(sisa_cuti="0"))
        self.assertEqual(User.objects.get(username=NIP).profile.sisa_cuti_tahun_berjalan, 0)

    def test_hanya_peran_pegawai(self):
        self.client.post(self.url, self.data())
        user = User.objects.get(username=NIP)
        peran = list(PeranUser.objects.filter(user=user).values_list("role", "is_active"))
        self.assertEqual(peran, [(User.Role.PEGAWAI, True)])
        self.assertEqual(PeranUser.objects.get(user=user).diberikan_oleh, self.pakln)
        self.assertEqual(user.daftar_peran(), [User.Role.PEGAWAI])

    def test_pegawai_baru_bisa_login_dengan_username_password(self):
        self.client.post(self.url, self.data())
        self.client.logout()
        self.assertTrue(self.client.login(username=NIP, password="KataSandi-Kuat-123"))

    def test_peran_dari_post_diabaikan(self):
        """Peran tidak bisa dipaksa lewat POST: selalu Pegawai."""
        self.client.post(self.url, self.data(role="admin_pakln"))
        self.assertEqual(User.objects.get(username=NIP).role, User.Role.PEGAWAI)

    def test_dicatat_di_log_aktivitas(self):
        self.client.post(self.url, self.data())
        log = ActivityLog.objects.filter(aktivitas=ActivityLog.Aktivitas.UBAH_MASTER).latest("pk")
        self.assertIn(NIP, log.deskripsi)

    def test_pesan_sukses_tampil(self):
        resp = self.client.post(self.url, self.data(), follow=True)
        self.assertContains(resp, "berhasil ditambahkan")
        self.assertContains(resp, "Budi Santoso, S.T.")

    def test_email_disimpan_huruf_kecil(self):
        self.client.post(self.url, self.data(email="Budi.Santoso@Example.GO.ID"))
        self.assertEqual(User.objects.get(username=NIP).email, "budi.santoso@example.go.id")


class TambahPegawaiManualDitolakTests(PegawaiManualBase):
    def assertDitolak(self, resp, field, pesan=None):
        self.assertEqual(resp.status_code, 200)
        self.assertIn(field, resp.context["pegawai_form"].errors)
        if pesan:
            self.assertContains(resp, pesan)
        self.assertFalse(PegawaiProfile.objects.exists())
        self.assertFalse(User.objects.exclude(pk=self.pakln.pk).exists())

    def test_nip_duplikat(self):
        self.client.post(self.url, self.data())
        resp = self.client.post(self.url, self.data(
            username="lain", email="lain@example.go.id", no_hp="0812-9999-0000",
        ))
        self.assertIn("nip", resp.context["pegawai_form"].errors)
        self.assertContains(resp, "NIP sudah terdaftar di PASPOR.")
        self.assertEqual(PegawaiProfile.objects.filter(nip=NIP).count(), 1)

    def test_nip_dipakai_sebagai_username_akun_lain(self):
        User.objects.create_user(NIP, password="x", role="admin_bko", no_hp="6281100000001")
        resp = self.client.post(self.url, self.data(username="budi.baru"))
        self.assertIn("nip", resp.context["pegawai_form"].errors)
        self.assertFalse(PegawaiProfile.objects.exists())

    def test_nip_bukan_angka(self):
        self.assertDitolak(self.client.post(self.url, self.data(nip="19900101abc")), "nip", "NIP hanya berisi angka.")

    def test_email_duplikat(self):
        User.objects.create_user("lain", password="x", role="admin_bko", email="Budi.Santoso@example.go.id", no_hp="6281100000002")
        resp = self.client.post(self.url, self.data())
        self.assertIn("email", resp.context["pegawai_form"].errors)
        self.assertContains(resp, "Email sudah digunakan akun lain.")
        self.assertFalse(PegawaiProfile.objects.exists())

    def test_unit_organisasi_kosong(self):
        self.assertDitolak(self.client.post(self.url, self.data(unit_organisasi="")), "unit_organisasi")

    def test_username_duplikat(self):
        User.objects.create_user("budi.santoso", password="x", role="admin_bko", no_hp="6281100000003")
        resp = self.client.post(self.url, self.data(username="Budi.Santoso"))
        self.assertIn("username", resp.context["pegawai_form"].errors)
        self.assertFalse(PegawaiProfile.objects.exists())

    def test_no_hp_wajib_dan_valid(self):
        for nilai in ("", "812345", "0812abc"):
            with self.subTest(no_hp=nilai):
                self.assertDitolak(self.client.post(self.url, self.data(no_hp=nilai)), "no_hp")

    def test_field_identitas_wajib(self):
        for field in ("nama_lengkap", "jabatan", "pangkat_golongan", "unit_kerja", "username", "email", "nip"):
            with self.subTest(field=field):
                self.assertDitolak(self.client.post(self.url, self.data(**{field: ""})), field)

    def test_password_tidak_cocok(self):
        self.assertDitolak(
            self.client.post(self.url, self.data(password_confirm="Beda-Sama-Sekali-9")),
            "password_confirm", "Konfirmasi password tidak cocok.",
        )

    def test_password_lemah_ditolak_validator_django(self):
        self.assertDitolak(self.client.post(self.url, self.data(password="12345678", password_confirm="12345678")), "password")

    def test_password_kosong(self):
        self.assertDitolak(self.client.post(self.url, self.data(password="", password_confirm="")), "password")

    def test_sisa_cuti_negatif_ditolak(self):
        self.assertDitolak(self.client.post(self.url, self.data(sisa_cuti="-1")), "sisa_cuti")

    def test_gagal_tidak_meninggalkan_data_yatim(self):
        """Bila pembuatan profil gagal di tengah, User yang sudah tersimpan ikut dibatalkan."""
        from unittest import mock

        with mock.patch.object(PegawaiProfile.objects, "create", side_effect=RuntimeError("gagal")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.data())
        self.assertFalse(User.objects.filter(username=NIP).exists())
        self.assertFalse(PegawaiProfile.objects.exists())


class TambahPegawaiManualTampilanTests(PegawaiManualBase):
    def test_kotak_tampil_berdampingan_dengan_kotak_lama(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Tambah Pegawai Manual", html)
        self.assertIn('value="tambah_pegawai"', html)
        # Kotak lama tetap ada: Pra-daftar via NIP (e-HRM) dan Tambah Akun Admin.
        self.assertIn("Pra-daftar Pegawai via NIP", html)
        self.assertIn("Cek di e-HRM", html)
        self.assertIn("Tambah Akun Admin", html)

    def test_dropdown_akun_lokal_tetap_tanpa_pegawai(self):
        """AB-05: form Tambah Akun Admin tidak menawarkan peran Pegawai."""
        pilihan = [nilai for nilai, _ in TambahUserForm().fields["role"].choices]
        self.assertNotIn("pegawai", pilihan)

    def test_form_pegawai_tanpa_pilihan_peran(self):
        self.assertNotIn("role", TambahPegawaiForm().fields)
        self.assertNotIn("sumber_akun", TambahPegawaiForm().fields)

    def test_kesalahan_tampil_di_kotak_pegawai(self):
        resp = self.client.post(self.url, self.data(nip="abc"))
        self.assertContains(resp, "NIP hanya berisi angka.")
        self.assertContains(resp, "Periksa kembali isian formulir Tambah Pegawai Manual.")
        # Isian lain tetap terisi kembali.
        self.assertContains(resp, "Budi Santoso, S.T.")

    def test_pegawai_manual_muncul_di_daftar_user(self):
        self.client.post(self.url, self.data())
        resp = self.client.get(reverse("pakln:users_data"), {"draw": 1, "start": 0, "length": 10, "search[value]": NIP})
        baris = resp.json()["data"]
        self.assertEqual(len(baris), 1)
        self.assertIn(NIP, " ".join(str(k) for k in baris[0]))

    def test_hanya_admin_pakln(self):
        pegawai = User.objects.create_user("peg1", password="x", role="pegawai", no_hp="6281100000077")
        self.client.force_login(pegawai)
        resp = self.client.post(self.url, self.data())
        self.assertNotEqual(resp.status_code, 200)
        self.assertFalse(PegawaiProfile.objects.exists())
