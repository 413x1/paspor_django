"""Surat Tugas Pimpinan Unor (PDLN Tipe 2) — Modul 2A: registri dokumen dan pembukaan jalur oleh Admin BPSDM."""

from datetime import date, timedelta

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import persyaratan
from .models import DokumenBpsdm, DokumenUnor, Pengajuan
from .tests_pdln import _Basis

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
TIPE2 = ("T2P", "T2L")
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
PDF = b"%PDF-1.4\n%uji\n"


def _pdln(tipe):
    """Pengajuan tidak disimpan: cukup untuk membaca registri (kunci_alur)."""
    return Pengajuan(jenis_perjalanan="pdln", tipe_pdln=tipe)


def _jenis(tipe, tahap):
    return [s.jenis for s in persyaratan.daftar_syarat(_pdln(tipe), tahap)]


class RegistriSuratTugasTests(TestCase):
    def test_surat_tugas_keluar_dari_syarat_tahap_unor_pada_tipe_2(self):
        for tipe in TIPE2:
            self.assertNotIn("surat_tugas", _jenis(tipe, "unor"), tipe)

    def test_tipe_1_dan_tipe_3_tidak_berubah(self):
        for tipe in ("T1", "T3"):
            self.assertIn("surat_tugas", _jenis(tipe, "unor"), tipe)
            self.assertEqual(_jenis(tipe, "surat_tugas"), [], tipe)

    def test_syarat_unor_tipe_2_yang_tersisa(self):
        self.assertEqual(_jenis("T2P", "unor"), ["nd_sek_bpsdm", "drh_ttd"])
        self.assertEqual(_jenis("T2L", "unor"), ["nd_sek_bpsdm"])

    def test_tahap_surat_tugas_berisi_satu_syarat_ber_tanggal_surat(self):
        for tipe in TIPE2:
            (syarat,) = persyaratan.daftar_syarat(_pdln(tipe), "surat_tugas")
            self.assertEqual(syarat.jenis, "surat_tugas", tipe)
            self.assertTrue(syarat.tanggal_surat, tipe)
            self.assertTrue(syarat.is_wajib(_pdln(tipe)), tipe)

    def test_tahap_surat_tugas_memakai_model_dokumen_unor(self):
        self.assertIs(persyaratan.TAHAP_MODEL["surat_tugas"], DokumenUnor)
        self.assertEqual(persyaratan.TAHAP_RELATED["surat_tugas"], "dokumen_unor")

    def test_izin_prinsip_wajib_tanggal_surat_pada_tipe_2(self):
        for tipe in TIPE2:
            self.assertTrue(persyaratan.jenis_perlu_tanggal_surat(_pdln(tipe), "bpsdm", "izin_prinsip"), tipe)


