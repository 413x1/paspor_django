"""Pembatasan semua unggahan dokumen menjadi PDF saja (paspor/validators.py)."""

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import DokumenKepegawaian
from fileupload.forms import PdfUploadForm
from paspor.middleware import UnggahDitolakMiddleware
from paspor.validators import PESAN_BUKAN_PDF, PESAN_ISI_BUKAN_PDF, error_pdf, periksa_pdf

from .forms import (
    DokumenBkoForm, DokumenPaklnForm, DokumenPegawaiForm, DokumenTemplateForm, DokumenUnorForm,
    DokumenBpsdmForm, ImporHariLiburForm,
)
from .models import DokumenPegawai, DokumenUnorPendukung, DokumenPaklnPendukung, Pengajuan
from .tests import _AlurMixin

PDF = b"%PDF-1.4\n%contoh isi pdf\n"

# Penyimpanan berkas di memori: unggahan yang lolos tidak menyentuh S3 saat tes.
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}


def berkas(nama="a.pdf", isi=PDF, tipe="application/pdf"):
    return SimpleUploadedFile(nama, isi, content_type=tipe)


class ErrorPdfTests(SimpleTestCase):
    def test_pdf_sah_diterima(self):
        self.assertIsNone(error_pdf(berkas()))
        self.assertIsNone(error_pdf(berkas("LAPORAN.PDF")))   # ekstensi tak peka huruf besar
        self.assertIsNone(error_pdf(None))                    # tidak ada berkas: bukan urusan validator

    def test_ekstensi_bukan_pdf_ditolak(self):
        for nama in ("a.docx", "a.png", "a.exe", "a.pdf.exe", "a", "a.pdf.txt"):
            self.assertEqual(error_pdf(berkas(nama)), PESAN_BUKAN_PDF, nama)

    def test_mime_bukan_pdf_ditolak(self):
        for tipe in ("image/png", "application/octet-stream", "text/plain", ""):
            self.assertEqual(error_pdf(berkas(tipe=tipe)), PESAN_BUKAN_PDF, tipe)

    def test_isi_bukan_pdf_ditolak_walau_nama_dan_mime_pdf(self):
        self.assertEqual(error_pdf(berkas(isi=b"MZ\x90\x00 ini executable")), PESAN_ISI_BUKAN_PDF)
        self.assertEqual(error_pdf(berkas(isi=b"<html>bukan pdf</html>")), PESAN_ISI_BUKAN_PDF)
        self.assertEqual(error_pdf(berkas(isi=b"")), PESAN_ISI_BUKAN_PDF)

    def test_posisi_baca_dikembalikan_ke_awal(self):
        f = berkas()
        error_pdf(f)
        self.assertEqual(f.read(), PDF)  # berkas tetap utuh untuk disimpan

    def test_periksa_pdf_menandai_request_bila_ditolak(self):
        request = RequestFactory().post("/x/")
        self.assertIsNone(periksa_pdf(request, berkas()))
        self.assertFalse(getattr(request, "unggah_ditolak", False))
        self.assertEqual(periksa_pdf(request, berkas("a.txt")), PESAN_BUKAN_PDF)
        self.assertTrue(request.unggah_ditolak)


