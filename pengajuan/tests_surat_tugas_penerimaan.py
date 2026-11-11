"""Surat Tugas Pimpinan Unor (PDLN Tipe 2) — Modul 7: tes penerimaan end-to-end.

Menjalankan perjalanan LENGKAP lewat view yang sebenarnya (Pegawai → Admin Unor → Admin BPSDM → Biro PAKLN → Selesai),
sesuai "Kriteria Penerimaan" pada wiki/perancangan/RANCANGAN_UPDATE_AJUAN_TP2_PENDIDIKAN_TP2_PELATIHAN.md. Uji per modul
(state machine, halaman Unor/PAKLN, notifikasi, format, tampilan) ada di tests_surat_tugas*.py; berkas ini memastikan
semuanya bekerja bersama, untuk T2P maupun T2L.

Peta kriteria penerimaan → tes lihat PETA_KRITERIA di bawah dan wiki/instructions/PDLN_TIPE_2_FLOW.MD §9.10.
"""

from datetime import date

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from notifications.models import Notification

from . import surat_tugas
from .models import DokumenBpsdm, DokumenPakln, DokumenUnor, PermohonanPembatalan, Pengajuan
from .tests_surat_tugas_notif import _DasarNotif

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
E = Notification.Event
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
PDF = b"%PDF-1.4\n%uji\n"

# Kriteria penerimaan (urut seperti di rancangan) → tes yang membuktikannya.
PETA_KRITERIA = {
    "Admin Unor meneruskan ke BPSDM tanpa Surat Tugas; slot tidak tampil di tahap proses":
        "AlurLengkapTests.langkah 1 (+ tests_surat_tugas_alur.AdminUnorTanpaSuratTugasTests)",
    "Sebelum Izin Prinsip ada, Admin Unor tidak dapat mengunggah Surat Tugas":
        "AlurLengkapTests.langkah 2 (+ tests_surat_tugas_unor.UnggahSuratTugasTests)",
    "Admin BPSDM wajib mengisi Tanggal Surat Izin Prinsip dan tanggalnya muncul di format Surat Tugas":
        "AlurLengkapTests.langkah 3 + tests_surat_tugas_format",
    "Setelah Izin Prinsip, Admin Unor diberi notifikasi dan dapat mengunggah serta mengirim untuk unitnya":
        "AlurLengkapTests.langkah 3 dan 6 + tests_surat_tugas_notif",
    "Admin BPSDM dapat meneruskan ke Biro PAKLN dan Admin BKO walau Surat Tugas belum ada":
        "AlurLengkapTests.langkah 4",
    "Admin Unor tidak dapat mengubah Surat Tugas yang sudah dikirim kecuali dikembalikan":
        "AlurLengkapTests.langkah 6 dan 8",
    "Biro PAKLN dapat mengembalikan Surat Tugas (catatan wajib) tanpa mengubah status; Admin Unor diberi notifikasi":
        "AlurLengkapTests.langkah 7 + tests_surat_tugas_pakln.KembalikanSuratTugasTests",
    "Biro PAKLN dapat meninjau tetapi tidak dapat mengunggah/menghapus dokumen PAKLN sebelum Surat Tugas dikirim":
        "AlurLengkapTests.langkah 5 dan 7 + tests_surat_tugas_pakln.UnggahDokumenPaklnTerkunciTests",
    "Biro PAKLN tidak dapat menyelesaikan pengajuan sebelum Surat Tugas dikirim":
        "AlurLengkapTests.langkah 5 + tests_surat_tugas_pakln.SelesaikanMenungguSuratTugasTests",
    "Selama pembatalan terbuka semua aksi jalur Surat Tugas ditolak":
        "PembatalanDanDataLamaTests + tests_surat_tugas_unor/pakln (unggah, kirim, kembalikan)",
    "Pengajuan lama yang Surat Tugasnya sudah diunggah di tahap Unor tetap dapat diselesaikan":
        "PembatalanDanDataLamaTests.test_pengajuan_lama_tetap_dapat_diselesaikan",
    "Non-Kedinasan, T1, dan T3 tidak berubah dan seluruh uji yang ada tetap lulus":
        "tests_surat_tugas*.TipeLain + seluruh suite (manage.py test)",
}


