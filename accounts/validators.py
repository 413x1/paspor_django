import re

from django.core.exceptions import ValidationError

PESAN_NO_HP = "Nomor HP tidak valid. Gunakan format 08…, +62…, atau 62… (10–15 digit)."


def normalisasi_no_hp(nilai: str) -> str:
    """'0812-3456 7890' / '+62 812…' / '62812…' -> '6281234567890' (AB-15).

    Raise ValidationError bila bukan 10–15 digit setelah normalisasi. Input
    kosong dikembalikan kosong (kewajiban isian ditegakkan oleh form)."""
    teks = (nilai or "").strip()
    if not teks:
        return ""
    if re.search(r"[^\d+\s\-().]", teks):
        raise ValidationError(PESAN_NO_HP)
    bersih = re.sub(r"[^\d+]", "", teks)
    if bersih.startswith("+"):
        bersih = bersih[1:]
    if "+" in bersih:
        raise ValidationError(PESAN_NO_HP)
    if bersih.startswith("0"):
        bersih = "62" + bersih[1:]
    if not bersih.startswith("62") or not 10 <= len(bersih) <= 15:
        raise ValidationError(PESAN_NO_HP)
    return bersih
