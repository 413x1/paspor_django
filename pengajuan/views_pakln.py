import base64
import csv
from datetime import datetime

from django.contrib import messages
from django.contrib.staticfiles import finders
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from accounts.forms import EditUserForm, TambahUserForm
from accounts.models import User
from notifications.services import notify_complete_pkln, notify_reject_pakln_to_unor
from paspor.models import KategoriPerjalanan, Negara, SumberPembiayaan

from .decorators import role_required
from .forms import DokumenPaklnForm, DokumenTemplateForm, KategoriPerjalananForm, NegaraForm, SumberPembiayaanForm
from .models import DokumenPakln, DokumenPaklnPendukung, DokumenTemplate, Pengajuan

_BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _tanggal_indonesia(tanggal):
    return f"{tanggal.day} {_BULAN_ID[tanggal.month - 1]} {tanggal.year}"


def _parse_tanggal_display(value):
    """String tanggal dari <input type="date"> (YYYY-MM-DD) -> 'd Bulan
    YYYY' berbahasa Indonesia, atau '' jika kosong/tidak valid."""
    try:
        tanggal = datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return ""
    return _tanggal_indonesia(tanggal)


def _hitung_hari_kalender(tgl_berangkat, tgl_kembali):
    try:
        berangkat = datetime.strptime(tgl_berangkat, "%Y-%m-%d").date()
        kembali = datetime.strptime(tgl_kembali, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    delta = (kembali - berangkat).days + 1
    return delta if delta > 0 else None


def _logo_data_uri():
    """Logo sebagai data URI (base64) — dipakai di template PDF supaya
    WeasyPrint tidak perlu fetch balik ke server (menghindari risiko
    deadlock/lambat saat render PDF dari dalam request yang sedang berjalan)."""
    path = finders.find("images/logopu.png")
    if not path:
        return ""
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@role_required("admin_pakln")
def generate_nd_kabag(request):
    """Generate Dokumen — Nota Dinas Kepala Bagian (konsep ND dari Plt.
    Kepala Bagian Kerja Sama Luar Negeri ke Kepala Biro PAKLN). Halaman
    berisi form input + pratinjau langsung (live preview) yang diperbarui
    lewat jQuery di sisi klien. Tombol "Unduh PDF" men-submit form ini
    (POST biasa) ke `download_nd_kabag_pdf`."""
    return render(request, "pakln/generate_nd_kabag.html")


@role_required("admin_pakln")
@require_POST
def download_nd_kabag_pdf(request):
    """Cetak Nota Dinas Kepala Bagian jadi PDF (WeasyPrint) dari data form
    Generate ND Kabag. Dikirim lewat submit form biasa (bukan AJAX) supaya
    browser langsung menerima file unduhan dari response ini."""
    context = {
        "nama": request.POST.get("nama", "").strip() or "[nama]",
        "negara_tujuan": request.POST.get("negara_tujuan", "").strip() or "[negara tujuan]",
        "nip": request.POST.get("nip", "").strip(),
        "pangkat_golongan": request.POST.get("pangkat_golongan", "").strip(),
        "jabatan": request.POST.get("jabatan", "").strip(),
        "unit_kerja": request.POST.get("unit_kerja", "").strip(),
        "maksud_perjalanan": request.POST.get("maksud_perjalanan", "").strip(),
        "sumber_pembiayaan": request.POST.get("sumber_pembiayaan", "").strip(),
        "tgl_berangkat": request.POST.get("tgl_berangkat", "").strip(),
        "tgl_kembali": request.POST.get("tgl_kembali", "").strip(),
        "tanggal_nota_dinas": _tanggal_indonesia(timezone.now().date()),
        "logo_data_uri": _logo_data_uri(),
    }
    html_string = render_to_string("pakln/pdf_template_nd_kabag.html", context)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_string).write_pdf()
    except ImportError:
        messages.error(request, "Gagal membuat PDF: pustaka WeasyPrint belum terpasang di server ini.")
        return redirect("pakln:generate_nd_kabag")
    except OSError:
        messages.error(
            request,
            "Gagal membuat PDF: WeasyPrint memerlukan pustaka native GTK/Pango yang belum "
            "terpasang di server ini (lihat dokumentasi instalasi WeasyPrint untuk Windows/Linux).",
        )
        return redirect("pakln:generate_nd_kabag")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="Nota_Dinas_Kabag.pdf"'
    return response


@role_required("admin_pakln")
def generate_nd_karo(request):
    """Generate Dokumen — Nota Dinas Kepala Biro (permohonan Persetujuan
    Izin Perjalanan ke Luar Negeri dari Kepala Biro PAKLN ke Sekretaris
    Jenderal), meniru struktur `generate_nd_kabag` — form input + live
    preview jQuery, tombol "Unduh PDF" men-submit ke
    `download_nd_karo_pdf`."""
    return render(request, "pakln/generate_nd_karo.html")


