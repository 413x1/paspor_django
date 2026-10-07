from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.views.decorators.http import require_POST

from notifications.services import notify_approve_unor, notify_forward_bpsdm, notify_reject_unor

from . import alur, pembatalan, persyaratan, report, riwayat, tahap
from .decorators import role_required
from .models import DokumenUnorPendukung, LaporanPdln, Pengajuan, PermohonanPembatalan, RiwayatPengajuan

S = Pengajuan.Status
Aksi = RiwayatPengajuan.Aksi


def _scoped(request, qs=None):
    """Batasi queryset Pengajuan pada unit organisasi yang dikelola Admin
    Unor yang sedang login (snapshot unit organisasi pengajuan)."""
    if qs is None:
        qs = Pengajuan.objects.all()
    if not request.user.unit_organisasi_id:
        return qs.none()
    return qs.filter(report.q_unor(request.user.unit_organisasi_id))


def _tab(request):
    return "nondinas" if request.GET.get("tab") == "nondinas" else "pdln"


@role_required("admin_unor")
def dashboard(request):
    """Dasbor Admin Unor — tab PDLN / Non-Kedinasan, ringkasan progres &
    tabel rincian pengajuan pegawai pada unit organisasinya."""
    tab = _tab(request)
    qs = report.queryset_untuk(request.user).filter(jenis_perjalanan=tab)
    return render(request, "unor/dashboard.html", {
        "summary": report.ringkasan(request.user, qs),
        "tab": tab,
    })


_UNOR_DASHBOARD_ORDER_FIELDS = {
    "0": "pegawai__profile__nama",
    "1": "pegawai__profile__unit_kerja",
    "2": "tipe_pdln",
    "3": "kategori__nama_kategori",
    "5": "tgl_berangkat",
    "6": "tgl_kembali",
    "7": "tgl_pengajuan",
    "8": "kanal",
    "9": "status",
}


def status_html(p):
    html = format_html(
        '<span class="tag paspor-status is-{}"><span class="dot"></span>{}</span>', p.status, p.get_status_display(),
    )
    if p.pembatalan_terbuka:
        html = format_html('{}<br><span class="cell-muted">✕ Pembatalan diproses</span>', html)
    return html


@role_required("admin_unor")
def dashboard_data(request):
    """Endpoint JSON server-side DataTables untuk tabel rincian Dasbor."""
    qs = (
        report.queryset_untuk(request.user)
        .filter(jenis_perjalanan=_tab(request))
        .select_related("pegawai__profile", "kategori")
    )

    def baris(p):
        if p.pembatalan_terbuka:
            aksi = format_html('<a href="{}" class="button is-small">Lihat</a>', reverse("unor:preview", args=[p.kode]))
        elif p.status == S.PROSES:
            url = reverse("unor:upload_dokumen" if p.preview_unor_agree else "unor:preview", args=[p.kode])
            aksi = format_html('<a href="{}" class="button is-warning is-small">TL →</a>', url)
        else:
            aksi = format_html('<a href="{}" class="button is-small">Lihat</a>', reverse("unor:preview", args=[p.kode]))
        return [
            format_html("<strong>{}</strong><br><span class=\"cell-muted\">{}</span>",
                        p.pegawai.profile.nama, p.pegawai.profile.nip),
            escape(p.pegawai.profile.unit_kerja or "—"),
            escape(p.jenis_label),
            escape(p.kategori.nama_kategori) if p.kategori else "—",
            escape(p.tujuan_negara_display or "—"),
            p.tgl_berangkat.strftime("%d %b %Y") if p.tgl_berangkat else "—",
            p.tgl_kembali.strftime("%d %b %Y") if p.tgl_kembali else "—",
            p.tgl_pengajuan.strftime("%d %b %Y") if p.tgl_pengajuan else "—",
            p.get_kanal_display(),
            status_html(p),
            aksi,
        ]

    return report.datatable(request, qs, _UNOR_DASHBOARD_ORDER_FIELDS, baris, report.search_pengajuan)


def _konteks_pembatalan(request, pengajuan):
    return {
        "pembatalan_terbuka": pengajuan.pembatalan_terbuka,
        "pembatalan_alasan_tidak_bisa": pembatalan.alasan_tidak_bisa(pengajuan, request.user),
        "pembatalan_url": reverse("unor:ajukan_pembatalan", args=[pengajuan.kode]),
        "pembatalan_draft": False,
    }