@override_settings(STORAGES=_STORAGES_MEMORI)
class AlurLengkapTests(_DasarNotif, TestCase):
    """Satu perjalanan penuh per tipe. Setiap 'langkah' sesuai butir di PETA_KRITERIA."""

    def _perjalanan(self, tipe):
        p = self.isi_formulir(tipe)
        self.kirim(p)

        # --- langkah 1: Admin Unor meneruskan tanpa Surat Tugas; slot Surat Tugas tidak tampil di tahap proses
        self.post(self.admin_unor, "unor:preview", {"lanjutkan": "1"}, kode=p.kode)
        halaman = self.get(self.admin_unor, "unor:upload_dokumen", kode=p.kode)
        self.assertEqual(halaman.status_code, 200)
        # Baris dokumen Surat Tugas tidak ada (teks timeline boleh menyebutnya, jadi periksa isian formulirnya).
        self.assertNotContains(halaman, 'value="surat_tugas"')
        self.assertContains(halaman, 'value="nd_sek_bpsdm"')       # dokumen tahap Unor lain tetap ada
        self.unor_teruskan(p)
        p.refresh_from_db()
        self.assertEqual(p.status, S.PROSES_BPSDM, tipe)
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())
        self.assertEqual(p.status_surat_tugas, "")

        # --- langkah 2: sebelum Izin Prinsip ada, Admin Unor tidak dapat mengunggah Surat Tugas
        self.unggah(p)
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

        # --- langkah 3: Izin Prinsip wajib Tanggal Surat; unggahan pertama membuka jalur dan memberi tahu Admin Unor
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.unggah_izin_prinsip(p, tanggal=False)
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, "", "tanpa Tanggal Surat ditolak")
        self.unggah_izin_prinsip(p)
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.MENUNGGU)
        self.assertEqual(DokumenBpsdm.objects.get(pengajuan=p, jenis="izin_prinsip").tanggal_surat, date.today())
        self.assertEqual(self.notif(E.SURAT_TUGAS_DIBUKA, p).get().recipient, self.admin_unor)

        # --- langkah 4: Admin BPSDM meneruskan walau Surat Tugas belum ada
        self.bpsdm_teruskan(p)
        p.refresh_from_db()
        self.assertEqual(p.status, S.PROSES_PAKLN, tipe)
        self.assertEqual(p.status_surat_tugas, SS.MENUNGGU)
        if tipe == "T2P":
            self.assertEqual(p.status_bko, Pengajuan.StatusBko.MENUNGGU)        # jalur BKO ikut terbuka

        # --- langkah 5: Biro PAKLN meninjau, tetapi unggah dokumen PAKLN dan Selesai terkunci
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.assertEqual(self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode).status_code, 200)
        self.unggah_dokumen_pakln(p, "sp_setneg")
        self.assertFalse(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists())
        self.lengkapi(p, "pakln")
        if tipe == "T2P":
            self.bko_unggah(p)
        self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
        p.refresh_from_db()
        self.assertEqual(p.status, S.PROSES_PAKLN, "Selesai terkunci sebelum Surat Tugas dikirim")
        DokumenPakln.objects.filter(pengajuan=p).delete()        # dokumen PAKLN diunggah ulang nanti lewat view

        # --- langkah 6: Admin Unor mengunggah dan mengirim; setelah dikirim berkas terkunci
        self.unggah(p, nama="asli.pdf")
        self.kirim_post(p)
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)
        self.assertEqual(self.notif(E.SURAT_TUGAS_DIKIRIM, p).get().recipient, self.admin_pakln)
        self.unggah(p, nama="ganti.pdf")
        self.assertIn("asli", DokumenUnor.objects.get(pengajuan=p, jenis="surat_tugas").file.name)

        # --- langkah 7: Biro PAKLN mengembalikan (catatan wajib); status pengajuan tetap; dokumen PAKLN terkunci lagi
        self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": " "})
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM, "catatan kosong ditolak")
        self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "Nomor surat tidak sesuai"})
        p.refresh_from_db()
        self.assertEqual((p.status, p.status_surat_tugas), (S.PROSES_PAKLN, SS.DIKEMBALIKAN))
        self.assertIn("Nomor surat tidak sesuai", self.notif(E.SURAT_TUGAS_DIKEMBALIKAN, p).get().body)
        self.unggah_dokumen_pakln(p, "sp_setneg")
        self.assertFalse(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists())

        # --- langkah 8: Admin Unor memperbaiki dan mengirim ulang
        self.unggah(p, nama="perbaikan.pdf")
        self.assertIn("perbaikan", DokumenUnor.objects.get(pengajuan=p, jenis="surat_tugas").file.name)
        self.kirim_post(p)
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

        # --- langkah 9: dokumen PAKLN terbuka (unggah nyata), lalu Biro PAKLN menyelesaikan
        self.unggah_dokumen_pakln(p, "sp_setneg")
        self.assertTrue(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists())
        self.lengkapi(p, "pakln")
        self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
        p.refresh_from_db()
        self.assertEqual(p.status, S.SELESAI, tipe)

    def test_perjalanan_lengkap_t2p_pendidikan(self):
        self._perjalanan("T2P")

    def test_perjalanan_lengkap_t2l_pelatihan(self):
        self._perjalanan("T2L")


