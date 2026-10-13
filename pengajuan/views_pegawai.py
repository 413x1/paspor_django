import os
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.views.decorators.http import require_POST

from accounts.models import DokumenKepegawaian, PasporPegawai
from logs.models import ActivityLog
from paspor.validators import KODE_BUKAN_PDF, periksa_pdf, tandai_ditolak
from logs.utils import catat_riwayat, record_activity
from notifications import services as notif
from notifications.services import notify_resubmit_unor, notify_submit_unor
from paspor.integrasi import pintar
from paspor.kalender import rincian_hari

from . import alur, pembatalan, riwayat, tahap
from .decorators import role_required
from .forms import LaporanPdlnForm, PdlnForm, PengajuanForm
from .models import DokumenBko, DokumenPakln, LaporanPdln, Pengajuan, PermohonanPembatalan, RiwayatPengajuan

S = Pengajuan.Status
JP = Pengajuan.JenisPerjalanan

# Dokumen hasil PDLN yang boleh diunduh pegawai saat PDLN selesai
# (BISNIS_PROSES_PDLN.MD §14 pertanyaan terbuka #3 — default): dari tahap
# Biro PAKLN, ditambah SK Tugas Belajar dari Admin BKO (T2P).
_UNDUH_HASIL_PDLN = {
    DokumenPakln.Jenis.SP_SETNEG, DokumenPakln.Jenis.EXIT_PERMIT, DokumenPakln.Jenis.VISA,
    DokumenPakln.Jenis.ND_KARO_UNOR,
}
_UNDUH_HASIL_BKO = {DokumenBko.Jenis.SK_TUBEL}


def _active_pengajuan(user):
    """Pengajuan pegawai yang belum tuntas (aturan satu pengajuan aktif,
    BISNIS_PROSES_PDLN.MD §2.1) — lihat `alur.pengajuan_belum_tuntas`."""
    return alur.pengajuan_belum_tuntas(user)


def _status_html(p):
    html = format_html(
        '<span class="tag paspor-status is-{}"><span class="dot"></span>{}</span>',
        p.status, p.get_status_display(),
    )
    return html


@role_required("pegawai")
def beranda(request):
    aktif = _active_pengajuan(request.user)
    context = {
        "aktif": aktif,
        "alasan_blokir": alur.alasan_belum_tuntas(aktif),
        "profile": getattr(request.user, "profile", None),
        "tab": request.GET.get("tab", "pdln"),
        "tipe_choices": Pengajuan.TipePdln.choices,
    }
    return render(request, "pegawai/beranda.html", context)


# Kolom tabel "Riwayat" (index sesuai urutan kolom pada pegawai/beranda.html)
# -> field untuk pengurutan (ORDER BY) di endpoint server-side DataTables.
_RIWAYAT_DATA_ORDER_FIELDS = {
    "0": "tipe_pdln",
    "2": "kategori__nama_kategori",
    "3": "tgl_pengajuan",
    "4": "status",
}


