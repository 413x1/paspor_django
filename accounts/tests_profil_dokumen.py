"""Profil: unggah dan ganti dokumen kepegawaian (revisi kompatibilitas Edge + penyimpanan aman)."""

import re
from unittest import mock

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import DokumenKepegawaian, PegawaiProfile, User

_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
PDF = b"%PDF-1.4\n%isi dokumen\n"
# Emoji dekoratif (panah, tambah, tanda seru, dst.), ditulis sebagai kode karakter. Tanda centang tipografis
# U+2713 pada status "Diunggah" bukan emoji dan sengaja tidak termasuk.
EMOJI = re.compile("[\U0001F300-\U0001FAFF⬀-⯿➕-➗✅❌⚠]")


def pdf(nama="ktp.pdf", isi=PDF):
    return SimpleUploadedFile(nama, isi, content_type="application/pdf")


def kosongkan_penyimpanan(folder=""):
    """InMemoryStorage dipakai bersama antar-tes dalam satu kelas; bersihkan agar hitungan berkas tidak bocor."""
    subfolder, berkas = default_storage.listdir(folder)
    for nama in berkas:
        default_storage.delete(f"{folder}/{nama}" if folder else nama)
    for sub in subfolder:
        kosongkan_penyimpanan(f"{folder}/{sub}" if folder else sub)


@override_settings(STORAGES=_STORAGES_MEMORI)
class ProfilDokumenBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("peg1", password="x", role="pegawai", no_hp="6281100000001")
        PegawaiProfile.objects.create(
            user=self.user, nip="1990", nama="Pegawai Satu", jabatan="Staf", pangkat_golongan="III-a", unit_kerja="Biro",
        )
        self.client.force_login(self.user)
        self.url = reverse("profil")
        kosongkan_penyimpanan()
        self.addCleanup(kosongkan_penyimpanan)

    def unggah(self, jenis="ktp", **ekstra):
        data = {"aksi": "unggah_dokumen", "jenis": jenis, **ekstra}
        return self.client.post(self.url, data, follow=True)

    def dok(self, jenis="ktp"):
        return DokumenKepegawaian.objects.get(user=self.user, jenis=jenis)

    @staticmethod
    def pesan(resp):
        return [str(m) for m in resp.context["messages"]]


class UnggahDanGantiTests(ProfilDokumenBase):
    def test_unggah_pertama_membuat_dokumen(self):
        resp = self.unggah(file=pdf())
        self.assertIn("Dokumen berhasil diunggah.", self.pesan(resp))
        self.assertTrue(default_storage.exists(self.dok().file.name))

    def test_ganti_menyimpan_berkas_baru_dan_menghapus_yang_lama(self):
        self.unggah(file=pdf("lama.pdf", PDF + b"lama"))
        nama_lama = self.dok().file.name
        resp = self.unggah(file=pdf("baru.pdf", PDF + b"baru"))
        self.assertIn("Dokumen berhasil diunggah.", self.pesan(resp))
        dok = self.dok()
        self.assertNotEqual(dok.file.name, nama_lama)
        self.assertTrue(default_storage.exists(dok.file.name))
        self.assertFalse(default_storage.exists(nama_lama))
        self.assertEqual(DokumenKepegawaian.objects.filter(user=self.user, jenis="ktp").count(), 1)

    def test_ganti_dengan_nama_berkas_yang_sama(self):
        """Memindai ulang dokumen biasanya menghasilkan nama berkas yang sama: tetap berhasil, hanya satu berkas tersisa."""
        self.unggah(file=pdf("ktp.pdf", PDF + b"v1"))
        nama_lama = self.dok().file.name
        self.unggah(file=pdf("ktp.pdf", PDF + b"v2"))
        dok = self.dok()
        with default_storage.open(dok.file.name) as f:
            self.assertEqual(f.read(), PDF + b"v2")
        self.assertTrue(default_storage.exists(dok.file.name))
        if nama_lama != dok.file.name:
            self.assertFalse(default_storage.exists(nama_lama))

    def test_ganti_berkali_kali_berturut_turut(self):
        for i in range(4):
            resp = self.unggah(file=pdf("ktp.pdf", PDF + str(i).encode()))
            self.assertIn("Dokumen berhasil diunggah.", self.pesan(resp))
        with default_storage.open(self.dok().file.name) as f:
            self.assertEqual(f.read(), PDF + b"3")
        self.assertEqual(len(default_storage.listdir(f"kepegawaian/{self.user.pk}/ktp")[1]), 1)

    def test_tanpa_berkas_baru_dokumen_lama_dipertahankan(self):
        self.unggah(file=pdf("lama.pdf", PDF + b"lama"))
        sebelum = self.dok()
        resp = self.unggah()          # tidak memilih berkas baru
        self.assertTrue(any("Pilih berkas PDF" in m for m in self.pesan(resp)))
        sesudah = self.dok()
        self.assertEqual((sesudah.file.name, sesudah.uploaded_at), (sebelum.file.name, sebelum.uploaded_at))
        with default_storage.open(sesudah.file.name) as f:
            self.assertEqual(f.read(), PDF + b"lama")

    def test_jenis_tidak_dikenal_ditolak(self):
        resp = self.unggah(jenis="tidak-ada", file=pdf())
        self.assertIn("Jenis dokumen tidak dikenali.", self.pesan(resp))
        self.assertFalse(DokumenKepegawaian.objects.exists())

    def test_berkas_bukan_pdf_ditolak_dan_dokumen_lama_utuh(self):
        self.unggah(file=pdf("lama.pdf", PDF + b"lama"))
        nama_lama = self.dok().file.name
        self.unggah(file=SimpleUploadedFile("foto.jpg", b"\xff\xd8\xff", content_type="image/jpeg"))
        self.assertEqual(self.dok().file.name, nama_lama)
        self.assertTrue(default_storage.exists(nama_lama))


