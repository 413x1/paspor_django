"""
Integrasi e-HRM — sumber data kepegawaian (nama, NIP, jabatan, pangkat, unit,
email, nomor HP). Lihat wiki/instructions/IMPROVEMENT_PLAN_19102026.MD §9.2.

PASPOR hanya membaca. Selama `settings.EHRM_API_URL` kosong, dipakai data stub
lokal (pegawai seed) di balik antarmuka yang sama — pola `pintar.py`.

Kontrak API yang diasumsikan (sesuaikan saat spesifikasi e-HRM tersedia, Q2):
    GET {EHRM_API_URL}/pegawai/{nip}
    -> {"nip","nama","jabatan","pangkat_golongan","unit_kerja","kode_unit_organisasi","email","no_hp"}
    404 -> NIP tidak ditemukan.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataPegawai:
    nip: str
    nama: str
    jabatan: str = ""
    pangkat_golongan: str = ""
    unit_kerja: str = ""
    kode_unit_organisasi: str = ""
    email: str = ""
    no_hp: str = ""


class EhrmTidakTersedia(Exception):
    """Gangguan jaringan/server e-HRM (berbeda dengan NIP tidak ditemukan)."""


def memakai_stub():
    return not getattr(settings, "EHRM_API_URL", "")


def _stub():
    """Data stub: pegawai demo + pegawai seed per unit organisasi
    (seed_demo_data & seed_pegawai_org_units), ditambah satu pegawai yang
    belum ada di PASPOR untuk mencoba provisioning SSO pertama."""
    from accounts.management.commands.seed_demo_data import ORG_UNITS
    from accounts.management.commands.seed_pegawai_org_units import NAMA_PEGAWAI, PANGKAT_GOLONGAN

    data = {
        "198703142011011007": DataPegawai(
            nip="198703142011011007", nama="Andra Wibisono, S.T.",
            jabatan="Kepala Seksi Perencanaan Teknis", pangkat_golongan="Penata Tk. I / III-d",
            unit_kerja="Direktorat Bina Teknik Sumber Daya Air", kode_unit_organisasi="03",
            email="andra.wibisono@pu.go.id", no_hp="6281100000001",
        ),
        "199001012015031001": DataPegawai(
            nip="199001012015031001", nama="Citra Lestari, S.T., M.T.",
            jabatan="Analis Kebijakan Ahli Muda", pangkat_golongan="Penata / III-c",
            unit_kerja="Direktorat Jenderal Bina Marga", kode_unit_organisasi="06",
            email="citra.lestari@pu.go.id", no_hp="6281100000002",
        ),
    }
    nama_iter = iter(NAMA_PEGAWAI)
    for code, alias, name in ORG_UNITS:
        for n in range(1, 4):
            nama = next(nama_iter, f"Pegawai {alias} {n}")
            nip = f"90{code}{n}" + "0" * 13
            data[nip] = DataPegawai(
                nip=nip, nama=nama, jabatan="Staf Pelaksana", pangkat_golongan=PANGKAT_GOLONGAN[n - 1],
                unit_kerja=name, kode_unit_organisasi=code,
                email=f"pegawai.{alias.lower()}{n}@pu.go.id", no_hp=f"628110{code}{n:05d}",
            )
    return data


def daftar_stub():
    """[(nip, nama)] untuk halaman stub SSO (DEBUG)."""
    return [(d.nip, d.nama) for d in _stub().values()]


def _dari_json(item):
    return DataPegawai(
        nip=str(item.get("nip", "")).strip(),
        nama=str(item.get("nama", "")).strip(),
        jabatan=str(item.get("jabatan", "") or "").strip(),
        pangkat_golongan=str(item.get("pangkat_golongan", "") or "").strip(),
        unit_kerja=str(item.get("unit_kerja", "") or "").strip(),
        kode_unit_organisasi=str(item.get("kode_unit_organisasi", "") or "").strip(),
        email=str(item.get("email", "") or "").strip(),
        no_hp=str(item.get("no_hp", "") or "").strip(),
    )


def ambil_pegawai(nip: str) -> DataPegawai | None:
    """Data pegawai `nip` dari e-HRM. None = NIP tidak ditemukan.
    EhrmTidakTersedia = gangguan jaringan/server (pemanggil memutuskan)."""
    nip = (nip or "").strip()
    if not nip:
        return None
    if memakai_stub():
        return _stub().get(nip)

    url = f"{settings.EHRM_API_URL.rstrip('/')}/pegawai/{urllib.parse.quote(nip)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    if getattr(settings, "EHRM_API_TOKEN", ""):
        request.add_header("Authorization", f"Bearer {settings.EHRM_API_TOKEN}")
    try:
        with urllib.request.urlopen(request, timeout=settings.EHRM_TIMEOUT) as resp:
            item = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        logger.warning("e-HRM merespons HTTP %s untuk NIP %s", exc.code, nip)
        raise EhrmTidakTersedia(f"e-HRM merespons HTTP {exc.code}") from exc
    except Exception as exc:  # noqa: BLE001 — timeout/jaringan/JSON rusak
        logger.warning("Gagal menghubungi e-HRM untuk NIP %s: %s", nip, exc)
        raise EhrmTidakTersedia("e-HRM tidak dapat dihubungi") from exc
    if not isinstance(item, dict) or not item.get("nip"):
        return None
    return _dari_json(item)
