"""Rekap Pelaporan PDLN: agregasi per Unit Organisasi, daftar detail, filter periode, dan akses per role."""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from . import report
from .models import LaporanPdln, Pengajuan
from .tests_pdln import _Basis

L = LaporanPdln.Status
CUTOFF = date(2026, 8, 28)
HARI_INI = date(2026, 10, 30)   # Jumat


class _DataRekap(_Basis):
    def pdln(self, unit, berangkat, laporan=None, status=Pengajuan.Status.SELESAI, jenis="pdln"):
        p = Pengajuan.objects.create(
            pegawai=self.pegawai, jenis_perjalanan=jenis, tipe_pdln="T1" if jenis == "pdln" else "",
            unit_organisasi=unit, tgl_berangkat=berangkat, tgl_kembali=berangkat + timedelta(days=3),
            status=status, tgl_pengajuan=berangkat - timedelta(days=20),
        )
        if laporan:
            LaporanPdln.objects.create(pengajuan=p, status=laporan, diunggah_oleh=self.pegawai)
        return p

    def setUp(self):
        super().setUp()
        # Unit A: 5 data wajib lapor — 2 sebelum cut-off (Data Awal), 3 sesudahnya. Laporan: disetujui, menunggu,
        # dikembalikan (terkumpul = 3), draft dan tanpa laporan (belum = 2).
        self.pdln(self.unor, date(2026, 3, 1), L.DISETUJUI)
        self.pdln(self.unor, date(2026, 6, 1), L.MENUNGGU)
        self.pdln(self.unor, date(2026, 9, 10), L.DRAFT)
        self.pdln(self.unor, date(2026, 10, 5), L.DIKEMBALIKAN)
        self.pdln(self.unor, date(2026, 10, 20))
        # Tidak ikut dihitung: belum selesai diproses dan perjalanan Non-Kedinasan.
        self.pdln(self.unor, date(2026, 10, 1), status=Pengajuan.Status.PROSES)
        self.pdln(self.unor, date(2026, 10, 2), jenis="nondinas")
        # Unit B: 1 data sesudah cut-off, belum lapor.
        self.pdln(self.unor_lain, date(2026, 7, 1))

    def baris(self, data, unit):
        return next(b for b in data["ringkasan"] if b["unit"].startswith(f"{unit.code} "))


class DataRekapPelaporanTests(_DataRekap, TestCase):
    def test_agregasi_per_unit_organisasi(self):
        data = report.data_rekap_pelaporan(self.admin_pakln, sampai=HARI_INI, cutoff=CUTOFF)
        a = self.baris(data, self.unor)
        self.assertEqual((a["awal"], a["total"], a["terkumpul"], a["belum"]), (2, 5, 3, 2))
        b = self.baris(data, self.unor_lain)
        self.assertEqual((b["awal"], b["total"], b["terkumpul"], b["belum"]), (1, 1, 0, 1))

    def test_semua_unit_tampil_dan_grand_total_sama_dengan_jumlah_baris(self):
        from paspor.models import UnitOrganisasi
        data = report.data_rekap_pelaporan(self.admin_pakln, sampai=HARI_INI, cutoff=CUTOFF)
        self.assertEqual(len(data["ringkasan"]), UnitOrganisasi.objects.count())
        for kunci in ("awal", "total", "terkumpul", "belum"):
            self.assertEqual(data["grand_total"][kunci], sum(b[kunci] for b in data["ringkasan"]))
        self.assertEqual(data["grand_total"]["total"], 6)
        for b in data["ringkasan"]:
            self.assertEqual(b["belum"], b["total"] - b["terkumpul"])

    def test_laporan_draft_dihitung_belum_kumpul(self):
        data = report.data_rekap_pelaporan(self.admin_pakln, sampai=HARI_INI, cutoff=CUTOFF)
        a = self.baris(data, self.unor)
        # 5 data, 4 punya baris laporan, tetapi satu masih draft → terkumpul 3.
        self.assertEqual(a["terkumpul"], 3)

    def test_periode_membatasi_data_periode_tetapi_bukan_data_awal(self):
        data = report.data_rekap_pelaporan(
            self.admin_pakln, dari=date(2026, 10, 1), sampai=date(2026, 10, 31), cutoff=CUTOFF)
        a = self.baris(data, self.unor)
        self.assertEqual((a["awal"], a["total"], a["terkumpul"]), (2, 2, 1))

    def test_admin_unor_hanya_melihat_unitnya(self):
        data = report.data_rekap_pelaporan(self.admin_unor, sampai=HARI_INI, cutoff=CUTOFF)
        self.assertEqual([b["unit"].split()[0] for b in data["ringkasan"]], [self.unor.code])
        self.assertEqual(len(data["detail"]), 5)
        self.assertEqual({r["unit"] for r in data["detail"]}, {self.unor.name})

    def test_detail_urut_per_unit_lalu_tanggal_berangkat_dengan_subtotal(self):
        data = report.data_rekap_pelaporan(self.admin_pakln, sampai=HARI_INI, cutoff=CUTOFF)
        detail = data["detail"]
        self.assertEqual([r["no"] for r in detail], list(range(1, 7)))
        urut = [(u.code, u.name) for u in sorted([self.unor, self.unor_lain], key=lambda u: u.code)]
        self.assertEqual([r["unit"] for r in detail if r["unit"] in {n for _, n in urut}][0], urut[0][1])
        for unit in (self.unor, self.unor_lain):
            tgl = [r["tgl_berangkat"] for r in detail if r["unit"] == unit.name]
            self.assertEqual(tgl, sorted(tgl))
        subtotal = {g["unit"]: (g["total"], g["sudah"]) for g in data["grup"]}
        self.assertEqual(subtotal[self.unor.name], (5, 3))
        self.assertEqual(subtotal[self.unor_lain.name], (1, 0))

    def test_isi_baris_detail(self):
        data = report.data_rekap_pelaporan(self.admin_unor, sampai=HARI_INI, cutoff=CUTOFF)
        pertama = data["detail"][0]
        self.assertEqual(pertama["nama"], "Andra")
        self.assertEqual(pertama["jabatan"], "Kasi")
        self.assertEqual(pertama["tgl_berangkat"], date(2026, 3, 1))
        self.assertTrue(pertama["sudah"])
        self.assertIsNotNone(pertama["tgl_upload"])
        belum = data["detail"][-1]
        self.assertFalse(belum["sudah"])
        self.assertIsNone(belum["tgl_upload"])