@role_required("admin_pakln")
@require_POST
def download_nd_karo_pdf(request):
    """Cetak Nota Dinas Kepala Biro jadi PDF (WeasyPrint) dari data form
    Generate ND Karo."""
    tgl_berangkat = request.POST.get("tgl_berangkat", "").strip()
    tgl_kembali = request.POST.get("tgl_kembali", "").strip()
    hari_kalender = _hitung_hari_kalender(tgl_berangkat, tgl_kembali)

    context = {
        "nama": request.POST.get("nama", "").strip() or "[nama]",
        "negara_tujuan": request.POST.get("negara_tujuan", "").strip() or "[negara tujuan]",
        "nip": request.POST.get("nip", "").strip() or "[nip]",
        "pangkat_golongan": request.POST.get("pangkat_golongan", "").strip(),
        "jabatan": request.POST.get("jabatan", "").strip() or "[jabatan]",
        "unit_kerja": request.POST.get("unit_kerja", "").strip() or "[nama unor]",
        "maksud_perjalanan": request.POST.get("maksud_perjalanan", "").strip() or "[keperluan]",
        "sumber_pembiayaan": request.POST.get("sumber_pembiayaan", "").strip() or "[sumber biaya]",
        "tgl_berangkat_display": _parse_tanggal_display(tgl_berangkat) or "[tanggal berangkat]",
        "tgl_kembali_display": _parse_tanggal_display(tgl_kembali) or "[tanggal pulang]",
        "jumlah_hari_kerja": request.POST.get("jumlah_hari_kerja", "").strip() or "[h_kerja]",
        "jumlah_hari_kalender": hari_kalender if hari_kalender is not None else "[h_kalender]",
        "tanggal_nota_dinas": _tanggal_indonesia(timezone.now().date()),
        "logo_data_uri": _logo_data_uri(),
    }
    html_string = render_to_string("pakln/pdf_template_nd_karo.html", context)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_string).write_pdf()
    except ImportError:
        messages.error(request, "Gagal membuat PDF: pustaka WeasyPrint belum terpasang di server ini.")
        return redirect("pakln:generate_nd_karo")
    except OSError:
        messages.error(
            request,
            "Gagal membuat PDF: WeasyPrint memerlukan pustaka native GTK/Pango yang belum "
            "terpasang di server ini (lihat dokumentasi instalasi WeasyPrint untuk Windows/Linux).",
        )
        return redirect("pakln:generate_nd_karo")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="Nota_Dinas_Karo.pdf"'
    return response


@role_required("admin_pakln")
def dashboard(request):
    """Tahap 2: Dasbor — menampilkan seluruh pengajuan yang sudah dikirim
    pegawai (status != belum), termasuk yang masih diproses Admin Unor,
    supaya Admin Biro PAKLN dapat memantau progres lebih awal. Hanya
    pengajuan berstatus proses_pakln/selesai yang dapat ditindaklanjuti
    (lihat template — link TL hanya muncul untuk status tersebut)."""
    pengajuan_list = (
        Pengajuan.objects.exclude(status=Pengajuan.Status.BELUM)
        .select_related("pegawai__profile")
    )
    summary = {
        "total": pengajuan_list.count(),
        "proses_unor": pengajuan_list.filter(status=Pengajuan.Status.PROSES).count(),
        "proses_pakln": pengajuan_list.filter(status=Pengajuan.Status.PROSES_PAKLN).count(),
        "selesai": pengajuan_list.filter(status=Pengajuan.Status.SELESAI).count(),
    }
    return render(request, "pakln/dashboard.html", {"summary": summary})


# Kolom tabel "Tabel Rincian Pengajuan" (index sesuai urutan kolom pada
# pakln/dashboard.html) -> field untuk pengurutan (ORDER BY) di endpoint
# server-side DataTables. Kolom Jenis (statis), Tujuan (M2M), dan Action
# sengaja tidak disertakan — tidak diurutkan di JS (orderable:false).
_PAKLN_DASHBOARD_ORDER_FIELDS = {
    "0": "pegawai__profile__nama",
    "1": "pegawai__profile__unit_organisasi__name",
    "3": "kategori__nama_kategori",
    "5": "tgl_berangkat",
    "6": "tgl_kembali",
    "7": "tgl_masuk_pakln",
    "8": "status",
}


