"""Surat Tugas Pimpinan Unor (PDLN Tipe 2) — Modul 2B: halaman Admin Unor (unggah, ganti, hapus, kirim)."""

from datetime import date, timedelta

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from . import surat_tugas
from .models import DokumenBpsdm, DokumenUnor, Pengajuan, RiwayatPengajuan
from .tests_surat_tugas import _Dasar

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
Aksi = RiwayatPengajuan.Aksi
TIPE2 = ("T2P", "T2L")
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
PDF = b"%PDF-1.4\n%uji\n"


class _DasarUnor(_Dasar):
    def url(self, p):
        return reverse("unor:surat_tugas", kwargs={"kode": p.kode})

    def halaman(self, p, user=None):
        self.login(user or self.admin_unor)
        return self.client.get(self.url(p))

    def unggah(self, p, tanggal=True, nama="st.pdf", user=None):
        data = {"jenis": "surat_tugas", "file": SimpleUploadedFile(nama, PDF, content_type="application/pdf")}
        if tanggal is True:
            data["tanggal_surat"] = date.today().isoformat()
        elif tanggal:
            data["tanggal_surat"] = tanggal
        self.login(user or self.admin_unor)
        return self.client.post(self.url(p), data, follow=True)

    def kirim_post(self, p, agree=True, user=None):
        self.login(user or self.admin_unor)
        return self.client.post(self.url(p), {"kirim": "1", **({"agree": "on"} if agree else {})}, follow=True)


