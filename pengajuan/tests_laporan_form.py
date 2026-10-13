"""Formulir Pelaporan PDLN oleh Pegawai: Simpan (draft) dan Laporkan (kirim ke Biro PAKLN)."""

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from logs.models import ActivityLog
from notifications.models import Notification
from paspor.validators import PESAN_BUKAN_PDF

from .forms import LaporanPdlnForm, format_rupiah
from .models import DetailPdln, LaporanPdln, Pengajuan, RiwayatPengajuan
from .tests import _AlurMixin

_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
PDF = b"%PDF-1.4\n%laporan\n"
ISI = {
    "tujuan_kegiatan": "Mengikuti pertemuan bilateral", "materi_kegiatan": "Materi kerja sama",
    "tindak_lanjut": "Menyusun nota kesepahaman", "dampak_rekomendasi": "Dampak positif bagi unit",
}


def pdf(nama="laporan.pdf", isi=PDF, tipe="application/pdf"):
    return SimpleUploadedFile(nama, isi, content_type=tipe)


class FormBiayaTests(SimpleTestCase):
    def test_format_rupiah_dibersihkan_menjadi_angka(self):
        angka = LaporanPdlnForm._angka
        self.assertEqual(angka("10.000.000"), Decimal(10000000))
        self.assertEqual(angka("Rp 1.500.000"), Decimal(1500000))
        self.assertEqual(angka("1.500.000,75"), Decimal(1500000))   # desimal setelah koma diabaikan
        self.assertEqual(angka("0"), Decimal(0))
        self.assertIsNone(angka(""))
        self.assertIsNone(angka("abc"))
        self.assertIsNone(angka(None))

    def test_nilai_terlalu_besar_ditolak(self):
        from django import forms
        with self.assertRaises(forms.ValidationError):
            LaporanPdlnForm._angka("1" * 16)

    def test_format_rupiah_untuk_tampilan(self):
        self.assertEqual(format_rupiah(Decimal(10000000)), "10.000.000")
        self.assertEqual(format_rupiah(999), "999")


