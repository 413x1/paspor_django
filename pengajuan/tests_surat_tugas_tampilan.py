"""Surat Tugas Pimpinan Unor (PDLN Tipe 2) — Modul 6: Timeline Proses, ikon riwayat, dan penanda dasbor."""

from django.conf import settings
from django.test import TestCase, override_settings

from . import alur, riwayat, surat_tugas
from .models import DokumenUnor, Pengajuan, RiwayatPengajuan
from .tests_surat_tugas_pakln import _DasarPakln
from .views_unor import status_html

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
Aksi = RiwayatPengajuan.Aksi
TIPE2 = ("T2P", "T2L")
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
AWAL = "Surat Tugas Pimpinan Unor (Admin Unor): "


def tahap(p, status):
    """Satu langkah Timeline Proses untuk status tertentu."""
    return next(t for t in alur.timeline(Pengajuan.objects.get(pk=p.pk)) if t["status"] == status)


def teks_sub(p, status):
    return [teks for teks, _ in tahap(p, status)["subs"] if teks.startswith(AWAL)]


class DeskripsiTimelineTests(_DasarPakln, TestCase):
    def test_tahap_unor_tipe_2_tidak_lagi_menyebut_surat_tugas(self):
        for tipe in TIPE2:
            desc = tahap(self.pengajuan(tipe, S.PROSES), S.PROSES)["desc"]
            self.assertNotIn("Surat Tugas", desc, tipe)
            self.assertIn("Nota Dinas", desc)

    def test_tahap_bpsdm_dan_pakln_menjelaskan_jalur_surat_tugas(self):
        for tipe in TIPE2:
            p = self.pengajuan(tipe, S.PROSES_BPSDM)
            self.assertIn("membuka penerbitan Surat Tugas Pimpinan Unor", tahap(p, S.PROSES_BPSDM)["desc"], tipe)
            self.assertIn("setelah Surat Tugas Pimpinan Unor diterima", tahap(p, S.PROSES_PAKLN)["desc"], tipe)

    def test_tipe_1_dan_3_tidak_berubah(self):
        for tipe in ("T1", "T3"):
            desc = tahap(self.pengajuan(tipe, S.PROSES, ""), S.PROSES)["desc"]
            self.assertIn("penerbitan Surat Tugas", desc, tipe)