@role_required("admin_pakln")
def dashboard_data(request):
    """Endpoint JSON server-side untuk "Tabel Rincian Pengajuan" pada
    Dasbor Admin Biro PAKLN (protokol DataTables: draw/start/length/
    search/order pada GET), mengikuti pola `users_data` (Manajemen User)."""
    qs = (
        Pengajuan.objects.exclude(status=Pengajuan.Status.BELUM)
        .select_related("pegawai__profile__unit_organisasi", "kategori")
    )
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(pegawai__profile__nama__icontains=search_value)
            | Q(pegawai__profile__nip__icontains=search_value)
            | Q(pegawai__profile__unit_organisasi__name__icontains=search_value)
            | Q(kategori__nama_kategori__icontains=search_value)
            | Q(tujuan_negara__nama_negara__icontains=search_value)
        ).distinct()
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _PAKLN_DASHBOARD_ORDER_FIELDS.get(order_col, "-created_at")
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
        pegawai_html = format_html(
            "<strong>{}</strong><br><span class=\"cell-muted\">{}</span>",
            p.pegawai.profile.nama, p.pegawai.profile.nip,
        )
        unit = p.pegawai.profile.unit_organisasi
        status_html = format_html(
            '<span class="tag paspor-status is-{}"><span class="dot"></span>{}</span>',
            p.status, p.get_status_display(),
        )

        if p.status == Pengajuan.Status.PROSES:
            aksi_html = mark_safe('<span class="cell-muted">Menunggu Admin Unor</span>')
        elif p.status == Pengajuan.Status.PROSES_PAKLN and not p.preview_pakln_agree:
            aksi_html = format_html(
                '<a href="{}" class="button is-warning is-small">TL →</a>',
                reverse("pakln:preview", args=[p.kode]),
            )
        elif p.status == Pengajuan.Status.PROSES_PAKLN:
            aksi_html = format_html(
                '<a href="{}" class="button is-warning is-small">TL →</a>',
                reverse("pakln:upload_dokumen", args=[p.kode]),
            )
        else:
            aksi_html = format_html(
                '<a href="{}" class="button is-small">Lihat</a>',
                reverse("pakln:preview", args=[p.kode]),
            )

        data.append([
            pegawai_html,
            escape(unit.name if unit else "—"),
            "Non-Kedinasan",
            escape(p.kategori.nama_kategori) if p.kategori else "—",
            escape(p.tujuan_negara_display or "—"),
            p.tgl_berangkat.strftime("%d %b %Y") if p.tgl_berangkat else "—",
            p.tgl_kembali.strftime("%d %b %Y") if p.tgl_kembali else "—",
            p.tgl_masuk_pakln.strftime("%d %b %Y") if p.tgl_masuk_pakln else "—",
            status_html,
            aksi_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


@role_required("admin_pakln")
def kelola_user(request):
    """Manajemen User — Admin Biro PAKLN membuat akun baru untuk
    Pegawai atau Admin Unor."""
    if request.method == "POST":
        form = TambahUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f"User {user.username} ({user.get_role_display()}) berhasil dibuat.",
            )
            return redirect("pakln:kelola_user")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = TambahUserForm()

    users_count = User.objects.filter(role__in=[User.Role.PEGAWAI, User.Role.ADMIN_UNOR]).count()
    return render(request, "pakln/users.html", {"form": form, "users_count": users_count})


# Kolom tabel "Daftar User" (index sesuai urutan kolom pada users.html) ->
# field untuk pengurutan (ORDER BY) di endpoint server-side DataTables.
_USERS_DATA_ORDER_FIELDS = {
    "0": "username",
    "1": "profile__nama",
    "2": "role",
    "3": "profile__nip",
    "4": "unit_organisasi__name",
    "5": "is_active",
}


@role_required("admin_pakln")
def users_data(request):
    """Endpoint JSON server-side untuk tabel "Daftar User" (protokol
    DataTables: draw/start/length/search/order pada GET)."""
    qs = (
        User.objects.filter(role__in=[User.Role.PEGAWAI, User.Role.ADMIN_UNOR])
        .select_related("profile", "unit_organisasi", "profile__unit_organisasi")
    )
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(username__icontains=search_value)
            | Q(first_name__icontains=search_value)
            | Q(last_name__icontains=search_value)
            | Q(profile__nama__icontains=search_value)
            | Q(profile__nip__icontains=search_value)
            | Q(unit_organisasi__name__icontains=search_value)
            | Q(profile__unit_organisasi__name__icontains=search_value)
        ).distinct()
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _USERS_DATA_ORDER_FIELDS.get(order_col, "username")
    if request.GET.get("order[0][dir]") == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field, "username")

    try:
        start = int(request.GET.get("start", 0))
        length = int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    page = qs[start:] if length == -1 else qs[start:start + length]

    data = []
    for u in page:
        profile = getattr(u, "profile", None)
        nama = (profile.nama if profile else None) or u.get_full_name() or "—"
        nip = (profile.nip if profile else "") or "—"
        unit = u.unit_organisasi or (profile.unit_organisasi if profile else None)
        if u.is_active:
            status_html = mark_safe(
                '<span class="tag paspor-status is-selesai"><span class="dot"></span>Aktif</span>'
            )
        else:
            status_html = mark_safe(
                '<span class="tag paspor-status is-belum"><span class="dot"></span>Nonaktif</span>'
            )
        aksi_html = format_html(
            '<a href="{}" class="button is-small">✎ Edit</a>',
            reverse("pakln:edit_user", args=[u.pk]),
        )
        data.append([
            format_html("<strong>{}</strong>", u.username),
            escape(nama),
            u.get_role_display(),
            escape(nip),
            escape(unit.name if unit else "—"),
            status_html,
            aksi_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


@role_required("admin_pakln")
def edit_user(request, user_id):
    """Sunting user (Pegawai / Admin Unor) yang sudah ada."""
    user_obj = get_object_or_404(
        User.objects.select_related("profile", "unit_organisasi"),
        pk=user_id,
        role__in=[User.Role.PEGAWAI, User.Role.ADMIN_UNOR],
    )
    profile = getattr(user_obj, "profile", None)

    if request.method == "POST":
        form = EditUserForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"User {user_obj.username} berhasil diperbarui.")
            return redirect("pakln:kelola_user")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        nama = (profile.nama if profile else user_obj.get_full_name()) or user_obj.username
        initial = {
            "username": user_obj.username,
            "nama": nama,
            "is_active": user_obj.is_active,
            "unit_organisasi": user_obj.unit_organisasi_id,
            "unit_kerja": user_obj.unit_kerja,
        }
        if profile:
            initial.update({
                "nip": profile.nip,
                "jabatan": profile.jabatan,
                "pangkat_golongan": profile.pangkat_golongan,
                "sisa_cuti_tahun_berjalan": profile.sisa_cuti_tahun_berjalan,
            })
        form = EditUserForm(instance=user_obj, initial=initial)

    return render(request, "pakln/edit_user.html", {"form": form, "user_obj": user_obj})


@role_required("admin_pakln")
def kelola_template(request):
    """Manajemen Template — Admin Biro PAKLN mengunggah berkas template
    (PDF/DOCX) yang dapat diunduh Pegawai dan/atau Admin Unor, dengan
    penargetan opsional (peran, unit organisasi, kategori perjalanan)."""
    if request.method == "POST":
        form = DokumenTemplateForm(request.POST, request.FILES)
        if form.is_valid():
            template = form.save(commit=False)
            template.diunggah_oleh = request.user
            template.save()
            form.save_m2m()
            messages.success(request, f"Template '{template.nama}' berhasil disimpan.")
            return redirect("pakln:kelola_template")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = DokumenTemplateForm()

    return render(
        request, "pakln/templates.html",
        {"form": form, "template_count": DokumenTemplate.objects.count()},
    )


# Kolom tabel "Daftar Template" (index sesuai urutan kolom pada
# templates.html) -> field untuk pengurutan (ORDER BY) di endpoint
# server-side DataTables. Kolom Target/Unit Organisasi (M2M/kombinasi
# boolean) sengaja tidak disertakan — tidak diurutkan di JS (orderable:false).
_TEMPLATES_DATA_ORDER_FIELDS = {
    "0": "nama",
    "3": "kategori__nama_kategori",
    "4": "aktif",
}


@role_required("admin_pakln")
def templates_data(request):
    """Endpoint JSON server-side untuk tabel "Daftar Template" (protokol
    DataTables: draw/start/length/search/order pada GET), mengikuti pola
    `users_data` (Manajemen User)."""
    qs = DokumenTemplate.objects.select_related("kategori").prefetch_related("unit_organisasi")
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(nama__icontains=search_value)
            | Q(keterangan__icontains=search_value)
            | Q(kategori__nama_kategori__icontains=search_value)
            | Q(unit_organisasi__name__icontains=search_value)
        ).distinct()
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _TEMPLATES_DATA_ORDER_FIELDS.get(order_col, "nama")
    if request.GET.get("order[0][dir]") == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field, "nama")

    try:
        start = int(request.GET.get("start", 0))
        length = int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    page = qs[start:] if length == -1 else qs[start:start + length]

    data = []
    for t in page:
        nama_html = format_html("<strong>{}</strong>", t.nama)
        if t.keterangan:
            nama_html = format_html("{}<br><span class=\"cell-muted\">{}</span>", nama_html, t.keterangan)

        target_parts = []
        if t.untuk_pegawai:
            target_parts.append('<span class="badge-auto">Pegawai</span>')
        if t.untuk_admin_unor:
            target_parts.append('<span class="badge-auto">Admin Unor</span>')
        target_html = mark_safe("".join(target_parts))

        units = list(t.unit_organisasi.all())
        if units:
            unit_html = mark_safe("".join(
                format_html('<span class="badge-auto">{}</span>', u.alias) for u in units
            ))
        else:
            unit_html = mark_safe('<span class="cell-muted">Semua unit</span>')

        kategori_html = escape(t.kategori.nama_kategori) if t.kategori else mark_safe(
            '<span class="cell-muted">Semua kategori</span>'
        )

        if t.aktif:
            status_html = mark_safe(
                '<span class="tag paspor-status is-selesai"><span class="dot"></span>Aktif</span>'
            )
            toggle_label = "🙈 Sembunyikan"
        else:
            status_html = mark_safe(
                '<span class="tag paspor-status is-belum"><span class="dot"></span>Disembunyikan</span>'
            )
            toggle_label = "👁 Tampilkan"

        aksi_html = format_html(
            '<div class="table-actions">'
            '<a href="{}" target="_blank" rel="noopener" class="button is-small">⬇ Unduh</a>'
            '<a href="{}" class="button is-small">✎ Edit</a>'
            '<button type="button" class="button is-small" data-template-toggle="{}">{}</button>'
            '<button type="button" class="button is-small is-danger" data-template-hapus="{}">🗑 Hapus</button>'
            '</div>',
            t.file.url,
            reverse("pakln:edit_template", args=[t.pk]),
            reverse("pakln:toggle_template", args=[t.pk]),
            toggle_label,
            reverse("pakln:hapus_template", args=[t.pk]),
        )
        data.append([nama_html, target_html, unit_html, kategori_html, status_html, aksi_html])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


