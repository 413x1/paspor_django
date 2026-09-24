import csv
import json

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from accounts.forms import EditUserForm, TambahUserForm
from accounts.models import User
from notifications.services import notify_complete_pkln, notify_reject_pakln_to_unor
from paspor.models import KategoriPerjalanan, Negara, SumberPembiayaan

from .decorators import role_required
from .forms import DokumenPaklnForm, DokumenTemplateForm, NegaraForm, PengaturanNDForm, SumberPembiayaanForm, KategoriPerjalananForm
from .models import DokumenPakln, DokumenTemplate, NotaDinas, Pengajuan, PengaturanND
from .nota_dinas import build_nd_context, nama_ringkas_pengajuan

# Status Pengajuan yang bisa ditindaklanjuti Admin Biro PAKLN (termasuk
# digenerate ND-nya) — sudah diteruskan Admin Unor.
_ND_ELIGIBLE_STATUS = [Pengajuan.Status.PROSES_PAKLN, Pengajuan.Status.SELESAI]


@role_required("admin_pakln")
def dashboard(request):
    """Tahap 2: Dasbor — menampilkan seluruh pengajuan yang sudah dikirim
    pegawai (status != belum), termasuk yang masih diproses Admin Unor,
    supaya Admin Biro PAKLN dapat memantau progres lebih awal. Hanya
    pengajuan berstatus proses_pakln/selesai yang dapat ditindaklanjuti
    (link TL, checklist pemilihan pegawai untuk Generate ND) — lihat
    template untuk kondisi tampil masing-masing. Baris tabel dimuat lewat
    `dashboard_data`."""
    counts = (
        Pengajuan.objects.exclude(status=Pengajuan.Status.BELUM)
        .values("status").annotate(n=Count("pk"))
    )
    by_status = {row["status"]: row["n"] for row in counts}

    summary = {
        "total": sum(by_status.values()),
        "proses_unor": by_status.get(Pengajuan.Status.PROSES, 0),
        "proses_pakln": by_status.get(Pengajuan.Status.PROSES_PAKLN, 0),
        "selesai": by_status.get(Pengajuan.Status.SELESAI, 0),
    }
    return render(request, "pakln/dashboard.html", {"summary": summary})


# Kolom tabel "Tabel Rincian Pengajuan" (index sesuai urutan kolom pada
# pakln/dashboard.html) -> field untuk pengurutan (ORDER BY) di endpoint
# server-side DataTables. Kolom checklist ND, Jenis (statis), Tujuan (M2M),
# dan Action sengaja tidak disertakan — tidak diurutkan di JS (orderable:false).
_PAKLN_DASHBOARD_ORDER_FIELDS = {
    "1": "pegawai__profile__nama",
    "2": "pegawai__profile__unit_organisasi__name",
    "4": "kategori__nama_kategori",
    "6": "tgl_berangkat",
    "7": "tgl_kembali",
    "8": "tgl_masuk_pakln",
    "9": "status",
}


