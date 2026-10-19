from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Ambil DokumenPegawai/Unor/Pakln dari dict {jenis: instance} pada
    template, mis. {{ dokumen_map|get_item:value }}."""
    if not mapping:
        return None
    return mapping.get(key)


@register.filter
def get_attr(obj, name):
    """Ambil atribut objek berdasarkan nama dinamis, mis.
    {{ pendukung|get_attr:field_name }} — dipakai saat nama field berasal
    dari variabel (loop), bukan literal pada template."""
    if obj is None:
        return None
    return getattr(obj, str(name), None)


@register.filter
def initials(value):
    """Inisial nama untuk avatar chip pada topbar, mis.
    'Budi Santoso' -> 'BS', 'Sari, S.T.' -> 'SS'."""
    if not value:
        return ""
    parts = str(value).replace(",", " ").split()
    letters = [p[0] for p in parts if p and p[0].isalnum()][:2]
    return "".join(letters).upper()


@register.filter
def file_url(document):
    """Mengembalikan URL file dari sebuah objek dokumen, atau None jika
    dokumen belum ada."""
    if not document or not getattr(document, "file", None):
        return None
    try:
        return document.file.url
    except ValueError:
        return None


@register.filter
def rupiah(value):
    """100000000 -> 'Rp 100.000.000'; kosong -> '—'."""
    if value is None or value == "":
        return "—"
    return "Rp " + f"{int(value):,}".replace(",", ".")


@register.filter
def format_hp(value):
    """Nomor HP ternormalisasi -> tampilan, mis. '6281234567890' ->
    '+62 812-3456-7890'. Nilai kosong -> ''."""
    nomor = str(value or "").strip()
    if not nomor:
        return ""
    if not nomor.startswith("62"):
        return nomor
    sisa = nomor[2:]
    bagian = [sisa[:3], sisa[3:7], sisa[7:]]
    return "+62 " + "-".join(b for b in bagian if b)


@register.filter
def wa_link(value):
    """Tautan WhatsApp (AB-22): '6281234567890' -> 'https://wa.me/6281234567890'."""
    nomor = "".join(c for c in str(value or "") if c.isdigit())
    return f"https://wa.me/{nomor}" if nomor else ""


@register.filter
def label_peran(value):
    """Kode role -> label, mis. 'admin_unor' -> 'Admin Unor'."""
    from accounts.models import User

    try:
        return User.Role(value).label
    except ValueError:
        return value or ""
