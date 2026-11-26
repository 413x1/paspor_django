"""Admin Biro PAKLN: tanpa tanda panah dan ikon dekoratif pada Dasbor, Pratinjau, dan Administrasi Biro PAKLN (perbaikan UI).

Dasbor: tombol TL dan notifikasi kuning "Nomor HP Anda belum tercatat". Pratinjau: Lanjut/Lanjutkan ke Administrasi Biro PAKLN,
Kembalikan ke Admin BPSDM/Unor (judul dan tombol), dan Kembali ke Dasbor. Administrasi: Kembalikan Surat Tugas ke Admin Unor,
Selesaikan Proses, dan Kembali ke Pratinjau. Juga: ikon tombol Generate ND, ikon Generate otomatis, dan ceklis
"Lanjutkan tanpa SK Tubel"."""

from django.test import TestCase
from django.urls import reverse

from .models import Pengajuan
from .tests_pdln import _Basis

S = Pengajuan.Status
PANAH = ("→", "←")
IKON_KEMBALI = "↩"
CENTANG = "✓"


class PaklnTanpaIkonTests(_Basis, TestCase):
    def pengajuan_t1_di_pakln(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        return p

    def pengajuan_t2p_di_pakln(self):
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.kirim(p)
        self.unor_teruskan(p)
        self.bpsdm_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        return p

    # ---- Dasbor ----
    def test_dasbor_tombol_tl_tanpa_panah_di_kedua_kondisi(self):
        p = self.pengajuan_t1_di_pakln()
        isi = str(self.get(self.admin_pakln, "pakln:dashboard_data").json()["data"])
        self.assertIn('class="button is-warning is-small">TL</a>', isi)                 # belum menyetujui: tautan ke pratinjau
        self.assertIn(reverse("pakln:preview", args=[p.kode]), isi)
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        isi = str(self.get(self.admin_pakln, "pakln:dashboard_data").json()["data"])    # sudah menyetujui: tautan ke administrasi
        self.assertIn('class="button is-warning is-small">TL</a>', isi)
        self.assertIn(reverse("pakln:upload_dokumen", args=[p.kode]), isi)
        for panah in PANAH:
            self.assertNotIn("TL " + panah, isi)

    def test_notifikasi_nomor_hp_tanpa_panah(self):
        self.admin_pakln.no_hp = ""
        self.admin_pakln.save()
        html = self.get(self.admin_pakln, "pakln:dashboard").content.decode()
        self.assertIn("Nomor HP Anda belum tercatat.", html)
        self.assertRegex(html, r'<a href="[^"]*">Lengkapi di menu Profil</a>')
        self.assertNotIn("Lengkapi di menu Profil →", html)

    # ---- Pratinjau ----
    def test_pratinjau_sebelum_menyetujui_tanpa_panah_dan_ikon_kembali(self):
        p = self.pengajuan_t1_di_pakln()
        html = self.get(self.admin_pakln, "pakln:preview", kode=p.kode).content.decode()
        self.assertIn('class="button is-primary is-fullwidth">Lanjutkan ke Administrasi Biro PAKLN</button>', html)
        self.assertRegex(html, r'<div class="section-title is-small">Kembalikan ke [^<]+</div>')
        self.assertRegex(html, r'class="button is-danger is-fullwidth">Kembalikan ke [^<]+</button>')
        self.assertIn('class="button is-fullwidth">Kembali ke Dasbor</a>', html)
        self.assertNotIn(IKON_KEMBALI, html)
        self.assertNotIn("← Kembali ke Dasbor", html)
        self.assertNotIn("Biro PAKLN →", html)

    def test_pratinjau_sesudah_menyetujui_tautan_lanjut_tanpa_panah(self):
        p = self.pengajuan_t1_di_pakln()
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        html = self.get(self.admin_pakln, "pakln:preview", kode=p.kode).content.decode()
        self.assertRegex(html, r"Lanjut ke Administrasi Biro PAKLN\s*</a>")
        self.assertNotIn("Lanjut ke Administrasi Biro PAKLN →", html)

    # ---- Administrasi Biro PAKLN ----
    def test_administrasi_selesaikan_proses_tanpa_centang_dan_kembali_tanpa_panah(self):
        p = self.pengajuan_t1_di_pakln()
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        resp = self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode)
        html = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        self.assertRegex(html, r"Selesaikan Proses\s*</button>")
        self.assertNotRegex(html, r"Selesaikan Proses\s*" + CENTANG)
        self.assertIn('class="button">Kembali ke Pratinjau</a>', html)
        self.assertNotIn("← Kembali ke Pratinjau", html)

    def test_administrasi_tombol_kembalikan_surat_tugas_tanpa_ikon(self):
        p = self.pengajuan_t2p_di_pakln()
        self.surat_tugas_dikirim(p)
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        html = self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode).content.decode()
        self.assertIn('class="button is-danger is-light">Kembalikan Surat Tugas ke Admin Unor</button>', html)
        self.assertNotIn(IKON_KEMBALI, html)

    def test_penanda_status_hijau_tetap_dipertahankan(self):
        """Tanda centang pada status ("Sudah diunggah", "Dikirim Admin Unor", dst.) membawa makna dan tidak diubah."""
        isi = open("templates/pakln/upload.html", encoding="utf-8").read()
        self.assertIn(CENTANG + " Dikirim Admin Unor", isi)
        self.assertIn(CENTANG + " Sudah diunggah", isi)

    def test_tombol_generate_nd_tanpa_ikon_dokumen(self):
        p = self.pengajuan_t1_di_pakln()
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        html = self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode).content.decode()
        self.assertRegex(html, r"Generate ND<span")
        self.assertNotIn("\U0001F4C4 Generate ND", html)

    def test_petunjuk_generate_otomatis_tanpa_ikon_gigi(self):
        p = self.pengajuan_t1_di_pakln()
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        html = self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode).content.decode()
        self.assertIn("Generate otomatis menyusul", html)
        self.assertIn('<p class="cell-muted">Generate otomatis menyusul', html)
        self.assertNotIn("\u2699", html)

    def test_lanjutkan_tanpa_sk_tubel_tanpa_ceklis_pada_tombol_dan_label(self):
        p = self.pengajuan_t2p_di_pakln()
        self.post(self.admin_bko, "bko:proses", {"tutup": "1", "catatan": "Pencalonan beasiswa belum ditetapkan"}, kode=p.kode)
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        html = self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode).content.decode()
        self.assertIn('for="catatan_lanjut">Lanjutkan tanpa SK Tubel \u2014 catatan internal', html)
        self.assertRegex(html, r'name="selesaikan_tanpa_sk_tubel"[^>]*>Lanjutkan tanpa SK Tubel</button>')
        self.assertNotIn(CENTANG + " Lanjutkan tanpa SK Tubel", html)
        # tombol lain pada kotak yang sama tidak diubah (hanya ceklis yang diminta)
        self.assertIn("\u21bb Buka Kembali Pemrosesan BKO", html)
        self.assertIn("\u2715 Hentikan Pengajuan", html)

    def test_ringkasan_perubahan_log_tanpa_panah(self):
        from .views_pakln import _ringkas_perubahan

        hasil = _ringkas_perubahan({"email": ("a@pu.go.id", "b@pu.go.id"), "no_hp": ("", "6281200000000")})
        self.assertEqual(hasil, "email: dari a@pu.go.id menjadi b@pu.go.id; no_hp: dari \u2014 menjadi 6281200000000")
        self.assertNotIn("\u2192", hasil)