class FormDokumenTests(TestCase):
    FORM = (DokumenPegawaiForm, DokumenUnorForm, DokumenBpsdmForm, DokumenBkoForm, DokumenPaklnForm)

    def _form(self, kelas, f):
        return kelas({"tanggal_surat": ""}, {"file": f})

    def test_semua_form_dokumen_menolak_non_pdf_dan_menerima_pdf(self):
        for kelas in self.FORM:
            for salah in (berkas("a.docx"), berkas("a.png", tipe="image/png"), berkas(isi=b"bukan pdf")):
                form = self._form(kelas, salah)
                self.assertFalse(form.is_valid(), (kelas.__name__, salah.name))
                self.assertIn(form.errors["file"][0], (PESAN_BUKAN_PDF, PESAN_ISI_BUKAN_PDF))
            form = self._form(kelas, berkas())
            self.assertTrue(form.is_valid(), (kelas.__name__, form.errors))

    def test_widget_hanya_menawarkan_pdf(self):
        for kelas in self.FORM:
            self.assertEqual(kelas().fields["file"].widget.attrs["accept"], ".pdf,application/pdf")

    def test_berkas_lama_tidak_divalidasi_ulang_saat_hanya_ubah_tanggal(self):
        # Berkas lama (mis. sebelum aturan ini ada) tetap boleh; hanya unggahan BARU yang dicek.
        dok = DokumenPegawai(jenis="cuti", file="pengajuan/lama.docx")
        form = DokumenPegawaiForm({"tanggal_surat": ""}, {}, instance=dok)
        self.assertTrue(form.is_valid(), form.errors)

    def test_pengecualian_template_dan_impor_kalender_tidak_diubah(self):
        from .models import DokumenTemplate
        izin = [v.allowed_extensions for v in DokumenTemplate._meta.get_field("file").validators
                if hasattr(v, "allowed_extensions")]
        self.assertEqual(izin, [["pdf", "docx"]])   # Template Dokumen tetap boleh docx
        self.assertNotIn("accept", DokumenTemplateForm().fields["file"].widget.attrs)
        impor = ImporHariLiburForm.base_fields["berkas"]
        self.assertEqual(impor.widget.attrs["accept"], ".xlsx,.csv")

    def test_form_demo_fileupload_ikut_memeriksa_isi_berkas(self):
        self.assertTrue(PdfUploadForm({}, {"file": berkas()}).is_valid())
        self.assertFalse(PdfUploadForm({}, {"file": berkas(isi=b"bukan pdf")}).is_valid())
        self.assertFalse(PdfUploadForm({}, {"file": berkas("a.docx")}).is_valid())


class MiddlewareTests(SimpleTestCase):
    def _jalan(self, status, ditandai):
        from django.http import HttpResponse

        def view(request):
            request.unggah_ditolak = ditandai
            return HttpResponse("x", status=status)
        return UnggahDitolakMiddleware(view)(RequestFactory().post("/x/")).status_code

    def test_200_menjadi_400_hanya_bila_ditandai(self):
        self.assertEqual(self._jalan(200, True), 400)
        self.assertEqual(self._jalan(200, False), 200)
        self.assertEqual(self._jalan(302, True), 302)   # redirect dibiarkan