def _catatan_kembali(pengajuan):
    """Catatan pengembalian dari tahap berikutnya yang masih berlaku."""
    if pengajuan.status != S.PROSES:
        return "", ""
    if pengajuan.is_tipe2 and pengajuan.catatan_bpsdm:
        return "Admin BPSDM", pengajuan.catatan_bpsdm
    if not pengajuan.is_tipe2 and pengajuan.catatan_pakln:
        return "Admin PKLN", pengajuan.catatan_pakln
    return "", ""


@role_required("admin_unor")
def preview(request, kode):
    """Pratinjau Pengajuan dari Pegawai (read-only) + persetujuan sebelum
    lanjut ke unggah dokumen administrasi, atau kembalikan ke pegawai."""
    pengajuan = get_object_or_404(_scoped(request).exclude(tgl_pengajuan__isnull=True), kode=kode)

    if request.method == "POST" and ("lanjutkan" in request.POST or "kembalikan" in request.POST):
        pesan = alur.alasan_dibekukan(pengajuan)
        if pesan:
            messages.error(request, pesan)
            return redirect("unor:preview", kode=kode)

    if request.method == "POST" and "lanjutkan" in request.POST and pengajuan.status == S.PROSES:
        pengajuan.preview_unor_agree = True
        pengajuan.save(update_fields=["preview_unor_agree"])
        return redirect("unor:upload_dokumen", kode=pengajuan.kode)

    if request.method == "POST" and "kembalikan" in request.POST:
        catatan = request.POST.get("catatan", "").strip()
        if not catatan:
            messages.error(request, "Isi catatan untuk pegawai sebelum mengembalikan pengajuan.")
        else:
            with transaction.atomic():
                p = alur.kunci(pengajuan)
                if p.status != S.PROSES or alur.alasan_dibekukan(p):
                    messages.error(request, "Pengajuan sudah diproses pihak lain atau sedang dibekukan.")
                    return redirect("unor:preview", kode=kode)
                status_dari = p.status
                p.status = S.BELUM
                p.submitted = False
                p.preview_unor_agree = False
                p.catatan_unor = catatan
                p.save()
                riwayat.catat(p, Aksi.DIKEMBALIKAN_UNOR, request.user, status_dari, catatan=catatan)
            notify_reject_unor(p, catatan)
            messages.success(request, f"Pengajuan {p.kode} dikembalikan ke pegawai beserta catatan.")
            return redirect("unor:dashboard")

    dari, catatan_kembali = _catatan_kembali(pengajuan)
    return render(request, "unor/preview.html", {
        "pengajuan": pengajuan,
        "direktori": persyaratan.direktori(pengajuan, "unor"),
        "catatan_kembali_dari": dari,
        "catatan_kembali": catatan_kembali,
        "dibekukan": alur.alasan_dibekukan(pengajuan),
        **riwayat.konteks(pengajuan, request.user),
        "catatan_perbaikan": riwayat.catatan_perbaikan(pengajuan, Aksi.DIKIRIM_ULANG),
        **_konteks_pembatalan(request, pengajuan),
    })


