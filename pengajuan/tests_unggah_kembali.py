"""Tombol "Kembali" pada halaman Unggah Dokumen Pegawai (revisi Pegawai Non-Dinas, Poin 2).

Isian formulir tidak dibawa lewat session atau hidden input: `formulir_pengajuan` menyimpannya ke database sebagai
draft, lalu membukanya lagi dari draft yang sama. Tes di sini memastikan tombol menuju formulir itu dan data utuh."""

import re
from datetime import date, timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from paspor.models import KategoriPerjalanan, SumberPembiayaan

from .models import DokumenPegawai, Pengajuan
from .tests_pdln import _Basis


class KembaliBase(_Basis, TestCase):
    def isi_formulir_nondinas(self, maksud="Ibadah umrah bersama keluarga"):
        kategori = KategoriPerjalanan.objects.filter(jenis_perjalanan="Non-Dinas").first()
        sumber = SumberPembiayaan.objects.filter(tipe_perjalanan="Non-Dinas").first()
        self.assertIsNotNone(kategori)
        self.assertIsNotNone(sumber)
        self.data_nondinas = {
            "kategori": kategori.pk, "maksud": maksud, "tujuan_negara": [self.jepang.pk],
            "sumber_pembiayaan": sumber.pk, "tgl_berangkat": self.berangkat.isoformat(),
            "tgl_kembali": (self.berangkat + timedelta(days=4)).isoformat(),
        }
        self.login(self.pegawai)
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas", self.data_nondinas)
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["form"].errors)
        return Pengajuan.objects.filter(pegawai=self.pegawai).latest("created_at")

    def halaman_unggah(self, p):
        self.login(self.pegawai)
        return self.client.get(reverse("pegawai:upload_dokumen", kwargs={"kode": p.kode}))


