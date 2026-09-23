"""Util murni-Python untuk menyiapkan data Nota Dinas (ND) sebelum dikirim
ke halaman pratinjau — PDF-nya sendiri dibangun di browser memakai jsPDF
(lihat static/js/nota_dinas_pdf.js dan templates/pakln/preview_nd.html),
mengikuti wiki/instructions/GENERATE_ND.MD.
"""

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


def nama_ringkas_pengajuan(pengajuan_list):
    nama_pertama = pengajuan_list[0].pegawai.profile.nama
    if len(pengajuan_list) > 1:
        return f"{nama_pertama} dkk"
    return nama_pertama


def build_nd_context(pengajuan_list):
    """Susun data siap-JSON untuk mengisi form pratinjau + jsPDF di
    `preview_nd.html`, dari `pengajuan_list` (list Pengajuan yang sudah
    divalidasi berasal dari 1 unit organisasi/negara/maksud yang sama)."""
    first = pengajuan_list[0]
    sumber_biaya_list = []
    for p in pengajuan_list:
        nama_sumber = str(p.sumber_pembiayaan) if p.sumber_pembiayaan else ""
        if nama_sumber and nama_sumber not in sumber_biaya_list:
            sumber_biaya_list.append(nama_sumber)

    employees = []
    for idx, p in enumerate(pengajuan_list, start=1):
        profile = p.pegawai.profile
        employees.append({
            "no": idx,
            "nama": profile.nama,
            "nip": profile.nip,
            "jabatan": profile.jabatan,
            "periode": format_periode(p.tgl_berangkat, p.tgl_kembali),
            "h_kerja": p.jumlah_hari_kerja or "-",
            "h_kalender": p.jumlah_hari_kalender or "-",
        })

    return {
        "nama_display": nama_ringkas_pengajuan(pengajuan_list),
        "negara_display": first.tujuan_negara_display,
        "keperluan": first.maksud,
        "nama_unor": first.pegawai.profile.unit_organisasi.name,
        "sumber_biaya_display": ", ".join(sumber_biaya_list) or "-",
        "employees": employees,
    }