@role_required("pegawai")
def riwayat_data(request):
    """Endpoint JSON server-side untuk tabel "Riwayat" pada Beranda
    Pegawai (protokol DataTables), dengan filter `jenis` (pdln/nondinas)
    sesuai tab yang aktif. Pengajuan aktif ditampilkan terpisah."""
    aktif = _active_pengajuan(request.user)
    qs = Pengajuan.objects.filter(pegawai=request.user).select_related("kategori", "laporan_pdln")
    jenis = request.GET.get("jenis")
    if jenis in JP.values:
        qs = qs.filter(jenis_perjalanan=jenis)
    if aktif:
        qs = qs.exclude(pk=aktif.pk)
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(kode__icontains=search_value)
            | Q(kategori__nama_kategori__icontains=search_value)
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
        if p.pernah_dikirim or p.status == S.DIBATALKAN:
            aksi_html = format_html(
                '<a href="{}" class="button is-small">Lihat</a>',
                reverse("pegawai:monitor_progres", args=[p.kode]),
            )
        else:
            aksi_html = format_html(
                '<a href="{}" class="button is-small">Lanjutkan</a>',
                reverse("pegawai:formulir_pengajuan"),
            )
        laporan = p.laporan if p.is_pdln else None
        if p.is_pdln and p.status == S.SELESAI and not p.tuntas:
            aksi_html = format_html(
                '{} <a href="{}" class="button is-small is-info btn-pelaporan-info">Pelaporan PDLN</a>',
                aksi_html, reverse("pegawai:laporan_form", args=[p.kode]),
            )
        if not p.is_pdln:
            laporan_html = "—"
        elif p.status != S.SELESAI:
            laporan_html = "—"
        else:
            laporan_html = escape(laporan.get_status_display() if laporan else "Belum melapor")

        data.append([
            format_html("<strong>{}</strong><br><span class=\"cell-muted\">{}</span>", p.jenis_label, p.kode),
            escape(p.tujuan_negara_display or "—"),
            escape(p.kategori.nama_kategori) if p.kategori else "—",
            p.tgl_pengajuan.strftime("%d %b %Y") if p.tgl_pengajuan else "—",
            _status_html(p),
            laporan_html,
            aksi_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


def _tipe_dari_request(request):
    jenis = request.GET.get("jenis", JP.NONDINAS)
    tipe = request.GET.get("tipe", "")
    if jenis == JP.PDLN and tipe in Pengajuan.TipePdln.values:
        return JP.PDLN, tipe
    return JP.NONDINAS, ""


@role_required("pegawai")
def formulir_pengajuan(request):
    """Tahap 2: Formulir Pengajuan. Jenis & tipe dipilih lewat modal
    "Tambah Usulan Baru" (`?jenis=pdln&tipe=T1`). Selama pegawai masih punya
    pengajuan belum tuntas, formulir hanya membuka draft/pengajuan yang
    dikembalikan tersebut (aturan satu pengajuan aktif)."""
    aktif = _active_pengajuan(request.user)
    if aktif and aktif.status != S.BELUM:
        messages.warning(request, alur.alasan_belum_tuntas(aktif))
        return redirect("pegawai:beranda")

    if aktif:
        jenis, tipe = aktif.jenis_perjalanan, aktif.tipe_pdln
    else:
        jenis, tipe = _tipe_dari_request(request)

    profile = getattr(request.user, "profile", None)

    if jenis == JP.PDLN:
        return _formulir_pdln(request, aktif, tipe, profile)

    if request.method == "POST":
        form = PengajuanForm(request.POST, instance=aktif, profile=profile)
        if form.is_valid():
            with transaction.atomic():
                if alur.pengajuan_belum_tuntas(request.user) not in (None, aktif):
                    messages.error(request, "Anda masih memiliki pengajuan yang belum tuntas.")
                    return redirect("pegawai:beranda")
                pengajuan = form.save(commit=False)
                pengajuan.pegawai = request.user
                pengajuan.jenis_perjalanan = JP.NONDINAS
                pengajuan.kanal = Pengajuan.Kanal.WEB
                pengajuan.form_saved = True
                pengajuan.save()
                form.save_m2m()
            record_activity(
                request, ActivityLog.Aktivitas.SIMPAN_FORMULIR, f"Menyimpan formulir pengajuan {pengajuan.kode}",
                target_type="pengajuan", target_id=pengajuan.kode,
            )
            messages.success(request, "Formulir pengajuan berhasil disimpan.")
            return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)
        record_activity(
            request, ActivityLog.Aktivitas.SIMPAN_FORMULIR, "Menyimpan formulir pengajuan",
            status=ActivityLog.Status.GAGAL, detail="Validasi gagal: " + ", ".join(form.errors),  # nama field saja
        )
    else:
        form = PengajuanForm(instance=aktif, profile=profile)

    return render(request, "pegawai/formulir.html", {"form": form, "profile": profile})


def _formulir_pdln(request, aktif, tipe, profile):
    pencalonan = []
    if tipe in (Pengajuan.TipePdln.T2P, Pengajuan.TipePdln.T2L):
        nip = profile.nip if profile else ""
        jenis_beasiswa = pintar.JENIS_PENDIDIKAN if tipe == Pengajuan.TipePdln.T2P else pintar.JENIS_PELATIHAN
        pencalonan = pintar.daftar_pencalonan_selesai(nip, jenis_beasiswa)

    instance = aktif or Pengajuan(pegawai=request.user, jenis_perjalanan=JP.PDLN, tipe_pdln=tipe)
    if request.method == "POST":
        form = PdlnForm(request.POST, instance=instance, tipe=tipe, pencalonan=pencalonan)
        if form.is_valid():
            with transaction.atomic():
                if alur.pengajuan_belum_tuntas(request.user) not in (None, aktif):
                    messages.error(request, "Anda masih memiliki pengajuan yang belum tuntas.")
                    return redirect("pegawai:beranda")
                pengajuan = form.save(commit=False)
                pengajuan.pegawai = request.user
                pengajuan.jenis_perjalanan = JP.PDLN
                pengajuan.tipe_pdln = tipe
                pengajuan.kanal = Pengajuan.Kanal.WEB
                pengajuan.form_saved = True
                pengajuan.save()
                form.save_m2m()
                form.save_detail(pengajuan)
            record_activity(
                request, ActivityLog.Aktivitas.SIMPAN_FORMULIR, f"Menyimpan formulir pengajuan {pengajuan.kode}",
                target_type="pengajuan", target_id=pengajuan.kode,
            )
            messages.success(request, "Formulir pengajuan berhasil disimpan.")
            return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)
        record_activity(
            request, ActivityLog.Aktivitas.SIMPAN_FORMULIR, "Menyimpan formulir pengajuan",
            status=ActivityLog.Status.GAGAL, detail="Validasi gagal: " + ", ".join(form.errors),  # nama field saja
        )
    else:
        form = PdlnForm(instance=instance, tipe=tipe, pencalonan=pencalonan)

    return render(request, "pegawai/formulir_pdln.html", {
        "form": form,
        "profile": profile,
        "pengajuan": instance,
        "tipe": tipe,
        "tipe_label": dict(Pengajuan.TipePdln.choices).get(tipe, ""),
        "pintar_stub": pintar.memakai_stub() and "beasiswa" in form.fields,
    })


