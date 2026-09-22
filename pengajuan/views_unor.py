import csv

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from notifications.services import notify_approve_unor, notify_reject_unor

from .decorators import role_required
from .forms import DokumenUnorForm
from .models import DokumenTemplate, DokumenUnor, DokumenUnorPendukung, Pengajuan


def _scoped(request, qs=None):
    """Batasi queryset Pengajuan pada unit organisasi yang dikelola Admin
    Unor yang sedang login. Seorang Admin Unor hanya memproses pengajuan
    pegawai dari unit organisasi yang sama."""
    if qs is None:
        qs = Pengajuan.objects.all()
    if not request.user.unit_organisasi_id:
        return qs.none()
    return qs.filter(pegawai__profile__unit_organisasi_id=request.user.unit_organisasi_id)


@role_required("admin_unor")
def dashboard(request):
    """Tahap 2: Dasbor — ringkasan progres + tabel rincian pengajuan
    pegawai pada unit organisasi Admin Unor (status != belum)."""
    pengajuan_list = (
        _scoped(request)
        .exclude(status=Pengajuan.Status.BELUM)
        .select_related("pegawai__profile")
    )
    summary = {
        "total": pengajuan_list.count(),
        "proses": pengajuan_list.filter(status=Pengajuan.Status.PROSES).count(),
        "proses_pakln": pengajuan_list.filter(status=Pengajuan.Status.PROSES_PAKLN).count(),
        "selesai": pengajuan_list.filter(status=Pengajuan.Status.SELESAI).count(),
    }
    return render(request, "unor/dashboard.html", {"pengajuan_list": pengajuan_list, "summary": summary})


@role_required("admin_unor")
def preview(request, kode):
    """Tahap 3: Pratinjau Pengajuan dari Pegawai (read-only) + persetujuan
    sebelum lanjut ke tahap unggah dokumen administrasi."""
    pengajuan = get_object_or_404(
        _scoped(request).exclude(status=Pengajuan.Status.BELUM), kode=kode
    )
    if request.method == "POST" and "lanjutkan" in request.POST:
        pengajuan.preview_unor_agree = True
        pengajuan.save(update_fields=["preview_unor_agree"])
        return redirect("unor:upload_dokumen", kode=pengajuan.kode)

    if request.method == "POST" and "kembalikan" in request.POST:
        catatan = request.POST.get("catatan", "").strip()
        if not catatan:
            messages.error(request, "Isi catatan untuk pegawai sebelum mengembalikan pengajuan.")
        else:
            pengajuan.status = Pengajuan.Status.BELUM
            pengajuan.submitted = False
            pengajuan.preview_unor_agree = False
            pengajuan.catatan_unor = catatan
            pengajuan.save()
            notify_reject_unor(pengajuan, catatan)
            messages.success(
                request,
                f"Pengajuan {pengajuan.kode} dikembalikan ke pegawai beserta catatan.",
            )
            return redirect("unor:dashboard")

    return render(request, "unor/preview.html", {"pengajuan": pengajuan})


