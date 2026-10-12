"""
Validasi unggahan "hanya PDF" — dipakai di SEMUA tempat pengguna mengunggah dokumen
(dokumen pengajuan, dokumen pendukung, laporan PDLN, dokumen kepegawaian, dan
halaman demo `fileupload`).

Tiga pemeriksaan di server (validasi di browser hanya kenyamanan, mudah dilewati):
1. ekstensi nama berkas harus `.pdf`;
2. MIME type kiriman klien harus `application/pdf`;
3. isi berkas harus diawali tanda tangan PDF (`%PDF-`), sehingga berkas lain yang
   hanya diganti nama menjadi `.pdf` tetap ditolak.

Template Dokumen (pdf/docx) dan impor kalender libur (xlsx/csv) sengaja TIDAK memakai
validator ini: keduanya bukan dokumen pengajuan, dan formatnya memang bukan PDF.
"""

from django.core.exceptions import ValidationError

PDF_MIME = "application/pdf"
PDF_ACCEPT = ".pdf,application/pdf"  # untuk atribut `accept` pada <input type="file">
_PDF_MAGIC = b"%PDF-"

PESAN_BUKAN_PDF = "Hanya berkas PDF (.pdf) yang diperbolehkan."
PESAN_ISI_BUKAN_PDF = "Isi berkas tidak dikenali sebagai PDF yang valid."
KODE_BUKAN_PDF = "bukan_pdf"


def error_pdf(berkas):
    """Pesan error bila `berkas` bukan PDF yang sah; None bila sah (atau kosong)."""
    if not berkas:
        return None
    nama = (getattr(berkas, "name", "") or "").lower()
    if not nama.endswith(".pdf"):
        return PESAN_BUKAN_PDF
    if (getattr(berkas, "content_type", "") or "").lower() != PDF_MIME:
        return PESAN_BUKAN_PDF
    try:
        berkas.seek(0)
        kepala = berkas.read(len(_PDF_MAGIC))
        berkas.seek(0)
    except Exception:  # noqa: BLE001 - berkas tak terbaca = tidak valid
        return PESAN_ISI_BUKAN_PDF
    if kepala != _PDF_MAGIC:
        return PESAN_ISI_BUKAN_PDF
    return None


def validate_pdf(berkas):
    """Validator Django untuk field berkas (form/serializer)."""
    pesan = error_pdf(berkas)
    if pesan:
        raise ValidationError(pesan, code=KODE_BUKAN_PDF)


def periksa_pdf(request, berkas):
    """Untuk view yang membaca `request.FILES` langsung (tanpa form): kembalikan
    pesan error (atau None). Bila ditolak, request ditandai agar
    `paspor.middleware.UnggahDitolakMiddleware` mengubah status response menjadi 400."""
    pesan = error_pdf(berkas)
    if pesan:
        tandai_ditolak(request)
    return pesan


def tandai_ditolak(request):
    request.unggah_ditolak = True