# Batas rentang untuk endpoint `hitung_hari` — perjalanan non-dinas
# normalnya hitungan hari–minggu; mencegah iterasi tanggal yang tidak wajar.
# PDLN (`?jenis=pdln`) boleh lebih panjang karena tugas belajar bisa
# berlangsung beberapa tahun.
_MAKS_RENTANG_HITUNG_HARI = 366
_MAKS_RENTANG_HITUNG_HARI_PDLN = 366 * 6


@role_required("pegawai", "admin_unor", "admin_bpsdm", "admin_bko", "admin_pakln")
def hitung_hari(request):
    """Endpoint JSON untuk mengisi otomatis Jumlah Hari Kalender & Jumlah
    Hari Kerja begitu tanggal berangkat/kembali diubah (lihat
    `paspor.kalender.rincian_hari`). Hanya untuk tampilan — nilai final
    tetap dihitung ulang di server saat formulir disimpan."""
    try:
        berangkat = date.fromisoformat(request.GET.get("berangkat", ""))
        kembali = date.fromisoformat(request.GET.get("kembali", ""))
    except ValueError:
        return JsonResponse({"error": "Format tanggal tidak valid (YYYY-MM-DD)."}, status=400)
    if kembali < berangkat:
        return JsonResponse({"error": "Tanggal kembali tidak boleh sebelum tanggal keberangkatan."}, status=400)
    maks = _MAKS_RENTANG_HITUNG_HARI_PDLN if request.GET.get("jenis") == "pdln" else _MAKS_RENTANG_HITUNG_HARI
    if (kembali - berangkat).days + 1 > maks:
        return JsonResponse({"error": f"Rentang maksimal {maks} hari."}, status=400)
    return JsonResponse(rincian_hari(berangkat, kembali))