@role_required("admin_unor")
def upload_dokumen(request, kode):
    """Tahap 4: Unggah Dokumen Administrasi Unor, lalu meneruskan berkas
    ke Admin Biro PAKLN (fungsi teruskanKePakln pada mockup)."""
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    if not pengajuan.preview_unor_agree:
        return redirect("unor:preview", kode=kode)

    jenis_choices = DokumenUnor.Jenis.choices
    dokumen_map = {d.jenis: d for d in pengajuan.dokumen_unor.all()}
    pendukung, _ = DokumenUnorPendukung.objects.get_or_create(pengajuan=pengajuan)

    wajib_lengkap = len(dokumen_map) >= len(jenis_choices)
    lengkap = wajib_lengkap and pendukung.is_lengkap()

    templates = [
        t for t in DokumenTemplate.objects.filter(aktif=True, untuk_admin_unor=True).prefetch_related("unit_organisasi")
        if t.relevan_untuk(request.user, kategori=pengajuan.kategori)
    ]

    if request.method == "POST":
        if "teruskan" in request.POST:
            if not lengkap:
                messages.error(request, "Lengkapi seluruh dokumen administrasi Unor sebelum meneruskan berkas.")
            elif not request.POST.get("agree"):
                messages.error(request, "Centang pernyataan kelengkapan dokumen terlebih dahulu.")
            else:
                pengajuan.status = Pengajuan.Status.PROSES_PAKLN
                pengajuan.tgl_masuk_pakln = timezone.now().date()
                pengajuan.save()
                notify_approve_unor(pengajuan)
                messages.success(request, f"Pengajuan {pengajuan.kode} diteruskan ke Admin Biro PAKLN.")
                return redirect("unor:dashboard")
        elif "pendukung_upload" in request.POST:
            # Proses unggah berkas pendukung — berdiri sendiri, tidak
            # memerlukan checklist jenis sudah dicentang lebih dulu.
            file_obj = request.FILES.get("file")
            if not file_obj:
                messages.error(request, "Pilih berkas dokumen pendukung terlebih dahulu.")
            else:
                pendukung.file = file_obj
                pendukung.uploaded_at = timezone.now()
                pendukung.save(update_fields=["file", "uploaded_at"])
                messages.success(request, "Dokumen pendukung berhasil diunggah.")
                return redirect("unor:upload_dokumen", kode=kode)
        elif "pendukung_hapus" in request.POST:
            pendukung.file.delete(save=False)
            pendukung.file = ""
            pendukung.uploaded_at = None
            pendukung.save(update_fields=["file", "uploaded_at"])
            messages.success(request, "Berkas dokumen pendukung dihapus.")
            return redirect("unor:upload_dokumen", kode=kode)
        elif "toggle_pendukung" in request.POST:
            # Proses mencentang jenis — berdiri sendiri, tidak memerlukan
            # berkas diunggah ulang.
            kategori = request.POST.get("kategori")
            if kategori not in DokumenUnorPendukung.KATEGORI_LABELS:
                messages.error(request, "Jenis dokumen pendukung tidak valid.")
            else:
                setattr(pendukung, kategori, not getattr(pendukung, kategori))
                pendukung.save(update_fields=[kategori])
                return redirect("unor:upload_dokumen", kode=kode)
        else:
            jenis = request.POST.get("jenis")
            existing = dokumen_map.get(jenis)
            form = DokumenUnorForm(request.POST, request.FILES, instance=existing)
            if jenis in dict(jenis_choices) and form.is_valid():
                dok = form.save(commit=False)
                dok.pengajuan = pengajuan
                dok.jenis = jenis
                dok.save()
                messages.success(request, "Dokumen berhasil diunggah.")
                return redirect("unor:upload_dokumen", kode=kode)
            else:
                messages.error(request, "Gagal mengunggah dokumen. Periksa kembali berkas Anda.")

    context = {
        "pengajuan": pengajuan,
        "jenis_choices": jenis_choices,
        "dokumen_map": dokumen_map,
        "pendukung": pendukung,
        "pendukung_kategori": list(DokumenUnorPendukung.KATEGORI_LABELS.items()),
        "lengkap": lengkap,
        "templates": templates,
    }
    return render(request, "unor/upload.html", context)


@role_required("admin_unor")
def hapus_dokumen(request, kode, jenis):
    """Hapus salah satu dokumen administrasi Unor yang sudah diunggah."""
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    if request.method == "POST":
        dok = pengajuan.dokumen_unor.filter(jenis=jenis).first()
        if dok:
            dok.file.delete(save=False)
            dok.delete()
            messages.success(request, "Dokumen berhasil dihapus.")
    return redirect("unor:upload_dokumen", kode=pengajuan.kode)


@role_required("admin_unor")
def export_database(request):
    """Tahap 5: Export Database — tabel rincian + unduh CSV
    (representasi sederhana dari tombol "Export Excel" pada mockup)."""
    pengajuan_list = (
        _scoped(request)
        .exclude(status=Pengajuan.Status.BELUM)
        .select_related("pegawai__profile")
    )

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="paspor_pengajuan_unor.csv"'
        writer = csv.writer(response)
        writer.writerow(["Kode", "Nama Pegawai", "Kategori", "Tujuan", "Tgl Pengajuan", "Status"])
        for p in pengajuan_list:
            nama = getattr(getattr(p.pegawai, "profile", None), "nama", p.pegawai.get_full_name())
            writer.writerow([p.kode, nama, p.kategori, p.tujuan_negara, p.tgl_pengajuan or "", p.get_status_display()])
        return response

    return render(request, "unor/export.html", {"pengajuan_list": pengajuan_list})
