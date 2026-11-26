"""Admin BPSDM: tanpa tanda panah dan ikon dekoratif pada Dasbor, Pratinjau, dan Administrasi BPSDM (perbaikan UI).

Dasbor: tombol TL. Pratinjau: Lanjut/Lanjutkan ke Administrasi BPSDM, Kembalikan ke Admin Unor (judul dan tombol), dan
Kembali ke Dasbor. Administrasi: Teruskan ke Admin Biro PAKLN, Kembali ke Pratinjau, dan ikon dokumen pada petunjuk format.
Templat dokumen bersama (`_dokumen_tahap.html`) hanya membuang ikon bila halamannya meminta (`tanpa_ikon`)."""

from django.test import TestCase

from .tests_pdln import _Basis

PANAH = ("→", "←")
IKON_KEMBALI = "↩"
IKON_DOKUMEN = "\U0001F4C4"


class BpsdmTanpaIkonTests(_Basis, TestCase):
    def pengajuan_di_bpsdm(self):
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.kirim(p)
        self.unor_teruskan(p)
        return p

    def test_dasbor_tombol_tl_tanpa_panah(self):
        self.pengajuan_di_bpsdm()
        isi = str(self.get(self.admin_bpsdm, "bpsdm:dashboard_data").json()["data"])
        self.assertIn('class="button is-warning is-small">TL</a>', isi)
        self.assertNotIn("TL →", isi)

    def test_pratinjau_sebelum_menyetujui_tanpa_panah_dan_ikon_kembali(self):
        p = self.pengajuan_di_bpsdm()
        html = self.get(self.admin_bpsdm, "bpsdm:preview", kode=p.kode).content.decode()
        self.assertIn('class="button is-primary is-fullwidth">Lanjutkan ke Administrasi BPSDM</button>', html)
        self.assertIn('<div class="section-title is-small">Kembalikan ke Admin Unor</div>', html)
        self.assertIn('class="button is-danger is-fullwidth">Kembalikan ke Admin Unor</button>', html)
        self.assertIn('class="button is-fullwidth">Kembali ke Dasbor</a>', html)
        self.assertNotIn(IKON_KEMBALI, html)
        for panah in PANAH:
            self.assertNotIn(panah + " Kembali", html)
            self.assertNotIn("BPSDM " + panah, html)

    def test_pratinjau_sesudah_menyetujui_tautan_lanjut_tanpa_panah(self):
        p = self.pengajuan_di_bpsdm()
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        html = self.get(self.admin_bpsdm, "bpsdm:preview", kode=p.kode).content.decode()
        self.assertRegex(html, r">Lanjut ke Administrasi BPSDM</a>")
        self.assertNotIn("Lanjut ke Administrasi BPSDM →", html)

    def test_administrasi_tanpa_panah_dan_tanpa_ikon_dokumen(self):
        p = self.pengajuan_di_bpsdm()
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1", "confirm": "on"}, kode=p.kode)
        resp = self.get(self.admin_bpsdm, "bpsdm:upload_dokumen", kode=p.kode)
        html = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        self.assertRegex(html, r"Teruskan ke Admin Biro PAKLN\s*</button>")
        self.assertNotRegex(html, r"Teruskan ke Admin Biro PAKLN\s*→")
        self.assertIn('class="button">Kembali ke Pratinjau</a>', html)
        self.assertNotIn("← Kembali ke Pratinjau", html)
        self.assertIn("Nota Dinas Sekretaris BPSDM", html)
        self.assertIn("Format tersedia pada", html)                          # petunjuk tetap ada
        self.assertNotIn(IKON_DOKUMEN + " Format tersedia", html)           # ikon dokumen dibuang