@role_required("pegawai")
def upload_dokumen(request, kode):
    """Tahap 3: Unggah Dokumen — dokumen wajib sesuai registri
    `persyaratan` (per jenis/tipe), lalu Kirim ke Admin Unor."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    if not pengajuan.form_saved:
        return redirect("pegawai:formulir_pengajuan")

    dapat_diubah = pengajuan.status == S.BELUM

    if request.method == "POST":
        if not dapat_diubah:
            messages.error(request, "Dokumen tidak dapat diubah — pengajuan sedang diproses.")
            return redirect("pegawai:upload_dokumen", kode=kode)
        if "kirim" in request.POST:
            hasil = _kirim(request, pengajuan)
            if hasil:
                return hasil
        else:
            hasil = tahap.proses_unggah(request, pengajuan, "pegawai", "pegawai:upload_dokumen")
            if hasil:
                return hasil

    context = {
        "pengajuan": pengajuan,
        "templates": tahap.templates_untuk(request.user, pengajuan, "pegawai"),
        "dapat_diubah": dapat_diubah,
        "readonly": not dapat_diubah,
        "dibekukan": alur.alasan_dibekukan(pengajuan),
        **tahap.konteks_dokumen(pengajuan, "pegawai"),
        **_konteks_pembatalan(pengajuan, request.user),
    }
    return render(request, "pegawai/upload.html", context)


def _kirim(request, pengajuan):
    # Sudah ada catatan revisi Unor sebelumnya -> pengiriman ulang (Event
    # 2C), wajib disertai catatan balasan untuk Admin Unor.
    is_resubmit = bool(pengajuan.catatan_unor)
    catatan = request.POST.get("catatan", "").strip() if is_resubmit else ""
    kurang = tahap.konteks_dokumen(pengajuan, "pegawai")["dokumen_kurang"]
    if kurang:
        messages.error(request, "Lengkapi dokumen wajib sebelum mengirim: " + ", ".join(kurang) + ".")
        return None
    if is_resubmit and not catatan:
        messages.error(request, "Isi catatan perbaikan untuk Admin Unor sebelum mengirim ulang.")
        return None
    if not request.POST.get("agree"):
        messages.error(request, "Centang pernyataan kelengkapan dokumen terlebih dahulu.")
        return None

    with transaction.atomic():
        p = alur.kunci(pengajuan)
        pesan = alur.alasan_dibekukan(p)
        if p.status != S.BELUM or pesan:
            messages.error(request, pesan or "Pengajuan sudah dikirim.")
            return redirect("pegawai:monitor_progres", kode=p.kode)
        status_dari = p.status
        p.status = S.PROSES
        p.submitted = True
        p.tgl_pengajuan = timezone.now().date()
        p.catatan_unor = ""
        profile = getattr(request.user, "profile", None)
        if profile and profile.unit_organisasi_id:
            p.unit_organisasi_id = profile.unit_organisasi_id
        p.save()
        riwayat.catat(
            p,
            RiwayatPengajuan.Aksi.DIKIRIM_ULANG if is_resubmit else RiwayatPengajuan.Aksi.DIKIRIM,
            request.user, status_dari, catatan=catatan,
        )
        catat_riwayat(request, p, RiwayatPengajuan.Aksi.DIKIRIM_ULANG if is_resubmit else RiwayatPengajuan.Aksi.DIKIRIM)

    if is_resubmit:
        notify_resubmit_unor(p, catatan)
    else:
        notify_submit_unor(p)

    messages.success(request, f"Pengajuan {p.kode} berhasil dikirim ke Admin Unor.")
    return redirect("pegawai:monitor_progres", kode=p.kode)


@role_required("pegawai")
def hapus_dokumen(request, kode, jenis):
    """Hapus salah satu dokumen yang sudah diunggah pegawai (hanya selama
    pengajuan belum dikirim / sedang dikembalikan)."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    if pengajuan.status == S.BELUM:
        tahap.hapus(request, pengajuan, "pegawai", jenis)
    return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)


