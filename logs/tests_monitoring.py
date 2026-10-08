"""Tes Langkah 2-3 Log Sistem: halaman monitoring, endpoint DataTables,
Reset Log, management command `bersihkan_log`, dan signal login/logout."""

import json
from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import ActivityLog


def _buat_log(n=1, **kw):
    return [ActivityLog.objects.create(aktivitas="auth.login", deskripsi=f"log {i}", username="budi", **kw)
            for i in range(n)]


class HalamanDanAksesTests(TestCase):
    def setUp(self):
        self.pakln = User.objects.create_user(username="adm.pakln", password="x", role="admin_pakln")
        self.pegawai = User.objects.create_user(username="peg", password="x", role="pegawai")

    def test_hanya_admin_pakln(self):
        for nama in ("pakln:log_sistem", "pakln:log_sistem_data"):
            self.assertEqual(self.client.get(reverse(nama)).status_code, 302)  # belum login
            self.client.force_login(self.pegawai)
            self.assertEqual(self.client.get(reverse(nama)).status_code, 403)
            self.client.logout()
        self.client.force_login(self.pegawai)
        self.assertEqual(self.client.post(reverse("pakln:log_sistem_reset"), {"rentang": "semua"}).status_code, 403)

    def test_halaman_tampil(self):
        self.client.force_login(self.pakln)
        r = self.client.get(reverse("pakln:log_sistem"))
        self.assertContains(r, "Reset Log")
        self.assertContains(r, 'id="logTable"')

    def test_menu_sidebar_hanya_untuk_pakln(self):
        self.client.force_login(self.pakln)
        self.assertContains(self.client.get(reverse("pakln:dashboard")), "Log Sistem")
        self.client.force_login(self.pegawai)
        self.assertNotContains(self.client.get(reverse("pegawai:beranda")), "Log Sistem")


class DataEndpointTests(TestCase):
    def setUp(self):
        self.pakln = User.objects.create_user(username="adm.pakln", password="x", role="admin_pakln")
        self.client.force_login(self.pakln)
        self.url = reverse("pakln:log_sistem_data")
        ActivityLog.objects.all().delete()  # force_login memicu signal login

    def _get(self, **params):
        return self.client.get(self.url, {"draw": 3, **params}).json()

    def test_format_datatables_dan_paginasi(self):
        _buat_log(25)
        data = self._get(start=0, length=10)
        self.assertEqual((data["draw"], data["recordsTotal"], data["recordsFiltered"]), (3, 25, 25))
        self.assertEqual(len(data["data"]), 10)
        self.assertEqual(len(data["data"][0]), 7)
        self.assertEqual(len(self._get(start=20, length=10)["data"]), 5)

    def test_length_dibatasi_maksimal_100(self):
        _buat_log(120)
        self.assertEqual(len(self._get(length=-1)["data"]), 100)
        self.assertEqual(len(self._get(length=5000)["data"]), 100)

    def test_search_dan_filter(self):
        ActivityLog.objects.create(aktivitas="auth.login", deskripsi="Login berhasil", username="ani", status="success")
        ActivityLog.objects.create(aktivitas="auth.login_failed", deskripsi="Login gagal", username="budi", status="failed")
        ActivityLog.objects.create(aktivitas="dokumen.unggah", deskripsi="Unggah", username="budi", target_id="PLN01-1")
        self.assertEqual(self._get(**{"search[value]": "PLN01"})["recordsFiltered"], 1)
        self.assertEqual(self._get(status="failed")["recordsFiltered"], 1)
        self.assertEqual(self._get(aktivitas="auth.login")["recordsFiltered"], 1)
        self.assertEqual(self._get(pengguna="bud")["recordsFiltered"], 2)
        self.assertEqual(self._get(aktivitas="tidak-ada")["recordsFiltered"], 3)  # nilai asing diabaikan
        self.assertEqual(self._get(status="failed")["recordsTotal"], 3)

    def test_filter_tanggal_inklusif(self):
        lama, baru = _buat_log(2)
        ActivityLog.objects.filter(pk=lama.pk).update(timestamp=timezone.now() - timedelta(days=10))
        hari_ini = timezone.localdate().isoformat()
        self.assertEqual(self._get(tgl_dari=hari_ini)["recordsFiltered"], 1)
        self.assertEqual(self._get(tgl_sampai=hari_ini)["recordsFiltered"], 2)
        self.assertEqual(self._get(tgl_dari="bukan-tanggal")["recordsFiltered"], 2)

    def test_urutan_whitelist(self):
        for nama in ("ani", "caca", "budi"):
            ActivityLog.objects.create(aktivitas="x", username=nama)

        def urut(d):
            return [row[1].split("<strong>")[1].split("</strong>")[0] for row in d["data"]]

        asc = self._get(**{"order[0][column]": "1", "order[0][dir]": "asc"})
        self.assertEqual(urut(asc), ["ani", "budi", "caca"])
        # kolom tak dikenal -> kembali ke urutan waktu, tanpa error
        self.assertEqual(self.client.get(self.url, {"order[0][column]": "999;DROP"}).status_code, 200)

    def test_isi_sel_di_escape(self):
        ActivityLog.objects.create(
            aktivitas="x", username="<script>alert(1)</script>", deskripsi="<b>x</b>", detail="<img src=x>",
            user_agent="\"><script>", target_id="<i>",
        )
        isi = json.dumps(self._get()["data"])
        self.assertNotIn("<script>", isi)
        self.assertNotIn("<img", isi)
        self.assertNotIn("<b>", isi)


