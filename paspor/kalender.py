"""Perhitungan Jumlah Hari Kalender & Jumlah Hari Kerja perjalanan.

Satu-satunya tempat rumus hari — formulir pegawai, endpoint JSON, generate
ND, dan management command semuanya memanggil modul ini supaya angkanya
selalu sama di mana pun ditampilkan.

Aturan:
- Rentang inklusif: berangkat & kembali sama-sama dihitung.
- Sabtu & Minggu selalu bukan hari kerja (konstanta, bukan data).
- Tanggal `HariLibur` aktif yang jatuh Senin–Jumat juga bukan hari kerja;
  yang jatuh di akhir pekan tidak dikurangkan dua kali.
"""

from datetime import timedelta

from .models import HariLibur

AKHIR_PEKAN = (5, 6)  # date.weekday(): Sabtu, Minggu


def hitung_hari_kalender(berangkat, kembali):
    if not berangkat or not kembali or kembali < berangkat:
        return None
    return (kembali - berangkat).days + 1


def _tanggal_libur(berangkat, kembali):
    return dict(
        HariLibur.objects
        .filter(is_active=True, tanggal__range=(berangkat, kembali))
        .values_list("tanggal", "keterangan")
    )


def _iter_tanggal(berangkat, jumlah):
    for i in range(jumlah):
        yield berangkat + timedelta(days=i)


def hitung_hari_kerja(berangkat, kembali):
    kalender = hitung_hari_kalender(berangkat, kembali)
    if kalender is None:
        return None
    libur = _tanggal_libur(berangkat, kembali)
    return sum(
        1 for d in _iter_tanggal(berangkat, kalender)
        if d.weekday() not in AKHIR_PEKAN and d not in libur
    )


def tahun_belum_diatur(berangkat, kembali):
    """Tahun-tahun dalam rentang yang belum punya satu pun data
    `HariLibur` — hasil hari kerjanya baru mengecualikan Sabtu & Minggu."""
    if not berangkat or not kembali or kembali < berangkat:
        return []
    return [
        tahun for tahun in range(berangkat.year, kembali.year + 1)
        if not HariLibur.objects.filter(tanggal__year=tahun).exists()
    ]


def rincian_hari(berangkat, kembali):
    """Rincian lengkap untuk endpoint JSON / helptext formulir, atau None
    jika rentang tanggal tidak valid."""
    kalender = hitung_hari_kalender(berangkat, kembali)
    if kalender is None:
        return None
    libur = _tanggal_libur(berangkat, kembali)
    akhir_pekan = 0
    libur_hari_kerja = []
    for d in _iter_tanggal(berangkat, kalender):
        if d.weekday() in AKHIR_PEKAN:
            akhir_pekan += 1
        elif d in libur:
            libur_hari_kerja.append({"tanggal": d.isoformat(), "keterangan": libur[d]})
    return {
        "hari_kalender": kalender,
        "hari_kerja": kalender - akhir_pekan - len(libur_hari_kerja),
        "akhir_pekan": akhir_pekan,
        "libur": libur_hari_kerja,
        "tahun_belum_diatur": tahun_belum_diatur(berangkat, kembali),
    }
