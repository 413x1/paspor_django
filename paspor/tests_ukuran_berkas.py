"""Batas ukuran unggahan: 2 MB untuk semua berkas, 10 MB untuk Laporan PDLN
(paspor.validators)."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from fileupload.forms import PdfUploadForm
from paspor.validators import MB, error_pdf, validate_pdf, validate_pdf_laporan
from pengajuan.forms import DokumenTemplateForm, ImporHariLiburForm


def pdf(ukuran, nama="dok.pdf"):
    isi = b"%PDF-1.4\n" + b"0" * (ukuran - 9)
    return SimpleUploadedFile(nama, isi, content_type="application/pdf")


class BatasUkuranTests(SimpleTestCase):
    def test_pdf_umum_maks_2mb(self):
        validate_pdf(pdf(2 * MB))  # tepat 2 MB masih boleh
        with self.assertRaisesMessage(ValidationError, "Ukuran berkas maksimal 2 MB."):
            validate_pdf(pdf(2 * MB + 1))

    def test_laporan_pdln_maks_10mb(self):
        validate_pdf_laporan(pdf(5 * MB))
        validate_pdf_laporan(pdf(10 * MB))
        with self.assertRaisesMessage(ValidationError, "Ukuran berkas maksimal 10 MB."):
            validate_pdf_laporan(pdf(10 * MB + 1))

    def test_view_tanpa_form_ikut_dibatasi(self):
        # periksa_pdf (dokumen pendukung & dokumen kepegawaian) memakai error_pdf.
        self.assertIsNone(error_pdf(pdf(MB)))
        self.assertEqual(error_pdf(pdf(3 * MB)), "Ukuran berkas maksimal 2 MB.")

    def test_bukan_pdf_tetap_ditolak_lebih_dulu(self):
        berkas = SimpleUploadedFile("x.docx", b"a" * (3 * MB), content_type="application/msword")
        self.assertEqual(error_pdf(berkas), "Hanya berkas PDF (.pdf) yang diperbolehkan.")

    def test_form_demo_unggah(self):
        form = PdfUploadForm(files={"file": pdf(3 * MB)})
        self.assertFalse(form.is_valid())
        self.assertIn("Ukuran berkas maksimal 2 MB.", form.errors["file"])

    def test_template_dokumen_dan_impor_kalender(self):
        docx = SimpleUploadedFile("t.docx", b"a" * (3 * MB), content_type="application/octet-stream")
        form = DokumenTemplateForm(data={"nama": "T", "untuk_pegawai": "on"}, files={"file": docx})
        self.assertFalse(form.is_valid())
        self.assertIn("Ukuran berkas maksimal 2 MB.", form.errors["file"])

        csv = SimpleUploadedFile("libur.csv", b"a" * (3 * MB), content_type="text/csv")
        form = ImporHariLiburForm(files={"berkas": csv})
        self.assertFalse(form.is_valid())
        self.assertIn("berkas", form.errors)
