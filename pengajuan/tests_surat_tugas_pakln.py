"""Surat Tugas Pimpinan Unor (PDLN Tipe 2) — Modul 3: sisi Biro PAKLN (penguncian dokumen PAKLN dan Selesai,
aksi Kembalikan Surat Tugas)."""

from datetime import date

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import surat_tugas
from .models import DokumenPakln, Pengajuan, PermohonanPembatalan
from .tests_surat_tugas import _Dasar

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
Aksi = surat_tugas.Aksi
TIPE2 = ("T2P", "T2L")
BELUM_DIKIRIM = ("", SS.MENUNGGU, SS.DIKEMBALIKAN)
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
PDF = b"%PDF-1.4\n%uji\n"


class _DasarPakln(_Dasar):
    def di_pakln(self, tipe="T2P", jalur=SS.DIKIRIM, lengkap=False):
        """Pengajuan Tipe 2 di Biro PAKLN, pratinjau sudah disetujui. T2P: jalur BKO dianggap sudah beres."""
        p = self.pengajuan(tipe, S.PROSES_PAKLN, jalur)
        fields = {"preview_pakln_agree": True}
        if tipe == "T2P":
            fields.update(status_bko=Pengajuan.StatusBko.DIUNGGAH, tgl_masuk_bko=date.today())
        Pengajuan.objects.filter(pk=p.pk).update(**fields)
        if jalur in (SS.DIKIRIM, SS.DIKEMBALIKAN):
            self.berkas(p)
        if lengkap:
            self.lengkapi(p, "pakln")
        p.refresh_from_db()
        return p

    def lengkapi(self, p, tahap):
        from . import persyaratan
        model = persyaratan.TAHAP_MODEL[tahap]
        for s in persyaratan.daftar_syarat(p, tahap):
            model.objects.get_or_create(pengajuan=p, jenis=s.jenis, defaults={"file": "x.pdf", "tanggal_surat": date.today()})

    def url_upload(self, p):
        return reverse("pakln:upload_dokumen", kwargs={"kode": p.kode})

    def post_pakln(self, p, data, user=None):
        self.login(user or self.admin_pakln)
        return self.client.post(self.url_upload(p), data, follow=True)

    def unggah_dokumen_pakln(self, p, jenis="sp_setneg"):
        return self.post_pakln(p, {
            "jenis": jenis, "file": SimpleUploadedFile(f"{jenis}.pdf", PDF, content_type="application/pdf"),
        })