@role_required("admin_pakln")
def edit_template(request, template_id):
    """Sunting template yang sudah ada."""
    template = get_object_or_404(DokumenTemplate, pk=template_id)

    if request.method == "POST":
        form = DokumenTemplateForm(request.POST, request.FILES, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, f"Template '{template.nama}' berhasil diperbarui.")
            return redirect("pakln:kelola_template")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = DokumenTemplateForm(instance=template)

    return render(request, "pakln/edit_template.html", {"form": form, "template": template})


@role_required("admin_pakln")
@require_POST
def toggle_template(request, template_id):
    """Tampilkan/sembunyikan template (AJAX, dipanggil dari tabel Data
    Table Server-Side) tanpa membuka form edit."""
    template = get_object_or_404(DokumenTemplate, pk=template_id)
    template.aktif = not template.aktif
    template.save(update_fields=["aktif"])
    return JsonResponse({"ok": True, "aktif": template.aktif})


@role_required("admin_pakln")
@require_POST
def hapus_template(request, template_id):
    """Hapus template beserta berkasnya (AJAX)."""
    template = get_object_or_404(DokumenTemplate, pk=template_id)
    template.file.delete(save=False)
    template.delete()
    return JsonResponse({"ok": True})


@role_required("admin_pakln")
def kelola_negara(request):
    """Manajemen Negara — Admin Biro PAKLN mengelola daftar negara yang
    menjadi sumber pilihan pada dropdown "Tujuan Negara" di Formulir
    Pengajuan (hanya negara `is_active=True` yang ditawarkan ke pegawai)."""
    if request.method == "POST":
        form = NegaraForm(request.POST)
        if form.is_valid():
            negara = form.save()
            messages.success(request, f"Negara '{negara.nama_negara}' berhasil ditambahkan.")
            return redirect("pakln:kelola_negara")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = NegaraForm()

    return render(
        request, "pakln/negara.html", {"form": form, "negara_count": Negara.objects.count()},
    )


# Kolom tabel "Daftar Negara" (index sesuai urutan kolom pada negara.html)
# -> field untuk pengurutan (ORDER BY) di endpoint server-side DataTables.
_NEGARA_DATA_ORDER_FIELDS = {
    "0": "nama_negara",
    "1": "kode_negara",
    "2": "is_active",
}