@override_settings(STORAGES=_STORAGES_MEMORI)
class LaporanFormBase(_AlurMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.p = Pengajuan.objects.create(
            pegawai=self.pegawai, form_saved=True, jenis_perjalanan="pdln", tipe_pdln="T1",
            status=Pengajuan.Status.SELESAI, unit_organisasi=self.unor, tgl_pengajuan=date(2026, 9, 1),
            tgl_berangkat=date(2026, 10, 1), tgl_kembali=date(2026, 10, 8), tgl_selesai=date(2026, 9, 20),
        )
        self.url = reverse("pegawai:laporan_form", args=[self.p.kode])
        self.client.force_login(self.pegawai)

    def kirim(self, aksi="submit", **ekstra):
        data = {"action": aksi, **ISI, "estimasi_biaya": "10.000.000", "realisasi_biaya": "9.250.000",
                "dokumen_laporan": pdf(), **ekstra}
        return self.client.post(self.url, data)

    def laporan(self):
        return LaporanPdln.objects.get(pengajuan=self.p)


class LaporanFormTampilTests(LaporanFormBase):
    def test_bagian_a_layout_horizontal_urutan_dan_label_sesuai_mockup(self):
        DetailPdln.objects.create(
            pengajuan=self.p, kota_tujuan="Sydney", penyelenggara="Universitas Sydney",
            tgl_mulai_kegiatan=date(2026, 10, 2), tgl_selesai_kegiatan=date(2026, 10, 6), pernyataan_benar=True,
        )
        html = self.client.get(self.url).content.decode()
        bagian_a = html.split("A. Data Pengajuan")[1].split("B. Uraian Laporan")[0]
        # urutan label persis sesuai mockup
        label = ["No.Register Yang Dilaporkan", "Nama Kegiatan", "Tempat", "Waktu Pelaksanaan"]
        posisi = [bagian_a.index(f">{nama}</label>") for nama in label]
        self.assertEqual(posisi, sorted(posisi))
        # field lama tidak ada lagi di bagian A
        for lama in ("Nama Pegawai", "Kode Pengajuan", "Tipe Pengajuan", "Negara Tujuan", "Tanggal Pelaksanaan"):
            self.assertNotIn(f">{lama}</label>", bagian_a)
        # struktur horizontal Bulma
        self.assertEqual(bagian_a.count('class="field is-horizontal"'), 4)       # satu baris per label
        self.assertEqual(bagian_a.count('class="field-label is-normal"'), 4)
        self.assertEqual(bagian_a.count('class="field-body"'), 4)
        # isian
        self.assertIn("Universitas Sydney", bagian_a)               # nama kegiatan
        self.assertIn("Sydney", bagian_a)                           # tempat
        self.assertIn("02/10/2026 s/d 06/10/2026", bagian_a)        # waktu pelaksanaan
        self.assertGreaterEqual(bagian_a.count("readonly"), 3)
        # No.Register: tautan biru ke detail (monitor progres) di tab baru + tombol "Lihat Detail"
        detail = reverse("pegawai:monitor_progres", args=[self.p.kode])
        self.assertIn(f'class="input laporan-kode-link" href="{detail}"', bagian_a)
        self.assertIn("Lihat Detail", bagian_a)
        self.assertIn('rel="noopener"', bagian_a)

    def test_nama_kegiatan_memakai_kategori_dan_penyelenggara_atau_perguruan_tinggi(self):
        DetailPdln.objects.create(pengajuan=self.p, kota_tujuan="Delft", perguruan_tinggi="TU Delft", pernyataan_benar=True)
        bagian_a = self.client.get(self.url).content.decode().split("B. Uraian Laporan")[0]
        self.assertIn("TU Delft", bagian_a)

    def test_tanpa_detail_tanggal_pelaksanaan_memakai_tanggal_perjalanan(self):
        self.assertIn("01/10/2026 s/d 08/10/2026", self.client.get(self.url).content.decode())

    def test_bagian_b_c_dan_tombol(self):
        html = self.client.get(self.url).content.decode()
        for nama in ("tujuan_kegiatan", "materi_kegiatan", "tindak_lanjut", "dampak_rekomendasi"):
            self.assertIn(f'name="{nama}"', html)
        self.assertIn('class="textarea"', html)
        self.assertIn('name="estimasi_biaya"', html)
        self.assertIn('name="realisasi_biaya"', html)
        self.assertIn('accept=".pdf,application/pdf"', html)
        self.assertIn('name="action" value="draft" class="button is-info btn-pelaporan-info">Simpan', html)
        self.assertIn('name="action" value="submit" class="button is-danger btn-pelaporan-danger"', html)
        self.assertIn("input-rupiah", html)                       # target skrip format Rupiah

    def test_nama_peserta_otomatis_dari_akun_dan_tidak_dapat_diubah(self):
        html = self.client.get(self.url).content.decode()
        bagian_c = html.split("C. Biaya dan Dokumen")[1]
        kolom = bagian_c.split('id="namaPeserta"')[1].split(">")[0]
        self.assertIn("readonly", kolom)
        self.assertIn('value="Pegawai Satu"', kolom)
        self.assertNotIn("name=", kolom)                       # tidak ikut terkirim bersama formulir
        # dikirim paksa pun tidak berpengaruh: nama peserta tidak ada di form maupun model laporan
        self.assertNotIn("nama_peserta", self.client.get(self.url).context["form"].fields)
        r = self.client.post(self.url, {"action": "draft", "nama_peserta": "Nama Palsu", "tujuan_kegiatan": "x"})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("Nama Palsu", self.client.get(self.url).content.decode())

    def test_hanya_pdln_selesai_milik_sendiri(self):
        self.client.force_login(self.admin_unor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        lain = User.objects.create_user(username="pegawai.lain", password="x", role="pegawai")
        self.client.force_login(lain)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.pegawai)
        Pengajuan.objects.filter(pk=self.p.pk).update(status=Pengajuan.Status.PROSES_PAKLN)
        r = self.client.get(self.url, follow=True)
        self.assertContains(r, "setelah pengajuan selesai diproses")
        self.assertEqual(self.client.get(reverse("pegawai:laporan_form", args=[self.pengajuan.kode])).status_code, 404)  # Non-Dinas


class LaporanFormSimpanTests(LaporanFormBase):
    def test_simpan_draft_tanpa_kelengkapan(self):
        r = self.client.post(self.url, {"action": "draft", "tujuan_kegiatan": "Baru sebagian"})
        self.assertRedirects(r, self.url)
        laporan = self.laporan()
        self.assertEqual((laporan.status, laporan.tujuan_kegiatan), ("draft", "Baru sebagian"))
        self.assertFalse(laporan.file)
        # draft: tidak ada riwayat pemrosesan dan tidak ada notifikasi ke Biro PAKLN
        self.assertFalse(RiwayatPengajuan.objects.filter(pengajuan=self.p, aksi="laporan_diunggah").exists())
        self.assertFalse(Notification.objects.filter(recipient=self.admin_pakln, event="NOTIF_05A_LAPORAN_DIUNGGAH").exists())
        self.assertTrue(ActivityLog.objects.filter(aktivitas="laporan.simpan", target_id=self.p.kode).exists())

    def test_draft_disimpan_dan_dimuat_ulang_dengan_format_rupiah(self):
        self.kirim("draft")
        laporan = self.laporan()
        self.assertEqual((laporan.estimasi_biaya, laporan.realisasi_biaya), (Decimal(10000000), Decimal(9250000)))
        self.assertTrue(laporan.file)
        html = self.client.get(self.url).content.decode()
        self.assertIn('value="10.000.000"', html)
        self.assertIn('value="9.250.000"', html)
        self.assertIn("Draft laporan tersimpan", html)
        self.assertIn("(tersimpan)", html)

    def test_draft_dapat_dilanjutkan_dan_berkas_tersimpan_dipertahankan(self):
        self.kirim("draft")
        nama = self.laporan().file.name
        r = self.client.post(self.url, {"action": "draft", **ISI})           # tanpa berkas baru
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.laporan().file.name, nama)

    def test_aksi_tidak_valid_ditolak(self):
        r = self.client.post(self.url, {"action": "hapus"}, follow=True)
        self.assertContains(r, "Aksi tidak valid")
        self.assertFalse(LaporanPdln.objects.filter(pengajuan=self.p).exists())