@override_settings(STORAGES=_STORAGES_MEMORI)
class UnggahDokumenPaklnTerkunciTests(_DasarPakln, TestCase):
    def test_unggah_ditolak_selama_surat_tugas_belum_dikirim(self):
        for tipe in TIPE2:
            for jalur in BELUM_DIKIRIM:
                p = self.di_pakln(tipe, jalur)
                resp = self.unggah_dokumen_pakln(p)
                self.assertContains(resp, "Surat Tugas")
                self.assertFalse(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists(), (tipe, jalur))
                Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)      # bebaskan pegawai untuk iterasi berikut

    def test_unggah_terbuka_setelah_surat_tugas_dikirim(self):
        for tipe in TIPE2:
            p = self.di_pakln(tipe, SS.DIKIRIM)
            self.unggah_dokumen_pakln(p)
            self.assertTrue(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists(), tipe)
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_hapus_dokumen_terkunci_saat_dikembalikan_dan_terbuka_saat_dikirim(self):
        p = self.di_pakln("T2L", SS.DIKEMBALIKAN, lengkap=True)
        self.login(self.admin_pakln)
        url = reverse("pakln:hapus_dokumen", kwargs={"kode": p.kode, "jenis": "sp_setneg"})
        resp = self.client.post(url, follow=True)
        self.assertContains(resp, "Surat Tugas dikembalikan")
        self.assertTrue(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists())
        Pengajuan.objects.filter(pk=p.pk).update(status_surat_tugas=SS.DIKIRIM)
        self.client.post(url)
        self.assertFalse(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists())

    def test_dokumen_yang_sudah_ada_tetap_tersimpan_saat_surat_tugas_dikembalikan(self):
        p = self.di_pakln("T2L", SS.DIKIRIM, lengkap=True)
        jumlah = DokumenPakln.objects.filter(pengajuan=p).count()
        surat_tugas.kembalikan(p, self.admin_pakln, "Tanggal tidak sesuai")
        self.assertEqual(DokumenPakln.objects.filter(pengajuan=p).count(), jumlah)

    def test_tipe_1_tidak_terpengaruh(self):
        p = self.pengajuan("T1", S.PROSES_PAKLN, "")
        Pengajuan.objects.filter(pk=p.pk).update(preview_pakln_agree=True)
        self.unggah_dokumen_pakln(p)
        self.assertTrue(DokumenPakln.objects.filter(pengajuan=p, jenis="sp_setneg").exists())

    def test_halaman_terkunci_menampilkan_alasan_dan_tanpa_formulir_unggah(self):
        p = self.di_pakln("T2L", SS.MENUNGGU)
        self.login(self.admin_pakln)
        resp = self.client.get(self.url_upload(p))
        self.assertContains(resp, "Menunggu Surat Tugas Pimpinan Unor dikirim")
        self.assertNotContains(resp, "doc-upload-form")

    def test_halaman_terbuka_setelah_dikirim_menampilkan_formulir_unggah(self):
        p = self.di_pakln("T2L", SS.DIKIRIM)
        self.login(self.admin_pakln)
        resp = self.client.get(self.url_upload(p))
        self.assertContains(resp, "doc-upload-form")
        self.assertNotContains(resp, "Menunggu Surat Tugas Pimpinan Unor dikirim")

    def test_pratinjau_menampilkan_status_surat_tugas(self):
        p = self.di_pakln("T2P", SS.MENUNGGU)
        self.login(self.admin_pakln)
        resp = self.client.get(reverse("pakln:preview", kwargs={"kode": p.kode}))
        self.assertContains(resp, "Surat Tugas Pimpinan Unor:")
        sudah = self.di_pakln("T2L", SS.DIKIRIM)
        Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)
        resp = self.client.get(reverse("pakln:preview", kwargs={"kode": sudah.kode}))
        self.assertNotContains(resp, "Surat Tugas Pimpinan Unor:")


@override_settings(STORAGES=_STORAGES_MEMORI)
class SelesaikanMenungguSuratTugasTests(_DasarPakln, TestCase):
    def test_selesai_ditolak_selama_surat_tugas_belum_dikirim(self):
        for tipe in TIPE2:
            for jalur in BELUM_DIKIRIM:
                p = self.di_pakln(tipe, jalur, lengkap=True)
                resp = self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
                self.assertContains(resp, "Surat Tugas")
                p.refresh_from_db()
                self.assertEqual(p.status, S.PROSES_PAKLN, (tipe, jalur))
                Pengajuan.objects.filter(pk=p.pk).update(status=S.DIBATALKAN)

    def test_selesai_berhasil_setelah_surat_tugas_dikirim(self):
        for tipe in TIPE2:
            p = self.di_pakln(tipe, SS.DIKIRIM, lengkap=True)
            self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
            p.refresh_from_db()
            self.assertEqual(p.status, S.SELESAI, tipe)

    def test_lanjutkan_tanpa_sk_tubel_juga_menunggu_surat_tugas(self):
        p = self.di_pakln("T2P", SS.MENUNGGU, lengkap=True)
        Pengajuan.objects.filter(pk=p.pk).update(status_bko=Pengajuan.StatusBko.DITUTUP, catatan_bko="SK tidak terbit")
        data = {"selesaikan_tanpa_sk_tubel": "1", "agree": "on", "catatan": "Lanjut tanpa SK"}
        self.post_pakln(p, data)
        p.refresh_from_db()
        self.assertEqual(p.status, S.PROSES_PAKLN)
        Pengajuan.objects.filter(pk=p.pk).update(status_surat_tugas=SS.DIKIRIM)
        self.post_pakln(p, data)
        p.refresh_from_db()
        self.assertEqual(p.status, S.SELESAI)

    def test_selesai_tipe_1_tidak_terpengaruh(self):
        p = self.pengajuan("T1", S.PROSES_PAKLN, "")
        Pengajuan.objects.filter(pk=p.pk).update(preview_pakln_agree=True)
        self.lengkapi(p, "pakln")
        self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
        p.refresh_from_db()
        self.assertEqual(p.status, S.SELESAI)

    def test_hentikan_pengajuan_tetap_bisa_walau_surat_tugas_belum_dikirim(self):
        p = self.di_pakln("T2P", SS.MENUNGGU)
        Pengajuan.objects.filter(pk=p.pk).update(status_bko=Pengajuan.StatusBko.DITUTUP, catatan_bko="SK tidak terbit")
        self.post_pakln(p, {"hentikan": "1", "alasan": "Dihentikan"})
        p.refresh_from_db()
        self.assertEqual(p.status, S.DIBATALKAN)