@role_required("admin_pakln")
def negara_data(request):
    """Endpoint JSON server-side untuk tabel "Daftar Negara" (protokol
    DataTables: draw/start/length/search/order pada GET), mengikuti pola
    `users_data` (Manajemen User)."""
    qs = Negara.objects.all()
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(nama_negara__icontains=search_value) | Q(kode_negara__icontains=search_value)
        )
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _NEGARA_DATA_ORDER_FIELDS.get(order_col, "nama_negara")
    if request.GET.get("order[0][dir]") == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field, "nama_negara")

    try:
        start = int(request.GET.get("start", 0))
        length = int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    page = qs[start:] if length == -1 else qs[start:start + length]

    data = []
    for n in page:
        if n.is_active:
            status_html = mark_safe(
                '<span class="tag paspor-status is-selesai"><span class="dot"></span>Aktif</span>'
            )
            toggle_label = "🙏 Nonaktifkan"
        else:
            status_html = mark_safe(
                '<span class="tag paspor-status is-belum"><span class="dot"></span>Nonaktif</span>'
            )
            toggle_label = "👁 Aktifkan"

        aksi_html = format_html(
            '<div class="table-actions">'
            '<a href="{}" class="button is-small">✎ Edit</a>'
            '<button type="button" class="button is-small" data-negara-toggle="{}">{}</button>'
            '<button type="button" class="button is-small is-danger" data-negara-hapus="{}">🗑 Hapus</button>'
            '</div>',
            reverse("pakln:edit_negara", args=[n.pk]),
            reverse("pakln:toggle_negara", args=[n.pk]),
            toggle_label,
            reverse("pakln:hapus_negara", args=[n.pk]),
        )
        data.append([
            format_html("<strong>{}</strong>", n.nama_negara),
            escape(n.kode_negara or "—"),
            status_html,
            aksi_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


@role_required("admin_pakln")
def edit_negara(request, negara_id):
    """Sunting negara yang sudah ada."""
    negara = get_object_or_404(Negara, pk=negara_id)

    if request.method == "POST":
        form = NegaraForm(request.POST, instance=negara)
        if form.is_valid():
            form.save()
            messages.success(request, f"Negara '{negara.nama_negara}' berhasil diperbarui.")
            return redirect("pakln:kelola_negara")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = NegaraForm(instance=negara)

    return render(request, "pakln/edit_negara.html", {"form": form, "negara": negara})


@role_required("admin_pakln")
@require_POST
def toggle_negara(request, negara_id):
    """Aktifkan/nonaktifkan negara (AJAX, dipanggil dari tabel Data Table
    Server-Side) tanpa membuka form edit. Negara nonaktif tidak lagi
    ditawarkan pada Formulir Pengajuan, tapi pengajuan lama yang sudah
    memilihnya tidak terpengaruh."""
    negara = get_object_or_404(Negara, pk=negara_id)
    negara.is_active = not negara.is_active
    negara.save(update_fields=["is_active"])
    return JsonResponse({"ok": True, "is_active": negara.is_active})


@role_required("admin_pakln")
@require_POST
def hapus_negara(request, negara_id):
    """Hapus permanen data negara (AJAX). Ditolak jika negara ini masih
    dipakai pada satu atau lebih pengajuan (riwayat/jejak audit) — gunakan
    nonaktifkan untuk kasus itu."""
    negara = get_object_or_404(Negara, pk=negara_id)
    if negara.pengajuan_list.exists():
        return JsonResponse({
            "ok": False,
            "error": (
                f"Negara '{negara.nama_negara}' tidak dapat dihapus karena masih dipakai pada "
                f"pengajuan yang sudah ada. Nonaktifkan saja agar tidak lagi ditawarkan."
            ),
        }, status=400)
    negara.delete()
    return JsonResponse({"ok": True})


@role_required("admin_pakln")
def kelola_sumber_pembiayaan(request):
    """Manajemen Sumber Pembiayaan — Admin Biro PAKLN mengelola daftar
    sumber pembiayaan yang menjadi pilihan pada dropdown "Sumber
    Pembiayaan" di Formulir Pengajuan (hanya `is_active=True` yang
    ditawarkan ke pegawai)."""
    if request.method == "POST":
        form = SumberPembiayaanForm(request.POST)
        if form.is_valid():
            sumber = form.save()
            messages.success(request, f"Sumber pembiayaan '{sumber.nama}' berhasil ditambahkan.")
            return redirect("pakln:kelola_sumber_pembiayaan")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = SumberPembiayaanForm()

    return render(
        request, "pakln/sumber_pembiayaan.html",
        {"form": form, "sumber_count": SumberPembiayaan.objects.count()},
    )


# Kolom tabel "Daftar Sumber Pembiayaan" (index sesuai urutan kolom pada
# sumber_pembiayaan.html) -> field untuk pengurutan (ORDER BY) di endpoint
# server-side DataTables.
_SUMBER_PEMBIAYAAN_DATA_ORDER_FIELDS = {
    "0": "nama",
    "1": "tipe_perjalanan",
    "2": "keterangan",
    "3": "is_active",
}


@role_required("admin_pakln")
def sumber_pembiayaan_data(request):
    """Endpoint JSON server-side untuk tabel "Daftar Sumber Pembiayaan"
    (protokol DataTables: draw/start/length/search/order pada GET),
    mengikuti pola `users_data` (Manajemen User)."""
    qs = SumberPembiayaan.objects.all()
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(nama__icontains=search_value)
            | Q(tipe_perjalanan__icontains=search_value)
            | Q(keterangan__icontains=search_value)
        )
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _SUMBER_PEMBIAYAAN_DATA_ORDER_FIELDS.get(order_col, "nama")
    if request.GET.get("order[0][dir]") == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field, "nama")

    try:
        start = int(request.GET.get("start", 0))
        length = int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    page = qs[start:] if length == -1 else qs[start:start + length]

    data = []
    for s in page:
        if s.is_active:
            status_html = mark_safe(
                '<span class="tag paspor-status is-selesai"><span class="dot"></span>Aktif</span>'
            )
            toggle_label = "🙏 Nonaktifkan"
        else:
            status_html = mark_safe(
                '<span class="tag paspor-status is-belum"><span class="dot"></span>Nonaktif</span>'
            )
            toggle_label = "👁 Aktifkan"

        aksi_html = format_html(
            '<div class="table-actions">'
            '<a href="{}" class="button is-small">✎ Edit</a>'
            '<button type="button" class="button is-small" data-sumber-toggle="{}">{}</button>'
            '<button type="button" class="button is-small is-danger" data-sumber-hapus="{}">🗑 Hapus</button>'
            '</div>',
            reverse("pakln:edit_sumber_pembiayaan", args=[s.pk]),
            reverse("pakln:toggle_sumber_pembiayaan", args=[s.pk]),
            toggle_label,
            reverse("pakln:hapus_sumber_pembiayaan", args=[s.pk]),
        )
        data.append([
            format_html("<strong>{}</strong>", s.nama),
            s.get_tipe_perjalanan_display(),
            escape(s.keterangan or "—"),
            status_html,
            aksi_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


@role_required("admin_pakln")
def edit_sumber_pembiayaan(request, sumber_id):
    """Sunting sumber pembiayaan yang sudah ada."""
    sumber = get_object_or_404(SumberPembiayaan, pk=sumber_id)

    if request.method == "POST":
        form = SumberPembiayaanForm(request.POST, instance=sumber)
        if form.is_valid():
            form.save()
            messages.success(request, f"Sumber pembiayaan '{sumber.nama}' berhasil diperbarui.")
            return redirect("pakln:kelola_sumber_pembiayaan")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = SumberPembiayaanForm(instance=sumber)

    return render(request, "pakln/edit_sumber_pembiayaan.html", {"form": form, "sumber": sumber})


@role_required("admin_pakln")
@require_POST
def toggle_sumber_pembiayaan(request, sumber_id):
    """Aktifkan/nonaktifkan sumber pembiayaan (AJAX, dipanggil dari tabel
    Data Table Server-Side) tanpa membuka form edit. Sumber nonaktif tidak
    lagi ditawarkan pada Formulir Pengajuan, tapi pengajuan lama yang
    sudah memilihnya tidak terpengaruh."""
    sumber = get_object_or_404(SumberPembiayaan, pk=sumber_id)
    sumber.is_active = not sumber.is_active
    sumber.save(update_fields=["is_active"])
    return JsonResponse({"ok": True, "is_active": sumber.is_active})


@role_required("admin_pakln")
@require_POST
def hapus_sumber_pembiayaan(request, sumber_id):
    """Hapus permanen data sumber pembiayaan (AJAX). Ditolak jika masih
    dipakai pada satu atau lebih pengajuan (riwayat/jejak audit) — gunakan
    nonaktifkan untuk kasus itu."""
    sumber = get_object_or_404(SumberPembiayaan, pk=sumber_id)
    if sumber.pengajuan_list.exists():
        return JsonResponse({
            "ok": False,
            "error": (
                f"Sumber pembiayaan '{sumber.nama}' tidak dapat dihapus karena masih dipakai pada "
                f"pengajuan yang sudah ada. Nonaktifkan saja agar tidak lagi ditawarkan."
            ),
        }, status=400)
    sumber.delete()
    return JsonResponse({"ok": True})


@role_required("admin_pakln")
def kelola_kategori(request):
    """Manajemen Kategori Perjalanan — Admin Biro PAKLN mengelola daftar
    kategori yang menjadi pilihan pada dropdown "Kategori Perjalanan" di
    Formulir Pengajuan (hanya `is_active=True` yang ditawarkan ke pegawai).
    Daftarnya ditampilkan sebagai Data Table Server-Side (lihat
    `kategori_data`)."""
    if request.method == "POST":
        form = KategoriPerjalananForm(request.POST)
        if form.is_valid():
            kategori = form.save()
            messages.success(request, f"Kategori '{kategori.nama_kategori}' berhasil ditambahkan.")
            return redirect("pakln:kelola_kategori")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = KategoriPerjalananForm()

    return render(
        request, "pakln/kategori.html",
        {"form": form, "kategori_count": KategoriPerjalanan.objects.count()},
    )


# Kolom tabel "Daftar Kategori Perjalanan" (index sesuai urutan kolom pada
# kategori.html) -> field untuk pengurutan (ORDER BY) di endpoint
# server-side DataTables.
_KATEGORI_DATA_ORDER_FIELDS = {
    "0": "nama_kategori",
    "1": "jenis_perjalanan",
    "2": "is_active",
}


@role_required("admin_pakln")
def kategori_data(request):
    """Endpoint JSON server-side untuk tabel "Daftar Kategori Perjalanan"
    (protokol DataTables: draw/start/length/search/order pada GET) —
    dipanggil oleh field dropdown Kategori Perjalanan pada Formulir
    Pengajuan secara tidak langsung (lewat `KategoriPerjalanan.objects
    .filter(is_active=True)` di form), dan langsung oleh tabel admin ini."""
    qs = KategoriPerjalanan.objects.all()
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(nama_kategori__icontains=search_value) | Q(jenis_perjalanan__icontains=search_value)
        )
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _KATEGORI_DATA_ORDER_FIELDS.get(order_col, "nama_kategori")
    if request.GET.get("order[0][dir]") == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field, "nama_kategori")

    try:
        start = int(request.GET.get("start", 0))
        length = int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    page = qs[start:] if length == -1 else qs[start:start + length]

    data = []
    for k in page:
        if k.is_active:
            status_html = mark_safe(
                '<span class="tag paspor-status is-selesai"><span class="dot"></span>Aktif</span>'
            )
            toggle_label = "🙏 Nonaktifkan"
        else:
            status_html = mark_safe(
                '<span class="tag paspor-status is-belum"><span class="dot"></span>Nonaktif</span>'
            )
            toggle_label = "👁 Aktifkan"

        aksi_html = format_html(
            '<div class="table-actions">'
            '<a href="{}" class="button is-small">✎ Edit</a>'
            '<button type="button" class="button is-small" data-kategori-toggle="{}">{}</button>'
            '<button type="button" class="button is-small is-danger" data-kategori-hapus="{}">🗑 Hapus</button>'
            '</div>',
            reverse("pakln:edit_kategori", args=[k.pk]),
            reverse("pakln:toggle_kategori", args=[k.pk]),
            toggle_label,
            reverse("pakln:hapus_kategori", args=[k.pk]),
        )
        data.append([
            format_html("<strong>{}</strong>", k.nama_kategori),
            k.get_jenis_perjalanan_display(),
            status_html,
            aksi_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })


@role_required("admin_pakln")
def edit_kategori(request, kategori_id):
    """Sunting kategori perjalanan yang sudah ada."""
    kategori = get_object_or_404(KategoriPerjalanan, pk=kategori_id)

    if request.method == "POST":
        form = KategoriPerjalananForm(request.POST, instance=kategori)
        if form.is_valid():
            form.save()
            messages.success(request, f"Kategori '{kategori.nama_kategori}' berhasil diperbarui.")
            return redirect("pakln:kelola_kategori")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = KategoriPerjalananForm(instance=kategori)

    return render(request, "pakln/edit_kategori.html", {"form": form, "kategori": kategori})


@role_required("admin_pakln")
@require_POST
def toggle_kategori(request, kategori_id):
    """Aktifkan/nonaktifkan kategori perjalanan (AJAX, dipanggil dari
    tabel Data Table Server-Side) tanpa membuka form edit."""
    kategori = get_object_or_404(KategoriPerjalanan, pk=kategori_id)
    kategori.is_active = not kategori.is_active
    kategori.save(update_fields=["is_active"])
    return JsonResponse({"ok": True, "is_active": kategori.is_active})


@role_required("admin_pakln")
@require_POST
def hapus_kategori(request, kategori_id):
    """Hapus permanen data kategori perjalanan (AJAX). Ditolak jika masih
    dipakai pada satu atau lebih pengajuan/template dokumen (riwayat/jejak
    audit serta penargetan template) — gunakan nonaktifkan untuk kasus itu."""
    kategori = get_object_or_404(KategoriPerjalanan, pk=kategori_id)
    if kategori.pengajuan_list.exists() or kategori.dokumen_template_list.exists():
        return JsonResponse({
            "ok": False,
            "error": (
                f"Kategori '{kategori.nama_kategori}' tidak dapat dihapus karena masih dipakai pada "
                f"pengajuan atau template dokumen yang sudah ada. Nonaktifkan saja agar tidak lagi ditawarkan."
            ),
        }, status=400)
    kategori.delete()
    return JsonResponse({"ok": True})