class ResetTests(TestCase):
    def setUp(self):
        self.pakln = User.objects.create_user(username="adm.pakln", password="x", role="admin_pakln")
        self.client.force_login(self.pakln)
        self.url = reverse("pakln:log_sistem_reset")
        ActivityLog.objects.all().delete()  # force_login memicu signal login

    def test_get_ditolak(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_rentang_tidak_valid(self):
        _buat_log(3)
        r = self.client.post(self.url, {"rentang": "1; DROP"}, follow=True)
        self.assertContains(r, "tidak valid")
        self.assertEqual(ActivityLog.objects.count(), 3)

    def test_reset_semua_menyisakan_entri_audit(self):
        _buat_log(5)
        r = self.client.post(self.url, {"rentang": "semua"}, follow=True)
        self.assertContains(r, "5 baris log dihapus permanen")
        self.assertEqual(ActivityLog.objects.count(), 1)
        audit = ActivityLog.objects.get()
        self.assertEqual((audit.aktivitas, audit.username, audit.user), ("log.reset", "adm.pakln", self.pakln))

    def test_reset_hari_hanya_menghapus_yang_lama(self):
        lama, baru = _buat_log(2)
        ActivityLog.objects.filter(pk=lama.pk).update(timestamp=timezone.now() - timedelta(days=8))
        self.client.post(self.url, {"rentang": "7"})
        self.assertFalse(ActivityLog.objects.filter(pk=lama.pk).exists())
        self.assertTrue(ActivityLog.objects.filter(pk=baru.pk).exists())


class CommandTests(TestCase):
    def _jalan(self, *args, **kw):
        out = StringIO()
        call_command("bersihkan_log", *args, stdout=out, **kw)
        return out.getvalue()

    def test_wajib_salah_satu_opsi(self):
        _buat_log(2)
        with self.assertRaises(CommandError):
            self._jalan()
        with self.assertRaises(CommandError):
            self._jalan(hari=7, semua=True)
        with self.assertRaises(CommandError):
            self._jalan(hari=0)
        self.assertEqual(ActivityLog.objects.count(), 2)

    def test_dry_run_tidak_menghapus(self):
        _buat_log(4)
        self.assertIn("Akan dihapus: 4", self._jalan(semua=True, dry_run=True))
        self.assertEqual(ActivityLog.objects.count(), 4)

    def test_batch_kecil_tetap_menghapus_semua(self):
        _buat_log(7)
        self.assertIn("Dihapus: 7", self._jalan(semua=True, batch_size=2))
        self.assertEqual(ActivityLog.objects.count(), 1)  # hanya entri audit


class SignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="budi", password="rahasia123", role="pegawai")

    def test_login_logout_dan_gagal_tercatat(self):
        self.client.post("/login/", {"username": "budi", "password": "rahasia123"})
        self.client.post("/logout/")
        self.client.post("/login/", {"username": "budi", "password": "salah-banget"})
        urut = list(ActivityLog.objects.order_by("pk").values_list("aktivitas", "status", "username"))
        self.assertEqual(urut, [
            ("auth.login", "success", "budi"),
            ("auth.logout", "success", "budi"),
            ("auth.login_failed", "failed", "budi"),
        ])
        gagal = ActivityLog.objects.get(aktivitas="auth.login_failed")
        self.assertIsNone(gagal.user)
        self.assertNotIn("salah-banget", f"{gagal.detail}{gagal.deskripsi}{gagal.user_agent}")
        self.assertEqual(ActivityLog.objects.get(aktivitas="auth.login").user, self.user)
