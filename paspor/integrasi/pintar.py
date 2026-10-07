"""
Integrasi Aplikasi PINTAR — sumber pencalonan beasiswa yang berstatus
Selesai (mendapat rekomendasi Admin BPSDM & Admin Biro PAKLN), dipakai
droplist "Nama Beasiswa" pada formulir PDLN Tipe 2. Lihat
wiki/instructions/BISNIS_PROSES_PDLN.MD §12.

PASPOR hanya membaca. Selama `settings.PINTAR_API_URL` kosong, dipakai data
stub lokal (contoh dari mockup Tahap 2) di balik antarmuka yang sama.

Kontrak API yang diasumsikan (sesuaikan saat spesifikasi PINTAR tersedia):
    GET {PINTAR_API_URL}/pencalonan?nip=<nip>&jenis=<pendidikan|pelatihan>&status=selesai
    -> [{"id": "...", "nama_beasiswa": "...", "institusi": "...", "tgl_rekomendasi": "YYYY-MM-DD"}, ...]
"""

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

JENIS_PENDIDIKAN = "pendidikan"
JENIS_PELATIHAN = "pelatihan"


@dataclass(frozen=True)
class Pencalonan:
    id: str
    nama_beasiswa: str
    institusi: str = ""
    tgl_rekomendasi: str = ""

    @property
    def label(self):
        bagian = [self.nama_beasiswa]
        if self.institusi:
            bagian.append(self.institusi)
        teks = " — ".join(bagian)
        return f"{teks} (Rekomendasi {self.tgl_rekomendasi})" if self.tgl_rekomendasi else teks


_STUB = {
    JENIS_PENDIDIKAN: [
        Pencalonan("STUB-P-001", "Beasiswa Master Teknik Sipil", "Delft University of Technology", "2026-03-15"),
        Pencalonan("STUB-P-002", "Beasiswa Doctoral Manajemen Sumber Daya Air", "Kyoto University", "2026-04-02"),
    ],
    JENIS_PELATIHAN: [
        Pencalonan("STUB-L-001", "Short Course Manajemen Proyek Infrastruktur", "JICA", "2026-02-28"),
        Pencalonan("STUB-L-002", "Workshop Smart Water Management", "KOICA", "2026-03-10"),
    ],
}


def memakai_stub():
    return not getattr(settings, "PINTAR_API_URL", "")


def daftar_pencalonan_selesai(nip, jenis):
    """Daftar `Pencalonan` berstatus Selesai atas nama pegawai `nip` untuk
    `jenis` ("pendidikan"/"pelatihan"). Mengembalikan list kosong bila API
    tidak dapat dihubungi (dicatat di log)."""
    if memakai_stub():
        return list(_STUB.get(jenis, []))

    query = urllib.parse.urlencode({"nip": nip, "jenis": jenis, "status": "selesai"})
    url = f"{settings.PINTAR_API_URL.rstrip('/')}/pencalonan?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    if getattr(settings, "PINTAR_API_TOKEN", ""):
        request.add_header("Authorization", f"Bearer {settings.PINTAR_API_TOKEN}")
    try:
        with urllib.request.urlopen(request, timeout=settings.PINTAR_API_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — layanan eksternal, jangan gagalkan halaman
        logger.exception("Gagal mengambil pencalonan dari Aplikasi PINTAR")
        return []
    return [
        Pencalonan(
            id=str(item.get("id", "")),
            nama_beasiswa=item.get("nama_beasiswa", ""),
            institusi=item.get("institusi", ""),
            tgl_rekomendasi=item.get("tgl_rekomendasi", ""),
        )
        for item in data if item.get("id")
    ]