@role_required("admin_pakln")
def preview(request, kode):
    """Tahap 3: Pratinjau Pengajuan dari Admin Unor (read-only)."""
    pengajuan = get_object_or_404(
        Pengajuan.objects.filter(status__in=[Pengajuan.Status.PROSES_PAKLN, Pengajuan.Status.SELESAI]),
        kode=kode,
    )
    if request.method == "POST" and "lanjutkan" in request.POST:
        pengajuan.preview_pakln_agree = True
        pengajuan.save(update_fields=["preview_pakln_agree"])
        return redirect("pakln:upload_dokumen", kode=pengajuan.kode)

    if request.method == "POST" and "kembalikan" in request.POST:
        catatan = request.POST.get("catatan", "").strip()
        if not catatan:
            messages.error(request, "Isi catatan perbaikan untuk Admin Unor sebelum mengembalikan pengajuan.")
        elif pengajuan.status != Pengajuan.Status.PROSES_PAKLN:
            messages.error(request, "Pengajuan yang sudah selesai tidak dapat dikembalikan.")
        else:
            pengajuan.status = Pengajuan.Status.PROSES
            pengajuan.preview_unor_agree = False
            pengajuan.preview_pakln_agree = False
            pengajuan.catatan_pakln = catatan
            pengajuan.save()
            notify_reject_pakln_to_unor(pengajuan, catatan)
            messages.success(
                request,
                f"Pengajuan {pengajuan.kode} dikembalikan ke Admin Unor beserta catatan.",
            )
            return redirect("pakln:dashboard")

    return render(request, "pakln/preview.html", {"pengajuan": pengajuan})


