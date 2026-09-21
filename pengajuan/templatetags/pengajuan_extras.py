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