class LaporanFormLaporkanTests(LaporanFormBase):
    def test_laporkan_lengkap_mengirim_ke_biro_pakln(self):
        r = self.kirim()
        self.assertRedirects(r, reverse("pegawai:pelaporan"))
        laporan = self.laporan()
        self.assertEqual((laporan.status, laporan.diunggah_oleh), ("menunggu", self.pegawai))
        self.assertTrue(laporan.file.name.endswith(".pdf"))
        self.assertTrue(RiwayatPengajuan.objects.filter(pengajuan=self.p, aksi="laporan_diunggah").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.admin_pakln, event="NOTIF_05A_LAPORAN_DIUNGGAH").exists())

    def test_laporkan_tidak_lengkap_ditolak_dengan_pesan_per_kolom(self):
        r = self.client.post(self.url, {"action": "submit", "tujuan_kegiatan": "hanya ini"})
        self.assertEqual(r.status_code, 200)
        form = r.context["form"]
        for nama in ("materi_kegiatan", "tindak_lanjut", "dampak_rekomendasi"):
            self.assertIn("Wajib diisi untuk melaporkan.", form.errors[nama])
        self.assertIn("Dokumen laporan wajib diunggah untuk melaporkan.", form.errors["dokumen_laporan"])
        for nama in ("estimasi_biaya", "realisasi_biaya"):          # biaya ikut wajib saat Laporkan
            self.assertIn("Wajib diisi untuk melaporkan.", form.errors[nama])
        self.assertFalse(LaporanPdln.objects.filter(pengajuan=self.p).exists())

    def test_laporkan_wajib_estimasi_realisasi_dan_dokumen_masing_masing(self):
        """Setiap isian yang dikosongkan menggagalkan Laporkan, tepat pada kolom itu."""
        for kosong in ("estimasi_biaya", "realisasi_biaya", "dokumen_laporan", *ISI):
            data = {"action": "submit", **ISI, "estimasi_biaya": "1.000", "realisasi_biaya": "900", "dokumen_laporan": pdf()}
            data.pop(kosong)
            r = self.client.post(self.url, data)
            self.assertEqual(r.status_code, 200, kosong)
            self.assertEqual(list(r.context["form"].errors), [kosong], kosong)
        self.assertFalse(LaporanPdln.objects.filter(pengajuan=self.p).exists())

    def test_biaya_tanpa_angka_dianggap_kosong_dan_nol_dianggap_terisi(self):
        r = self.kirim(estimasi_biaya="abc", realisasi_biaya="---")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(r.context["form"].errors), ["estimasi_biaya", "realisasi_biaya"])
        r = self.kirim(estimasi_biaya="0", realisasi_biaya="0")      # nol adalah nilai yang sah
        self.assertRedirects(r, reverse("pegawai:pelaporan"))
        self.assertEqual((self.laporan().estimasi_biaya, self.laporan().realisasi_biaya), (0, 0))

    def test_simpan_draft_tetap_boleh_tanpa_biaya_dan_dokumen(self):
        r = self.client.post(self.url, {"action": "draft", **ISI})
        self.assertRedirects(r, self.url)
        laporan = self.laporan()
        self.assertEqual((laporan.status, laporan.estimasi_biaya, laporan.realisasi_biaya), ("draft", None, None))
        self.assertFalse(laporan.file)

    def test_tanda_wajib_pada_semua_isian_di_halaman(self):
        html = self.client.get(self.url).content.decode()
        for label in ("Estimasi Biaya (Rp)", "Realisasi Biaya (Rp)", "Dokumen Laporan Kegiatan", "Tujuan Kegiatan"):
            potongan = html.split(label)[1][:120]
            self.assertIn('class="wajib"', potongan, label)
        self.assertIn("uraian, biaya, dan dokumen PDF", html)

    def test_uraian_hanya_spasi_dianggap_kosong(self):
        r = self.kirim(tujuan_kegiatan="   ")
        self.assertEqual(r.status_code, 200)
        self.assertIn("tujuan_kegiatan", r.context["form"].errors)

    def test_setelah_dilaporkan_hanya_dapat_dilihat(self):
        self.kirim()
        html = self.client.get(self.url).content.decode()
        self.assertIn("menunggu verifikasi Biro PAKLN", html)
        self.assertNotIn('value="draft"', html)
        self.assertNotIn('value="submit"', html)
        self.assertIn("disabled", html)
        r = self.client.post(self.url, {"action": "draft", "tujuan_kegiatan": "diubah paksa"}, follow=True)
        self.assertContains(r, "tidak dapat diubah")
        self.assertEqual(self.laporan().tujuan_kegiatan, ISI["tujuan_kegiatan"])
        self.assertEqual(self.laporan().status, "menunggu")