@role_required("admin_pakln")
def upload_dokumen(request, kode):
    """Tahap 4: Unggah Dokumen Administrasi Biro PAKLN, lalu menyelesaikan
    proses (fungsi selesaikanProses pada mockup)."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode)
    if not pengajuan.preview_pakln_agree:
        return redirect("pakln:preview", kode=kode)

    jenis_choices = DokumenPakln.Jenis.choices
    dokumen_map = {d.jenis: d for d in pengajuan.dokumen_pakln.all()}
    pendukung, _ = DokumenPaklnPendukung.objects.get_or_create(pengajuan=pengajuan)

    # Dokumen Izin Luar Negeri (TTD Sekjen) wajib; dokumen pendukung
    # (Nota Dinas Kepala Bagian/Kepala Biro) opsional — tidak menjadi
    # syarat kelengkapan untuk menyelesaikan proses.
    lengkap = len(dokumen_map) >= len(jenis_choices)

    if request.method == "POST":
        if "selesaikan" in request.POST:
            if not lengkap:
                messages.error(request, "Lengkapi dokumen Izin Luar Negeri (TTD Sekjen a.n. Menteri) sebelum menyelesaikan proses.")
            elif not request.POST.get("agree"):
                messages.error(request, "Centang pernyataan kelengkapan dokumen terlebih dahulu.")
            elif pengajuan.status == Pengajuan.Status.SELESAI:
                # Sudah pernah diselesaikan sebelumnya — hindari potong cuti dua kali.
                return redirect("pakln:dashboard")
            else:
                with transaction.atomic():
                    profile = getattr(pengajuan.pegawai, "profile", None)
                    hari_terpakai = pengajuan.jumlah_hari_kalender or 0
                    if profile and hari_terpakai:
                        profile.sisa_cuti_tahun_berjalan = max(
                            profile.sisa_cuti_tahun_berjalan - hari_terpakai, 0
                        )
                        profile.save(update_fields=["sisa_cuti_tahun_berjalan"])

                    pengajuan.status = Pengajuan.Status.SELESAI
                    pengajuan.tgl_selesai = timezone.now().date()
                    pengajuan.save()
                notify_complete_pkln(pengajuan)
                messages.success(
                    request,
                    f"Pengajuan {pengajuan.kode} telah diselesaikan. "
                    f"Sisa cuti tahun berjalan pegawai berkurang {hari_terpakai} hari.",
                )
                return redirect("pakln:dashboard")
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
                return redirect("pakln:upload_dokumen", kode=kode)
        elif "pendukung_hapus" in request.POST:
            pendukung.file.delete(save=False)
            pendukung.file = ""
            pendukung.uploaded_at = None
            pendukung.save(update_fields=["file", "uploaded_at"])
            messages.success(request, "Berkas dokumen pendukung dihapus.")
            return redirect("pakln:upload_dokumen", kode=kode)
        elif "toggle_pendukung" in request.POST:
            # Proses mencentang jenis — berdiri sendiri, tidak memerlukan
            # berkas diunggah ulang.
            kategori = request.POST.get("kategori")
            if kategori not in DokumenPaklnPendukung.KATEGORI_LABELS:
                messages.error(request, "Jenis dokumen pendukung tidak valid.")
            else:
                setattr(pendukung, kategori, not getattr(pendukung, kategori))
                pendukung.save(update_fields=[kategori])
                return redirect("pakln:upload_dokumen", kode=kode)
        else:
            jenis = request.POST.get("jenis")
            existing = dokumen_map.get(jenis)
            form = DokumenPaklnForm(request.POST, request.FILES, instance=existing)
            if jenis in dict(jenis_choices) and form.is_valid():
                dok = form.save(commit=False)
                dok.pengajuan = pengajuan
                dok.jenis = jenis
                dok.save()
                messages.success(request, "Dokumen berhasil diunggah.")
                return redirect("pakln:upload_dokumen", kode=kode)
            else:
                messages.error(request, "Gagal mengunggah dokumen. Periksa kembali berkas Anda.")

    context = {
        "pengajuan": pengajuan,
        "jenis_choices": jenis_choices,
        "dokumen_map": dokumen_map,
        "pendukung": pendukung,
        "pendukung_kategori": list(DokumenPaklnPendukung.KATEGORI_LABELS.items()),
        "lengkap": lengkap,
    }
    return render(request, "pakln/upload.html", context)


@role_required("admin_pakln")
def hapus_dokumen(request, kode, jenis):
    """Hapus salah satu dokumen administrasi Biro PAKLN yang sudah diunggah."""
    pengajuan = get_object_or_404(Pengajuan, kode=kode)
    if request.method == "POST":
        dok = pengajuan.dokumen_pakln.filter(jenis=jenis).first()
        if dok:
            dok.file.delete(save=False)
            dok.delete()
            messages.success(request, "Dokumen berhasil dihapus.")
    return redirect("pakln:upload_dokumen", kode=pengajuan.kode)


@role_required("admin_pakln")
def export_database(request):
    """Tahap 5: Export Database untuk Admin Biro PAKLN. Tabel pratinjau
    di halaman ditampilkan lewat Data Table Server-Side (lihat
    `export_data`) — CSV tetap mengekspor seluruh baris yang cocok,
    bukan hanya satu halaman tabel."""
    pengajuan_list = Pengajuan.objects.filter(
        status__in=[Pengajuan.Status.PROSES_PAKLN, Pengajuan.Status.SELESAI]
    ).select_related("pegawai__profile")

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="paspor_pengajuan_pakln.csv"'
        writer = csv.writer(response)
        writer.writerow(["Kode", "Nama Pegawai", "Kategori", "Tujuan", "Tgl Masuk PAKLN", "Status"])
        for p in pengajuan_list:
            nama = getattr(getattr(p.pegawai, "profile", None), "nama", p.pegawai.get_full_name())
            writer.writerow([p.kode, nama, p.kategori, p.tujuan_negara_display, p.tgl_masuk_pakln or "", p.get_status_display()])
        return response

    return render(request, "pakln/export.html", {})


# Kolom tabel pratinjau "Export Database" (index sesuai urutan kolom pada
# pakln/export.html) -> field untuk pengurutan (ORDER BY) di endpoint
# server-side DataTables. Kolom Tujuan (M2M) sengaja tidak disertakan.
_PAKLN_EXPORT_ORDER_FIELDS = {
    "0": "pegawai__profile__nama",
    "1": "kategori__nama_kategori",
    "3": "tgl_masuk_pakln",
    "4": "status",
}


@role_required("admin_pakln")
def export_data(request):
    """Endpoint JSON server-side untuk tabel pratinjau "Export Database"
    (protokol DataTables: draw/start/length/search/order pada GET),
    mengikuti pola `users_data` (Manajemen User)."""
    qs = Pengajuan.objects.filter(
        status__in=[Pengajuan.Status.PROSES_PAKLN, Pengajuan.Status.SELESAI]
    ).select_related("pegawai__profile", "kategori")
    records_total = qs.count()

    search_value = request.GET.get("search[value]", "").strip()
    if search_value:
        qs = qs.filter(
            Q(pegawai__profile__nama__icontains=search_value)
            | Q(kategori__nama_kategori__icontains=search_value)
            | Q(tujuan_negara__nama_negara__icontains=search_value)
        ).distinct()
    records_filtered = qs.count()

    order_col = request.GET.get("order[0][column]")
    order_field = _PAKLN_EXPORT_ORDER_FIELDS.get(order_col, "-tgl_masuk_pakln")
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
        data.append([
            format_html("<strong>{}</strong>", p.pegawai.profile.nama),
            escape(p.kategori.nama_kategori) if p.kategori else "—",
            escape(p.tujuan_negara_display or "—"),
            p.tgl_masuk_pakln.strftime("%d %b %Y") if p.tgl_masuk_pakln else "—",
            status_html,
        ])

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1)),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data,
    })