@override_settings(STORAGES=_STORAGES_MEMORI)
class AdminUnorTanpaSuratTugasTests(_Basis, TestCase):
    def _teruskan_tanpa_surat_tugas(self, tipe):
        p = self.isi_formulir(tipe)
        self.kirim(p)
        self.unor_teruskan(p)
        p.refresh_from_db()
        self.assertEqual(p.status, S.PROSES_BPSDM)
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())
        self.assertEqual(p.status_surat_tugas, "")      # jalur baru dibuka oleh Izin Prinsip, bukan oleh Unor

    def test_t2p_diteruskan_ke_bpsdm_tanpa_surat_tugas(self):
        self._teruskan_tanpa_surat_tugas("T2P")

    def test_t2l_diteruskan_ke_bpsdm_tanpa_surat_tugas(self):
        self._teruskan_tanpa_surat_tugas("T2L")

    def test_halaman_unggah_lama_menolak_surat_tugas(self):
        p = self.isi_formulir("T2P")
        self.kirim(p)
        self.post(self.admin_unor, "unor:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.login(self.admin_unor)
        resp = self.client.post(reverse("unor:upload_dokumen", kwargs={"kode": p.kode}), {
            "jenis": "surat_tugas", "tanggal_surat": date.today().isoformat(),
            "file": SimpleUploadedFile("st.pdf", PDF, content_type="application/pdf"),
        }, follow=True)
        self.assertContains(resp, "Jenis dokumen tidak valid")
        self.assertFalse(DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists())

    def test_pengajuan_tipe_1_tetap_mewajibkan_surat_tugas_di_tahap_unor(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.post(self.admin_unor, "unor:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.lengkapi(p, "unor", kecuali=("surat_tugas",))
        self.post(self.admin_unor, "unor:upload_dokumen", {"teruskan": "1", "agree": "on"}, kode=p.kode)
        p.refresh_from_db()
        self.assertEqual(p.status, S.PROSES)               # tertahan: Surat Tugas T1 belum ada


@override_settings(STORAGES=_STORAGES_MEMORI)
class IzinPrinsipMembukaJalurTests(_Basis, TestCase):
    def di_bpsdm(self, tipe):
        p = self.isi_formulir(tipe)
        self.kirim(p)
        self.unor_teruskan(p)
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1"}, kode=p.kode)
        p.refresh_from_db()
        self.assertEqual(p.status, S.PROSES_BPSDM)
        return p

    def unggah(self, p, jenis, tanggal=True):
        data = {"jenis": jenis, "file": SimpleUploadedFile(f"{jenis}.pdf", PDF, content_type="application/pdf")}
        if tanggal:
            data["tanggal_surat"] = date.today().isoformat()
        self.login(self.admin_bpsdm)
        return self.client.post(reverse("bpsdm:upload_dokumen", kwargs={"kode": p.kode}), data, follow=True)

    def _izin_prinsip_membuka_jalur(self, tipe):
        p = self.di_bpsdm(tipe)
        self.assertEqual(p.status_surat_tugas, "")
        self.unggah(p, "izin_prinsip")
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.MENUNGGU)
        dok = DokumenBpsdm.objects.get(pengajuan=p, jenis="izin_prinsip")
        self.assertEqual(dok.tanggal_surat, date.today())      # Tanggal Surat Izin Prinsip tersimpan
        self.assertEqual(p.status, S.PROSES_BPSDM)

    def test_izin_prinsip_membuka_jalur_pada_t2p(self):
        self._izin_prinsip_membuka_jalur("T2P")

    def test_izin_prinsip_membuka_jalur_pada_t2l(self):
        self._izin_prinsip_membuka_jalur("T2L")

    def test_izin_prinsip_tanpa_tanggal_surat_ditolak_dan_jalur_tetap_tertutup(self):
        p = self.di_bpsdm("T2P")
        resp = self.unggah(p, "izin_prinsip", tanggal=False)
        self.assertContains(resp, "Tanggal Surat")
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, "")
        self.assertFalse(DokumenBpsdm.objects.filter(pengajuan=p, jenis="izin_prinsip").exists())

    def test_tanggal_surat_di_masa_depan_ditolak(self):
        p = self.di_bpsdm("T2P")
        self.login(self.admin_bpsdm)
        self.client.post(reverse("bpsdm:upload_dokumen", kwargs={"kode": p.kode}), {
            "jenis": "izin_prinsip", "tanggal_surat": (date.today() + timedelta(days=3)).isoformat(),
            "file": SimpleUploadedFile("ip.pdf", PDF, content_type="application/pdf"),
        })
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, "")

    def test_dokumen_bpsdm_lain_tidak_membuka_jalur(self):
        p = self.di_bpsdm("T2P")
        self.unggah(p, "ikatan_dinas_ttd", tanggal=False)
        self.assertTrue(DokumenBpsdm.objects.filter(pengajuan=p, jenis="ikatan_dinas_ttd").exists())
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, "")

    def test_mengganti_izin_prinsip_tidak_membuka_ulang_atau_menimpa_status(self):
        p = self.di_bpsdm("T2P")
        self.unggah(p, "izin_prinsip")
        Pengajuan.objects.filter(pk=p.pk).update(status_surat_tugas=SS.DIKIRIM)
        self.unggah(p, "izin_prinsip")                         # ganti berkas sebelum diteruskan
        p.refresh_from_db()
        self.assertEqual(p.status_surat_tugas, SS.DIKIRIM)

    def test_bpsdm_dapat_meneruskan_tanpa_menunggu_surat_tugas(self):
        for tipe in TIPE2:
            p = self.di_bpsdm(tipe)
            self.unggah(p, "izin_prinsip")
            self.bpsdm_teruskan(p)
            p.refresh_from_db()
            self.assertEqual(p.status, S.PROSES_PAKLN, tipe)
            self.assertEqual(p.status_surat_tugas, SS.MENUNGGU, tipe)   # belum dikirim Admin Unor
            # bersihkan agar iterasi berikutnya (satu pengajuan aktif per pegawai) tidak terblokir
            Pengajuan.objects.filter(pk=p.pk).update(status=S.DIBATALKAN)

    def test_pengajuan_tipe_1_tidak_terpengaruh(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.unor_teruskan(p)
        p.refresh_from_db()
        self.assertEqual((p.status, p.status_surat_tugas), (S.PROSES_PAKLN, ""))