def _konteks_pembatalan(pengajuan, user):
    terbuka = pengajuan.pembatalan_terbuka
    return {
        "pembatalan_terbuka": terbuka,
        "pembatalan_alasan_tidak_bisa": pembatalan.alasan_tidak_bisa(pengajuan, user),
        "pembatalan_url": reverse("pegawai:ajukan_pembatalan", args=[pengajuan.kode]),
        "pembatalan_draft": not pengajuan.pernah_dikirim,
    }


@role_required("pegawai")
def monitor_progres(request, kode):
    """Tahap 4: Monitor Progres — timeline status pengajuan, pelaporan
    (PDLN), dan pembatalan."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    if not pengajuan.pernah_dikirim and pengajuan.status != S.DIBATALKAN:
        return redirect("pegawai:upload_dokumen", kode=pengajuan.kode)

    hasil_pdln = []
    if pengajuan.is_pdln and pengajuan.status == S.SELESAI:
        hasil_pdln = [d for d in pengajuan.dokumen_pakln.all() if d.jenis in _UNDUH_HASIL_PDLN]
        hasil_pdln += [d for d in pengajuan.dokumen_bko.all() if d.jenis in _UNDUH_HASIL_BKO]

    return render(request, "pegawai/monitor.html", {
        "pengajuan": pengajuan,
        "laporan": pengajuan.laporan,
        "hasil_pdln": hasil_pdln,
        **riwayat.konteks(pengajuan, request.user),
        **_konteks_pembatalan(pengajuan, request.user),
    })


def _kirim_berkas(dok, nama_unduhan):
    try:
        file_handle = dok.file.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        return None
    ekstensi = os.path.splitext(dok.file.name)[1]
    return FileResponse(file_handle, as_attachment=True, filename=f"{nama_unduhan}{ekstensi}")


@role_required("pegawai")
def download_iln(request, kode):
    """Unduh dokumen "Izin Luar Negeri (TTD Sekjen a.n. Menteri)" yang
    diunggah Admin Biro PAKLN — hanya setelah pengajuan Non-Dinas selesai."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)

    if pengajuan.status != S.SELESAI:
        messages.error(
            request,
            "Dokumen ILN belum tersedia — pengajuan belum diselesaikan oleh Admin Biro PAKLN.",
        )
        return redirect("pegawai:monitor_progres", kode=kode)

    dok = pengajuan.dokumen_pakln.filter(jenis=DokumenPakln.Jenis.ILN_SEKJEN).first()
    if not dok or not dok.file:
        messages.error(request, "Dokumen ILN belum tersedia. Silakan hubungi Admin Biro PAKLN.")
        return redirect("pegawai:monitor_progres", kode=kode)

    respons = _kirim_berkas(dok, f"ILN_{pengajuan.kode}")
    if respons is None:
        messages.error(request, "Gagal mengunduh dokumen ILN — berkas tidak ditemukan di penyimpanan.")
        return redirect("pegawai:monitor_progres", kode=kode)
    return respons


