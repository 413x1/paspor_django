"""
Kegiatan PDLN — wiki/instructions/EVENT_IMPLEMENTATION_PLAN.MD §5 & §8.

- Admin Biro PAKLN : kelola semua kegiatan, putus usulan, aktif/nonaktif, hapus (bila belum dipakai).
- Admin BPSDM      : lihat kegiatan pendidikan/pelatihan, buat usulan T2P/T2L (B10a),
                     sunting usulannya selama menunggu.
- Pegawai          : usulkan kegiatan (B10) dari Formulir PDLN.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.views.decorators.http import require_POST

from logs.models import ActivityLog
from logs.utils import record_activity
from paspor.models import TIPE_KEGIATAN_BPSDM, Kegiatan, berlaku_untuk_tipe

from . import kegiatan as layanan
from . import report
from .decorators import role_required
from .forms import KegiatanForm, KeputusanKegiatanForm, dasar_formset
from .models import Pengajuan

K = Kegiatan.Status
AKTIVITAS = ActivityLog.Aktivitas.UBAH_KEGIATAN


def _log(request, deskripsi, kegiatan, status=ActivityLog.Status.BERHASIL, detail=""):
    record_activity(
        request, AKTIVITAS, deskripsi, status=status, detail=detail,
        target_type="kegiatan", target_id=str(kegiatan.pk) if kegiatan else "",
    )


def status_kegiatan_html(k):
    if k.status == K.DISETUJUI and not k.is_active:
        return format_html('<span class="tag kegiatan-status is-nonaktif">Nonaktif</span>')
    return format_html('<span class="tag kegiatan-status is-{}">{}</span>', k.status, k.get_status_display())


def _kategori_html(k):
    return format_html_join(", ", "{}", ((kat.nama_kategori,) for kat in k.kategori.all())) or "—"


def _search(nilai):
    return (
        Q(nama__icontains=nilai) | Q(penyelenggara__icontains=nilai) | Q(kota__icontains=nilai)
        | Q(negara__nama_negara__icontains=nilai)
    )


_ORDER_FIELDS = {"0": "nama", "2": "tgl_mulai", "3": "tahun_pelaksanaan", "5": "status", "6": "jumlah_peserta"}


def _datatable(request, qs, aksi_fn):
    """Respons DataTables server-side daftar kegiatan (pola `report.datatable`)."""
    qs = layanan.dengan_jumlah_peserta(qs).prefetch_related("negara", "kategori")
    records_total = qs.count()
    nilai = request.GET.get("search[value]", "").strip()
    if nilai:
        qs = qs.filter(_search(nilai)).distinct()
    records_filtered = qs.count()
    order_field = _ORDER_FIELDS.get(request.GET.get("order[0][column]"), "tgl_mulai")
    if request.GET.get("order[0][dir]") == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field, "nama")
    try:
        start, length = int(request.GET.get("start", 0)), int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    page = qs[start:] if length == -1 else qs[start:start + length]
    data = [[
        format_html('<strong>{}</strong><br><span class="cell-muted">{}</span>', k.nama, k.penyelenggara),
        format_html('{}<br><span class="cell-muted">{}</span>', k.negara_display or "—", k.kota),
        format_html("{}<br>s.d. {}", k.tgl_mulai.strftime("%d %b %Y"), k.tgl_selesai.strftime("%d %b %Y")),
        k.tahun_pelaksanaan,
        _kategori_html(k),
        status_kegiatan_html(k),
        k.jumlah_peserta,
        aksi_fn(k),
    ] for k in page]
    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


def _peserta(kegiatan, user):
    """Pengajuan yang memilih kegiatan, dibatasi cakupan role (§5.2)."""
    return (
        report.queryset_untuk(user).filter(kegiatan=kegiatan)
        .select_related("pegawai__profile", "unit_organisasi").order_by("-tgl_pengajuan")
    )


def _form_kegiatan(request, kegiatan, peran):
    data = request.POST if request.method == "POST" else None
    files = request.FILES if request.method == "POST" else None
    form = KegiatanForm(data, files, instance=kegiatan, peran=peran)
    formset = dasar_formset(data, files, instance=kegiatan, peran=peran)
    return form, formset


# ---------------------------------------------------------------------------
# Admin Biro PAKLN
# ---------------------------------------------------------------------------

_TAB_PAKLN = {
    "semua": ("Semua", lambda qs: qs.exclude(status=K.DITOLAK)),
    "menunggu": ("Menunggu Persetujuan", lambda qs: qs.filter(status=K.MENUNGGU)),
    "ditolak": ("Ditolak", lambda qs: qs.filter(status=K.DITOLAK)),
}


def _tab(request, daftar, bawaan):
    tab = request.GET.get("tab", bawaan)
    return tab if tab in daftar else bawaan


@role_required("admin_pakln")
def pakln_daftar(request):
    return render(request, "kegiatan/daftar.html", {
        "peran": "admin_pakln",
        "tab": _tab(request, _TAB_PAKLN, "semua"),
        "tabs": [(kunci, label) for kunci, (label, _) in _TAB_PAKLN.items()],
        "jumlah_menunggu": Kegiatan.objects.filter(status=K.MENUNGGU).count(),
        "data_url": reverse("pakln:kegiatan_data"),
        "tambah_url": reverse("pakln:tambah_kegiatan"),
    })


@role_required("admin_pakln")
def pakln_data(request):
    _, saring = _TAB_PAKLN[_tab(request, _TAB_PAKLN, "semua")]

    def aksi(k):
        tombol = [format_html('<a href="{}" class="button is-small{}">{}</a>',
                              reverse("pakln:edit_kegiatan", args=[k.pk]),
                              " is-warning" if k.status == K.MENUNGGU else "",
                              "Tinjau →" if k.status == K.MENUNGGU else "✎ Edit")]
        if k.status == K.DISETUJUI:
            tombol.append(format_html(
                '<button type="button" class="button is-small" data-kegiatan-toggle="{}">{}</button>',
                reverse("pakln:toggle_kegiatan", args=[k.pk]), "Nonaktifkan" if k.is_active else "Aktifkan",
            ))
        if not k.jumlah_peserta:
            tombol.append(format_html(
                '<button type="button" class="button is-small is-danger" data-kegiatan-hapus="{}">🗑 Hapus</button>',
                reverse("pakln:hapus_kegiatan", args=[k.pk]),
            ))
        return format_html('<div class="table-actions">{}</div>', format_html_join("", "{}", ((t,) for t in tombol)))

    return _datatable(request, saring(Kegiatan.objects.all()), aksi)


@role_required("admin_pakln")
def pakln_tambah(request):
    form, formset = _form_kegiatan(request, Kegiatan(), "admin_pakln")
    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            kegiatan = layanan.simpan(form, formset, request.user)
            _log(request, f"Menambah kegiatan {kegiatan.nama}", kegiatan)
            messages.success(request, f"Kegiatan '{kegiatan.nama}' berhasil ditambahkan.")
            return redirect("pakln:kelola_kegiatan")
        messages.error(request, "Periksa kembali isian formulir.")
    return render(request, "kegiatan/form.html", {
        "peran": "admin_pakln", "judul": "Tambah Kegiatan", "form": form, "formset": formset,
        "kembali_url": reverse("pakln:kelola_kegiatan"), "kembali_label": "Daftar Kegiatan",
        "tombol_simpan": "Simpan Kegiatan",
    })


@role_required("admin_pakln")
def pakln_edit(request, pk):
    kegiatan = get_object_or_404(Kegiatan, pk=pk)
    form, formset = _form_kegiatan(request, kegiatan, "admin_pakln")
    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            layanan.simpan(form, formset, request.user)
            _log(request, f"Mengubah kegiatan {kegiatan.nama}", kegiatan)
            messages.success(request, f"Kegiatan '{kegiatan.nama}' berhasil diperbarui.")
            return redirect("pakln:edit_kegiatan", pk=kegiatan.pk)
        messages.error(request, "Periksa kembali isian formulir.")
    return render(request, "kegiatan/form.html", {
        "peran": "admin_pakln", "judul": "Tinjau Usulan Kegiatan" if kegiatan.status == K.MENUNGGU else "Edit Kegiatan",
        "kegiatan": kegiatan, "form": form, "formset": formset,
        "kembali_url": reverse("pakln:kelola_kegiatan") + ("?tab=menunggu" if kegiatan.status == K.MENUNGGU else ""),
        "kembali_label": "Daftar Kegiatan", "tombol_simpan": "Simpan Perubahan",
        "keputusan_url": reverse("pakln:putuskan_kegiatan", args=[kegiatan.pk]) if kegiatan.status == K.MENUNGGU else "",
        "mirip": layanan.mirip(kegiatan.nama, kegiatan.tahun_pelaksanaan, kecuali=kegiatan.pk) if kegiatan.status == K.MENUNGGU else [],
        "peserta": _peserta(kegiatan, request.user),
    })


@role_required("admin_pakln")
@require_POST
def pakln_putuskan(request, pk):
    kegiatan = get_object_or_404(Kegiatan, pk=pk)
    form = KeputusanKegiatanForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
        return redirect("pakln:edit_kegiatan", pk=pk)
    setuju = form.cleaned_data["keputusan"] == "setujui"
    try:
        if setuju:
            layanan.setujui(kegiatan, request.user, form.cleaned_data["catatan"])
        else:
            layanan.tolak(kegiatan, request.user, form.cleaned_data["catatan"])
    except layanan.KegiatanError as exc:
        _log(request, "Memutus usulan kegiatan", kegiatan, status=ActivityLog.Status.GAGAL, detail=str(exc))
        messages.error(request, str(exc))
        return redirect("pakln:edit_kegiatan", pk=pk)
    _log(request, f"{'Menyetujui' if setuju else 'Menolak'} usulan kegiatan {kegiatan.nama}", kegiatan)
    messages.success(request, f"Usulan kegiatan '{kegiatan.nama}' {'disetujui' if setuju else 'ditolak'}.")
    return redirect(reverse("pakln:kelola_kegiatan") + "?tab=menunggu")


@role_required("admin_pakln")
@require_POST
def pakln_toggle(request, pk):
    kegiatan = get_object_or_404(Kegiatan, pk=pk, status=K.DISETUJUI)
    kegiatan.is_active = not kegiatan.is_active
    kegiatan.save(update_fields=["is_active", "updated_at"])
    _log(request, f"{'Mengaktifkan' if kegiatan.is_active else 'Menonaktifkan'} kegiatan {kegiatan.nama}", kegiatan)
    return JsonResponse({"ok": True, "is_active": kegiatan.is_active})


@role_required("admin_pakln")
@require_POST
def pakln_hapus(request, pk):
    """Hapus kegiatan yang belum dipakai pengajuan mana pun; yang sudah
    dipakai hanya dapat dinonaktifkan (B12)."""
    kegiatan = get_object_or_404(Kegiatan, pk=pk)
    if kegiatan.pengajuan_list.exists():
        _log(request, f"Menghapus kegiatan {kegiatan.nama}", kegiatan, status=ActivityLog.Status.GAGAL,
             detail="Masih dipakai pengajuan")
        return JsonResponse({
            "ok": False,
            "error": f"Kegiatan '{kegiatan.nama}' sudah dipakai pengajuan dan tidak dapat dihapus. Nonaktifkan saja.",
        }, status=400)
    for dasar in kegiatan.dasar_list.all():
        if dasar.berkas:
            dasar.berkas.delete(save=False)
    _log(request, f"Menghapus kegiatan {kegiatan.nama}", kegiatan)
    kegiatan.delete()
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Admin BPSDM (B10a)
# ---------------------------------------------------------------------------

_TAB_BPSDM = {"daftar": "Kegiatan Pendidikan & Pelatihan", "usulan": "Usulan Saya"}


def _qs_bpsdm(request, tab):
    if tab == "usulan":
        return Kegiatan.objects.filter(diusulkan_oleh=request.user)
    qs = Kegiatan.objects.filter(status=K.DISETUJUI, is_active=True).prefetch_related("kategori")
    ids = [k.pk for k in qs if any(berlaku_untuk_tipe(kat, t) for kat in k.kategori.all()
                                   for t in TIPE_KEGIATAN_BPSDM if kat.tipe_pdln)]
    return Kegiatan.objects.filter(pk__in=ids)


@role_required("admin_bpsdm")
def bpsdm_daftar(request):
    return render(request, "kegiatan/daftar.html", {
        "peran": "admin_bpsdm",
        "tab": _tab(request, _TAB_BPSDM, "daftar"),
        "tabs": list(_TAB_BPSDM.items()),
        "data_url": reverse("bpsdm:kegiatan_data"),
        "tambah_url": reverse("bpsdm:tambah_kegiatan"),
    })


@role_required("admin_bpsdm")
def bpsdm_data(request):
    tab = _tab(request, _TAB_BPSDM, "daftar")

    def aksi(k):
        if layanan.boleh_disunting_pengusul(k, request.user):
            return format_html('<a href="{}" class="button is-small">✎ Edit</a>', reverse("bpsdm:edit_kegiatan", args=[k.pk]))
        return format_html('<a href="{}" class="button is-small">Lihat</a>', reverse("bpsdm:edit_kegiatan", args=[k.pk]))

    return _datatable(request, _qs_bpsdm(request, tab), aksi)


@role_required("admin_bpsdm")
def bpsdm_tambah(request):
    form, formset = _form_kegiatan(request, Kegiatan(), "admin_bpsdm")
    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            kegiatan = layanan.usulkan(form, formset, request.user)
            _log(request, f"Mengusulkan kegiatan {kegiatan.nama}", kegiatan)
            messages.success(request, f"Usulan kegiatan '{kegiatan.nama}' dikirim ke Admin Biro PAKLN untuk disetujui.")
            return redirect(reverse("bpsdm:kegiatan") + "?tab=usulan")
        messages.error(request, "Periksa kembali isian formulir.")
    return render(request, "kegiatan/form.html", {
        "peran": "admin_bpsdm", "judul": "Tambah Kegiatan Pendidikan/Pelatihan", "form": form, "formset": formset,
        "kembali_url": reverse("bpsdm:kegiatan"), "kembali_label": "Daftar Kegiatan",
        "tombol_simpan": "Kirim untuk Persetujuan →",
        "info": "Kegiatan baru dapat dipilih pegawai setelah disetujui Admin Biro PAKLN.",
    })


@role_required("admin_bpsdm")
def bpsdm_edit(request, pk):
    """Sunting usulan sendiri selama menunggu; selain itu tampil read-only
    (kegiatan pendidikan/pelatihan yang disetujui, atau usulan sendiri)."""
    kegiatan = get_object_or_404(Kegiatan, pk=pk)
    dapat_diubah = layanan.boleh_disunting_pengusul(kegiatan, request.user)
    terlihat = kegiatan.diusulkan_oleh_id == request.user.pk or _qs_bpsdm(request, "daftar").filter(pk=pk).exists()
    if not terlihat:
        raise PermissionDenied("Anda tidak memiliki akses ke kegiatan ini.")
    if request.method == "POST" and not dapat_diubah:
        raise PermissionDenied("Usulan yang sudah diputus tidak dapat diubah.")
    form, formset = _form_kegiatan(request, kegiatan, "admin_bpsdm")
    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            layanan.simpan(form, formset, request.user)
            _log(request, f"Mengubah usulan kegiatan {kegiatan.nama}", kegiatan)
            messages.success(request, f"Usulan kegiatan '{kegiatan.nama}' berhasil diperbarui.")
            return redirect(reverse("bpsdm:kegiatan") + "?tab=usulan")
        messages.error(request, "Periksa kembali isian formulir.")
    return render(request, "kegiatan/form.html", {
        "peran": "admin_bpsdm", "judul": "Edit Usulan Kegiatan" if dapat_diubah else "Detail Kegiatan",
        "kegiatan": kegiatan, "form": form, "formset": formset, "readonly": not dapat_diubah,
        "kembali_url": reverse("bpsdm:kegiatan") + ("?tab=usulan" if kegiatan.diusulkan_oleh_id == request.user.pk else ""),
        "kembali_label": "Daftar Kegiatan", "tombol_simpan": "Simpan Perubahan",
        "peserta": _peserta(kegiatan, request.user),
    })


# ---------------------------------------------------------------------------
# Pegawai (B10)
# ---------------------------------------------------------------------------

def _url_formulir(request):
    tipe = request.GET.get("tipe") or request.POST.get("tipe") or ""
    url = reverse("pegawai:formulir_pengajuan")
    return f"{url}?jenis=pdln&tipe={tipe}" if tipe in Pengajuan.TipePdln.values else url


@role_required("pegawai")
def pegawai_usulkan(request):
    form, formset = _form_kegiatan(request, Kegiatan(), "pegawai")
    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            kegiatan = layanan.usulkan(form, formset, request.user)
            _log(request, f"Mengusulkan kegiatan {kegiatan.nama}", kegiatan)
            messages.success(request, (
                f"Usulan kegiatan '{kegiatan.nama}' dikirim ke Admin Biro PAKLN. Kegiatan dapat dipilih setelah "
                "disetujui; sementara itu formulir dapat disimpan tanpa kegiatan."
            ))
            return redirect(_url_formulir(request))
        messages.error(request, "Periksa kembali isian formulir.")
    nama = request.POST.get("nama", "") if request.method == "POST" else ""
    return render(request, "kegiatan/form.html", {
        "peran": "pegawai", "judul": "Usulkan Kegiatan Baru", "form": form, "formset": formset,
        "kembali_url": _url_formulir(request), "kembali_label": "Formulir Pengajuan",
        "tombol_simpan": "Kirim Usulan →", "tipe": request.GET.get("tipe", ""),
        "info": "Usulan kegiatan baru dapat dipilih setelah disetujui Admin Biro PAKLN. Periksa dulu daftar "
                "kegiatan pada formulir agar tidak terjadi duplikat.",
        "mirip": layanan.mirip(nama) if nama else [],
    })


def usulan_pegawai(user):
    """Usulan kegiatan milik pegawai — kartu "Usulan Kegiatan Saya" pada
    Beranda (§8.3) dan pengingat di Formulir PDLN."""
    return Kegiatan.objects.filter(diusulkan_oleh=user).order_by("-created_at")
