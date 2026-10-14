"""Kolom "Keterangan Sumber Pembiayaan" (textarea, WAJIB) pada form ajuan perjalanan PDLN."""

import csv
import io
import re
from datetime import timedelta

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from . import report
from .models import DetailPdln, Pengajuan
from .tests_pdln import _Basis


class KeteranganSumberPembiayaanTests(_Basis, TestCase):
    URL = "pegawai:formulir_pengajuan"

    def _data(self, tipe="T1", **ekstra):
        """Isian form PDLN yang valid (mengikuti `_Basis.isi_formulir`) + isian tambahan."""
        kegiatan = self.buat_kegiatan(tipe, self.singapura)
        return {
            "kategori": self.kategori(tipe).pk, "kegiatan": kegiatan.pk, "tujuan_negara": [self.singapura.pk],
            "sumber_pembiayaan": self.sumber(tipe).pk,
            "tgl_berangkat": self.berangkat.isoformat(), "tgl_kembali": (self.berangkat + timedelta(days=6)).isoformat(),
            "keterangan_sumber_pembiayaan": "Biaya instansi pengundang",
            "pernyataan_benar": "on", **ekstra,
        }

    def _kirim(self, tipe="T1", **ekstra):
        self.login(self.pegawai)
        return self.client.post(reverse(self.URL) + f"?jenis=pdln&tipe={tipe}", self._data(tipe, **ekstra))

    def _pengajuan(self):
        return Pengajuan.objects.filter(pegawai=self.pegawai).latest("created_at")

    # --- form ---------------------------------------------------------------
    def test_kolom_tampil_di_form_pdln_setelah_sumber_pembiayaan(self):
        self.login(self.pegawai)
        html = self.client.get(reverse(self.URL) + "?jenis=pdln&tipe=T1").content.decode()
        self.assertIn("Keterangan Sumber Pembiayaan", html)
        self.assertIsNone(re.search(r'<input[^>]*name="keterangan_sumber_pembiayaan"', html))   # bukan input lagi
        tag = re.search(r'<textarea[^>]*name="keterangan_sumber_pembiayaan"[^>]*>', html).group(0)
        self.assertIn('class="textarea"', tag)     # gaya Bulma
        self.assertIn('rows="3"', tag)
        self.assertIn('maxlength="2000"', tag)
        self.assertIn("required", tag)             # wajib diisi
        # urutan: Sumber Pembiayaan (dropdown) -> Keterangan -> pernyataan kebenaran
        self.assertLess(html.index('name="sumber_pembiayaan"'), html.index('name="keterangan_sumber_pembiayaan"'))
        self.assertLess(html.index('name="keterangan_sumber_pembiayaan"'), html.index('name="pernyataan_benar"'))
        self.assertIn('<div class="control"><textarea', html.split("Keterangan Sumber Pembiayaan")[1])

    def test_wajib_diisi_kosong_dan_hanya_spasi_ditolak(self):
        for kosong in ("", "    "):
            r = self._kirim(keterangan_sumber_pembiayaan=kosong)
            self.assertEqual(r.status_code, 200, repr(kosong))
            self.assertIn("keterangan_sumber_pembiayaan", r.context["form"].errors)
            self.assertContains(r, 'class="help is-danger"')          # pesan error tampil di bawah kolom
        self.assertFalse(Pengajuan.objects.filter(pegawai=self.pegawai).exists())

    def test_tanpa_kolom_sama_sekali_ditolak(self):
        data = self._data()
        data.pop("keterangan_sumber_pembiayaan")
        self.login(self.pegawai)
        r = self.client.post(reverse(self.URL) + "?jenis=pdln&tipe=T1", data)
        self.assertEqual(r.status_code, 200)
        self.assertIn("keterangan_sumber_pembiayaan", r.context["form"].errors)

    def test_nilai_tersimpan_dirapikan_dan_terisi_lagi_saat_form_dibuka_ulang(self):
        r = self._kirim(keterangan_sumber_pembiayaan="  Beasiswa LPDP  ")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(DetailPdln.objects.get(pengajuan=self._pengajuan()).keterangan_sumber_pembiayaan, "Beasiswa LPDP")
        html = self.client.get(reverse(self.URL)).content.decode()   # draft yang sama dibuka ulang
        self.assertRegex(html, r'<textarea[^>]*name="keterangan_sumber_pembiayaan"[^>]*>\s*Beasiswa LPDP</textarea>')

    def test_teks_panjang_dan_multi_baris_diterima_sampai_batas(self):
        panjang = "Baris pertama\nBaris kedua " + "x" * 600          # jauh melewati batas 255 lama
        self.assertEqual(self._kirim(keterangan_sumber_pembiayaan=panjang).status_code, 302)
        tersimpan = DetailPdln.objects.get(pengajuan=self._pengajuan()).keterangan_sumber_pembiayaan
        self.assertEqual(tersimpan, panjang)
        self.assertIn("\n", tersimpan)                                  # pemisah baris dipertahankan

    def test_lebih_dari_2000_karakter_ditolak(self):
        r = self._kirim(keterangan_sumber_pembiayaan="x" * 2001)
        self.assertEqual(r.status_code, 200)
        self.assertIn("keterangan_sumber_pembiayaan", r.context["form"].errors)
        self.assertFalse(Pengajuan.objects.filter(pegawai=self.pegawai).exists())

    def test_form_non_dinas_tidak_berubah(self):
        self.login(self.pegawai)
        html = self.client.get(reverse(self.URL) + "?jenis=nondinas").content.decode()
        self.assertNotIn("keterangan_sumber_pembiayaan", html)

    # --- tampilan baca-saja -----------------------------------------------------
    def test_ringkasan_admin_menampilkan_hanya_bila_terisi(self):
        self._kirim()
        p = self._pengajuan()
        html = render_to_string("partials/_ringkasan_pengajuan.html", {"pengajuan": p})
        self.assertIn("Keterangan Sumber Pembiayaan", html)
        self.assertIn("Biaya instansi pengundang", html)
        self.assertRegex(html, r'<textarea class="textarea" rows="2" readonly>Biaya instansi pengundang</textarea>')
        DetailPdln.objects.filter(pengajuan=p).update(keterangan_sumber_pembiayaan="")   # data lama sebelum kolom wajib
        p = Pengajuan.objects.get(pk=p.pk)
        self.assertNotIn("Keterangan Sumber Pembiayaan", render_to_string("partials/_ringkasan_pengajuan.html", {"pengajuan": p}))

    def test_monitor_progres_pegawai_menampilkan_sumber_biaya(self):
        self._kirim(keterangan_sumber_pembiayaan="Beasiswa LPDP")
        p = self._pengajuan()
        self.kirim(p)
        self.login(self.pegawai)
        html = self.client.get(reverse("pegawai:monitor_progres", args=[p.kode])).content.decode()
        self.assertIn("Sumber biaya: Beasiswa LPDP", html)
        DetailPdln.objects.filter(pengajuan=p).update(keterangan_sumber_pembiayaan="")
        html = self.client.get(reverse("pegawai:monitor_progres", args=[p.kode])).content.decode()
        self.assertNotIn("Sumber biaya:", html)

    def test_monitor_memotong_keterangan_yang_sangat_panjang(self):
        self._kirim(keterangan_sumber_pembiayaan="y" * 500)
        p = self._pengajuan()
        self.kirim(p)
        self.login(self.pegawai)
        html = self.client.get(reverse("pegawai:monitor_progres", args=[p.kode])).content.decode()
        self.assertIn("Sumber biaya: " + "y" * 119 + "…", html)
        self.assertNotIn("y" * 200, html)

    # --- export -----------------------------------------------------------------
    def test_export_memuat_kolom_baru_di_ujung_kanan_tanpa_menggeser_kolom_lama(self):
        self.assertEqual(report.KOLOM_EXPORT[-1], "Keterangan Sumber Pembiayaan")
        self.assertEqual(report.KOLOM_EXPORT[0], "Kode")                       # kolom lama tidak bergeser
        self.assertEqual(report.KOLOM_EXPORT.index("Alasan Pembatalan"), len(report.KOLOM_EXPORT) - 2)

        self._kirim(keterangan_sumber_pembiayaan="Beasiswa LPDP")
        p = self._pengajuan()
        self.kirim(p)
        csv_teks = self.get(self.admin_pakln, "pakln:export", query="?format=csv&jenis=pdln").content.decode("utf-8-sig")
        baris = list(csv.reader(io.StringIO(csv_teks)))
        kolom = baris[0]
        self.assertEqual(kolom[-1], "Keterangan Sumber Pembiayaan")
        data = next(b for b in baris[1:] if b[0] == p.kode)
        self.assertEqual(len(data), len(kolom))
        self.assertEqual(data[-1], "Beasiswa LPDP")

    def test_export_csv_memuat_keterangan_multi_baris_dalam_satu_sel(self):
        self._kirim(keterangan_sumber_pembiayaan="Baris 1\nBaris 2")
        p = self._pengajuan()
        self.kirim(p)
        csv_teks = self.get(self.admin_pakln, "pakln:export", query="?format=csv&jenis=pdln").content.decode("utf-8-sig")
        baris = list(csv.reader(io.StringIO(csv_teks)))
        data = next(b for b in baris[1:] if b[0] == p.kode)
        self.assertEqual(len(data), len(baris[0]))                     # tidak memecah baris/kolom
        self.assertEqual(data[-1], "Baris 1\nBaris 2")

    def test_export_pengajuan_non_dinas_kolom_baru_kosong(self):
        nondinas = Pengajuan.objects.create(pegawai=self.pegawai, form_saved=True)   # jenis bawaan: Non-Dinas
        baris = next(report.baris_export(Pengajuan.objects.filter(pk=nondinas.pk)))
        self.assertEqual(len(baris), len(report.KOLOM_EXPORT))
        self.assertEqual(baris[-1], "")