class KeteranganJalurTimelineTests(_DasarPakln, TestCase):
    def test_tanpa_keterangan_sebelum_jalur_dibuka(self):
        for status in (S.PROSES_BPSDM, S.PROSES_PAKLN):
            p = self.pengajuan("T2P", status, "")
            self.assertEqual(teks_sub(p, status), [], status)

    def test_menunggu_tampil_di_tahap_bpsdm_lalu_pindah_ke_tahap_pakln(self):
        p = self.pengajuan("T2L", S.PROSES_BPSDM, SS.MENUNGGU)
        self.assertEqual(teks_sub(p, S.PROSES_BPSDM), [AWAL + "Menunggu diunggah dan dikirim"])
        self.assertEqual(teks_sub(p, S.PROSES_PAKLN), [])
        Pengajuan.objects.filter(pk=p.pk).update(status=S.PROSES_PAKLN)
        self.assertEqual(teks_sub(p, S.PROSES_BPSDM), [])
        self.assertEqual(teks_sub(p, S.PROSES_PAKLN), [AWAL + "Menunggu diunggah dan dikirim"])

    def test_dikembalikan_menandai_menunggu_perbaikan_tanpa_membocorkan_catatan(self):
        p = self.di_pakln("T2L", SS.DIKIRIM)
        surat_tugas.kembalikan(p, self.admin_pakln, "Nomor surat rahasia salah")
        (teks,) = teks_sub(p, S.PROSES_PAKLN)
        self.assertIn("Dikembalikan Biro PAKLN, menunggu perbaikan", teks)
        self.assertNotIn("rahasia", teks)
        self.assertEqual(tahap(p, S.PROSES_PAKLN)["subs"][-1][1], "warning")

    def test_dikirim_memuat_tanggal_dari_riwayat(self):
        p = self.di_pakln("T2L", SS.MENUNGGU)
        self.berkas(p)
        surat_tugas.kirim(p, self.admin_unor)
        (teks,) = teks_sub(p, S.PROSES_PAKLN)
        self.assertTrue(teks.startswith(AWAL + "Dikirim ke Biro PAKLN ("), teks)
        self.assertEqual(tahap(p, S.PROSES_PAKLN)["subs"][-1][1], "success")

    def test_pengajuan_lama_berstatus_dikirim_tanpa_riwayat_tetap_tampil_tanpa_tanggal(self):
        p = self.pengajuan("T2P", S.PROSES_BPSDM, SS.DIKIRIM)          # mis. hasil migrasi data
        self.assertEqual(teks_sub(p, S.PROSES_BPSDM), [AWAL + "Dikirim ke Biro PAKLN"])

    def test_tidak_tampil_saat_masih_di_unor_atau_dibatalkan(self):
        p = self.pengajuan("T2P", S.PROSES, SS.DIKIRIM)
        for status in (S.PROSES, S.PROSES_BPSDM, S.PROSES_PAKLN):
            self.assertEqual(teks_sub(p, status), [], status)
        Pengajuan.objects.filter(pk=p.pk).update(status=S.DIBATALKAN)
        for status in (S.PROSES_BPSDM, S.PROSES_PAKLN):
            self.assertEqual(teks_sub(p, status), [], status)

    def test_tetap_tampil_di_tahap_pakln_setelah_selesai(self):
        p = self.di_pakln("T2L", SS.DIKIRIM)
        Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)
        self.assertEqual(len(teks_sub(p, S.PROSES_PAKLN)), 1)

    def test_t2p_menampilkan_keterangan_bko_dan_surat_tugas_berdampingan(self):
        p = self.di_pakln("T2P", SS.MENUNGGU)            # track BKO sudah terbuka (diunggah)
        subs = tahap(p, S.PROSES_PAKLN)["subs"]
        self.assertEqual(len(subs), 2)
        self.assertIn("SK Tugas Belajar", subs[0][0])
        self.assertTrue(subs[1][0].startswith(AWAL))

    def test_tipe_1_tidak_punya_keterangan_surat_tugas(self):
        p = self.pengajuan("T1", S.PROSES_PAKLN, "")
        self.assertEqual(tahap(p, S.PROSES_PAKLN)["subs"], [])

    @override_settings(STORAGES=_STORAGES_MEMORI)
    def test_pegawai_melihat_keterangan_di_halaman_monitor_progres(self):
        p = self.di_pakln("T2L", SS.MENUNGGU)
        resp = self.get(self.pegawai, "pegawai:monitor_progres", kode=p.kode)
        self.assertContains(resp, AWAL + "Menunggu diunggah dan dikirim")


class RiwayatSuratTugasTests(_DasarPakln, TestCase):
    def siapkan(self):
        p = self.di_pakln("T2L", SS.MENUNGGU)
        self.berkas(p)
        surat_tugas.kirim(p, self.admin_unor)
        surat_tugas.kembalikan(p, self.admin_pakln, "Tanggal tidak sesuai")
        return p

    def entri(self, p, user, aksi):
        return next(e for e in riwayat.riwayat_untuk(Pengajuan.objects.get(pk=p.pk), user) if e["aksi"] == aksi)

    def test_ikon_dan_warna(self):
        p = self.siapkan()
        kirim = self.entri(p, self.admin_pakln, Aksi.SURAT_TUGAS_DIKIRIM)
        kembali = self.entri(p, self.admin_pakln, Aksi.SURAT_TUGAS_DIKEMBALIKAN)
        self.assertEqual((kirim["ikon"], kirim["tone"]), ("→", "success"))
        self.assertEqual((kembali["ikon"], kembali["tone"]), ("↩", "warning"))

    def test_catatan_pengembalian_hanya_untuk_admin_dan_tidak_untuk_pegawai(self):
        p = self.siapkan()
        for user in (self.admin_unor, self.admin_pakln):
            self.assertEqual(self.entri(p, user, Aksi.SURAT_TUGAS_DIKEMBALIKAN)["catatan"], "Tanggal tidak sesuai", user.role)
        self.assertEqual(self.entri(p, self.pegawai, Aksi.SURAT_TUGAS_DIKEMBALIKAN)["catatan"], "")

    def test_label_netral_untuk_pegawai(self):
        p = self.siapkan()
        self.assertEqual(self.entri(p, self.pegawai, Aksi.SURAT_TUGAS_DIKEMBALIKAN)["label"],
                         "Surat Tugas dikembalikan untuk perbaikan")
        self.assertIn("Biro PAKLN", self.entri(p, self.admin_unor, Aksi.SURAT_TUGAS_DIKEMBALIKAN)["label"])

    def test_riwayat_menempel_pada_tahap_biro_pakln(self):
        p = self.siapkan()
        langkah = riwayat.timeline_dengan_riwayat(Pengajuan.objects.get(pk=p.pk), self.admin_pakln)
        pakln = next(t for t in langkah if t["status"] == S.PROSES_PAKLN)
        aksi = [e["aksi"] for e in pakln["riwayat"]]
        self.assertIn(Aksi.SURAT_TUGAS_DIKIRIM, aksi)
        self.assertIn(Aksi.SURAT_TUGAS_DIKEMBALIKAN, aksi)


