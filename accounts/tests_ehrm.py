"""Fase 4 — Integrasi e-HRM (SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD §6.6)."""

import io
import json
import urllib.error
from dataclasses import replace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from paspor.integrasi import ehrm
from paspor.models import UnitOrganisasi

from .ehrm_sync import buat_user_dari_ehrm, sinkron_profil
from .models import PegawaiProfile, PeranUser, User

NIP_BARU = "199001012015031001"  # ada di stub, belum ada di PASPOR


def _data(**ubah):
    return replace(ehrm.ambil_pegawai(NIP_BARU), **ubah)


class StubEhrmTests(TestCase):
    def test_stub_dipakai_bila_url_kosong(self):
        self.assertTrue(ehrm.memakai_stub())
        data = ehrm.ambil_pegawai(NIP_BARU)
        self.assertEqual(data.nip, NIP_BARU)
        self.assertTrue(data.email and data.no_hp)
        self.assertIsNone(ehrm.ambil_pegawai("000"))


class SinkronTests(TestCase):
    def test_buat_user_dari_ehrm(self):
        user = buat_user_dari_ehrm(_data())
        self.assertEqual(user.username, NIP_BARU)
        self.assertEqual(user.sumber_akun, User.SumberAkun.SSO)
        self.assertFalse(user.has_usable_password())
        self.assertIsNone(user.sso_sub)
        self.assertEqual(user.profile.nip, NIP_BARU)
        self.assertEqual(user.profile.unit_organisasi.code, "06")
        self.assertEqual(user.no_hp, "6281100000002")
        self.assertEqual(list(PeranUser.objects.filter(user=user).values_list("role", flat=True)), ["pegawai"])
        self.assertIsNotNone(user.ehrm_sinkron_at)

    def test_sinkron_memperbarui_jabatan_dan_menghormati_kunci(self):
        user = buat_user_dari_ehrm(_data())
        user.email = "koreksi@pu.go.id"
        user.email_dikunci = True
        user.save()
        berubah = sinkron_profil(user, _data(jabatan="Analis Ahli Madya", email="baru@pu.go.id"))
        user.refresh_from_db()
        self.assertEqual(user.profile.jabatan, "Analis Ahli Madya")
        self.assertIn("jabatan", berubah)
        self.assertEqual(user.email, "koreksi@pu.go.id")
        self.assertNotIn("email", berubah)

    def test_no_hp_ehrm_tidak_valid_diabaikan(self):
        user = buat_user_dari_ehrm(_data())
        sinkron_profil(user, _data(no_hp="12ab"))
        user.refresh_from_db()
        self.assertEqual(user.no_hp, "6281100000002")

    def test_kode_unit_tidak_dikenal_mempertahankan_unit_lama(self):
        user = buat_user_dari_ehrm(_data())
        with self.assertLogs("accounts.ehrm_sync", level="WARNING"):
            sinkron_profil(user, _data(kode_unit_organisasi="ZZ"))
        user.refresh_from_db()
        self.assertEqual(user.profile.unit_organisasi.code, "06")

    def test_tabrakan_username_diberi_sufiks(self):
        User.objects.create_user(NIP_BARU, password="x", role="admin_bko")
        user = buat_user_dari_ehrm(_data())
        self.assertEqual(user.username, f"{NIP_BARU}-1")