class PenyimpananAmanTests(ProfilDokumenBase):
    def test_berkas_lama_terkunci_tidak_menggagalkan_unggahan(self):
        """Di Windows berkas yang sedang terbuka tidak bisa dihapus; unggahan baru tetap harus berhasil."""
        self.unggah(file=pdf("lama.pdf", PDF + b"lama"))
        nama_lama = self.dok().file.name
        with mock.patch("django.core.files.storage.memory.InMemoryStorage.delete", side_effect=PermissionError("terkunci")):
            resp = self.unggah(file=pdf("baru.pdf", PDF + b"baru"))
        self.assertIn("Dokumen berhasil diunggah.", self.pesan(resp))
        self.assertNotEqual(self.dok().file.name, nama_lama)
        self.assertTrue(default_storage.exists(self.dok().file.name))

    def test_gagal_menyimpan_mempertahankan_dokumen_lama(self):
        self.unggah(file=pdf("lama.pdf", PDF + b"lama"))
        sebelum = self.dok()
        with mock.patch.object(DokumenKepegawaian, "save", side_effect=OSError("disk penuh")):
            resp = self.unggah(file=pdf("baru.pdf", PDF + b"baru"))
        self.assertEqual(resp.status_code, 200)       # tidak menjadi error 500
        self.assertTrue(any("Dokumen sebelumnya tetap dipertahankan" in m for m in self.pesan(resp)))
        sesudah = self.dok()
        self.assertEqual(sesudah.file.name, sebelum.file.name)
        with default_storage.open(sesudah.file.name) as f:
            self.assertEqual(f.read(), PDF + b"lama")

    def test_gagal_menyimpan_pada_unggah_pertama_tidak_meninggalkan_baris(self):
        with mock.patch.object(DokumenKepegawaian.objects, "create", side_effect=OSError("disk penuh")):
            resp = self.unggah(file=pdf())
        self.assertTrue(any("gagal disimpan" in m for m in self.pesan(resp)))
        self.assertFalse(DokumenKepegawaian.objects.exists())


class TampilanProfilTests(ProfilDokumenBase):
    def test_input_berkas_memakai_atribut_standar(self):
        self.unggah(file=pdf())
        html = self.client.get(self.url).content.decode()
        for atribut in ('type="file"', 'accept=".pdf,application/pdf"', "data-pdf-only", 'data-max-mb="2"', "doc-file-input"):
            self.assertIn(atribut, html)
        # Berkas sudah ada: tombol berlabel "Ganti" dan pratinjau tersedia.
        self.assertIn(">Ganti<", html)
        self.assertIn("data-doc-preview", html)

    def test_skrip_mengosongkan_pilihan_sebelum_dialog_dan_memulihkan_dari_cache(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("$(document).on('click', '.doc-file-input', function () { this.value = ''; });", html)
        self.assertIn("window.addEventListener('pageshow'", html)
        self.assertIn("Berkas dipilih: ", html)

    def test_pratinjau_pdf_hanya_lihat_tanpa_toolbar_penampil(self):
        """Toolbar penampil PDF Edge memuat alat gambar/sorot/teks; pratinjau tidak boleh menampilkannya."""
        self.unggah(file=pdf())
        html = self.client.get(self.url).content.decode()
        self.assertIn("toolbar=0&navpanes=0&statusbar=0&view=FitH", html)
        self.assertNotIn("toolbar=1", html)
        self.assertIn("Buka di tab baru", html)       # dokumen utuh tetap bisa dibuka di tab baru

    def test_tidak_ada_emoji_pada_komponen_unggah_dan_pesan(self):
        self.unggah(file=pdf())
        html = self.client.get(self.url).content.decode()
        baris_dokumen = html.split('class="section-title is-small">Dokumen Kepegawaian')[1].split("Data Paspor")[0]
        self.assertIsNone(EMOJI.search(baris_dokumen))
        for resp in (self.unggah(), self.unggah(jenis="x", file=pdf())):
            for m in self.pesan(resp):
                self.assertIsNone(EMOJI.search(m), m)