class PenandaDasborTests(_DasarPakln, TestCase):
    def test_penanda_menunggu_dan_dikembalikan(self):
        p = self.pengajuan("T2P", S.PROSES_PAKLN, SS.MENUNGGU)
        html = str(status_html(p))
        self.assertIn("Menunggu Surat Tugas", html)
        self.assertIn("st-status is-menunggu", html)
        Pengajuan.objects.filter(pk=p.pk).update(status_surat_tugas=SS.DIKEMBALIKAN)
        html = str(status_html(Pengajuan.objects.get(pk=p.pk)))
        self.assertIn("Surat Tugas dikembalikan", html)
        self.assertIn("st-status is-dikembalikan", html)

    def test_tanpa_penanda_bila_tidak_menahan_proses(self):
        sudah = self.pengajuan("T2P", S.PROSES_PAKLN, SS.DIKIRIM)
        self.assertNotIn("st-status", str(status_html(sudah)))
        belum_dibuka = self.pengajuan("T2L", S.PROSES_BPSDM, "")
        self.assertNotIn("st-status", str(status_html(belum_dibuka)))
        masih_di_unor = self.pengajuan("T2P", S.PROSES, SS.MENUNGGU)
        self.assertNotIn("st-status", str(status_html(masih_di_unor)))
        selesai = self.pengajuan("T2L", S.SELESAI, SS.DIKEMBALIKAN)
        self.assertNotIn("st-status", str(status_html(selesai)))
        t1 = self.pengajuan("T1", S.PROSES_PAKLN, "")
        self.assertNotIn("st-status", str(status_html(t1)))

    def test_dasbor_bko_dapat_mematikan_penanda(self):
        p = self.pengajuan("T2P", S.PROSES_PAKLN, SS.MENUNGGU)
        self.assertNotIn("st-status", str(status_html(p, dengan_bko=False, dengan_surat_tugas=False)))

    def test_penanda_tampil_di_tabel_dasbor_unor_pakln_dan_bpsdm(self):
        p = self.pengajuan("T2P", S.PROSES_PAKLN, SS.MENUNGGU)
        Pengajuan.objects.filter(pk=p.pk).update(preview_pakln_agree=True)
        parameter = "?tab=pdln&draw=1&start=0&length=50"
        for user, url in ((self.admin_unor, "unor:dashboard_data"), (self.admin_pakln, "pakln:dashboard_data")):
            resp = self.get(user, url, parameter)
            self.assertEqual(resp.status_code, 200, url)
            self.assertIn("Menunggu Surat Tugas", str(resp.json()["data"]), url)
        Pengajuan.objects.filter(pk=p.pk).update(status=S.PROSES_BPSDM)
        resp = self.get(self.admin_bpsdm, "bpsdm:dashboard_data", parameter)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Menunggu Surat Tugas", str(resp.json()["data"]))