@role_required("admin_unor")
def upload_dokumen(request, kode):
    """Unggah Dokumen Administrasi Unor (sesuai registri per tipe), lalu
    meneruskan ke tahap berikut — Admin BPSDM (PDLN Tipe 2) atau Biro PAKLN."""
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    if not pengajuan.preview_unor_agree or pengajuan.status != S.PROSES:
        return redirect("unor:preview", kode=kode)

    pendukung = None
    if not pengajuan.is_pdln:
        pendukung, _ = DokumenUnorPendukung.objects.get_or_create(pengajuan=pengajuan)
    tujuan = alur.tahap_berikut(pengajuan)
    ke_bpsdm = tujuan == S.PROSES_BPSDM

    if request.method == "POST":
        if "teruskan" in request.POST:
            hasil = _teruskan(request, pengajuan, ke_bpsdm)
            if hasil:
                return hasil
        elif "pendukung_upload" in request.POST and pendukung:
            file_obj = request.FILES.get("file")
            if not file_obj:
                messages.error(request, "Pilih berkas dokumen pendukung terlebih dahulu.")
            else:
                pendukung.file = file_obj
                pendukung.uploaded_at = timezone.now()
                pendukung.save(update_fields=["file", "uploaded_at"])
                messages.success(request, "Dokumen pendukung berhasil diunggah.")
                return redirect("unor:upload_dokumen", kode=kode)
        elif "pendukung_hapus" in request.POST and pendukung:
            pendukung.file.delete(save=False)
            pendukung.file = ""
            pendukung.uploaded_at = None
            pendukung.save(update_fields=["file", "uploaded_at"])
            messages.success(request, "Berkas dokumen pendukung dihapus.")
            return redirect("unor:upload_dokumen", kode=kode)
        else:
            hasil = tahap.proses_unggah(request, pengajuan, "unor", "unor:upload_dokumen")
            if hasil:
                return hasil

    dok = tahap.konteks_dokumen(pengajuan, "unor")
    # Dokumen Pendukung Unor opsional — tidak memengaruhi kelengkapan.
    lengkap = dok["lengkap"]
    dari, catatan_kembali = _catatan_kembali(pengajuan)
    context = {
        "pengajuan": pengajuan,
        "pendukung": pendukung,
        **dok,
        "lengkap": lengkap,
        "ke_bpsdm": ke_bpsdm,
        "tujuan_label": "Admin BPSDM" if ke_bpsdm else "Biro PAKLN",
        "catatan_kembali_dari": dari,
        "catatan_kembali": catatan_kembali,
        "dibekukan": alur.alasan_dibekukan(pengajuan),
        "templates": tahap.templates_untuk(request.user, pengajuan, "unor"),
        **riwayat.konteks(pengajuan, request.user),
    }
    return render(request, "unor/upload.html", context)


def _teruskan(request, pengajuan, ke_bpsdm):
    # Penerusan ulang setelah dikembalikan tahap berikutnya wajib disertai
    # catatan balasan (BISNIS_PROSES_PDLN.MD §7).
    is_ulang = bool(pengajuan.catatan_bpsdm if ke_bpsdm else pengajuan.catatan_pakln)
    catatan = request.POST.get("catatan", "").strip() if is_ulang else ""
    tujuan_label = "Admin BPSDM" if ke_bpsdm else "Admin Biro PAKLN"
    kurang = tahap.konteks_dokumen(pengajuan, "unor")["dokumen_kurang"]
    if kurang:
        messages.error(request, "Lengkapi dokumen administrasi Unor sebelum meneruskan: " + ", ".join(kurang) + ".")
        return None
    if is_ulang and not catatan:
        messages.error(request, f"Isi catatan perbaikan untuk {tujuan_label} sebelum meneruskan ulang.")
        return None
    if not request.POST.get("agree"):
        messages.error(request, "Centang pernyataan kelengkapan dokumen terlebih dahulu.")
        return None

    with transaction.atomic():
        p = alur.kunci(pengajuan)
        pesan = alur.alasan_dibekukan(p)
        if p.status != S.PROSES or pesan:
            messages.error(request, pesan or "Pengajuan sudah diproses pihak lain.")
            return redirect("unor:dashboard")
        status_dari = p.status
        if ke_bpsdm:
            p.status = S.PROSES_BPSDM
            p.tgl_masuk_bpsdm = timezone.now().date()
            p.catatan_bpsdm = ""
            aksi = Aksi.DITERUSKAN_ULANG_BPSDM if is_ulang else Aksi.DITERUSKAN_BPSDM
        else:
            p.status = S.PROSES_PAKLN
            p.tgl_masuk_pakln = timezone.now().date()
            p.catatan_pakln = ""
            aksi = Aksi.DITERUSKAN_ULANG if is_ulang else Aksi.DITERUSKAN_PAKLN
        p.save()
        riwayat.catat(p, aksi, request.user, status_dari, catatan=catatan)

    if ke_bpsdm:
        notify_forward_bpsdm(p, catatan)
    else:
        notify_approve_unor(p, catatan)
    messages.success(request, f"Pengajuan {p.kode} diteruskan ke {tujuan_label}.")
    return redirect("unor:dashboard")


