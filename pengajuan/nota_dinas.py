"""Generate dokumen Nota Dinas (ND) — Admin Biro PAKLN.

Mengisi template docx pada `static/templateND/` dengan data pegawai/
pengajuan terpilih, lalu mengonversinya ke PDF (satu-satunya output yang
disimpan — lihat wiki/instructions/GENERATE_ND.MD). Konversi PDF memakai
`docx2pdf`, yang menjalankan Microsoft Word lewat COM automation — hanya
berjalan di Windows dengan MS Word terpasang.
"""

import tempfile
from copy import deepcopy
from pathlib import Path

from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from docx import Document
from docx2pdf import convert as docx2pdf_convert

TEMPLATE_PATH = Path(django_settings.BASE_DIR) / "static" / "templateND" / "ND Kabag KLN ke Karo PAKLN_Non Dinas.docx"

_MONTHS_ID = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def format_tanggal_indo(tgl):
    if not tgl:
        return "-"
    return f"{tgl.day} {_MONTHS_ID[tgl.month]} {tgl.year}"


def format_periode(tgl_berangkat, tgl_kembali):
    return f"{format_tanggal_indo(tgl_berangkat)} s.d. {format_tanggal_indo(tgl_kembali)}"


def _replace_in_paragraph(paragraph, mapping):
    """Ganti teks pada `paragraph` sesuai `mapping` (old -> new), lintas
    run (satu potongan teks berformat di Word bisa terpecah jadi beberapa
    run). Format run pertama yang cocok dipertahankan; run selanjutnya
    yang ikut terpakai teksnya dikosongkan."""
    runs = paragraph.runs
    if not runs:
        return
    original = "".join(r.text for r in runs)
    text = original
    for old, new in mapping.items():
        if old in text:
            text = text.replace(old, str(new))
    if text == original:
        return
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""


def _iter_paragraphs(container):
    """Iterasi seluruh paragraph pada `container` (Document atau _Cell),
    termasuk yang berada di dalam tabel (dan tabel bersarang)."""
    for p in container.paragraphs:
        yield p
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_paragraphs(cell)


def _replace_everywhere(document, mapping):
    for paragraph in _iter_paragraphs(document):
        _replace_in_paragraph(paragraph, mapping)


def _is_data_pegawai_table(table):
    if len(table.rows) < 2 or len(table.columns) < 4:
        return False
    header = [c.text.strip() for c in table.rows[0].cells]
    return header[:2] == ["No.", "Nama/NIP"]


def _fill_data_pegawai_table(table, pengajuan_list):
    """Ganti 2 baris contoh pada tabel "Data Pegawai" dengan satu baris
    per pengajuan terpilih (data pegawai bisa 1 orang atau lebih)."""
    template_row = table.rows[1]._tr
    proto = deepcopy(template_row)

    for row in list(table.rows[1:]):
        row._tr.getparent().remove(row._tr)

    tbl = table._tbl
    for idx, pengajuan in enumerate(pengajuan_list, start=1):
        new_tr = deepcopy(proto)
        tbl.append(new_tr)
        row = table.rows[-1]
        profile = pengajuan.pegawai.profile
        _replace_in_paragraph(row.cells[0].paragraphs[0], {"1.": f"{idx}."})
        for p in row.cells[1].paragraphs:
            _replace_in_paragraph(p, {"[nama]": profile.nama, "[nip]": profile.nip})
        for p in row.cells[2].paragraphs:
            _replace_in_paragraph(p, {"[jabatan]": profile.jabatan})
        for p in row.cells[3].paragraphs:
            _replace_in_paragraph(p, {
                "[tanggal berangkat s.d. tanggal pulang]": format_periode(
                    pengajuan.tgl_berangkat, pengajuan.tgl_kembali
                ),
                "[h_kerja]": str(pengajuan.jumlah_hari_kerja or "-"),
                "[h_kalender]": str(pengajuan.jumlah_hari_kalender or "-"),
            })


def nama_ringkas_pengajuan(pengajuan_list):
    nama_pertama = pengajuan_list[0].pegawai.profile.nama
    if len(pengajuan_list) > 1:
        return f"{nama_pertama} dkk"
    return nama_pertama


def generate_nota_dinas_pdf(pengajuan_list, pengaturan):
    """Isi template ND untuk `pengajuan_list` (list Pengajuan, sudah
    divalidasi berasal dari 1 unit organisasi/negara/maksud yang sama) dan
    kembalikan bytes PDF hasilnya."""
    document = Document(str(TEMPLATE_PATH))

    first = pengajuan_list[0]
    nama_display = nama_ringkas_pengajuan(pengajuan_list)
    negara_display = first.tujuan_negara_display
    nama_unor = first.pegawai.profile.unit_organisasi.name

    sumber_biaya_list = []
    for p in pengajuan_list:
        nama_sumber = str(p.sumber_pembiayaan) if p.sumber_pembiayaan else ""
        if nama_sumber and nama_sumber not in sumber_biaya_list:
            sumber_biaya_list.append(nama_sumber)
    sumber_biaya_display = ", ".join(sumber_biaya_list) or "-"

    for table in document.tables:
        if _is_data_pegawai_table(table):
            _fill_data_pegawai_table(table, pengajuan_list)

    mapping = {
        "[nama/nama dkk]": nama_display,
        "[nama]": nama_display,
        "[negara tujuan]": negara_display,
        "[tanggal bulan tahun]": " ",
        "[Nama Pejabat]": pengaturan.nama_pejabat_plt_kabag_kln or " ",
        "[keperluan]": first.maksud,
        "[nama unor]": nama_unor,
        "[sumber biaya]": sumber_biaya_display,
        "Plt. Kepala Bagian Kerja Sama Luar Negeri": pengaturan.jabatan_plt_kabag_kln,
        "Ketua Tim AKI": pengaturan.paraf_ketua_tim_aki,
        "Reiza Setiawan": pengaturan.nama_karo_pakln,
        "Katim AKI": pengaturan.paraf_katim_aki_nd2,
        "Plt. Kabag KLN": pengaturan.paraf_plt_kabag_kln_nd2,
    }
    _replace_everywhere(document, mapping)

    with tempfile.TemporaryDirectory() as tmp_dir:
        docx_path = Path(tmp_dir) / "nd.docx"
        pdf_path = Path(tmp_dir) / "nd.pdf"
        document.save(docx_path)
        docx2pdf_convert(str(docx_path), str(pdf_path))
        return pdf_path.read_bytes()


def build_nota_dinas_file(pengajuan_list, pengaturan, filename):
    pdf_bytes = generate_nota_dinas_pdf(pengajuan_list, pengaturan)
    return ContentFile(pdf_bytes, name=filename)
