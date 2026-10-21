"""
Validasi unggahan "hanya PDF" — dipakai di SEMUA tempat pengguna mengunggah dokumen
(dokumen pengajuan, dokumen pendukung, laporan PDLN, dokumen kepegawaian, dan
halaman demo `fileupload`).

Empat pemeriksaan di server (validasi di browser hanya kenyamanan, mudah dilewati):
1. ekstensi nama berkas harus `.pdf`;
2. MIME type kiriman klien harus `application/pdf`;
3. isi berkas harus diawali tanda tangan PDF (`%PDF-`), sehingga berkas lain yang
   hanya diganti nama menjadi `.pdf` tetap ditolak;
4. ukuran berkas maksimal **2 MB** (`MAKS_UKURAN`), kecuali Laporan PDLN **10 MB**
   (`MAKS_UKURAN_LAPORAN`, lewat `validate_pdf_laporan`).

Template Dokumen (pdf/docx) dan impor kalender libur (xlsx/csv) sengaja TIDAK memakai
validator PDF: keduanya bukan dokumen pengajuan, dan formatnya memang bukan PDF. Batas
ukuran 2 MB tetap berlaku lewat `validate_ukuran`.
"""

from django.core.exceptions import ValidationError

PDF_MIME = "application/pdf"
PDF_ACCEPT = ".pdf,application/pdf"  # untuk atribut `accept` pada <input type="file">
_PDF_MAGIC = b"%PDF-"

PESAN_BUKAN_PDF = "Hanya berkas PDF (.pdf) yang diperbolehkan."
PESAN_ISI_BUKAN_PDF = "Isi berkas tidak dikenali sebagai PDF yang valid."
KODE_BUKAN_PDF = "bukan_pdf"
KODE_TERLALU_BESAR = "terlalu_besar"

MB = 1024 * 1024
MAKS_UKURAN = 2 * MB            # semua unggahan
MAKS_UKURAN_LAPORAN = 10 * MB   # khusus Dokumen Laporan PDLN


def _label_mb(maks):
    return f"{maks // MB} MB"


def error_ukuran(berkas, maks=MAKS_UKURAN):
    """Pesan error bila `berkas` melebihi `maks` byte; None bila tidak (atau kosong)."""
    if berkas and (getattr(berkas, "size", 0) or 0) > maks:
        return f"Ukuran berkas maksimal {_label_mb(maks)}."
    return None


def validate_ukuran(berkas, maks=MAKS_UKURAN):
    """Validator Django batas ukuran (default 2 MB) untuk berkas non-PDF."""
    pesan = error_ukuran(berkas, maks)
    if pesan:
        raise ValidationError(pesan, code=KODE_TERLALU_BESAR)


def error_pdf(berkas, maks=MAKS_UKURAN):
    """Pesan error bila `berkas` bukan PDF yang sah atau melebihi `maks` byte; None
    bila sah (atau kosong)."""
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
    return error_ukuran(berkas, maks)


def validate_pdf(berkas, maks=MAKS_UKURAN):
    """Validator Django untuk field berkas PDF (form/serializer), maks. 2 MB."""
    pesan = error_pdf(berkas, maks)
    if pesan:
        kode = KODE_TERLALU_BESAR if pesan == error_ukuran(berkas, maks) else KODE_BUKAN_PDF
        raise ValidationError(pesan, code=kode)


def validate_pdf_laporan(berkas):
    """Validator Dokumen Laporan PDLN — PDF, maks. 10 MB."""
    validate_pdf(berkas, MAKS_UKURAN_LAPORAN)


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
