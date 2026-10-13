"""Pengkodean pengajuan — wiki/instructions/PENGKODEAN_AJUAN.MD."""

from datetime import date
from unittest import mock

from django.test import TestCase

from accounts.models import PegawaiProfile, User
from paspor.models import UnitOrganisasi

from .models import Pengajuan


class PengkodeanPengajuanTests(TestCase):
    def setUp(self):
        self.unor = UnitOrganisasi.objects.get(code="01")
        self.unor_lain = UnitOrganisasi.objects.exclude(code="01").first()
        self.pegawai = self._pegawai("peg1", self.unor)

    def _pegawai(self, username, unor):
        user = User.objects.create_user(username, password="x", role="pegawai")
        PegawaiProfile.objects.create(
            user=user, nip=username, nama=username, jabatan="Staf", pangkat_golongan="III-a",
            unit_kerja="Uji", unit_organisasi=unor,
        )
        return user

    def buat(self, tanggal, tipe="", pegawai=None):
        jenis = "pdln" if tipe else "nondinas"
        with mock.patch("pengajuan.models.timezone.localdate", return_value=tanggal):
            return Pengajuan.objects.create(pegawai=pegawai or self.pegawai, jenis_perjalanan=jenis, tipe_pdln=tipe).kode

    def test_format_non_dinas_dan_tiap_tipe_pdln(self):
        hari = date(2026, 10, 7)
        self.assertEqual(self.buat(hari), "PLN01-071026-001")
        self.assertEqual(self.buat(hari, "T1"), "PDLN01-1-071026-001")
        self.assertEqual(self.buat(hari, "T2P"), "PDLN01-2A-071026-001")
        self.assertEqual(self.buat(hari, "T2L"), "PDLN01-2B-071026-001")
        self.assertEqual(self.buat(hari, "T3"), "PDLN01-3-071026-001")

    def test_nomor_berlanjut_antar_hari_dan_rotasi_tahunan(self):
        self.assertEqual(self.buat(date(2026, 10, 7)), "PLN01-071026-001")
        self.assertEqual(self.buat(date(2026, 10, 7)), "PLN01-071026-002")
        self.assertEqual(self.buat(date(2026, 10, 8)), "PLN01-081026-003")
        self.assertEqual(self.buat(date(2026, 12, 31)), "PLN01-311226-004")
        self.assertEqual(self.buat(date(2027, 1, 2)), "PLN01-020127-001")
        self.assertEqual(self.buat(date(2027, 1, 3), "T2P"), "PDLN01-2A-030127-001")

    def test_urutan_terpisah_per_jenis_tipe_dan_unor(self):
        hari = date(2026, 10, 7)
        self.buat(hari)
        self.buat(hari, "T2P")
        self.assertEqual(self.buat(hari), "PLN01-071026-002")
        self.assertEqual(self.buat(hari, "T2P"), "PDLN01-2A-071026-002")
        self.assertEqual(self.buat(hari, "T2L"), "PDLN01-2B-071026-001")
        lain = self._pegawai("peg2", self.unor_lain)
        self.assertEqual(self.buat(hari, pegawai=lain), f"PLN{self.unor_lain.code}-071026-001")

    def test_padding_tiga_digit_dan_lebih_dari_999(self):
        Pengajuan.objects.create(pegawai=self.pegawai, kode="PLN01-010126-009")
        self.assertEqual(self.buat(date(2026, 3, 1)), "PLN01-010326-010")
        Pengajuan.objects.create(pegawai=self.pegawai, kode="PDLN01-2A-010126-999")
        kode = self.buat(date(2026, 3, 1), "T2P")
        self.assertEqual(kode, "PDLN01-2A-010326-1000")
        self.assertLessEqual(len(kode), Pengajuan._meta.get_field("kode").max_length)

    def test_kode_lama_tidak_ikut_dihitung(self):
        for kode in ("PSP-2026-0142", "PDLN-2026-T1-0005", "PDLN01-1-071025-050"):
            Pengajuan.objects.create(pegawai=self.pegawai, kode=kode)
        self.assertEqual(self.buat(date(2026, 10, 7), "T1"), "PDLN01-1-071026-001")

    def test_kode_tidak_berubah_saat_disimpan_ulang(self):
        p = Pengajuan.objects.create(pegawai=self.pegawai, jenis_perjalanan="pdln", tipe_pdln="T1")
        kode = p.kode
        p.tipe_pdln = "T3"
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.kode, kode)
