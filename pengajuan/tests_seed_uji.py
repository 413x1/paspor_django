"""Seed data uji (manage.py seed_pengajuan_uji): 10 pengajuan per pegawai dengan
status alur & pelaporan PDLN bervariasi, dan halaman yang memakainya tetap terbuka."""

import io
from collections import Counter

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from . import report
from .models import LaporanPdln, Pengajuan, RiwayatPengajuan

S = Pengajuan.Status
L = LaporanPdln.Status
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}


def seed(*args):
    call_command("seed_pengajuan_uji", *args, stdout=io.StringIO())


@override_settings(STORAGES=_STORAGES_MEMORI)
class SeedPengajuanUjiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data", stdout=io.StringIO())
        call_command("seed_pegawai_org_units", stdout=io.StringIO())

    def setUp(self):
        seed()
        self.uji = Pengajuan.objects.filter(maksud__startswith="[UJI]")

    def test_sepuluh_pengajuan_per_pegawai(self):
        pegawai = User.objects.filter(peran_list__role=User.Role.PEGAWAI, peran_list__is_active=True).distinct()
        jumlah = Counter(self.uji.values_list("pegawai__username", flat=True))
        self.assertEqual(set(jumlah), set(pegawai.values_list("username", flat=True)))
        self.assertEqual(set(jumlah.values()), {10})

    def test_status_dan_pelaporan_bervariasi(self):
        self.assertEqual(set(self.uji.values_list("status", flat=True)), set(S.values))
        self.assertEqual(set(self.uji.values_list("tipe_pdln", flat=True)), {"", "T1", "T2P", "T2L", "T3"})
        self.assertEqual(
            set(LaporanPdln.objects.filter(pengajuan__in=self.uji).values_list("status", flat=True)), set(L.values),
        )
        pelaporan = Counter(report.status_pelaporan(p) for p in self.uji.select_related("laporan_pdln"))
        self.assertGreater(pelaporan["Belum Melapor (Terlambat)"], 0)
        # T2P studi masih berjalan: selesai diproses, belum pulang, belum ada laporan.
        self.assertTrue(self.uji.filter(
            tipe_pdln="T2P", status=S.SELESAI, laporan_pdln__isnull=True, tgl_kembali__gt=report.timezone.localdate(),
        ).exists())

    def test_data_konsisten(self):
        kode = list(self.uji.values_list("kode", flat=True))
        self.assertEqual(len(kode), len(set(kode)))
        for p in self.uji.exclude(status=S.BELUM, tgl_pengajuan__isnull=True):
            self.assertTrue(p.riwayat.exists(), p.kode)
        self.assertFalse(self.uji.filter(status=S.SELESAI, tgl_selesai__isnull=True).exists())
        self.assertFalse(self.uji.filter(tipe_pdln="T2P", status=S.SELESAI).exclude(status_bko="diunggah").exists())
        # Laporan yang sudah dilaporkan selalu punya berkas (halaman verifikasi menampilkannya).
        self.assertFalse(LaporanPdln.objects.filter(pengajuan__in=self.uji).exclude(status=L.DRAFT).filter(file="").exists())
        self.assertTrue(RiwayatPengajuan.objects.filter(pengajuan__in=self.uji, aksi="laporan_disetujui").exists())

    def test_idempoten_dan_hapus(self):
        jumlah = self.uji.count()
        seed()
        self.assertEqual(self.uji.count(), jumlah)
        seed("--hapus")
        self.assertFalse(self.uji.exists())
        self.assertTrue(Pengajuan.objects.filter(kode="PSP-2026-0091").exists())  # data non-uji tetap
        seed("--hapus", "--buat")
        self.assertEqual(self.uji.count(), jumlah)

    def test_halaman_terbuka(self):
        self.client.force_login(User.objects.get(username="andra.wibisono"))
        for nama in ("pegawai:beranda", "pegawai:pelaporan"):
            self.assertEqual(self.client.get(reverse(nama)).status_code, 200, nama)
        # Pengajuan berstatus belum diajukan diarahkan ke formulir, bukan ke Monitor Progres.
        for p in self.uji.filter(pegawai__username="andra.wibisono").exclude(status=S.BELUM):
            self.assertEqual(self.client.get(reverse("pegawai:monitor_progres", args=[p.kode])).status_code, 200, p.kode)
            if p.is_pdln and p.status == S.SELESAI:
                self.assertEqual(self.client.get(reverse("pegawai:laporan_form", args=[p.kode])).status_code, 200)

        self.client.force_login(User.objects.get(username="admin.pakln"))
        for nama in ("pakln:dashboard", "pakln:pelaporan", "pakln:rekap_pelaporan_pdln"):
            self.assertEqual(self.client.get(reverse(nama)).status_code, 200, nama)