class RentangPeriodeTests(TestCase):
    def test_tanpa_preset_kumulatif_sampai_hari_ini(self):
        self.assertEqual(report.rentang_periode({}, HARI_INI), ("", None, HARI_INI))

    def test_minggu_ini_senin_sampai_minggu(self):
        self.assertEqual(report.rentang_periode({"periode": "minggu"}, HARI_INI),
                         ("minggu", date(2026, 10, 26), date(2026, 11, 1)))

    def test_bulan_ini_dan_tahun_ini(self):
        self.assertEqual(report.rentang_periode({"periode": "bulan"}, HARI_INI),
                         ("bulan", date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(report.rentang_periode({"periode": "tahun"}, HARI_INI),
                         ("tahun", date(2026, 1, 1), date(2026, 12, 31)))

    def test_kustom_membaca_tanggal_dan_menukar_bila_terbalik(self):
        self.assertEqual(
            report.rentang_periode({"periode": "kustom", "dari": "2026-10-10", "sampai": "2026-10-01"}, HARI_INI),
            ("kustom", date(2026, 10, 1), date(2026, 10, 10)))

    def test_kustom_dengan_tanggal_tidak_valid_diabaikan(self):
        self.assertEqual(report.rentang_periode({"periode": "kustom", "dari": "bukan-tanggal"}, HARI_INI),
                         ("kustom", None, None))

    def test_preset_tidak_dikenal_dianggap_tanpa_preset(self):
        self.assertEqual(report.rentang_periode({"periode": "asal"}, HARI_INI), ("", None, HARI_INI))


class HalamanRekapPelaporanTests(_DataRekap, TestCase):
    def test_belum_login_diarahkan_ke_login(self):
        resp = self.client.get(reverse("pakln:rekap_pelaporan_pdln"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_pegawai_ditolak(self):
        self.assertEqual(self.get(self.pegawai, "pakln:rekap_pelaporan_pdln").status_code, 403)

    def test_halaman_tampil_untuk_setiap_role_admin(self):
        for user, ns in ((self.admin_unor, "unor"), (self.admin_bpsdm, "bpsdm"),
                         (self.admin_bko, "bko"), (self.admin_pakln, "pakln")):
            resp = self.get(user, f"{ns}:rekap_pelaporan_pdln")
            self.assertEqual(resp.status_code, 200, ns)
            self.assertContains(resp, "Data Telah Kumpul Laporan PDLN")
            self.assertContains(resp, "Grand Total")

    def test_halaman_memuat_dropdown_periode_dan_tabel_detail(self):
        resp = self.get(self.admin_pakln, "pakln:rekap_pelaporan_pdln", "?periode=bulan")
        self.assertContains(resp, 'name="periode"')
        self.assertContains(resp, 'id="tabelDetail"')
        self.assertEqual(resp.context["periode"], "bulan")

    def test_sidebar_memuat_grup_rekap_dengan_empat_item(self):
        resp = self.get(self.admin_pakln, "pakln:rekap_pelaporan_pdln")
        for teks in ("Rekap data", "Rekap Progres PDLN", "Rekap Progres ILN", "Rekap Pelaporan PDLN"):
            self.assertContains(resp, teks)
        self.assertContains(resp, 'data-sidebar-group')

    def test_progres_pdln_dan_iln_memfilter_rekap_berdasarkan_jenis(self):
        resp = self.get(self.admin_pakln, "pakln:rekap", "?jenis=nondinas")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["f"]["jenis"], "nondinas")
        self.assertEqual(resp.context["total"], 1)