@override_settings(STORAGES=_STORAGES_MEMORI)
class KembalikanSuratTugasTests(_DasarPakln, TestCase):
    def test_kembalikan_surat_tugas_tanpa_mengubah_status_pengajuan(self):
        for tipe in TIPE2:
            p = self.di_pakln(tipe, SS.DIKIRIM)
            resp = self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "Nomor surat salah"})
            self.assertContains(resp, "dikembalikan ke Admin Unor")
            p.refresh_from_db()
            self.assertEqual((p.status, p.status_surat_tugas, p.catatan_surat_tugas), (S.PROSES_PAKLN, SS.DIKEMBALIKAN, "Nomor surat salah"), tipe)
            self.assertEqual(self.riwayat(p, Aksi.SURAT_TUGAS_DIKEMBALIKAN).get().catatan, "Nomor surat salah")
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_catatan_wajib(self):
        p = self.di_pakln("T2P", SS.DIKIRIM)
        resp = self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "  "})
        self.assertContains(resp, "catatan")
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

    def test_hanya_surat_tugas_yang_sudah_dikirim_bisa_dikembalikan(self):
        for jalur in (SS.MENUNGGU, SS.DIKEMBALIKAN):
            p = self.di_pakln("T2L", jalur)
            self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "Tidak sesuai"})
            p.refresh_from_db()
            self.assertEqual(p.status_surat_tugas, jalur, jalur)
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_hanya_admin_biro_pakln(self):
        p = self.di_pakln("T2P", SS.DIKIRIM)
        for user in (self.admin_unor, self.admin_bpsdm, self.pegawai):
            self.assertEqual(self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "x"}, user=user).status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

    def test_tombol_kembalikan_hanya_tampil_saat_dikirim(self):
        self.login(self.admin_pakln)
        dikirim = self.di_pakln("T2L", SS.DIKIRIM)
        self.assertContains(self.client.get(self.url_upload(dikirim)), 'name="kembalikan_surat_tugas"')
        Pengajuan.objects.filter(pk=dikirim.pk).update(status=S.SELESAI)
        menunggu = self.di_pakln("T2L", SS.MENUNGGU)
        self.assertNotContains(self.client.get(self.url_upload(menunggu)), 'name="kembalikan_surat_tugas"')

    def test_ditolak_saat_pembatalan_terbuka(self):
        p = self.di_pakln("T2P", SS.DIKIRIM)
        PermohonanPembatalan.objects.create(
            pengajuan=p, diajukan_oleh=self.pegawai, diajukan_role="pegawai", alasan="Uji",
            status=PermohonanPembatalan.Status.MENUNGGU_PAKLN,
        )
        self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "Tidak sesuai"})
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

    def test_alur_penuh_dikirim_dikembalikan_dikirim_ulang_lalu_selesai(self):
        p = self.di_pakln("T2P", SS.DIKIRIM, lengkap=True)
        self.post_pakln(p, {"kembalikan_surat_tugas": "1", "catatan": "Perbaiki tanggal"})
        self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
        p.refresh_from_db()
        self.assertEqual((p.status, p.status_surat_tugas), (S.PROSES_PAKLN, SS.DIKEMBALIKAN))      # terkunci
        surat_tugas.kirim(p, self.admin_unor)                                                      # Admin Unor kirim ulang
        self.post_pakln(p, {"selesaikan": "1", "agree": "on"})
        p.refresh_from_db()
        self.assertEqual(p.status, S.SELESAI)