@override_settings(EHRM_API_URL="https://ehrm.contoh.go.id/api", EHRM_API_TOKEN="tkn", EHRM_TIMEOUT=2)
class HttpEhrmTests(TestCase):
    def test_http_berhasil(self):
        isi = json.dumps({"nip": "123", "nama": "Uji HTTP", "no_hp": "0812"}).encode()
        respons = mock.MagicMock()
        respons.__enter__.return_value.read.return_value = isi
        with mock.patch("urllib.request.urlopen", return_value=respons) as urlopen:
            data = ehrm.ambil_pegawai("123")
        self.assertEqual(data.nama, "Uji HTTP")
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "https://ehrm.contoh.go.id/api/pegawai/123")
        self.assertEqual(req.get_header("Authorization"), "Bearer tkn")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2)

    def test_http_404_berarti_tidak_ditemukan(self):
        galat = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO())
        with mock.patch("urllib.request.urlopen", side_effect=galat):
            self.assertIsNone(ehrm.ambil_pegawai("123"))

    def test_timeout_diteruskan_sebagai_ehrm_tidak_tersedia(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            with self.assertRaises(ehrm.EhrmTidakTersedia):
                ehrm.ambil_pegawai("123")


class FiturPaklnEhrmTests(TestCase):
    def setUp(self):
        self.pakln = User.objects.create_user("pakln1", password="x", role="admin_pakln", no_hp="6281100000099")
        self.client.force_login(self.pakln)

    def test_pra_daftar_via_nip(self):
        url = reverse("pakln:kelola_user")
        resp = self.client.post(url, {"aksi": "pra_daftar_cek", "nip": NIP_BARU})
        self.assertContains(resp, "Citra Lestari")
        self.assertFalse(PegawaiProfile.objects.filter(nip=NIP_BARU).exists())

        resp = self.client.post(url, {"aksi": "pra_daftar_simpan", "nip": NIP_BARU})
        user = User.objects.get(profile__nip=NIP_BARU)
        self.assertRedirects(resp, reverse("pakln:edit_user", args=[user.pk]), fetch_redirect_response=False)
        self.assertIsNone(user.sso_sub)
        self.assertFalse(user.has_usable_password())

    def test_pra_daftar_nip_tidak_ditemukan(self):
        resp = self.client.post(reverse("pakln:kelola_user"), {"aksi": "pra_daftar_simpan", "nip": "123456"})
        self.assertContains(resp, "tidak ditemukan di e-HRM")
        self.assertFalse(PegawaiProfile.objects.filter(nip="123456").exists())

    def test_sinkron_ulang_dan_kembalikan_ke_ehrm(self):
        user = buat_user_dari_ehrm(_data())
        PegawaiProfile.objects.filter(user=user).update(jabatan="Lama")
        User.objects.filter(pk=user.pk).update(no_hp="6289999999999", no_hp_dikunci=True)
        url = reverse("pakln:edit_user", args=[user.pk])

        self.client.post(url, {"aksi": "sinkron_ehrm"})
        user.refresh_from_db()
        self.assertEqual(user.profile.jabatan, "Analis Kebijakan Ahli Muda")
        self.assertEqual(user.no_hp, "6289999999999")  # masih dikunci

        self.client.post(url, {"aksi": "kembalikan_ehrm", "field": "no_hp"})
        user.refresh_from_db()
        self.assertFalse(user.no_hp_dikunci)
        self.assertEqual(user.no_hp, "6281100000002")

    def test_tambah_user_tidak_lagi_menyediakan_pegawai(self):
        resp = self.client.get(reverse("pakln:kelola_user"))
        pilihan = [nilai for nilai, _ in resp.context["form"].fields["role"].choices]
        self.assertNotIn("pegawai", pilihan)
        self.assertIn("admin_pakln", pilihan)


class CommandSinkronEhrmTests(TestCase):
    def test_command_dry_run_dan_sinkron(self):
        user = buat_user_dari_ehrm(_data())
        PegawaiProfile.objects.filter(user=user).update(jabatan="Lama")
        out = io.StringIO()
        call_command("sinkron_ehrm", "--dry-run", stdout=out)
        self.assertEqual(PegawaiProfile.objects.get(user=user).jabatan, "Lama")
        call_command("sinkron_ehrm", "--nip", NIP_BARU, stdout=out)
        self.assertEqual(PegawaiProfile.objects.get(user=user).jabatan, "Analis Kebijakan Ahli Muda")

    def test_unit_lama_dipakai_bila_unit_tidak_dikenal(self):
        unit = UnitOrganisasi.objects.get(code="06")
        user = buat_user_dari_ehrm(_data())
        self.assertEqual(user.profile.unit_organisasi, unit)
