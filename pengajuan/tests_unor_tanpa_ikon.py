"""Halaman Admin Unor setelah Pratinjau: tanpa ikon dekoratif dan tanpa tanda panah pada tombol (perbaikan UI).

Ikon 📄/⚙️ pada petunjuk format dokumen, tanda panah pada "Teruskan ke ..." dan "Kirim ke Biro PAKLN", serta panah pada
"Kembali ke Pratinjau" dibuang untuk Admin Unor. Templat dokumen bersama (`_dokumen_tahap.html`) juga dipakai Pegawai,
BPSDM, Biro PAKLN, dan BKO, jadi ikon hanya dibuang bila halamannya meminta (`tanpa_ikon`)."""

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Pengajuan
from .tests_pdln import _Basis
from .tests_surat_tugas_unor import _STORAGES_MEMORI, SS, _DasarUnor

IKON_DOKUMEN = "\U0001F4C4"
IKON_GIGI = "⚙"


def _baris(aksi):
    return {
        "jenis": "surat_tugas", "label": "Surat Tugas", "wajib": True, "keterangan": "", "aksi": aksi,
        "dok": None, "tanggal_surat": False,
    }


def _render_partial(aksi, **konteks):
    return render_to_string("partials/_dokumen_tahap.html", {
        "syarat_list": [_baris(aksi)], "pengajuan": SimpleNamespace(kode="PDLN00-1-000000-001"),
        "hapus_url": "unor:hapus_dokumen", **konteks,
    })


class PartialDokumenTests(TestCase):
    def test_ikon_format_dan_generate_dibuang_hanya_bila_diminta(self):
        for aksi, ikon, kalimat in (
            ("format", IKON_DOKUMEN, "Format tersedia pada"),
            ("generate", IKON_GIGI, "Generate otomatis menyusul"),
        ):
            with self.subTest(aksi=aksi):
                polos = _render_partial(aksi, tanpa_ikon=True)
                self.assertIn(kalimat, polos)
                self.assertNotIn(ikon, polos)
                self.assertIn(f'<p class="cell-muted">{kalimat}', polos)       # kalimat langsung, tanpa spasi pendahulu
                bawaan = _render_partial(aksi)                                  # peran lain tidak berubah
                self.assertIn(ikon, bawaan)


class HalamanUnorTanpaIkonTests(_Basis, TestCase):
    def halaman_upload(self):
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.kirim(p)
        self.post(self.admin_unor, "unor:preview", {"lanjutkan": "1"}, kode=p.kode)
        return self.get(self.admin_unor, "unor:upload_dokumen", kode=p.kode), p

    def test_upload_unor_tanpa_ikon_dokumen_dan_tanpa_panah(self):
        resp, p = self.halaman_upload()
        html = resp.content.decode()
        self.assertContains(resp, "Format tersedia pada")                       # petunjuk tetap ada
        self.assertNotIn(IKON_DOKUMEN + " Format tersedia", html)
        self.assertNotIn(IKON_DOKUMEN + " ", html.split('class="section-title">')[1])   # kotak dokumen utama: tanpa ikon
        self.assertContains(resp, "Teruskan ke Admin BPSDM")
        self.assertNotIn("Teruskan ke Admin BPSDM →", html)
        self.assertContains(resp, ">Kembali ke Pratinjau</a>")
        self.assertNotIn("← Kembali ke Pratinjau", html)
        self.assertContains(resp, ">Kembali ke Dasbor</a>")

    def test_pratinjau_unor_tombol_lanjut_tanpa_panah_di_kedua_kondisi(self):
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.kirim(p)
        sebelum = self.get(self.admin_unor, "unor:preview", kode=p.kode).content.decode()          # belum menyetujui: form + checkbox
        self.assertIn(">Lanjutkan ke Administrasi Unor</button>", sebelum)
        self.assertNotIn("Lanjutkan ke Administrasi Unor →", sebelum)
        self.post(self.admin_unor, "unor:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        sesudah = self.get(self.admin_unor, "unor:preview", kode=p.kode).content.decode()          # sudah menyetujui: tautan
        self.assertRegex(sesudah, r"Lanjut ke Administrasi Unor\s*</a>")
        self.assertNotIn("Lanjut ke Administrasi Unor →", sesudah)
        self.assertIn(">Kembali ke Dasbor</a>", sesudah)                                            # tombol kembali juga tanpa panah
        self.assertNotIn("← Kembali ke Dasbor", sesudah)
        self.assertNotIn("→", sesudah.split("Direktori Unggahan Pegawai")[1].split("Timeline Proses")[0])   # kotak aksi: tanpa panah

    def test_pratinjau_peran_lain_tidak_berubah(self):
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.kirim(p)
        self.unor_teruskan(p)
        html = self.get(self.admin_bpsdm, "bpsdm:preview", kode=p.kode).content.decode()
        self.assertIn("Lanjutkan ke Administrasi BPSDM →", html)                                   # BPSDM: bukan cakupan perubahan ini

    def test_upload_halaman_peran_lain_tidak_berubah(self):
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.kirim(p)
        self.unor_teruskan(p)
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1"}, kode=p.kode)
        html = self.get(self.admin_bpsdm, "bpsdm:upload_dokumen", kode=p.kode).content.decode()
        self.assertIn("← Kembali ke Pratinjau", html)                           # BPSDM: bukan cakupan perubahan ini
        self.assertIn("Teruskan ke Admin Biro PAKLN →", html)


@override_settings(STORAGES=_STORAGES_MEMORI)
class SuratTugasUnorTanpaIkonTests(_DasarUnor, TestCase):
    def test_halaman_surat_tugas_tanpa_ikon_dan_tanpa_panah_pada_tombol_kirim(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        resp = self.halaman(p)
        html = resp.content.decode()
        self.assertContains(resp, "Format tersedia pada")
        self.assertNotIn(IKON_DOKUMEN + " Format tersedia", html)
        self.assertContains(resp, "Kirim ke Biro PAKLN")
        self.assertNotIn("Kirim ke Biro PAKLN →", html)
        self.assertNotIn("Kirim Ulang ke Biro PAKLN →", html)

    def test_tombol_kirim_ulang_tanpa_panah(self):
        p = self.pengajuan(jalur=SS.DIKEMBALIKAN)
        html = self.halaman(p).content.decode()
        self.assertIn("Kirim Ulang ke Biro PAKLN", html)
        self.assertNotIn("Kirim Ulang ke Biro PAKLN →", html)