@override_settings(STORAGES=_STORAGES_MEMORI)
class PembatalanDanDataLamaTests(_DasarNotif, TestCase):
    def test_hapus_surat_tugas_juga_ditolak_saat_pembatalan_terbuka(self):
        p = self.pengajuan("T2P", S.PROSES_BPSDM, SS.MENUNGGU)
        self.berkas(p)
        PermohonanPembatalan.objects.create(
            pengajuan=p, diajukan_oleh=self.pegawai, diajukan_role="pegawai", alasan="Uji",
            status=PermohonanPembatalan.Status.MENUNGGU_UNOR,
        )
        self.login(self.admin_unor)
        resp = self.client.post(reverse("unor:hapus_surat_tugas", kwargs={"kode": p.kode, "jenis": "surat_tugas"}), follow=True)
        self.assertContains(resp, "pembatalan")
        self.assertTrue(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

    def test_unduh_format_surat_tugas_memerlukan_login(self):
        p = self.pengajuan("T2L", S.PROSES_BPSDM, SS.MENUNGGU)
        self.assertEqual(self.client.post(reverse("unor:unduh_format_surat_tugas", kwargs={"kode": p.kode})).status_code, 302)

    def _pengajuan_lama(self, tipe):
        """Keadaan hasil migrasi data 0032: Surat Tugas sudah diunggah di tahap Unor (aturan lama) → `dikirim`."""
        p = self.isi_formulir(tipe)
        self.kirim(p)
        self.berkas(p)
        Pengajuan.objects.filter(pk=p.pk).update(status_surat_tugas=SS.DIKIRIM)
        return p

    def _lama_diselesaikan(self, tipe):
        p = self._pengajuan_lama(tipe)
        self.unor_teruskan(p)
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.unggah_izin_prinsip(p)                         # tidak membuka ulang dan tidak menimpa status
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)
        self.assertFalse(self.notif(E.SURAT_TUGAS_DIBUKA, p).exists())
        self.bpsdm_teruskan(p)
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.lengkapi(p, "pakln")
        if tipe == "T2P":
            self.bko_unggah(p)
        self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
        p.refresh_from_db()
        self.assertEqual(p.status, S.SELESAI, tipe)

    def test_pengajuan_lama_tetap_dapat_diselesaikan_t2p(self):
        self._lama_diselesaikan("T2P")

    def test_pengajuan_lama_tetap_dapat_diselesaikan_t2l(self):
        self._lama_diselesaikan("T2L")


class PetaKriteriaTests(TestCase):
    def test_semua_dua_belas_kriteria_penerimaan_terpetakan(self):
        self.assertEqual(len(PETA_KRITERIA), 12)
        self.assertTrue(all(PETA_KRITERIA.values()))
