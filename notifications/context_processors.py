from .models import Notification
from .utils import group_by_day

TOAST_BATCH = 5
DROPDOWN_LIMIT = 8


def notifications(request):
    """Sediakan data notifikasi untuk navbar (bell + Notification Center)
    dan antrean toast pop-up di setiap render halaman.

    Tidak ada polling: notifikasi baru hanya tampak saat halaman dimuat
    ulang/berpindah. Toast hanya ditampilkan sekali per notifikasi — begitu
    ikut dirender di sini, langsung ditandai `is_toasted=True` supaya tidak
    muncul berulang di reload berikutnya.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    toast_queue = list(
        Notification.objects.filter(recipient=user, is_toasted=False).order_by("created_at")[:TOAST_BATCH]
    )
    if toast_queue:
        Notification.objects.filter(pk__in=[n.pk for n in toast_queue]).update(is_toasted=True)

    dropdown_qs = Notification.objects.filter(recipient=user, is_dismissed=False)[:DROPDOWN_LIMIT]

    return {
        "notif_toast_queue": toast_queue,
        "notif_unread_count": Notification.objects.filter(recipient=user, is_read=False).count(),
        "notif_dropdown_groups": group_by_day(dropdown_qs),
    }
