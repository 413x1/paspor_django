from django.utils import timezone

_MONTHS_ID = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


def _format_tanggal(d):
    return f"{d.day} {_MONTHS_ID[d.month - 1]} {d.year}"


def group_by_day(notifications):
    """Kelompokkan iterable Notification (urut -created_at) menjadi list
    (label, [notifikasi]) dengan label 'Hari Ini' / 'Kemarin' / tanggal,
    meniru pengelompokan pada Notification Center."""
    today = timezone.localdate()
    yesterday = today - timezone.timedelta(days=1)

    groups = []
    current_label = None
    bucket = []
    for n in notifications:
        created_date = timezone.localtime(n.created_at).date()
        if created_date == today:
            label = "Hari Ini"
        elif created_date == yesterday:
            label = "Kemarin"
        else:
            label = _format_tanggal(created_date)

        if label != current_label:
            if bucket:
                groups.append((current_label, bucket))
            bucket = []
            current_label = label
        bucket.append(n)

    if bucket:
        groups.append((current_label, bucket))
    return groups