@role_required("admin_unor")
def hapus_dokumen(request, kode, jenis):
    """Hapus salah satu dokumen administrasi Unor yang sudah diunggah."""
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    if pengajuan.status == S.PROSES:
        tahap.hapus(request, pengajuan, "unor", jenis)
    return redirect("unor:upload_dokumen", kode=pengajuan.kode)


# ---------------------------------------------------------------------------
# Pembatalan (jenjang 1) & Pelaporan PDLN (monitor)
# ---------------------------------------------------------------------------

@role_required("admin_unor")
def daftar_pembatalan(request):
    semua = request.GET.get("tampil") == "semua"
    qs = PermohonanPembatalan.objects.filter(pengajuan__in=_scoped(request)).select_related(
        "pengajuan__pegawai__profile", "diajukan_oleh",
    )
    if not semua:
        qs = qs.filter(status=PermohonanPembatalan.Status.MENUNGGU_UNOR)
    return render(request, "bersama/pembatalan.html", {
        "daftar": qs.order_by("-created_at"),
        "semua": semua,
        "menunggu": PermohonanPembatalan.Status.MENUNGGU_UNOR,
        "putuskan_url": "unor:putuskan_pembatalan",
        "preview_url": "unor:preview",
        "jumlah_menunggu": report.pembatalan_menunggu(request.user).count(),
    })


@role_required("admin_unor")
@require_POST
def putuskan_pembatalan(request, pk):
    permohonan = get_object_or_404(PermohonanPembatalan, pk=pk, pengajuan__in=_scoped(request))
    try:
        pembatalan.putuskan(
            permohonan, request.user, request.POST.get("keputusan") == "setuju", request.POST.get("catatan", ""),
        )
    except pembatalan.PembatalanError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Keputusan pembatalan {permohonan.pengajuan.kode} tersimpan.")
    return redirect("unor:pembatalan")


@role_required("admin_unor")
@require_POST
def ajukan_pembatalan(request, kode):
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    try:
        pembatalan.ajukan(pengajuan, request.user, request.POST.get("alasan", ""))
    except pembatalan.PembatalanError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Permohonan pembatalan {pengajuan.kode} diteruskan ke Admin Biro PAKLN.")
    return redirect("unor:preview", kode=kode)


@role_required("admin_unor")
@require_POST
def tarik_pembatalan(request, pk):
    permohonan = get_object_or_404(PermohonanPembatalan, pk=pk, pengajuan__in=_scoped(request))
    try:
        pembatalan.tarik(permohonan, request.user)
    except pembatalan.PembatalanError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Permohonan pembatalan ditarik.")
    return redirect("unor:preview", kode=permohonan.pengajuan.kode)


@role_required("admin_unor")
def pelaporan(request):
    """Monitor Pelaporan PDLN (read-only) untuk pegawai unit organisasinya."""
    return render(request, "bersama/pelaporan.html", {
        **_konteks_pelaporan(report.queryset_untuk(request.user)),
        "dapat_verifikasi": False,
        "preview_url": "unor:preview",
    })


def _konteks_pelaporan(qs_pengajuan):
    """Context bersama halaman Pelaporan PDLN admin (Unor & PAKLN)."""
    qs = (
        qs_pengajuan.filter(jenis_perjalanan=Pengajuan.JenisPerjalanan.PDLN, status=S.SELESAI)
        .select_related("pegawai__profile", "unit_organisasi", "laporan_pdln")
        .prefetch_related("tujuan_negara")
        .order_by("-tgl_selesai")
    )
    baris, hitung = [], {"selesai": 0, "belum": 0, "menunggu": 0, "dikembalikan": 0, "disetujui": 0, "terlambat": 0}
    hari_ini = timezone.localdate()
    for p in qs:
        laporan = p.laporan
        status = laporan.status if laporan else "belum"
        terlambat = laporan is None and p.tgl_kembali and (hari_ini - p.tgl_kembali).days > report.BATAS_HARI_LAPORAN
        hitung["selesai"] += 1
        hitung[status] = hitung.get(status, 0) + 1
        hitung["terlambat"] += 1 if terlambat else 0
        baris.append({"p": p, "laporan": laporan, "status": status, "terlambat": terlambat})
    return {"baris": baris, "hitung": hitung, "Status": LaporanPdln.Status}