class LaporanFormDikembalikanTests(LaporanFormBase):
    def setUp(self):
        super().setUp()
        self.kirim()
        LaporanPdln.objects.filter(pengajuan=self.p).update(status="dikembalikan", catatan_pakln="Lampirkan bukti biaya.")

    def test_banner_catatan_biro_pakln_dan_kolom_catatan_perbaikan(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Lampirkan bukti biaya.", html)
        self.assertIn('name="catatan_perbaikan"', html)

    def test_laporkan_ulang_wajib_catatan_perbaikan(self):
        r = self.kirim(catatan_perbaikan="")
        self.assertEqual(r.status_code, 200)
        self.assertIn("catatan_perbaikan", r.context["form"].errors)
        self.assertEqual(self.laporan().status, "dikembalikan")

        r = self.kirim(catatan_perbaikan="Bukti biaya sudah dilampirkan.")
        self.assertRedirects(r, reverse("pegawai:pelaporan"))
        self.assertEqual(self.laporan().status, "menunggu")
        notif = Notification.objects.filter(recipient=self.admin_pakln, event="NOTIF_05A_LAPORAN_DIUNGGAH").latest("pk")
        self.assertIn("Bukti biaya sudah dilampirkan.", notif.body)

    def test_simpan_draft_tidak_menghapus_status_dikembalikan(self):
        self.client.post(self.url, {"action": "draft", **ISI})
        self.assertEqual(self.laporan().status, "dikembalikan")

    def test_berkas_baru_menggantikan_dan_menghapus_berkas_lama(self):
        lama = self.laporan().file.name
        storage = self.laporan().file.storage
        self.assertTrue(storage.exists(lama))
        self.kirim(catatan_perbaikan="Diperbaiki.", dokumen_laporan=pdf("laporan-baru.pdf"))
        baru = self.laporan().file.name
        self.assertNotEqual(baru, lama)
        self.assertFalse(storage.exists(lama))
        self.assertTrue(storage.exists(baru))


class LaporanFormPdfOnlyTests(LaporanFormBase):
    def test_berkas_bukan_pdf_ditolak_dengan_status_400(self):
        for salah in (pdf("laporan.docx"), pdf("laporan.png", tipe="image/png"), pdf(isi=b"bukan pdf")):
            r = self.kirim(dokumen_laporan=salah)
            self.assertEqual(r.status_code, 400, salah.name)
            self.assertTrue(r.context["form"].errors["dokumen_laporan"])
        self.assertFalse(LaporanPdln.objects.filter(pengajuan=self.p).exists())

    def test_pesan_error_pdf_tampil(self):
        r = self.kirim(dokumen_laporan=pdf("laporan.docx"))
        self.assertContains(r, PESAN_BUKAN_PDF, status_code=400)


class LaporanDiAdminDanDaftarTests(LaporanFormBase):
    def test_daftar_pelaporan_memakai_tautan_bukan_modal(self):
        html = self.client.get(reverse("pegawai:pelaporan")).content.decode()
        self.assertIn(f'<a href="{self.url}" class="button is-small is-info btn-pelaporan-info">Pelaporan PDLN</a>', html)
        self.assertNotIn("laporanModal-", html)
        self.assertNotIn("Unggah Laporan", html)
        self.kirim()
        html = self.client.get(reverse("pegawai:pelaporan")).content.decode()
        self.assertIn("Lihat Laporan", html)       # menunggu verifikasi: hanya lihat

    def test_tabel_riwayat_beranda_memuat_tautan_pelaporan(self):
        # Pengajuan baru (aktif) di atas PDLN lama supaya PDLN lama masuk tabel riwayat.
        Pengajuan.objects.create(pegawai=self.pegawai, form_saved=True, jenis_perjalanan="pdln", tipe_pdln="T1",
                                 status=Pengajuan.Status.PROSES, tgl_pengajuan=date(2026, 10, 9))
        data = self.client.get(reverse("pegawai:riwayat_data"), {"jenis": "pdln", "length": 10}).json()["data"]
        baris = next(b for b in data if self.p.kode in b[0])
        self.assertIn(self.url, baris[6])
        self.assertIn("Pelaporan PDLN", baris[6])

    def test_admin_pakln_melihat_isi_laporan_untuk_verifikasi(self):
        self.kirim()
        self.client.force_login(self.admin_pakln)
        html = self.client.get(reverse("pakln:pelaporan")).content.decode()
        self.assertIn(ISI["tujuan_kegiatan"], html)
        self.assertIn(ISI["dampak_rekomendasi"], html)
        self.assertIn("Rp 10.000.000", html)       # biaya berformat Rupiah dengan titik ribuan
        self.assertIn("Rp 9.250.000", html)
        self.assertNotIn("Rp 10000000", html)
        modal = html.split('class="modal paspor-modal modal-verifikasi"')[1]
        self.assertIn("Estimasi Biaya", modal)
        self.assertIn("Realisasi Biaya", modal)
        self.assertIn("verif-aksi", modal)                         # tombol aksi dibungkus (wrap), tidak meluber

    def test_draft_dihitung_belum_melapor_oleh_admin_dan_laporan(self):
        from . import report
        from .views_unor import _konteks_pelaporan
        self.kirim("draft")
        ctx = _konteks_pelaporan(Pengajuan.objects.filter(pk=self.p.pk))
        self.assertEqual((ctx["hitung"]["belum"], ctx["hitung"]["menunggu"]), (1, 0))
        self.assertIsNone(ctx["baris"][0]["laporan"])
        self.assertTrue(report.status_pelaporan(Pengajuan.objects.get(pk=self.p.pk)).startswith("Belum Melapor"))

    def test_draft_tidak_menghitung_pengajuan_tuntas_dan_pesan_blokir(self):
        from . import alur
        self.kirim("draft")
        p = Pengajuan.objects.get(pk=self.p.pk)
        self.assertFalse(p.tuntas)
        self.assertIn("masih berupa draft", alur.alasan_belum_tuntas(p))


class FilterRupiahTests(SimpleTestCase):
    def test_rupiah(self):
        from .templatetags.pengajuan_extras import rupiah
        self.assertEqual(rupiah(Decimal(100000000)), "Rp 100.000.000")
        self.assertEqual(rupiah(0), "Rp 0")
        self.assertEqual(rupiah(None), "—")
        self.assertEqual(rupiah(""), "—")
