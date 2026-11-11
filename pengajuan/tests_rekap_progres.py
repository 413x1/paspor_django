"""Rekap Progres PDLN: periode berdasarkan tanggal terakhir diperbarui, tanggal tiap tahap, dan akses per role."""

from datetime import date, datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import report
from .models import DokumenGenerateLog, DokumenPakln, Pengajuan
from .tests_pdln import _Basis

HARI_INI = date(2026, 10, 30)   # Jumat


def waktu(tgl, jam=12):
    return timezone.make_aware(datetime(tgl.year, tgl.month, tgl.day, jam, 0))


class _DataProgres(_Basis):
    def pdln(self, diperbarui, negara=None, jenis="pdln", unit=None):
        p = Pengajuan.objects.create(
            pegawai=self.pegawai, jenis_perjalanan=jenis, tipe_pdln="T1" if jenis == "pdln" else "",
            unit_organisasi=unit or self.unor, tgl_berangkat=date(2026, 11, 20), tgl_kembali=date(2026, 11, 25),
            status=Pengajuan.Status.SELESAI, tgl_pengajuan=date(2026, 9, 1),
        )
        if negara:
            p.tujuan_negara.set([negara])
        # `updated_at` auto_now: nilai uji diset lewat update() agar tidak tertimpa.
        Pengajuan.objects.filter(pk=p.pk).update(updated_at=waktu(diperbarui))
        return Pengajuan.objects.get(pk=p.pk)

    def dokumen(self, p, jenis, tgl):
        d = DokumenPakln.objects.create(pengajuan=p, jenis=jenis, file="uji.pdf")
        DokumenPakln.objects.filter(pk=d.pk).update(uploaded_at=waktu(tgl))

    def generate(self, p, jenis, tgl):
        g = DokumenGenerateLog.objects.create(jenis=jenis, file="uji.pdf", dibuat_oleh=self.admin_pakln)
        g.pengajuan.add(p)
        DokumenGenerateLog.objects.filter(pk=g.pk).update(created_at=waktu(tgl))


class RentangProgresTests(TestCase):
    def test_default_bulan_berjalan(self):
        self.assertEqual(report.rentang_progres({}, HARI_INI),
                         ("bulanan", HARI_INI, date(2026, 10, 1), date(2026, 10, 31)))

    def test_harian_satu_tanggal(self):
        self.assertEqual(report.rentang_progres({"mode": "harian", "tanggal": "2026-10-10"}, HARI_INI),
                         ("harian", date(2026, 10, 10), date(2026, 10, 10), date(2026, 10, 10)))

    def test_mingguan_senin_sampai_minggu_pada_pekan_tanggal_dipilih(self):
        _, _, dari, sampai = report.rentang_progres({"mode": "mingguan", "tanggal": "2026-10-14"}, HARI_INI)
        self.assertEqual((dari, sampai), (date(2026, 10, 12), date(2026, 10, 18)))
        self.assertEqual((dari.weekday(), sampai.weekday()), (0, 6))

    def test_tahunan_dan_bulanan_di_akhir_tahun(self):
        self.assertEqual(report.rentang_progres({"mode": "tahunan", "tanggal": "2026-06-15"}, HARI_INI)[2:],
                         (date(2026, 1, 1), date(2026, 12, 31)))
        self.assertEqual(report.rentang_progres({"mode": "bulanan", "tanggal": "2026-12-05"}, HARI_INI)[2:],
                         (date(2026, 12, 1), date(2026, 12, 31)))

    def test_mode_atau_tanggal_tidak_valid_kembali_ke_default(self):
        mode, acuan, dari, sampai = report.rentang_progres({"mode": "asal", "tanggal": "bukan-tanggal"}, HARI_INI)
        self.assertEqual((mode, acuan, dari, sampai), ("bulanan", HARI_INI, date(2026, 10, 1), date(2026, 10, 31)))