@override_settings(STORAGES=_STORAGES_MEMORI)
class UnggahDokumenViewTests(_AlurMixin, TestCase):
    """Unggah lewat halaman: non-PDF ditolak dengan status 400 dan tidak tersimpan."""

    def _unggah(self, user, url_name, f, **data):
        self.client.force_login(user)
        return self.client.post(
            reverse(url_name, args=[self.pengajuan.kode]), {"file": f, **data}
        )

    def test_pegawai_dokumen_pengajuan(self):
        from . import persyaratan
        DokumenPegawai.objects.filter(pengajuan=self.pengajuan).delete()
        jenis = persyaratan.daftar_syarat(self.pengajuan, "pegawai")[0].jenis
        r = self._unggah(self.pegawai, "pegawai:upload_dokumen", berkas("a.docx"), jenis=jenis)
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, PESAN_BUKAN_PDF, status_code=400)
        self.assertFalse(DokumenPegawai.objects.filter(pengajuan=self.pengajuan).exists())

        r = self._unggah(self.pegawai, "pegawai:upload_dokumen", berkas(isi=b"bukan pdf"), jenis=jenis)
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, PESAN_ISI_BUKAN_PDF, status_code=400)

    def test_pegawai_pdf_sah_tersimpan(self):
        from . import persyaratan
        DokumenPegawai.objects.filter(pengajuan=self.pengajuan).delete()
        syarat = next(s for s in persyaratan.daftar_syarat(self.pengajuan, "pegawai") if not s.tanggal_surat)
        r = self._unggah(self.pegawai, "pegawai:upload_dokumen", berkas(), jenis=syarat.jenis)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(DokumenPegawai.objects.filter(pengajuan=self.pengajuan, jenis=syarat.jenis).exists())

    def test_pendukung_unor_dan_pakln(self):
        Pengajuan.objects.filter(pk=self.pengajuan.pk).update(
            status=Pengajuan.Status.PROSES, preview_unor_agree=True,
        )
        r = self._unggah(self.admin_unor, "unor:upload_dokumen", berkas("a.xlsx"), pendukung_upload="1")
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, PESAN_BUKAN_PDF, status_code=400)
        self.assertFalse(DokumenUnorPendukung.objects.get(pengajuan=self.pengajuan).file.name.endswith("a.xlsx"))

        Pengajuan.objects.filter(pk=self.pengajuan.pk).update(
            status=Pengajuan.Status.PROSES_PAKLN, preview_pakln_agree=True,
        )
        r = self._unggah(self.admin_pakln, "pakln:upload_dokumen", berkas("a.png", tipe="image/png"), pendukung_upload="1")
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, PESAN_BUKAN_PDF, status_code=400)
        self.assertFalse(DokumenPaklnPendukung.objects.get(pengajuan=self.pengajuan).file)

    def test_pendukung_pdf_sah_diterima(self):
        Pengajuan.objects.filter(pk=self.pengajuan.pk).update(
            status=Pengajuan.Status.PROSES, preview_unor_agree=True,
        )
        DokumenUnorPendukung.objects.filter(pengajuan=self.pengajuan).update(file="")
        r = self._unggah(self.admin_unor, "unor:upload_dokumen", berkas(), pendukung_upload="1")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(DokumenUnorPendukung.objects.get(pengajuan=self.pengajuan).file)

    def test_halaman_unggah_memuat_accept_pdf_dan_skrip_validasi(self):
        self.client.force_login(self.pegawai)
        html = self.client.get(reverse("pegawai:upload_dokumen", args=[self.pengajuan.kode])).content.decode()
        self.assertIn('accept=".pdf,application/pdf" data-pdf-only', html)
        self.assertIn("function berkasPdfValid", html)


@override_settings(STORAGES=_STORAGES_MEMORI)
class ProfilDanLaporanTests(_AlurMixin, TestCase):
    def test_profil_dokumen_kepegawaian_non_pdf_ditolak(self):
        from accounts.models import DokumenKepegawaian
        jenis = DokumenKepegawaian._meta.get_field("jenis").choices[0][0] if DokumenKepegawaian._meta.get_field("jenis").choices else None
        self.client.force_login(self.pegawai)
        r = self.client.post(reverse("profil"), {"aksi": "unggah_dokumen", "jenis": jenis, "file": berkas("a.jpg", tipe="image/jpeg")},
                             follow=True)
        self.assertContains(r, PESAN_BUKAN_PDF)
        self.assertFalse(DokumenKepegawaian.objects.filter(user=self.pegawai).exists())
        self.client.post(reverse("profil"), {"aksi": "unggah_dokumen", "jenis": jenis, "file": berkas()})
        self.assertTrue(DokumenKepegawaian.objects.filter(user=self.pegawai).exists())

    def test_laporan_pdln_non_pdf_ditolak(self):
        from .models import LaporanPdln
        p = Pengajuan.objects.create(
            pegawai=self.pegawai, form_saved=True, jenis_perjalanan="pdln", tipe_pdln="T1",
            status=Pengajuan.Status.SELESAI,
        )
        self.client.force_login(self.pegawai)
        isi = {"action": "submit", "tujuan_kegiatan": "a", "materi_kegiatan": "b", "tindak_lanjut": "c", "dampak_rekomendasi": "d",
               "estimasi_biaya": "1.000.000", "realisasi_biaya": "900.000"}
        r = self.client.post(reverse("pegawai:laporan_form", args=[p.kode]), {**isi, "dokumen_laporan": berkas("laporan.docx")})
        self.assertContains(r, PESAN_BUKAN_PDF, status_code=400)   # halaman form dirender ulang: 400
        self.assertFalse(LaporanPdln.objects.filter(pengajuan=p).exists())
        self.client.post(reverse("pegawai:laporan_form", args=[p.kode]), {**isi, "dokumen_laporan": berkas("laporan.pdf")})
        self.assertTrue(LaporanPdln.objects.filter(pengajuan=p).exists())
