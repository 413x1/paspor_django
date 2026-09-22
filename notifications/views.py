from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notification
from .utils import group_by_day

LIST_PAGE_SIZE = 15


@login_required
def go(request, pk):
    """Buka satu notifikasi dari Notification Center / Toast: tandai
    dibaca lalu arahkan ke deep link tujuannya."""
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=["is_read"])
    return redirect(notif.redirect_url or "home")


@login_required
def mark_all_read(request):
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(reverse("home"))


@login_required
@require_POST
def dismiss(request, pk):
    """Tutup ('x') satu notifikasi dari panel cepat Notification Center
    (AJAX). Baris tetap tersimpan untuk jejak audit — hanya disembunyikan
    dari panel & tidak lagi dihitung sebagai belum dibaca."""
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_dismissed = True
    notif.is_read = True
    notif.save(update_fields=["is_dismissed", "is_read"])
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({"ok": True, "unread_count": unread_count})


@login_required
@require_POST
def clear_all(request):
    """'Hapus Semua' pada panel cepat Notification Center (AJAX):
    menutup seluruh notifikasi yang sedang tampil di panel."""
    Notification.objects.filter(recipient=request.user, is_dismissed=False).update(
        is_dismissed=True, is_read=True
    )
    return JsonResponse({"ok": True, "unread_count": 0})


@login_required
def list_view(request):
    """'Lihat Semua' — riwayat lengkap notifikasi milik user (jejak audit),
    dikelompokkan per tanggal, dengan paginasi."""
    qs = Notification.objects.filter(recipient=request.user)
    paginator = Paginator(qs, LIST_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "notifications/list.html",
        {
            "page_obj": page_obj,
            "groups": group_by_day(page_obj.object_list),
        },
    )
