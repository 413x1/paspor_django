import csv

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from accounts.forms import EditUserForm, TambahUserForm
from accounts.models import User

from .decorators import role_required
from .forms import DokumenPaklnForm, DokumenTemplateForm
from .models import DokumenPakln, DokumenTemplate, Pengajuan


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
    return render(request, "pakln/dashboard.html", {"pengajuan_list": pengajuan_list, "summary": summary})


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

    templates = DokumenTemplate.objects.prefetch_related("unit_organisasi").all()
    return render(request, "pakln/templates.html", {"form": form, "templates": templates})


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
def toggle_template(request, template_id):
    """Tampilkan/sembunyikan template dengan satu klik dari Daftar
    Template, tanpa membuka form edit."""
    template = get_object_or_404(DokumenTemplate, pk=template_id)
    if request.method == "POST":
        template.aktif = not template.aktif
        template.save(update_fields=["aktif"])
        messages.success(
            request,
            f"Template '{template.nama}' kini {'ditampilkan' if template.aktif else 'disembunyikan'}.",
        )
    return redirect("pakln:kelola_template")


@role_required("admin_pakln")
def hapus_template(request, template_id):
    """Hapus template beserta berkasnya."""
    template = get_object_or_404(DokumenTemplate, pk=template_id)
    if request.method == "POST":
        nama = template.nama
        template.file.delete(save=False)
        template.delete()
        messages.success(request, f"Template '{nama}' berhasil dihapus.")
    return redirect("pakln:kelola_template")


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


@role_required("admin_pakln")
def export_database(request):
    """Tahap 5: Export Database untuk Admin Biro PAKLN."""
    pengajuan_list = (
        Pengajuan.objects.filter(status__in=[Pengajuan.Status.PROSES_PAKLN, Pengajuan.Status.SELESAI])
        .select_related("pegawai__profile")
    )

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="paspor_pengajuan_pakln.csv"'
        writer = csv.writer(response)
        writer.writerow(["Kode", "Nama Pegawai", "Kategori", "Tujuan", "Tgl Masuk PAKLN", "Status"])
        for p in pengajuan_list:
            nama = getattr(getattr(p.pegawai, "profile", None), "nama", p.pegawai.get_full_name())
            writer.writerow([p.kode, nama, p.kategori, p.tujuan_negara, p.tgl_masuk_pakln or "", p.get_status_display()])
        return response

    return render(request, "pakln/export.html", {"pengajuan_list": pengajuan_list})