class TombolKembaliTampilTests(KembaliBase):
    def test_tombol_kembali_di_kiri_tombol_kirim_dalam_field_is_grouped(self):
        p = self.isi_formulir("T1")
        html = self.halaman_unggah(p).content.decode()
        url_formulir = reverse("pegawai:formulir_pengajuan") + f"?kode={p.kode}"      # draft yang sedang dibuka
        self.assertIn('class="field is-grouped"', html)
        kembali = html.index(f'href="{url_formulir}" class="button is-light"')
        kirim = html.index('name="kirim"')
        self.assertLess(kembali, kirim)                       # tepat di sebelah kiri tombol Kirim
        wadah = html[html.index('class="field is-grouped"'):]
        self.assertLess(wadah.index("Kembali</a>"), wadah.index("Kirim ke Admin Unor"))
        self.assertIn("Kirim ke Admin Unor", html)

    def test_tombol_kembali_untuk_nondinas_dan_pdln(self):
        nondinas = self.isi_formulir_nondinas()
        self.assertContains(self.halaman_unggah(nondinas), ">Kembali</a>")

    def test_tombol_kembali_tidak_memuat_emoji_dan_aktif_walau_dokumen_belum_lengkap(self):
        p = self.isi_formulir("T1")
        html = self.halaman_unggah(p).content.decode()
        self.assertIn("disabled", html.split('name="kirim"')[1].split(">")[0])       # Kirim tetap terkunci
        self.assertNotIn("disabled", html.split('class="button is-light"')[1].split(">")[0])  # Kembali tidak
        self.assertNotRegex(html.split(">Kembali</a>")[0][-200:], "[\U0001F300-\U0001FAFF]")

    def test_tombol_kembali_tidak_tampil_setelah_dikirim(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        html = self.halaman_unggah(p).content.decode()
        self.assertNotIn(">Kembali</a>", html)
        self.assertNotIn('name="kirim"', html)               # halaman sudah hanya-lihat

    def test_tombol_kembali_tidak_tampil_saat_dibekukan(self):
        p = self.isi_formulir("T1")
        with mock.patch("pengajuan.alur.alasan_dibekukan", return_value="Pembatalan sedang diproses."):
            html = self.halaman_unggah(p).content.decode()
        self.assertNotIn(">Kembali</a>", html)
        self.assertIn("disabled", html.split('name="kirim"')[1].split(">")[0])


class KembaliDataUtuhTests(KembaliBase):
    def buka_formulir_lewat_tombol(self, p):
        """Meniru klik tombol Kembali: ikuti tautan yang benar-benar ada di halaman Unggah Dokumen."""
        html = self.halaman_unggah(p).content.decode()
        href = re.search(r'<a href="([^"]+)"\s+class="button is-light"', html).group(1)
        return self.client.get(href)

    def test_pdln_formulir_terisi_utuh(self):
        p = self.isi_formulir("T1")
        resp = self.buka_formulir_lewat_tombol(p)
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertEqual(form.instance.pk, p.pk)                         # draft yang sama, bukan pengajuan baru
        self.assertEqual(form["tgl_berangkat"].value(), p.tgl_berangkat)
        self.assertEqual(form["tgl_kembali"].value(), p.tgl_kembali)
        self.assertEqual(form["kategori"].value(), p.kategori_id)
        self.assertEqual(form["kegiatan"].value(), p.kegiatan_id)
        self.assertEqual(form["sumber_pembiayaan"].value(), p.sumber_pembiayaan_id)
        self.assertEqual(list(form["tujuan_negara"].value()), [self.singapura.pk])
        self.assertEqual(form["keterangan_sumber_pembiayaan"].value(), "Biaya Uji")
        self.assertTrue(form["pernyataan_benar"].value())
        self.assertEqual(resp.context["tipe"], "T1")

    def test_nondinas_formulir_terisi_utuh(self):
        p = self.isi_formulir_nondinas("Ibadah umrah bersama keluarga")
        resp = self.buka_formulir_lewat_tombol(p)
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertEqual(form.instance.pk, p.pk)
        self.assertEqual(form["maksud"].value(), "Ibadah umrah bersama keluarga")
        self.assertEqual(form["tgl_berangkat"].value(), p.tgl_berangkat)
        self.assertEqual(form["tgl_kembali"].value(), p.tgl_kembali)
        self.assertEqual(form["kategori"].value(), p.kategori_id)
        self.assertEqual(list(form["tujuan_negara"].value()), [self.jepang.pk])
        self.assertContains(resp, "Ibadah umrah bersama keluarga")

    def test_semua_tipe_pdln_membuka_formulir_tipe_yang_sama(self):
        for tipe in ("T1", "T2P", "T2L", "T3"):
            with self.subTest(tipe=tipe):
                Pengajuan.objects.filter(pegawai=self.pegawai).delete()
                p = self.isi_formulir(tipe)
                resp = self.buka_formulir_lewat_tombol(p)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.context["tipe"], tipe)
                self.assertEqual(resp.context["form"].instance.pk, p.pk)

    def test_kembali_lalu_simpan_ulang_tidak_membuat_pengajuan_baru_dan_dokumen_tetap_ada(self):
        p = self.isi_formulir("T1")
        DokumenPegawai.objects.create(pengajuan=p, jenis="cuti", file="x.pdf", tanggal_surat=date.today())
        self.buka_formulir_lewat_tombol(p)
        data = {
            "kategori": p.kategori_id, "kegiatan": p.kegiatan_id, "tujuan_negara": [self.singapura.pk],
            "sumber_pembiayaan": p.sumber_pembiayaan_id, "tgl_berangkat": p.tgl_berangkat.isoformat(),
            "tgl_kembali": p.tgl_kembali.isoformat(), "keterangan_sumber_pembiayaan": "Biaya Uji Revisi",
            "pernyataan_benar": "on",
        }
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + f"?kode={p.kode}", data)
        self.assertRedirects(resp, reverse("pegawai:upload_dokumen", kwargs={"kode": p.kode}), fetch_redirect_response=False)
        self.assertEqual(Pengajuan.objects.filter(pegawai=self.pegawai).count(), 1)
        self.assertEqual(DokumenPegawai.objects.filter(pengajuan=p).count(), 1)
        p.refresh_from_db()
        self.assertEqual(p.detail.keterangan_sumber_pembiayaan, "Biaya Uji Revisi")

    def test_pengajuan_yang_dikembalikan_unor_tetap_bisa_kembali_ke_formulir(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.post(self.admin_unor, "unor:preview", {"kembalikan": "1", "catatan": "Lengkapi dokumen."}, kode=p.kode)
        p.refresh_from_db()
        self.assertEqual(p.status, "belum")
        self.assertContains(self.halaman_unggah(p), ">Kembali</a>")
        resp = self.buka_formulir_lewat_tombol(p)
        self.assertEqual(resp.context["form"].instance.pk, p.pk)


class KirimTidakBerubahTests(KembaliBase):
    def test_kirim_tetap_berfungsi_dan_logikanya_tidak_berubah(self):
        p = self.isi_formulir("T1")
        resp = self.kirim(p)                                  # unggah dokumen wajib lalu POST "kirim"
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual((p.status, p.submitted), ("proses", True))

    def test_kirim_ditolak_bila_dokumen_belum_lengkap(self):
        p = self.isi_formulir("T1")
        self.login(self.pegawai)
        self.client.post(reverse("pegawai:upload_dokumen", kwargs={"kode": p.kode}), {"kirim": "1", "agree": "on"})
        p.refresh_from_db()
        self.assertEqual(p.status, "belum")
