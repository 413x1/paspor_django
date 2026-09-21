from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import role_required
from .forms import DokumenPegawaiForm, PengajuanForm
from .models import DokumenPegawai, DokumenTemplate, Pengajuan


def _active_pengajuan(user):
    """Pengajuan pegawai yang sedang berjalan (belum berstatus selesai).
    Meniru logika mockup: satu pengajuan aktif berjalan sampai selesai
    sebelum pegawai dapat memulai pengajuan baru."""
    return (
        Pengajuan.objects.filter(pegawai=user)
        .exclude(status=Pengajuan.Status.SELESAI)
        .order_by("-created_at")
        .first()
    )


@role_required("pegawai")
def beranda(request):
    aktif = _active_pengajuan(request.user)
    riwayat_qs = Pengajuan.objects.filter(pegawai=request.user).order_by("-created_at")
    if aktif:
        riwayat_qs = riwayat_qs.exclude(pk=aktif.pk)

    context = {
        "aktif": aktif,
        "riwayat": riwayat_qs,
        "profile": getattr(request.user, "profile", None),
    }
    return render(request, "pegawai/beranda.html", context)


@role_required("pegawai")
def formulir_pengajuan(request):
    """Tahap 2: Formulir Pengajuan. Jika pegawai sudah punya pengajuan aktif
    yang telah dikirim (status != belum), arahkan langsung ke tahap
    berikutnya alih-alih membuka ulang formulir."""
    aktif = _active_pengajuan(request.user)
    if aktif and aktif.status != Pengajuan.Status.BELUM:
        return redirect("pegawai:upload_dokumen", kode=aktif.kode)

    profile = getattr(request.user, "profile", None)

    if request.method == "POST":
        form = PengajuanForm(request.POST, instance=aktif, profile=profile)
        if form.is_valid():
            pengajuan = form.save(commit=False)
            pengajuan.pegawai = request.user
            pengajuan.kanal = Pengajuan.Kanal.WEB
            pengajuan.form_saved = True
            pengajuan.save()
            messages.success(request, "Formulir pengajuan berhasil disimpan.")
            return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)
    else:
        form = PengajuanForm(instance=aktif, profile=profile)

    return render(
        request,
        "pegawai/formulir.html",
        {"form": form, "profile": profile},
    )


@role_required("pegawai")
def upload_dokumen(request, kode):
    """Tahap 3: Unggah Dokumen — 4 direktori dokumen wajib sebelum
    pengajuan dapat dikirim ke Admin Unor (fungsi kirimKeUnor pada mockup)."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    if not pengajuan.form_saved:
        return redirect("pegawai:formulir_pengajuan")

    jenis_choices = DokumenPegawai.Jenis.choices
    dokumen_map = {d.jenis: d for d in pengajuan.dokumen_pegawai.all()}
    lengkap = len(dokumen_map) >= len(jenis_choices)

    templates = [
        t for t in DokumenTemplate.objects.filter(aktif=True, untuk_pegawai=True).prefetch_related("unit_organisasi")
        if t.relevan_untuk(request.user, kategori=pengajuan.kategori)
    ]

    if request.method == "POST":
        if "kirim" in request.POST:
            if not lengkap:
                messages.error(request, "Lengkapi seluruh dokumen sebelum mengirim ke Admin Unor.")
            elif not request.POST.get("agree"):
                messages.error(request, "Centang pernyataan kelengkapan dokumen terlebih dahulu.")
            else:
                pengajuan.status = Pengajuan.Status.PROSES
                pengajuan.submitted = True
                pengajuan.tgl_pengajuan = timezone.now().date()
                pengajuan.catatan_unor = ""
                pengajuan.save()
                messages.success(request, f"Pengajuan {pengajuan.kode} berhasil dikirim ke Admin Unor.")
                return redirect("pegawai:monitor_progres", kode=pengajuan.kode)
        else:
            jenis = request.POST.get("jenis")
            existing = dokumen_map.get(jenis)
            form = DokumenPegawaiForm(request.POST, request.FILES, instance=existing)
            if jenis in dict(jenis_choices) and form.is_valid():
                dok = form.save(commit=False)
                dok.pengajuan = pengajuan
                dok.jenis = jenis
                dok.save()
                messages.success(request, "Dokumen berhasil diunggah.")
                return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)
            else:
                messages.error(request, "Gagal mengunggah dokumen. Periksa kembali berkas Anda.")

    context = {
        "pengajuan": pengajuan,
        "jenis_choices": jenis_choices,
        "dokumen_map": dokumen_map,
        "lengkap": lengkap,
        "templates": templates,
    }
    return render(request, "pegawai/upload.html", context)


@role_required("pegawai")
def hapus_dokumen(request, kode, jenis):
    """Hapus salah satu dokumen yang sudah diunggah pegawai."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    if request.method == "POST":
        dok = pengajuan.dokumen_pegawai.filter(jenis=jenis).first()
        if dok:
            dok.file.delete(save=False)
            dok.delete()
            messages.success(request, "Dokumen berhasil dihapus.")
    return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)


@role_required("pegawai")
def monitor_progres(request, kode):
    """Tahap 4: Monitor Progres — timeline status pengajuan."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    if not pengajuan.submitted:
        return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)
    return render(request, "pegawai/monitor.html", {"pengajuan": pengajuan})
