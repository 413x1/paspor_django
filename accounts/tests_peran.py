"""Fase 3 — Role ganda (SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD §5.8)."""

import importlib
from datetime import date

from django.apps import apps
from django.test import TestCase
from django.urls import reverse

from logs.models import ActivityLog
from notifications import services as notif
from notifications.models import Notification
from paspor.models import UnitOrganisasi
from pengajuan.models import Pengajuan

from .models import PegawaiProfile, PeranUser, User


class _PeranBasis:
    """`ganda`: Pegawai (profil unit A) + Admin Unor (unit B), peran terakhir Admin Unor."""

    def setUp(self):
        self.unit_a, self.unit_b = UnitOrganisasi.objects.all()[:2]
        self.ganda = User.objects.create_user("ganda", password="x", role="admin_unor", unit_organisasi=self.unit_b)
        PegawaiProfile.objects.create(
            user=self.ganda, nip="198905102014021003", nama="Bayu Ganda", jabatan="Kasubbag",
            pangkat_golongan="III-c", unit_kerja="Dit. A", unit_organisasi=self.unit_a,
        )
        PeranUser.objects.create(user=self.ganda, role="pegawai")
        self.unor_a = User.objects.create_user("unor.a", password="x", role="admin_unor", unit_organisasi=self.unit_a)
        self.pakln = User.objects.create_user("pakln1", password="x", role="admin_pakln")

    def pengajuan(self, pegawai, unit):
        return Pengajuan.objects.create(
            pegawai=pegawai, form_saved=True, submitted=True, status=Pengajuan.Status.PROSES,
            unit_organisasi=unit, tgl_pengajuan=date.today(), maksud="Uji role ganda",
        )

    def pegawai_lain(self, unit, username="peg.lain", nip="199001012015031001"):
        user = User.objects.create_user(username, password="x", role="pegawai")
        PegawaiProfile.objects.create(
            user=user, nip=nip, nama="Pegawai Lain", jabatan="Staf", pangkat_golongan="III-a",
            unit_kerja="Dit.", unit_organisasi=unit,
        )
        return user