@role_required("admin_pakln")
def dashboard_data(request):
    """Endpoint JSON server-side untuk "Tabel Rincian Pengajuan" pada
    Dasbor Admin Biro PAKLN (protokol DataTables: draw/start/length/
    search/order pada GET), mengikuti pola `users_data` (Manajemen User)."""
    qs = (
        Pengajuan.objects.exclude(status=Pengajuan.Status.BELUM)
        .select_related("pegawai__profile__unit_organisasi", "kategori")
        .prefetch_related("tujuan_negara", "nota_dinas_list")
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

        # Checklist Generate ND: data-* dipakai JS untuk mengunci pilihan
        # ke unor/negara/maksud yang sama (divalidasi ulang di preview_nd).
        if p.status in _ND_ELIGIBLE_STATUS:
            sudah_ada_nd = bool(p.nota_dinas_list.all())
            check_html = format_html(
                '<input type="checkbox" class="nd-check" value="{}" data-unor="{}" '
                'data-negara="{}" data-maksud="{}" data-has-nd="{}" title="{}">',
                p.pk,
                p.pegawai.profile.unit_organisasi_id or "",
                "-".join(str(i) for i in sorted(n.id for n in p.tujuan_negara.all())),
                p.maksud.strip().lower(),
                "1" if sudah_ada_nd else "0",
                "Sudah pernah digenerate ND" if sudah_ada_nd else "",
            )
        else:
            check_html = ""

        data.append([
            check_html,
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
    lengkap = len(dokumen_map) >= len(jenis_choices)

    if request.method == "POST":
        if "selesaikan" in request.POST:
            if not lengkap:
                messages.error(request, "Lengkapi seluruh dokumen administrasi Biro PAKLN sebelum menyelesaikan proses.")
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


def _validasi_kesamaan_nd(selected):
    """Pastikan seluruh `selected` (list Pengajuan) berasal dari 1 unit
    organisasi, tujuan negara, dan maksud perjalanan yang sama — syarat
    generate ND untuk lebih dari satu pegawai sekaligus."""
    first = selected[0]
    unit_id = first.pegawai.profile.unit_organisasi_id
    if not unit_id:
        return "Pegawai belum memiliki unit organisasi pada profil."
    negara_ids = set(first.tujuan_negara.values_list("id", flat=True))
    if not negara_ids:
        return "Pengajuan belum memiliki tujuan negara."
    maksud = first.maksud.strip()

    for p in selected[1:]:
        if p.pegawai.profile.unit_organisasi_id != unit_id:
            return "Seluruh pegawai yang dipilih harus berasal dari unit organisasi yang sama."
        if set(p.tujuan_negara.values_list("id", flat=True)) != negara_ids:
            return "Seluruh pegawai yang dipilih harus memiliki tujuan negara yang sama."
        if p.maksud.strip() != maksud:
            return "Seluruh pegawai yang dipilih harus memiliki maksud/tujuan perjalanan yang sama."
    return None


def _get_selected_pengajuan(request):
    ids = request.POST.getlist("pengajuan_ids")
    return list(
        Pengajuan.objects.filter(pk__in=ids, status__in=_ND_ELIGIBLE_STATUS)
        .select_related("pegawai__profile__unit_organisasi", "sumber_pembiayaan")
        .prefetch_related("tujuan_negara")
    )


@role_required("admin_pakln")
def preview_nd(request):
    """Setelah pegawai dicentang pada Dasbor lalu tombol "Generate ND"
    diklik, tampilkan pratinjau ND (nilai pejabat/paraf bisa diedit)
    sebelum PDF-nya benar-benar dibangun (di browser, lihat
    `simpan_nd`)."""
    if request.method != "POST":
        return redirect("pakln:dashboard")

    selected = _get_selected_pengajuan(request)
    if not selected:
        messages.error(request, "Pilih minimal satu pegawai untuk digenerate ND.")
        return redirect("pakln:dashboard")

    error = _validasi_kesamaan_nd(selected)
    if error:
        messages.error(request, error)
        return redirect("pakln:dashboard")

    pengaturan = PengaturanND.get_solo()
    nd_data = build_nd_context(selected)
    nd_data.update({
        "jabatan_dari": pengaturan.jabatan_plt_kabag_kln,
        "nama_pejabat": pengaturan.nama_pejabat_plt_kabag_kln,
        "paraf_ketua_tim_aki": pengaturan.paraf_ketua_tim_aki,
        "nama_karo_pakln": pengaturan.nama_karo_pakln,
        "paraf_katim_aki_nd2": pengaturan.paraf_katim_aki_nd2,
        "paraf_plt_kabag_kln_nd2": pengaturan.paraf_plt_kabag_kln_nd2,
    })

    context = {
        "pengajuan_ids": [p.pk for p in selected],
        "nd_data_json": json.dumps(nd_data),
        "nama_ringkas": nd_data["nama_display"],
    }
    return render(request, "pakln/preview_nd.html", context)


@role_required("admin_pakln")
def simpan_nd(request):
    """Endpoint AJAX yang dipanggil dari `preview_nd.html` setelah PDF
    ND dibangun jsPDF di browser — validasi ulang pemilihan pegawai di
    server, lalu simpan berkasnya sebagai riwayat generate ND."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Metode tidak diizinkan."}, status=405)

    selected = _get_selected_pengajuan(request)
    if not selected:
        return JsonResponse({"ok": False, "error": "Pilih minimal satu pegawai untuk digenerate ND."}, status=400)

    error = _validasi_kesamaan_nd(selected)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    file_obj = request.FILES.get("file")
    if not file_obj:
        return JsonResponse({"ok": False, "error": "Berkas PDF hasil generate tidak diterima."}, status=400)

    nama_ringkas = nama_ringkas_pengajuan(selected)
    filename = f"ND_{slugify(nama_ringkas)}_{timezone.now():%Y%m%d%H%M%S}.pdf"

    with transaction.atomic():
        nota = NotaDinas.objects.create(
            unit_organisasi=selected[0].pegawai.profile.unit_organisasi,
            maksud=selected[0].maksud,
            nama_ringkas=nama_ringkas,
            generated_by=request.user,
        )
        nota.file.save(filename, file_obj, save=True)
        nota.pengajuan_list.set(selected)
        nota.negara_tujuan.set(selected[0].tujuan_negara.all())

    messages.success(request, f"Dokumen ND untuk {nama_ringkas} berhasil digenerate.")
    return JsonResponse({"ok": True, "redirect_url": reverse("pakln:riwayat_nd")})


@role_required("admin_pakln")
def riwayat_nd(request):
    """Riwayat Generate ND — seluruh dokumen ND yang pernah digenerate
    Admin Biro PAKLN."""
    riwayat = (
        NotaDinas.objects.select_related("unit_organisasi", "generated_by")
        .prefetch_related("negara_tujuan", "pengajuan_list__pegawai__profile")
    )
    return render(request, "pakln/riwayat_nd.html", {"riwayat": riwayat})


@role_required("admin_pakln")
def pengaturan_nd(request):
    """Pengaturan Nota Dinas — nilai pejabat penandatangan/paraf yang
    dipakai saat mengisi template ND (lihat `PengaturanND`)."""
    pengaturan = PengaturanND.get_solo()
    if request.method == "POST":
        form = PengaturanNDForm(request.POST, instance=pengaturan)
        if form.is_valid():
            form.save()
            messages.success(request, "Pengaturan Nota Dinas berhasil disimpan.")
            return redirect("pakln:pengaturan_nd")
        messages.error(request, "Periksa kembali isian formulir.")
    else:
        form = PengaturanNDForm(instance=pengaturan)
    return render(request, "pakln/pengaturan_nd.html", {"form": form})


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