@override_settings(STORAGES=_STORAGES_MEMORI)
class AksesHalamanTests(_DasarUnor, TestCase):
    def test_belum_login_dialihkan_dan_pegawai_ditolak(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.assertEqual(self.client.get(self.url(p)).status_code, 302)
        self.assertEqual(self.halaman(p, self.pegawai).status_code, 403)
        self.assertEqual(self.halaman(p, self.admin_pakln).status_code, 403)

    def test_admin_unor_unit_lain_tidak_menemukan_pengajuan(self):
        lain = User.objects.create_user("unor2", password="x", role="admin_unor", unit_organisasi=self.unor_lain)
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.assertEqual(self.halaman(p, lain).status_code, 404)

    def test_pengajuan_di_luar_tipe_2_tidak_punya_halaman_ini(self):
        for tipe in ("T1", "T3"):
            self.assertEqual(self.halaman(self.pengajuan(tipe, jalur="")).status_code, 404, tipe)

    def test_halaman_tampil_untuk_t2p_dan_t2l(self):
        for tipe in TIPE2:
            resp = self.halaman(self.pengajuan(tipe, S.PROSES_BPSDM, SS.MENUNGGU))
            self.assertEqual(resp.status_code, 200, tipe)
            self.assertContains(resp, "Surat Tugas Pimpinan Unor")
            self.assertContains(resp, "Kirim ke Biro PAKLN")
            self.assertContains(resp, "doc-upload-form")

    def test_tanpa_kotak_format_otomatis_dan_format_diambil_dari_template_dokumen(self):
        # Arahan review PR: kotak "Format Surat Tugas Otomatis" ditiadakan; format memakai Template Dokumen.
        p = self.pengajuan(jalur=SS.MENUNGGU)
        DokumenBpsdm.objects.create(pengajuan=p, jenis="izin_prinsip", file="ip.pdf", tanggal_surat=date(2026, 10, 5))
        resp = self.halaman(p)
        self.assertNotContains(resp, "Format Surat Tugas Otomatis")
        self.assertNotContains(resp, "Unduh Format Surat Tugas")
        self.assertContains(resp, "Format tersedia pada")

    def test_sebelum_izin_prinsip_halaman_terkunci_tanpa_formulir_unggah(self):
        resp = self.halaman(self.pengajuan(jalur=""))
        self.assertContains(resp, "setelah Admin BPSDM mengunggah Izin Prinsip")
        self.assertNotContains(resp, "doc-upload-form")
        self.assertNotContains(resp, "Kirim ke Biro PAKLN")

    def test_tanggal_izin_prinsip_ditampilkan(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        DokumenBpsdm.objects.create(pengajuan=p, jenis="izin_prinsip", file="ip.pdf", tanggal_surat=date(2026, 10, 5))
        self.assertContains(self.halaman(p), "05 Okt 2026")


@override_settings(STORAGES=_STORAGES_MEMORI)
class UnggahSuratTugasTests(_DasarUnor, TestCase):
    def test_unggah_dan_ganti_berkas_selama_menunggu(self):
        for tipe in TIPE2:
            p = self.pengajuan(tipe, jalur=SS.MENUNGGU)
            self.unggah(p, nama="satu.pdf")
            self.unggah(p, nama="dua.pdf")
            dok = DokumenUnor.objects.get(pengajuan=p, jenis="surat_tugas")      # tetap satu berkas
            self.assertIn("dua", dok.file.name, tipe)
            self.assertEqual(dok.tanggal_surat, date.today())
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)            # lepaskan agar iterasi berikutnya bebas

    def test_unggah_ditolak_sebelum_jalur_dibuka(self):
        p = self.pengajuan(jalur="")
        resp = self.unggah(p)
        self.assertContains(resp, "setelah Admin BPSDM mengunggah Izin Prinsip")
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

    def test_unggah_wajib_tanggal_surat_dan_tidak_boleh_masa_depan(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.assertContains(self.unggah(p, tanggal=False), "Tanggal Surat")
        self.unggah(p, tanggal=(date.today() + timedelta(days=2)).isoformat())
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

    def test_berkas_terkunci_setelah_dikirim(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.unggah(p, nama="asli.pdf")
        self.kirim_post(p)
        resp = self.unggah(p, nama="ganti.pdf")
        self.assertContains(resp, "terkunci")
        self.assertIn("asli", DokumenUnor.objects.get(pengajuan=p, jenis="surat_tugas").file.name)

    def test_berkas_terbuka_lagi_setelah_dikembalikan(self):
        p = self.pengajuan(status=S.PROSES_PAKLN, jalur=SS.MENUNGGU)
        self.unggah(p, nama="asli.pdf")
        self.kirim_post(p)
        surat_tugas.kembalikan(p, self.admin_pakln, "Tanggal tidak sesuai")
        self.unggah(p, nama="perbaikan.pdf")
        self.assertIn("perbaikan", DokumenUnor.objects.get(pengajuan=p, jenis="surat_tugas").file.name)

    def test_unggah_ditolak_saat_pembatalan_terbuka(self):
        from .models import PermohonanPembatalan
        p = self.pengajuan(jalur=SS.MENUNGGU)
        PermohonanPembatalan.objects.create(
            pengajuan=p, diajukan_oleh=self.pegawai, diajukan_role="pegawai", alasan="Uji",
            status=PermohonanPembatalan.Status.MENUNGGU_UNOR,
        )
        self.assertContains(self.unggah(p), "pembatalan")
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())


@override_settings(STORAGES=_STORAGES_MEMORI)
class KirimSuratTugasTests(_DasarUnor, TestCase):
    def test_kirim_mengunci_berkas_dan_mencatat_riwayat(self):
        for tipe in TIPE2:
            p = self.pengajuan(tipe, jalur=SS.MENUNGGU)
            self.unggah(p)
            resp = self.kirim_post(p)
            self.assertContains(resp, "dikirim ke Biro PAKLN")
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, SS.DIKIRIM, tipe)
            self.assertEqual(p.status, S.PROSES_BPSDM)
            self.assertEqual(self.riwayat(p, Aksi.SURAT_TUGAS_DIKIRIM).count(), 1)
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_kirim_butuh_pernyataan_dicentang(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.unggah(p)
        self.assertContains(self.kirim_post(p, agree=False), "Centang pernyataan")
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.MENUNGGU)

    def test_kirim_butuh_berkas(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.assertContains(self.kirim_post(p), "Unggah berkas")
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.MENUNGGU)

    def test_kirim_dua_kali_tidak_menggandakan_riwayat(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.unggah(p)
        self.kirim_post(p)
        self.assertContains(self.kirim_post(p), "sudah berubah")
        self.assertEqual(self.riwayat(p, Aksi.SURAT_TUGAS_DIKIRIM).count(), 1)

    def test_kirim_ulang_setelah_dikembalikan(self):
        p = self.pengajuan(status=S.PROSES_PAKLN, jalur=SS.MENUNGGU)
        self.unggah(p)
        self.kirim_post(p)
        surat_tugas.kembalikan(p, self.admin_pakln, "Nomor surat salah")
        resp = self.halaman(p)
        self.assertContains(resp, "Nomor surat salah")           # catatan pengembalian tampil
        self.assertContains(resp, "Kirim Ulang ke Biro PAKLN")
        self.kirim_post(p)
        p.refresh_from_db()
        self.assertEqual((p.status_surat_tugas, p.catatan_surat_tugas), (SS.DIKIRIM, ""))
        self.assertEqual(self.riwayat(p, Aksi.SURAT_TUGAS_DIKIRIM).count(), 2)

    def test_admin_unor_tidak_boleh_memproses_pengajuan_milik_sendiri(self):
        p = self.pengajuan(jalur=SS.MENUNGGU, pegawai=self.admin_unor)
        self.assertEqual(self.unggah(p).status_code, 403)
        self.assertEqual(self.kirim_post(p).status_code, 403)


@override_settings(STORAGES=_STORAGES_MEMORI)
class HapusSuratTugasTests(_DasarUnor, TestCase):
    def hapus(self, p, jenis="surat_tugas"):
        self.login(self.admin_unor)
        return self.client.post(reverse("unor:hapus_surat_tugas", kwargs={"kode": p.kode, "jenis": jenis}), follow=True)

    def test_hapus_selama_belum_dikirim(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.berkas(p)
        self.hapus(p)
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

    def test_tidak_bisa_dihapus_setelah_dikirim(self):
        p = self.pengajuan(jalur=SS.DIKIRIM)
        self.berkas(p)
        self.assertContains(self.hapus(p), "terkunci")
        self.assertTrue(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

    def test_hanya_jenis_surat_tugas_yang_bisa_dihapus_lewat_url_ini(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        DokumenUnor.objects.create(pengajuan=p, jenis="nd_sek_bpsdm", file="nd.pdf")
        self.hapus(p, jenis="nd_sek_bpsdm")
        self.assertTrue(DokumenUnor.objects.filter(pengajuan=p, jenis="nd_sek_bpsdm").exists())

    def test_get_tidak_menghapus(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.berkas(p)
        self.login(self.admin_unor)
        self.client.get(reverse("unor:hapus_surat_tugas", kwargs={"kode": p.kode, "jenis": "surat_tugas"}))
        self.assertTrue(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

    def test_endpoint_hapus_lama_tidak_bisa_melewati_penguncian(self):
        p = self.pengajuan(status=S.PROSES, jalur=SS.DIKIRIM)       # mis. data lama hasil migrasi
        self.berkas(p)
        self.login(self.admin_unor)
        resp = self.client.post(reverse("unor:hapus_dokumen", kwargs={"kode": p.kode, "jenis": "surat_tugas"}), follow=True)
        self.assertContains(resp, "halaman Surat Tugas")
        self.assertTrue(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())


@override_settings(STORAGES=_STORAGES_MEMORI)
class TombolDasborTests(_DasarUnor, TestCase):
    def baris_dasbor(self):
        self.login(self.admin_unor)
        resp = self.client.get(reverse("unor:dashboard_data"), {"tab": "pdln", "draw": 1, "start": 0, "length": 50})
        self.assertEqual(resp.status_code, 200)
        return str(resp.json()["data"])

    def test_tombol_muncul_bila_jalur_terbuka_dan_kuning_saat_perlu_aksi(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        teks = self.baris_dasbor()
        self.assertIn(self.url(p), teks)
        self.assertIn("button is-warning is-small", teks.split(self.url(p))[1][:80])

    def test_tombol_tidak_kuning_setelah_dikirim(self):
        p = self.pengajuan(jalur=SS.DIKIRIM)
        teks = self.baris_dasbor()
        self.assertIn(self.url(p), teks)
        self.assertNotIn("is-warning", teks.split(self.url(p))[1][:60])

    def test_tombol_tidak_muncul_sebelum_jalur_dibuka_atau_untuk_tipe_lain(self):
        belum = self.pengajuan(jalur="")
        t1 = self.pengajuan("T1", status=S.PROSES_PAKLN)
        teks = self.baris_dasbor()
        self.assertNotIn(self.url(belum), teks)
        self.assertNotIn("surat-tugas", teks.replace(self.url(belum), ""))
        self.assertNotIn(t1.kode + "/surat-tugas", teks)