@role_required("pegawai")
def unduh_hasil(request, kode, jenis):
    """Unduh dokumen hasil PDLN dari tahap Biro PAKLN (SP Setneg, Exit
    Permit, Rekomendasi Visa, ND Karo) atau Admin BKO (SK Tubel) setelah
    pengajuan selesai."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    if not pengajuan.is_pdln or pengajuan.status != S.SELESAI:
        raise Http404
    if jenis in _UNDUH_HASIL_PDLN:
        dok = get_object_or_404(DokumenPakln, pengajuan=pengajuan, jenis=jenis)
    elif jenis in _UNDUH_HASIL_BKO:
        dok = get_object_or_404(DokumenBko, pengajuan=pengajuan, jenis=jenis)
    else:
        raise Http404
    respons = _kirim_berkas(dok, f"{jenis}_{pengajuan.kode}")
    if respons is None:
        messages.error(request, "Berkas tidak ditemukan di penyimpanan.")
        return redirect("pegawai:monitor_progres", kode=kode)
    return respons


# ---------------------------------------------------------------------------
# Pelaporan PDLN (BISNIS_PROSES_PDLN.MD §4.4)
# ---------------------------------------------------------------------------

@role_required("pegawai")
def pelaporan(request):
    daftar = (
        Pengajuan.objects.filter(pegawai=request.user, jenis_perjalanan=JP.PDLN)
        .exclude(status=S.BELUM, tgl_pengajuan=None)
        .select_related("laporan_pdln", "detail_pdln")
        .prefetch_related("tujuan_negara")
        .order_by("-created_at")
    )
    return render(request, "pegawai/pelaporan.html", {"daftar": daftar})


def _laporan_dapat_diubah(laporan):
    """Laporan masih bisa diisi/diubah pegawai: belum ada, masih draft, atau dikembalikan."""
    return laporan is None or laporan.status in (LaporanPdln.Status.DRAFT, LaporanPdln.Status.DIKEMBALIKAN)


def _tanggal_pelaksanaan(pengajuan):
    """Tanggal kegiatan (bila ada pada detail PDLN), selain itu tanggal berangkat s.d. kembali."""
    detail = pengajuan.detail
    mulai = (detail.tgl_mulai_kegiatan if detail else None) or pengajuan.tgl_berangkat
    selesai = (detail.tgl_selesai_kegiatan if detail else None) or pengajuan.tgl_kembali
    if not mulai:
        return "—"
    return f"{mulai:%d/%m/%Y} s/d {(selesai or mulai):%d/%m/%Y}"


@role_required("pegawai")
def laporan_form(request, kode):
    """Formulir Pelaporan PDLN (Bagian A: data pengajuan, B: uraian, C: biaya dan dokumen).

    "Simpan" menyimpan draft (isian boleh belum lengkap); "Laporkan" mengirim laporan ke Biro
    PAKLN untuk diverifikasi. Laporan yang sedang menunggu verifikasi atau sudah disetujui hanya
    dapat dilihat."""
    pengajuan = get_object_or_404(
        Pengajuan.objects.select_related("detail_pdln", "laporan_pdln").prefetch_related("tujuan_negara"),
        kode=kode, pegawai=request.user, jenis_perjalanan=JP.PDLN,
    )
    if pengajuan.status != S.SELESAI:
        messages.error(request, "Laporan PDLN hanya dapat diisi setelah pengajuan selesai diproses Biro PAKLN.")
        return redirect("pegawai:pelaporan")

    laporan = pengajuan.laporan
    dibekukan = alur.alasan_dibekukan(pengajuan)
    dapat_diubah = _laporan_dapat_diubah(laporan) and not dibekukan
    perlu_catatan = laporan is not None and laporan.status == LaporanPdln.Status.DIKEMBALIKAN

    if request.method == "POST":
        aksi = request.POST.get("action")
        if not dapat_diubah:
            messages.error(request, dibekukan or "Laporan ini sedang diverifikasi atau sudah disetujui, tidak dapat diubah.")
            return redirect("pegawai:laporan_form", kode=kode)
        if aksi not in ("draft", "submit"):
            messages.error(request, "Aksi tidak valid.")
            return redirect("pegawai:laporan_form", kode=kode)

        kirim = aksi == "submit"
        form = LaporanPdlnForm(
            request.POST, request.FILES, instance=laporan or LaporanPdln(pengajuan=pengajuan),
            kirim=kirim, perlu_catatan=perlu_catatan,
        )
        if form.is_valid():
            hasil = _simpan_laporan(request, pengajuan, form, kirim)
            if hasil:
                return hasil
        else:
            if any(e.code == KODE_BUKAN_PDF for e in form.errors.as_data().get("dokumen_laporan", [])):
                tandai_ditolak(request)  # response menjadi 400 (UnggahDitolakMiddleware)
            messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = LaporanPdlnForm(instance=laporan or LaporanPdln(pengajuan=pengajuan), perlu_catatan=perlu_catatan)

    if not dapat_diubah:
        for field in form.fields.values():
            field.disabled = True

    return render(request, "pegawai/laporan_form.html", {
        "pengajuan": pengajuan,
        "laporan": laporan,
        "form": form,
        "dapat_diubah": dapat_diubah,
        "dibekukan": dibekukan,
        "tanggal_pelaksanaan": _tanggal_pelaksanaan(pengajuan),
        "negara_tujuan": " — ".join(
            bagian for bagian in (pengajuan.tujuan_negara_display, getattr(pengajuan.detail, "kota_tujuan", "")) if bagian
        ) or "—",
        "nama_berkas": os.path.basename(laporan.file.name) if laporan and laporan.file else "",
    })


def _simpan_laporan(request, pengajuan, form, kirim):
    """Simpan draft atau kirim laporan (atomik). Mengembalikan redirect, atau None bila ditolak
    (pesan error sudah ditambahkan)."""
    ulang = False
    with transaction.atomic():
        p = alur.kunci(pengajuan)
        terkini = LaporanPdln.objects.select_for_update().filter(pengajuan=p).first()
        pesan = ""
        if p.status != S.SELESAI:
            pesan = "Laporan PDLN hanya dapat diisi setelah pengajuan selesai diproses Biro PAKLN."
        elif alur.alasan_dibekukan(p):
            pesan = alur.alasan_dibekukan(p)
        elif not _laporan_dapat_diubah(terkini):
            pesan = "Laporan ini sedang diverifikasi atau sudah disetujui, tidak dapat diubah."
        elif terkini is not None and form.instance.pk != terkini.pk:
            pesan = "Laporan sudah dibuat dari tab lain. Muat ulang halaman ini."
        if pesan:
            messages.error(request, pesan)
            return redirect("pegawai:laporan_form", kode=p.kode)

        ulang = terkini is not None and terkini.status == LaporanPdln.Status.DIKEMBALIKAN
        catatan = (form.cleaned_data.get("catatan_perbaikan") or "").strip() if ulang else ""

        laporan = form.save(commit=False)
        laporan.diunggah_oleh = request.user
        if kirim:
            laporan.status = LaporanPdln.Status.MENUNGGU
            laporan.uploaded_at = timezone.now()
        elif not ulang:
            laporan.status = LaporanPdln.Status.DRAFT
        # Draft dari laporan yang dikembalikan tetap berstatus "dikembalikan" (catatan Biro PAKLN
        # masih berlaku sampai pegawai melaporkan ulang).
        laporan.save()
        form.bersihkan_berkas_lama(laporan)

        if kirim:
            riwayat.catat(p, RiwayatPengajuan.Aksi.LAPORAN_DIUNGGAH, request.user, p.status, catatan=catatan)
            catat_riwayat(request, p, RiwayatPengajuan.Aksi.LAPORAN_DIUNGGAH)
        else:
            record_activity(
                request, ActivityLog.Aktivitas.SIMPAN_LAPORAN, f"Menyimpan draft laporan PDLN — {p.kode}",
                target_type="pengajuan", target_id=p.kode,
            )

    if kirim:
        notif.notify_laporan_diunggah(p, catatan)
        messages.success(request, f"Laporan PDLN {p.kode} berhasil dikirim untuk diverifikasi Biro PAKLN.")
        return redirect("pegawai:pelaporan")
    messages.success(request, "Draft laporan disimpan. Anda dapat melanjutkannya nanti, lalu tekan Laporkan.")
    return redirect("pegawai:laporan_form", kode=p.kode)


# ---------------------------------------------------------------------------
# Pembatalan (BISNIS_PROSES_PDLN.MD §4.5)
# ---------------------------------------------------------------------------

@role_required("pegawai")
def daftar_pembatalan(request):
    daftar = (
        PermohonanPembatalan.objects.filter(pengajuan__pegawai=request.user)
        .select_related("pengajuan")
        .order_by("-created_at")
    )
    return render(request, "pegawai/pembatalan.html", {"daftar": daftar})


@role_required("pegawai")
@require_POST
def ajukan_pembatalan(request, kode):
    pengajuan = get_object_or_404(Pengajuan, kode=kode, pegawai=request.user)
    try:
        hasil = pembatalan.ajukan(pengajuan, request.user, request.POST.get("alasan", ""))
    except pembatalan.PembatalanError as exc:
        messages.error(request, str(exc))
    else:
        if hasil is None:
            messages.success(request, f"Draft {pengajuan.kode} dibatalkan.")
            return redirect("pegawai:beranda")
        messages.success(request, f"Permohonan pembatalan {pengajuan.kode} dikirim ke Admin Unor.")
    if pengajuan.pernah_dikirim:
        return redirect("pegawai:monitor_progres", kode=kode)
    return redirect("pegawai:upload_dokumen", kode=kode)


@role_required("pegawai")
@require_POST
def tarik_pembatalan(request, pk):
    permohonan = get_object_or_404(PermohonanPembatalan, pk=pk, pengajuan__pegawai=request.user)
    try:
        pembatalan.tarik(permohonan, request.user)
    except pembatalan.PembatalanError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Permohonan pembatalan ditarik. Proses pengajuan dilanjutkan.")
    return redirect("pegawai:monitor_progres", kode=permohonan.pengajuan.kode)


# ---------------------------------------------------------------------------
# Profil (BISNIS_PROSES_PDLN.MD §9.1)
# ---------------------------------------------------------------------------

@role_required("pegawai", "admin_unor", "admin_bpsdm", "admin_bko", "admin_pakln")
def profil(request):
    user = request.user
    jenis_dokumen = (
        [c for c in DokumenKepegawaian.Jenis.choices if c[0] != DokumenKepegawaian.Jenis.SK_PENUGASAN]
        if user.role == "pegawai" else [(DokumenKepegawaian.Jenis.SK_PENUGASAN, DokumenKepegawaian.Jenis.SK_PENUGASAN.label)]
    )

    if request.method == "POST":
        aksi = request.POST.get("aksi")
        if aksi == "tambah_paspor" and user.role == "pegawai":
            nomor = request.POST.get("nomor", "").strip()
            jenis = request.POST.get("jenis", "")
            try:
                expired = date.fromisoformat(request.POST.get("tgl_expired", ""))
            except ValueError:
                expired = None
            if not nomor or jenis not in PasporPegawai.Jenis.values or not expired:
                messages.error(request, "Lengkapi nomor, jenis, dan tanggal expired paspor.")
            else:
                PasporPegawai.objects.create(pegawai=user, nomor=nomor[:20], jenis=jenis, tgl_expired=expired)
                messages.success(request, "Data paspor ditambahkan.")
        elif aksi == "hapus_paspor" and user.role == "pegawai":
            PasporPegawai.objects.filter(pk=request.POST.get("id"), pegawai=user).delete()
            messages.success(request, "Data paspor dihapus.")
        elif aksi == "unggah_dokumen":
            jenis = request.POST.get("jenis", "")
            berkas = request.FILES.get("file")
            if jenis not in dict(jenis_dokumen) or not berkas:
                messages.error(request, "Pilih jenis dokumen dan berkasnya.")
            elif (galat := periksa_pdf(request, berkas)):
                messages.error(request, galat)
            else:
                dok = DokumenKepegawaian.objects.filter(user=user, jenis=jenis).first()
                if dok:
                    dok.file.delete(save=False)
                    dok.file = berkas
                    dok.save()
                else:
                    DokumenKepegawaian.objects.create(user=user, jenis=jenis, file=berkas)
                messages.success(request, "Dokumen berhasil diunggah.")
        return redirect("profil")

    dokumen = {d.jenis: d for d in DokumenKepegawaian.objects.filter(user=user)}
    return render(request, "akun/profil.html", {
        "profile": getattr(user, "profile", None),
        "paspor_list": PasporPegawai.objects.filter(pegawai=user),
        "jenis_paspor": PasporPegawai.Jenis.choices,
        "jenis_dokumen": [(k, label, dokumen.get(k)) for k, label in jenis_dokumen],
    })