class PeranAktifTests(_PeranBasis, TestCase):
    def test_daftar_peran_terurut(self):
        self.assertEqual(self.ganda.daftar_peran(), ["admin_unor", "pegawai"])
        self.assertTrue(self.ganda.punya_peran("pegawai"))
        self.assertFalse(self.ganda.punya_peran("admin_pakln"))

    def test_login_memakai_peran_terakhir_lalu_ganti(self):
        self.client.force_login(self.ganda)
        self.assertEqual(self.client.get(reverse("unor:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("pegawai:beranda")).status_code, 403)

        resp = self.client.post(reverse("ganti_peran"), {"peran": "pegawai"})
        self.assertRedirects(resp, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("pegawai:beranda")).status_code, 200)
        self.assertEqual(self.client.get(reverse("unor:dashboard")).status_code, 403)
        # Peran yang dipilih menjadi default login berikutnya.
        self.assertEqual(User.objects.get(pk=self.ganda.pk).role, "pegawai")
        self.assertTrue(ActivityLog.objects.filter(aktivitas=ActivityLog.Aktivitas.GANTI_PERAN).exists())

    def test_prioritas_bila_peran_terakhir_tidak_dimiliki(self):
        User.objects.filter(pk=self.ganda.pk).update(role="admin_bko")
        self.client.force_login(User.objects.get(pk=self.ganda.pk))
        self.assertEqual(self.client.get(reverse("unor:dashboard")).status_code, 200)

    def test_switcher_hanya_untuk_role_ganda(self):
        self.client.force_login(self.ganda)
        self.assertContains(self.client.get(reverse("unor:dashboard")), "Masuk sebagai:")
        self.client.force_login(self.unor_a)
        self.assertNotContains(self.client.get(reverse("unor:dashboard")), "Masuk sebagai:")

    def test_ganti_ke_peran_yang_tidak_dimiliki_ditolak(self):
        self.client.force_login(self.ganda)
        self.client.post(reverse("ganti_peran"), {"peran": "admin_pakln"})
        self.assertEqual(self.client.get(reverse("pakln:dashboard")).status_code, 403)
        self.assertEqual(User.objects.get(pk=self.ganda.pk).role, "admin_unor")

    def test_ganti_peran_wajib_post(self):
        self.client.force_login(self.ganda)
        self.assertEqual(self.client.get(reverse("ganti_peran"), {"peran": "pegawai"}).status_code, 405)

    def test_save_tidak_menyimpan_peran_aktif(self):
        user = User.objects.get(pk=self.ganda.pk)
        user._role_db = user.role
        user.role = "pegawai"
        user.first_name = "Bayu"
        user.save()
        self.assertEqual(user.role, "pegawai")  # tetap di memori
        segar = User.objects.get(pk=self.ganda.pk)
        self.assertEqual(segar.role, "admin_unor")
        self.assertEqual(segar.first_name, "Bayu")

    def test_save_request_user_lewat_view_tidak_mengubah_role(self):
        self.client.force_login(self.ganda)
        self.client.post(reverse("ganti_peran"), {"peran": "pegawai"})
        self.client.post(reverse("profil"), {"aksi": "ubah_username", "username": "ganda.baru"})
        segar = User.objects.get(pk=self.ganda.pk)
        self.assertEqual(segar.username, "ganda.baru")
        self.assertEqual(segar.role, "pegawai")


class CakupanUnitTests(_PeranBasis, TestCase):
    def test_admin_unor_melihat_unit_yang_dikelola(self):
        p_b = self.pengajuan(self.pegawai_lain(self.unit_b), self.unit_b)
        p_a = self.pengajuan(self.pegawai_lain(self.unit_a, "peg.a", "199001012015031002"), self.unit_a)
        self.client.force_login(self.ganda)
        self.assertEqual(self.client.get(reverse("unor:preview", args=[p_b.kode])).status_code, 200)
        self.assertEqual(self.client.get(reverse("unor:preview", args=[p_a.kode])).status_code, 404)
        self.assertEqual(self.ganda.unit_admin_id(), self.unit_b.pk)

    def test_tidak_bisa_memproses_pengajuan_sendiri(self):
        PeranUser.objects.filter(user=self.ganda, role="admin_unor").update(unit_organisasi=self.unit_a)
        p = self.pengajuan(self.ganda, self.unit_a)
        self.client.force_login(self.ganda)
        resp = self.client.post(reverse("unor:preview", args=[p.kode]), {"kembalikan": "1", "catatan": "x"})
        self.assertEqual(resp.status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.status, Pengajuan.Status.PROSES)
        # Halaman tetap bisa dibuka, dengan penanda "Pengajuan Anda".
        self.assertContains(self.client.get(reverse("unor:preview", args=[p.kode])), "Pengajuan Anda.")

        # Admin Unor lain di unit yang sama dapat memprosesnya.
        self.client.force_login(self.unor_a)
        resp = self.client.post(reverse("unor:preview", args=[p.kode]), {"kembalikan": "1", "catatan": "Lengkapi"})
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.status, Pengajuan.Status.BELUM)

    def test_pengajuan_sendiri_sebagai_pegawai_tetap_boleh(self):
        p = self.pengajuan(self.ganda, self.unit_a)
        self.client.force_login(self.ganda)
        self.client.post(reverse("ganti_peran"), {"peran": "pegawai"})
        self.assertEqual(self.client.get(reverse("pegawai:monitor_progres", args=[p.kode])).status_code, 200)


class NotifikasiPeranTests(_PeranBasis, TestCase):
    def test_notifikasi_admin_unor_untuk_unit_yang_dikelola(self):
        p = self.pengajuan(self.pegawai_lain(self.unit_b), self.unit_b)
        notif.notify_submit_unor(p)
        n = Notification.objects.get(recipient=self.ganda)
        self.assertEqual(n.untuk_peran, "admin_unor")
        self.assertFalse(Notification.objects.filter(recipient=self.unor_a).exists())

    def test_admin_unor_data_lama_tanpa_unit_di_peranuser(self):
        PeranUser.objects.filter(user=self.unor_a, role="admin_unor").update(unit_organisasi=None)
        p = self.pengajuan(self.pegawai_lain(self.unit_a), self.unit_a)
        notif.notify_submit_unor(p)
        self.assertTrue(Notification.objects.filter(recipient=self.unor_a).exists())

    def test_buka_notifikasi_memindahkan_peran(self):
        p = self.pengajuan(self.pegawai_lain(self.unit_b), self.unit_b)
        notif.notify_submit_unor(p)
        n = Notification.objects.get(recipient=self.ganda)
        self.client.force_login(self.ganda)
        self.client.post(reverse("ganti_peran"), {"peran": "pegawai"})
        resp = self.client.get(reverse("notifications:go", args=[n.pk]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.session["peran_aktif"], "admin_unor")

    def test_tidak_ada_notifikasi_ganda_untuk_peran_yang_sama(self):
        PeranUser.objects.create(user=self.pakln, role="admin_bpsdm")
        PeranUser.objects.create(user=self.pakln, role="admin_bko")
        p = self.pengajuan(self.pegawai_lain(self.unit_b), self.unit_b)
        notif.notify_bko_ditutup(p, "Ditutup")  # penerima: semua kelompok kecuali BKO
        self.assertEqual(Notification.objects.filter(recipient=self.pakln).count(), 1)

    def test_role_ganda_mendapat_notifikasi_per_peran(self):
        p = self.pengajuan(self.ganda, self.unit_b)
        notif.notify_complete_pkln(p)  # ke pegawai pemilik + Admin Unor unit B
        peran = set(Notification.objects.filter(recipient=self.ganda).values_list("untuk_peran", flat=True))
        self.assertEqual(peran, {"pegawai", "admin_unor"})


class KelolaPeranTests(_PeranBasis, TestCase):
    def data_peran(self, **centang):
        data = {"aksi": "simpan_peran"}
        for role, nilai in centang.items():
            if nilai:
                data[role] = "on"
        return data

    def test_halaman_edit_user_tampil(self):
        self.client.force_login(self.pakln)
        for user in (self.ganda, self.pakln, self.unor_a):
            with self.subTest(user=user.username):
                resp = self.client.get(reverse("pakln:edit_user", args=[user.pk]))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, "Simpan Peran")

    def test_cabut_admin_unor_jatuh_ke_pegawai(self):
        self.client.force_login(self.pakln)
        resp = self.client.post(reverse("pakln:edit_user", args=[self.ganda.pk]), self.data_peran())
        self.assertEqual(resp.status_code, 302)
        peran = PeranUser.objects.get(user=self.ganda, role="admin_unor")
        self.assertFalse(peran.is_active)  # baris tetap ada untuk jejak audit
        self.assertEqual(User.objects.get(pk=self.ganda.pk).role, "pegawai")
        self.assertTrue(ActivityLog.objects.filter(aktivitas=ActivityLog.Aktivitas.PERAN_DICABUT).exists())

        self.client.force_login(self.ganda)
        self.assertEqual(self.client.get(reverse("unor:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("pegawai:beranda")).status_code, 200)

    def test_cabut_peran_yang_sedang_aktif_di_sesi_lain(self):
        self.client.force_login(self.ganda)
        self.assertEqual(self.client.get(reverse("unor:dashboard")).status_code, 200)
        PeranUser.objects.filter(user=self.ganda, role="admin_unor").update(is_active=False)
        self.assertEqual(self.client.get(reverse("unor:dashboard")).status_code, 403)
        self.assertEqual(self.client.session["peran_aktif"], "pegawai")

    def test_beri_admin_unor_wajib_unit(self):
        pegawai = self.pegawai_lain(self.unit_a)
        self.client.force_login(self.pakln)
        resp = self.client.post(reverse("pakln:edit_user", args=[pegawai.pk]), self.data_peran(admin_unor=True))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(pegawai.peran_list.filter(role="admin_unor").exists())

        data = self.data_peran(admin_unor=True, admin_bko=True)
        data["unit_admin_unor"] = self.unit_b.pk
        resp = self.client.post(reverse("pakln:edit_user", args=[pegawai.pk]), data)
        self.assertEqual(resp.status_code, 302)
        segar = User.objects.get(pk=pegawai.pk)
        self.assertEqual(segar.daftar_peran(), ["admin_unor", "admin_bko", "pegawai"])
        self.assertEqual(segar.unit_admin_id(), self.unit_b.pk)
        self.assertEqual(PeranUser.objects.get(user=pegawai, role="admin_unor").diberikan_oleh, self.pakln)

    def test_tidak_bisa_mencabut_pakln_sendiri(self):
        self.client.force_login(self.pakln)
        resp = self.client.post(reverse("pakln:edit_user", args=[self.pakln.pk]), self.data_peran(admin_bko=True))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PeranUser.objects.get(user=self.pakln, role="admin_pakln").is_active)

    def test_filter_role_daftar_user(self):
        self.client.force_login(self.pakln)
        resp = self.client.get(reverse("pakln:users_data"), {"role": "pegawai"})
        baris = resp.json()["data"]
        self.assertEqual(len(baris), 1)
        self.assertIn("Admin Unor", baris[0][2])
        self.assertIn("Pegawai", baris[0][2])


class MigrasiPeranUserTests(TestCase):
    def test_data_migration_satu_peranuser_per_user(self):
        unit = UnitOrganisasi.objects.first()
        unor = User.objects.create_user("unor.lama", password="x", role="admin_unor", unit_organisasi=unit)
        pegawai = User.objects.create_user("peg.lama", password="x", role="pegawai")
        PeranUser.objects.all().delete()

        migrasi = importlib.import_module("accounts.migrations.0010_isi_peranuser")
        migrasi.isi_peranuser(apps, None)
        migrasi.isi_peranuser(apps, None)  # idempoten

        self.assertEqual(list(unor.peran_list.values_list("role", "unit_organisasi_id")), [("admin_unor", unit.pk)])
        self.assertEqual(list(pegawai.peran_list.values_list("role", "unit_organisasi_id")), [("pegawai", None)])
