"""
Helper bersama halaman unggah dokumen per tahap (Pegawai, Admin Unor,
Admin BPSDM, Admin Biro PAKLN) — membaca registri `persyaratan` sehingga
setiap jenis/tipe perjalanan memakai satu jalur kode yang sama.
"""

from django.contrib import messages
from django.shortcuts import redirect

from logs.models import ActivityLog
from logs.utils import record_activity

from . import persyaratan
from .forms import DokumenBpsdmForm, DokumenPaklnForm, DokumenPegawaiForm, DokumenUnorForm
from .models import DokumenTemplate

FORM_TAHAP = {
    "pegawai": DokumenPegawaiForm,
    "unor": DokumenUnorForm,
    "bpsdm": DokumenBpsdmForm,
    "pakln": DokumenPaklnForm,
}

_FLAG_TEMPLATE = {
    "pegawai": "untuk_pegawai",
    "unor": "untuk_admin_unor",
    "bpsdm": "untuk_admin_bpsdm",
}


def konteks_dokumen(pengajuan, tahap):
    """Context bersama: daftar syarat beserta dokumen terunggah,
    kelengkapan, dan daftar dokumen wajib yang kurang."""
    dok_map = persyaratan.dokumen_map(pengajuan, tahap)
    syarat = persyaratan.syarat_untuk(pengajuan, tahap, dok_map)
    kurang = [b["label"] for b in syarat if b["wajib"] and not b["dok"]]
    return {
        "syarat_list": syarat,
        "dokumen_map": dok_map,
        "lengkap": not kurang,
        "dokumen_kurang": kurang,
    }


def templates_untuk(user, pengajuan, tahap):
    flag = _FLAG_TEMPLATE.get(tahap)
    if not flag:
        return []
    return [
        t for t in DokumenTemplate.objects.filter(aktif=True, **{flag: True}).prefetch_related("unit_organisasi")
        if t.relevan_untuk(user, kategori=pengajuan.kategori, jenis_perjalanan=pengajuan.jenis_perjalanan)
    ]


def _catat(request, pengajuan, aktivitas, deskripsi, berhasil=True, detail=""):
    """Catat unggah/hapus dokumen ke Log Sistem (lihat wiki/instructions/SYSTEM_LOGGING.MD)."""
    record_activity(
        request, aktivitas, f"{deskripsi} — {pengajuan.kode}",
        status=ActivityLog.Status.BERHASIL if berhasil else ActivityLog.Status.GAGAL,
        target_type="pengajuan", target_id=pengajuan.kode, detail=detail,
    )


def proses_unggah(request, pengajuan, tahap, url_name):
    """Tangani POST unggah satu berkas (`jenis` + `file` [+ `tanggal_surat`]).
    Mengembalikan redirect bila berhasil, None bila gagal (pesan error
    sudah ditambahkan)."""
    jenis = request.POST.get("jenis")
    if not persyaratan.jenis_valid(pengajuan, tahap, jenis):
        messages.error(request, "Jenis dokumen tidak valid untuk pengajuan ini.")
        _catat(request, pengajuan, ActivityLog.Aktivitas.UNGGAH_DOKUMEN, "Mengunggah dokumen",
               berhasil=False, detail="Jenis dokumen tidak valid")
        return None
    model = persyaratan.TAHAP_MODEL[tahap]
    existing = model.objects.filter(pengajuan=pengajuan, jenis=jenis).first()
    form = FORM_TAHAP[tahap](request.POST, request.FILES, instance=existing)
    if not form.is_valid():
        if "tanggal_surat" in form.errors:
            messages.error(request, form.errors["tanggal_surat"][0] + ".")
        else:
            messages.error(request, "Gagal mengunggah dokumen. Periksa kembali berkas Anda.")
        _catat(request, pengajuan, ActivityLog.Aktivitas.UNGGAH_DOKUMEN, f"Mengunggah dokumen {jenis}",
               berhasil=False, detail="Validasi gagal: " + ", ".join(form.errors))  # nama field saja
        return None
    if persyaratan.jenis_perlu_tanggal_surat(pengajuan, tahap, jenis) and not form.cleaned_data.get("tanggal_surat"):
        messages.error(request, "Isi Tanggal Surat untuk dokumen ini.")
        _catat(request, pengajuan, ActivityLog.Aktivitas.UNGGAH_DOKUMEN, f"Mengunggah dokumen {jenis}",
               berhasil=False, detail="Tanggal Surat belum diisi")
        return None
    dok = form.save(commit=False)
    dok.pengajuan = pengajuan
    dok.jenis = jenis
    dok.save()
    _catat(request, pengajuan, ActivityLog.Aktivitas.UNGGAH_DOKUMEN, f"Mengunggah dokumen {jenis}")
    messages.success(request, "Dokumen berhasil diunggah.")
    return redirect(url_name, kode=pengajuan.kode)


def hapus(request, pengajuan, tahap, jenis):
    if request.method != "POST":
        return
    model = persyaratan.TAHAP_MODEL[tahap]
    dok = model.objects.filter(pengajuan=pengajuan, jenis=jenis).first()
    if dok:
        dok.file.delete(save=False)
        dok.delete()
        _catat(request, pengajuan, ActivityLog.Aktivitas.HAPUS_DOKUMEN, f"Menghapus dokumen {jenis}")
        messages.success(request, "Dokumen berhasil dihapus.")