class QuerysetProgresTests(_DataProgres, TestCase):
    def test_filter_berdasarkan_tanggal_terakhir_diperbarui_bukan_tanggal_pembuatan(self):
        dalam = self.pdln(date(2026, 10, 10))
        self.pdln(date(2026, 9, 30))
        self.pdln(date(2026, 11, 1))
        qs = report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(list(qs), [dalam])

    def test_batas_awal_dan_akhir_rentang_termasuk(self):
        awal = self.pdln(date(2026, 10, 1))
        akhir = self.pdln(date(2026, 10, 31))
        qs = report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
        self.assertCountEqual(list(qs), [awal, akhir])

    def test_harian_hanya_tanggal_itu(self):
        p = self.pdln(date(2026, 10, 10))
        self.pdln(date(2026, 10, 11))
        qs = report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 10), date(2026, 10, 10))
        self.assertEqual(list(qs), [p])

    def test_hanya_pdln_non_kedinasan_tidak_ikut(self):
        self.pdln(date(2026, 10, 10), jenis="nondinas")
        self.assertEqual(list(report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))), [])

    def test_admin_unor_hanya_unitnya(self):
        sendiri = self.pdln(date(2026, 10, 10))
        self.pdln(date(2026, 10, 10), unit=self.unor_lain)
        qs = report.queryset_progres_pdln(self.admin_unor, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(list(qs), [sendiri])


class TahapProgresTests(_DataProgres, TestCase):
    def tahap(self, p):
        qs = report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
        return report.tanggal_tahap_progres(qs.get(pk=p.pk))

    def test_tanggal_tiap_tahap_dari_dokumen_dan_log_generate(self):
        p = self.pdln(date(2026, 10, 20), negara=self.jepang)
        self.generate(p, DokumenGenerateLog.Jenis.ND_KABAG, date(2026, 10, 11))
        self.generate(p, DokumenGenerateLog.Jenis.ND_KARO, date(2026, 10, 12))
        self.dokumen(p, DokumenPakln.Jenis.SP_SETNEG, date(2026, 10, 13))
        self.dokumen(p, DokumenPakln.Jenis.PASPOR_DINAS, date(2026, 10, 14))
        self.dokumen(p, DokumenPakln.Jenis.VISA, date(2026, 10, 15))
        self.assertEqual(self.tahap(p), {
            "kabag": date(2026, 10, 11), "karo": date(2026, 10, 12), "setneg": date(2026, 10, 13),
            "kemlu": date(2026, 10, 14), "visa": date(2026, 10, 15),
        })

    def test_tahap_belum_dilalui_kosong(self):
        p = self.pdln(date(2026, 10, 20), negara=self.jepang)
        self.assertEqual(self.tahap(p), {"kabag": None, "karo": None, "setneg": None, "kemlu": None, "visa": None})

    def test_negara_tanpa_visa_ditandai_bebas_visa(self):
        p = self.pdln(date(2026, 10, 20), negara=self.singapura)
        self.assertEqual(self.tahap(p)["visa"], "Bebas Visa")

    def test_negara_wajib_visa_tanpa_dokumen_kosong_dan_dengan_dokumen_bertanggal(self):
        p = self.pdln(date(2026, 10, 20), negara=self.jepang)
        self.assertIsNone(self.tahap(p)["visa"])
        self.dokumen(p, DokumenPakln.Jenis.VISA, date(2026, 10, 18))
        self.assertEqual(self.tahap(p)["visa"], date(2026, 10, 18))

    def test_generate_berulang_memakai_tanggal_pertama(self):
        p = self.pdln(date(2026, 10, 20), negara=self.jepang)
        self.generate(p, DokumenGenerateLog.Jenis.ND_KABAG, date(2026, 10, 15))
        self.generate(p, DokumenGenerateLog.Jenis.ND_KABAG, date(2026, 10, 9))
        self.assertEqual(self.tahap(p)["kabag"], date(2026, 10, 9))

    def test_baris_progres_memuat_nama_negara_unit_dan_status(self):
        p = self.pdln(date(2026, 10, 20), negara=self.jepang)
        qs = report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
        baris = list(report.baris_progres_pdln(qs))
        self.assertEqual(len(baris), 1)
        b = baris[0]
        self.assertEqual(b["no_surat"], p.kode)
        self.assertEqual(b["nama_negara"], "Andra ke Jepang Uji")
        self.assertEqual(b["unit"], self.unor.alias)
        self.assertEqual((b["status"], b["status_kode"]), ("Selesai", "selesai"))
        self.assertEqual(b["tanggal"], date(2026, 9, 1))

    def test_tidak_ada_n_plus_1_query(self):
        for hari in range(10, 16):
            p = self.pdln(date(2026, 10, hari), negara=self.jepang)
            self.dokumen(p, DokumenPakln.Jenis.SP_SETNEG, date(2026, 10, 12))
            self.generate(p, DokumenGenerateLog.Jenis.ND_KABAG, date(2026, 10, 11))
        # 4 query tetap berapa pun jumlah baris: pengajuan (+ join), negara, dokumen PAKLN, log generate.
        with self.assertNumQueries(4):
            qs = report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
            self.assertEqual(len(list(report.baris_progres_pdln(qs))), 6)


class HalamanRekapProgresTests(_DataProgres, TestCase):
    def test_belum_login_diarahkan_ke_login(self):
        resp = self.client.get(reverse("pakln:rekap_progres_pdln"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
        self.assertEqual(self.client.get(reverse("pakln:rekap_progres_pdln_data")).status_code, 302)

    def test_pegawai_ditolak_di_halaman_dan_data(self):
        self.assertEqual(self.get(self.pegawai, "pakln:rekap_progres_pdln").status_code, 403)
        self.assertEqual(self.get(self.pegawai, "pakln:rekap_progres_pdln_data").status_code, 403)

    def test_halaman_tampil_untuk_setiap_role_admin(self):
        for user, ns in ((self.admin_unor, "unor"), (self.admin_bpsdm, "bpsdm"),
                         (self.admin_bko, "bko"), (self.admin_pakln, "pakln")):
            resp = self.get(user, f"{ns}:rekap_progres_pdln")
            self.assertEqual(resp.status_code, 200, ns)
            self.assertContains(resp, "Status Progres Surat")
            self.assertContains(resp, 'rowspan="2"')
            self.assertContains(resp, 'colspan="5"')
            self.assertContains(resp, "Karo/Setjen")

    def test_filter_mode_dan_tanggal_di_halaman(self):
        resp = self.get(self.admin_pakln, "pakln:rekap_progres_pdln")
        for label in ("Harian (Pilih Tanggal)", "Mingguan", "Bulanan", "Tahunan"):
            self.assertContains(resp, label)
        self.assertContains(resp, 'type="date"')

    def test_data_json_memuat_baris_dan_rentang(self):
        p = self.pdln(date(2026, 10, 10), negara=self.singapura)
        resp = self.get(self.admin_pakln, "pakln:rekap_progres_pdln_data", "?mode=harian&tanggal=2026-10-10")
        self.assertEqual(resp.status_code, 200)
        js = resp.json()
        self.assertEqual(js["rentang"], "10/10/2026")
        self.assertEqual(len(js["data"]), 1)
        baris = js["data"][0]
        self.assertEqual(baris["no_surat"], p.kode)
        self.assertEqual(baris["tanggal"], "01/09/2026")
        self.assertEqual(baris["visa"], "Bebas Visa")
        self.assertEqual(baris["status"], "Selesai")
        self.assertEqual(baris["status_kode"], "selesai")

    def test_data_json_kosong_bila_tidak_ada_update_pada_periode(self):
        self.pdln(date(2026, 10, 10))
        js = self.get(self.admin_pakln, "pakln:rekap_progres_pdln_data", "?mode=harian&tanggal=2026-10-11").json()
        self.assertEqual(js["data"], [])

    def test_rentang_mingguan_ditampilkan_senin_sampai_minggu(self):
        js = self.get(self.admin_pakln, "pakln:rekap_progres_pdln_data", "?mode=mingguan&tanggal=2026-10-14").json()
        self.assertEqual(js["rentang"], "12/10/2026 – 18/10/2026")

    def test_teks_dari_data_di_escape(self):
        self.pegawai.profile.nama = "<b>Andra</b>"
        self.pegawai.profile.save()
        self.pdln(date(2026, 10, 10), negara=self.jepang)
        resp = self.get(self.admin_pakln, "pakln:rekap_progres_pdln_data", "?mode=harian&tanggal=2026-10-10")
        self.assertIn("&lt;b&gt;Andra&lt;/b&gt;", resp.json()["data"][0]["nama_negara"])

    def test_sidebar_rekap_progres_pdln_menuju_halaman_baru(self):
        resp = self.get(self.admin_pakln, "pakln:rekap_progres_pdln")
        self.assertContains(resp, f'href="{reverse("pakln:rekap_progres_pdln")}"')


class ProgresIlnTests(_DataProgres, TestCase):
    """Rekap Progres ILN = pengajuan Non-Kedinasan, hanya tahap Kabag, Karo, dan Sekjen."""

    def iln(self, diperbarui, **kw):
        return self.pdln(diperbarui, jenis="nondinas", **kw)

    def tahap(self, p):
        qs = report.queryset_progres_iln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
        return report.tanggal_tahap_iln(qs.get(pk=p.pk))

    def test_queryset_hanya_non_kedinasan_pada_periode_updated_at(self):
        dalam = self.iln(date(2026, 10, 10))
        self.iln(date(2026, 9, 30))
        self.pdln(date(2026, 10, 10))   # PDLN tidak ikut
        qs = report.queryset_progres_iln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(list(qs), [dalam])

    def test_pdln_tidak_memuat_non_kedinasan(self):
        self.iln(date(2026, 10, 10))
        self.assertEqual(list(report.queryset_progres_pdln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))), [])

    def test_admin_unor_hanya_unitnya(self):
        sendiri = self.iln(date(2026, 10, 10))
        self.iln(date(2026, 10, 10), unit=self.unor_lain)
        qs = report.queryset_progres_iln(self.admin_unor, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(list(qs), [sendiri])

    def test_tiga_tahap_dari_log_generate_dan_izin_sekjen(self):
        p = self.iln(date(2026, 10, 20))
        self.generate(p, DokumenGenerateLog.Jenis.ND_KABAG, date(2026, 10, 11))
        self.generate(p, DokumenGenerateLog.Jenis.ND_KARO, date(2026, 10, 12))
        self.dokumen(p, DokumenPakln.Jenis.ILN_SEKJEN, date(2026, 10, 15))
        self.assertEqual(self.tahap(p), {"kabag": date(2026, 10, 11), "karo": date(2026, 10, 12), "sekjen": date(2026, 10, 15)})

    def test_sekjen_memakai_tanggal_surat_bila_ada(self):
        p = self.iln(date(2026, 10, 20))
        self.dokumen(p, DokumenPakln.Jenis.ILN_SEKJEN, date(2026, 10, 15))
        DokumenPakln.objects.filter(pengajuan=p).update(tanggal_surat=date(2026, 10, 13))
        self.assertEqual(self.tahap(p)["sekjen"], date(2026, 10, 13))

    def test_tahap_belum_dilalui_kosong(self):
        p = self.iln(date(2026, 10, 20))
        self.assertEqual(self.tahap(p), {"kabag": None, "karo": None, "sekjen": None})

    def test_baris_dan_jumlah_query_tetap(self):
        for hari in range(10, 16):
            p = self.iln(date(2026, 10, hari), negara=self.jepang)
            self.generate(p, DokumenGenerateLog.Jenis.ND_KABAG, date(2026, 10, 11))
            self.dokumen(p, DokumenPakln.Jenis.ILN_SEKJEN, date(2026, 10, 12))
        with self.assertNumQueries(4):
            qs = report.queryset_progres_iln(self.admin_pakln, date(2026, 10, 1), date(2026, 10, 31))
            baris = list(report.baris_progres_iln(qs))
        self.assertEqual(len(baris), 6)
        self.assertEqual(baris[0]["nama_negara"], "Andra ke Jepang Uji")
        self.assertEqual(set(baris[0]) & {"kabag", "karo", "sekjen"}, {"kabag", "karo", "sekjen"})
        self.assertNotIn("setneg", baris[0])


class HalamanRekapIlnTests(_DataProgres, TestCase):
    def test_akses_login_dan_peran(self):
        self.assertEqual(self.client.get(reverse("pakln:rekap_progres_iln")).status_code, 302)
        self.assertEqual(self.client.get(reverse("pakln:rekap_progres_iln_data")).status_code, 302)
        self.assertEqual(self.get(self.pegawai, "pakln:rekap_progres_iln").status_code, 403)
        self.assertEqual(self.get(self.pegawai, "pakln:rekap_progres_iln_data").status_code, 403)

    def test_halaman_hanya_tiga_kolom_tahap_untuk_setiap_role_admin(self):
        for user, ns in ((self.admin_unor, "unor"), (self.admin_bpsdm, "bpsdm"),
                         (self.admin_bko, "bko"), (self.admin_pakln, "pakln")):
            resp = self.get(user, f"{ns}:rekap_progres_iln")
            self.assertEqual(resp.status_code, 200, ns)
            self.assertContains(resp, "Rekap Progres ILN")
            self.assertContains(resp, "Status Progres Surat")
            self.assertContains(resp, 'colspan="3"')
            self.assertContains(resp, "Sekjen")
            self.assertNotContains(resp, "Setneg")
            self.assertNotContains(resp, "Kemlu")
            self.assertContains(resp, reverse(f"{ns}:rekap_progres_iln_data"))

    def test_halaman_pdln_tetap_lima_kolom_tahap(self):
        resp = self.get(self.admin_pakln, "pakln:rekap_progres_pdln")
        self.assertContains(resp, 'colspan="5"')
        self.assertContains(resp, reverse("pakln:rekap_progres_pdln_data"))
        self.assertNotContains(resp, "Sekjen")

    def test_filter_periode_sama_dengan_pdln(self):
        resp = self.get(self.admin_pakln, "pakln:rekap_progres_iln")
        for label in ("Harian (Pilih Tanggal)", "Mingguan", "Bulanan", "Tahunan"):
            self.assertContains(resp, label)
        self.assertContains(resp, 'type="date"')

    def test_data_json_hanya_non_kedinasan_dengan_kunci_tahap_iln(self):
        iln = self.pdln(date(2026, 10, 10), negara=self.singapura, jenis="nondinas")
        self.pdln(date(2026, 10, 10), negara=self.singapura)   # PDLN
        DokumenPakln.objects.create(pengajuan=iln, jenis=DokumenPakln.Jenis.ILN_SEKJEN, file="uji.pdf")
        js = self.get(self.admin_pakln, "pakln:rekap_progres_iln_data", "?mode=harian&tanggal=2026-10-10").json()
        self.assertEqual(js["rentang"], "10/10/2026")
        self.assertEqual(len(js["data"]), 1)
        baris = js["data"][0]
        self.assertEqual(baris["no_surat"], iln.kode)
        self.assertEqual(baris["status"], "Selesai")
        self.assertEqual(baris["status_kode"], "selesai")
        self.assertIn("sekjen", baris)
        self.assertNotIn("setneg", baris)
        self.assertEqual(baris["sekjen"], timezone.localdate().strftime("%d/%m/%Y"))

    def test_teks_dari_data_di_escape(self):
        self.pegawai.profile.nama = "<b>Andra</b>"
        self.pegawai.profile.save()
        self.pdln(date(2026, 10, 10), negara=self.jepang, jenis="nondinas")
        js = self.get(self.admin_pakln, "pakln:rekap_progres_iln_data", "?mode=harian&tanggal=2026-10-10").json()
        self.assertIn("&lt;b&gt;Andra&lt;/b&gt;", js["data"][0]["nama_negara"])

    def test_sidebar_rekap_progres_iln_menuju_halaman_baru(self):
        resp = self.get(self.admin_pakln, "pakln:rekap_progres_iln")
        self.assertContains(resp, f'href="{reverse("pakln:rekap_progres_iln")}"')
