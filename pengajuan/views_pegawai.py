import os

from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html

from notifications.services import notify_resubmit_unor, notify_submit_unor

from .decorators import role_required
from .forms import DokumenPegawaiForm, PengajuanForm
from .models import DokumenPakln, DokumenPegawai, DokumenTemplate, Pengajuan


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
    context = {
        "aktif": aktif,
        "profile": getattr(request.user, "profile", None),
    }
    return render(request, "pegawai/beranda.html", context)


# Kolom tabel "Riwayat" (index sesuai urutan kolom pada pegawai/beranda.html)
# -> field untuk pengurutan (ORDER BY) di endpoint server-side DataTables.
# Kolom Tujuan (M2M) dan Kanal (selalu "—" pada baris riwayat) sengaja
# tidak disertakan — tidak diurutkan di JS (orderable:false).
_RIWAYAT_DATA_ORDER_FIELDS = {
    "1": "kategori__nama_kategori",
    "2": "tgl_pengajuan",
    "4": "status",
}


@role_required("pegawai")
def riwayat_data(request):
    """Endpoint JSON server-side untuk tabel "Riwayat" pada Beranda
    Pegawai (protokol DataTables: draw/start/length/search/order pada
    GET), mengikuti pola `users_data` (Manajemen User). Pengajuan yang
    sedang aktif ditampilkan terpisah (baris tersendiri, bukan bagian
    tabel ini)."""
    aktif = _active_pengajuan(request.user)
    qs = Pengajuan.objects.filter(pegawai=request.user).select_related("kategori")
    if aktif:
        qs = qs.exclude(pk=aktif.pk)
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(kategori__nama_kategori__icontains=search_value)
            | Q(tujuan_negara__nama_negara__icontains=search_value)
        ).distinct()
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _RIWAYAT_DATA_ORDER_FIELDS.get(order_col, "-created_at")
    if request.GET.get("order[0][dir]") == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field, "-created_at")

    try:
        start = int(request.GET.get("start", 0))
        length = int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    page = qs[start:] if length == -1 else qs[start:start + length]

    data = []
    for p in page:
        status_html = format_html(
            '<span class="tag paspor-status is-{}"><span class="dot"></span>{}</span>',
            p.status, p.get_status_display(),
        )
        if p.submitted:
            aksi_html = format_html(
                '<a href="{}" class="button is-small">Lihat</a>',
                reverse("pegawai:monitor_progres", args=[p.kode]),
            )
        else:
            aksi_html = format_html(
                '<a href="{}" class="button is-small">Lanjutkan</a>',
                reverse("pegawai:formulir_pengajuan"),
            )

        data.append([
            format_html("🌏 <strong>{}</strong>", p.tujuan_negara_display or "—"),
            escape(p.kategori.nama_kategori) if p.kategori else "—",
            p.tgl_pengajuan.strftime("%d %b %Y") if p.tgl_pengajuan else "—",
            "—",
            status_html,
            aksi_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


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
            form.save_m2m()
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
                # Sudah ada catatan revisi Unor sebelumnya -> ini pengiriman
                # ulang (Event 2C), bukan pengajuan baru (Event 1).
                is_resubmit = bool(pengajuan.catatan_unor)

                pengajuan.status = Pengajuan.Status.PROSES
                pengajuan.submitted = True
                pengajuan.tgl_pengajuan = timezone.now().date()
                pengajuan.catatan_unor = ""
                pengajuan.save()

                if is_resubmit:
                    notify_resubmit_unor(pengajuan)
                else:
                    notify_submit_unor(pengajuan)

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


@role_required("pegawai")
def download_iln(request, kode):
    """Unduh dokumen "Izin Luar Negeri (TTD Sekjen a.n. Menteri)" yang
    diunggah Admin Biro PAKLN pada tahap pemrosesan administrasi — hanya
    tersedia setelah pengajuan berstatus selesai."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)

    if pengajuan.status != Pengajuan.Status.SELESAI:
        messages.error(
            request,
            "Dokumen ILN belum tersedia — pengajuan belum diselesaikan oleh Admin Biro PAKLN.",
        )
        return redirect("pegawai:monitor_progres", kode=kode)

    dok = pengajuan.dokumen_pakln.filter(jenis=DokumenPakln.Jenis.ILN_SEKJEN).first()
    if not dok or not dok.file:
        messages.error(request, "Dokumen ILN belum tersedia. Silakan hubungi Admin Biro PAKLN.")
        return redirect("pegawai:monitor_progres", kode=kode)

    try:
        file_handle = dok.file.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        messages.error(request, "Gagal mengunduh dokumen ILN — berkas tidak ditemukan di penyimpanan.")
        return redirect("pegawai:monitor_progres", kode=kode)

    ekstensi = os.path.splitext(dok.file.name)[1]
    return FileResponse(file_handle, as_attachment=True, filename=f"ILN_{pengajuan.kode}{ekstensi}")
