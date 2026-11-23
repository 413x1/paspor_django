"""Format PDF Nota Dinas Karo dan Kabag (WeasyPrint): kop satu baris, tanpa cetak tebal/garis bawah pada isian.

Memeriksa tata letak yang dihitung WeasyPrint (jumlah baris, tebal huruf, garis bawah, jarak), bukan sekadar teks
template. Font Arial/Liberation Sans (metrik identik) dipakai di mesin pengembang dan image Docker."""

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from weasyprint import HTML
from weasyprint.formatting_structure import boxes

from .views_pakln import _logo_data_uri

KARO, KABAG = "pakln/pdf_template_nd_karo.html", "pakln/pdf_template_nd_kabag.html"
KONTEKS = {
    "nama": "Andra Wibisono, S.T., M.Sc.", "negara_tujuan": "Jepang", "nip": "199001012015031001",
    "jabatan": "Analis Kebijakan Ahli Muda", "unit_kerja": "Sekretariat Jenderal",
    "maksud_perjalanan": "Mengunjungi keluarga dan berwisata", "sumber_pembiayaan": "Biaya Sendiri",
    "rentang_tanggal": "10 Desember 2026 s.d. 14 Desember 2026", "jumlah_hari_kerja": 3, "jumlah_hari_kalender": 5,
    "jabatan_baris1": "Kepala Biro Perencanaan Anggaran", "jabatan_baris2": "dan Kerja Sama Luar Negeri",
    "nama_pejabat": "Nama Pejabat, S.T., M.T.", "tanggal_nota_dinas": "23 November 2026",
    "label_paraf_kabag": "Kabag KLN", "tampilkan_paraf": True, "logo_data_uri": _logo_data_uri(),   # logo asli: lebar kolom teks sama dengan produksi
}
ALAMAT = "Jalan Pattimura Nomor 20, Kebayoran Baru, Jakarta Selatan 12110, Telepon (021)7392681, Surel: bpakln@pu.go.id"


def render(template, **ubah):
    html = render_to_string(template, {**KONTEKS, **ubah})
    return html, HTML(string=html).render()


def cari(kotak, kelas, hasil=None):
    """Kotak blok/sel (bukan baris atau teks) yang elemennya berkelas `kelas`, di seluruh pohon tata letak."""
    hasil = [] if hasil is None else hasil
    el = getattr(kotak, "element", None)
    if el is not None and kelas in (el.get("class") or "").split() and isinstance(kotak, (boxes.BlockBox, boxes.TableBox)):
        hasil.append(kotak)
    for anak in getattr(kotak, "children", None) or []:
        cari(anak, kelas, hasil)
    return hasil


def semua_sel(kotak, hasil=None):
    hasil = [] if hasil is None else hasil
    if isinstance(kotak, boxes.TableCellBox):
        hasil.append(kotak)
    for anak in getattr(kotak, "children", None) or []:
        semua_sel(anak, hasil)
    return hasil


class KopSuratTests(SimpleTestCase):
    def test_alamat_dan_surel_satu_baris_di_kedua_template(self):
        for template in (KARO, KABAG):
            with self.subTest(template=template):
                html, dok = render(template)
                self.assertIn(ALAMAT, html)
                alamat = cari(dok.pages[0]._page_box, "nd-addr")
                self.assertEqual(len(alamat), 1)
                garis = [c for c in alamat[0].children if isinstance(c, boxes.LineBox)]
                self.assertEqual(len(garis), 1, "alamat kop pecah menjadi lebih dari satu baris")

    def test_alamat_di_kolom_teks_sebelah_logo_dengan_jarak_ke_garis(self):
        """Alamat rata tengah di bawah nama instansi (di dalam kolom teks), bukan melebar sampai bawah logo."""
        for template in (KARO, KABAG):
            with self.subTest(template=template):
                _, dok = render(template)
                halaman = dok.pages[0]._page_box
                kolom = cari(halaman, "nd-head-text")[0]
                alamat = cari(kolom, "nd-addr")                       # berada DI DALAM kolom teks
                self.assertEqual(len(alamat), 1)
                self.assertLessEqual(alamat[0].width, kolom.width + 0.5)
                self.assertGreaterEqual(alamat[0].style["margin_bottom"].value, 6)      # jarak ke garis di bawahnya

    def test_nama_instansi_di_kop_tetap_tebal(self):
        for template in (KARO, KABAG):
            with self.subTest(template=template):
                _, dok = render(template)
                for kelas in ("nd-org1", "nd-org2"):
                    self.assertEqual(cari(dok.pages[0]._page_box, kelas)[0].style["font_weight"], 700)

    def test_tetap_satu_halaman_walau_data_panjang(self):
        panjang = {
            "nama": "Prof. Dr. Ir. Muhammad Abdurrahman Al-Fatih Wirakusumah Nugroho, S.T., M.Sc., Ph.D.",
            "maksud_perjalanan": "Menghadiri undangan konferensi internasional, kunjungan keluarga, dan perjalanan wisata "
                                 "ke beberapa kota di negara tujuan selama masa cuti tahunan",
            "negara_tujuan": "Jepang, Korea Selatan, Singapura, Malaysia",
            "jabatan": "Kepala Subbagian Perencanaan dan Evaluasi Kerja Sama Luar Negeri",
        }
        for template in (KARO, KABAG):
            with self.subTest(template=template):
                self.assertEqual(len(render(template, **panjang)[1].pages), 1)


class JudulDanTandaTanganTests(SimpleTestCase):
    def test_judul_nota_dinas_reguler_tanpa_garis_bawah(self):
        for template in (KARO, KABAG):
            with self.subTest(template=template):
                html, dok = render(template)
                judul = cari(dok.pages[0]._page_box, "nd-title")[0]
                self.assertEqual(judul.style["font_weight"], 400)
                self.assertNotIn("underline", judul.style["text_decoration_line"])
                self.assertIn("NOTA DINAS", html)

    def test_nama_pejabat_reguler_tanpa_garis_bawah_dengan_jarak_48px(self):
        for template in (KARO, KABAG):
            with self.subTest(template=template):
                _, dok = render(template)
                nama = cari(dok.pages[0]._page_box, "nd-sign-name")[0]
                self.assertEqual(nama.style["font_weight"], 400)
                self.assertNotIn("underline", nama.style["text_decoration_line"])
                self.assertEqual(nama.style["margin_top"].value, 48)

    def test_tanpa_tag_tebal_atau_garis_bawah(self):
        for template in (KARO, KABAG):
            with self.subTest(template=template):
                html, _ = render(template)
                for tag in ("<b>", "<strong>", "<u>"):
                    self.assertNotIn(tag, html)
                self.assertNotIn("underline", html.split("</style>")[1])


class IsianNdKaroTests(SimpleTestCase):
    def test_hal_tanggal_daftar_rincian_dan_tabel_pegawai_tidak_tebal(self):
        html, dok = render(KARO)
        self.assertNotIn('class="nd-dyn"', html)               # pembungkus tebal sudah dilepas seluruhnya
        halaman = dok.pages[0]._page_box
        for kelas in ("nd-meta", "nd-list", "nd-pegawai-table"):
            sel = [s for t in cari(halaman, kelas) for s in semua_sel(t)]
            self.assertTrue(sel, kelas)
            tebal = [s for s in sel if s.style["font_weight"] >= 600 and s.element.tag != "th"]
            self.assertEqual(tebal, [], f"sel tebal pada {kelas}")

    def test_nilai_isian_tetap_tampil_di_template(self):
        html, _ = render(KARO)
        for nilai in ("Andra Wibisono, S.T., M.Sc.", "Jepang", "Mengunjungi keluarga dan berwisata", "Sekretariat Jenderal",
                      "Biaya Sendiri", "199001012015031001", "Analis Kebijakan Ahli Muda", "23 November 2026",
                      "10 Desember 2026 s.d. 14 Desember 2026"):
            self.assertIn(nilai, html)

    def test_judul_kolom_tabel_pegawai_tetap_tebal(self):
        _, dok = render(KARO)
        tabel = cari(dok.pages[0]._page_box, "nd-pegawai-table")[0]
        header = [s for s in semua_sel(tabel) if s.element.tag == "th"]
        self.assertEqual(len(header), 4)
        self.assertTrue(all(s.style["font_weight"] == 700 for s in header))


class IsianNdKabagTests(SimpleTestCase):
    def test_hal_dan_tanggal_tidak_tebal(self):
        html, dok = render(KABAG)
        sel = [s for t in cari(dok.pages[0]._page_box, "nd-meta") for s in semua_sel(t)]
        self.assertTrue(sel)
        self.assertEqual([s for s in sel if s.style["font_weight"] >= 600], [])
        meta = html[html.index('<table class="nd-meta">'):html.index("</table>")]
        self.assertNotIn("nd-dyn", meta)

    def test_paragraf_isi_tidak_diubah_nama_dan_negara_tetap_tebal(self):
        """Tidak termasuk revisi: nama dan negara di paragraf isi ND Kabag tetap tebal seperti semula."""
        html, _ = render(KABAG)
        isi = html.split('<div class="nd-body">')[1]
        self.assertEqual(isi.count('class="nd-dyn"'), 2)


@override_settings(STORAGES={**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}})
class UnduhPdfTests(TestCase):
    """Endpoint unduh sungguhan (view -> template -> WeasyPrint): PDF tetap berhasil dibuat dengan template baru."""

    def setUp(self):
        from accounts.models import User

        self.admin = User.objects.create_user("pakln1", password="x", role="admin_pakln", no_hp="6281100000001")
        self.client.force_login(self.admin)
        self.data = {
            "nama": "Andra Wibisono", "negara_tujuan": "Jepang", "nip": "199001012015031001", "jabatan": "Analis",
            "unit_kerja": "Sekretariat Jenderal", "maksud_perjalanan": "Wisata", "sumber_pembiayaan": "Biaya Sendiri",
            "tgl_berangkat": "2026-12-10", "tgl_kembali": "2026-12-14", "jumlah_hari_kerja": "3",
            "jabatan_penandatangan": "Kepala Biro Perencanaan Anggaran dan Kerja Sama Luar Negeri",
            "nama_pejabat": "Nama Pejabat", "tanggal_nd": "2026-11-23", "tampilkan_paraf": "1",
        }

    def test_nd_karo_dan_nd_kabag_menghasilkan_pdf_valid(self):
        for rute in ("pakln:download_nd_karo_pdf", "pakln:download_nd_kabag_pdf"):
            with self.subTest(rute=rute):
                resp = self.client.post(reverse(rute), self.data)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp["Content-Type"], "application/pdf")
                isi = b"".join(resp.streaming_content) if resp.streaming else resp.content
                self.assertTrue(isi.startswith(b"%PDF"))
                self.assertGreater(len(isi), 2000)                    # PDF terisi (halaman dihitung di KopSuratTests)


class PratinjauGenerateNdTests(TestCase):
    """Halaman Generate ND memuat pratinjau HTML dengan CSS sendiri; harus sama dengan hasil PDF-nya."""

    def setUp(self):
        from accounts.models import User

        self.client.force_login(User.objects.create_user("pakln2", password="x", role="admin_pakln", no_hp="6281100000002"))

    def halaman(self, rute):
        return self.client.get(reverse(rute)).content.decode()

    def test_judul_dan_nama_pejabat_reguler_tanpa_garis_bawah_jarak_48px(self):
        for rute in ("pakln:generate_nd_karo", "pakln:generate_nd_kabag"):
            with self.subTest(rute=rute):
                html = self.halaman(rute)
                self.assertIn(".nd-title { text-align: center; font-weight: 400; text-decoration: none;", html)
                self.assertIn(".nd-sign-block .nd-sign-name { margin-top: 48px; font-weight: 400; text-decoration: none; }", html)
                self.assertNotIn("text-decoration: underline", html)

    def test_alamat_kop_satu_baris_di_kolom_teks_dengan_jarak(self):
        for rute in ("pakln:generate_nd_karo", "pakln:generate_nd_kabag"):
            with self.subTest(rute=rute):
                html = self.halaman(rute)
                self.assertEqual(html.count('class="nd-addr"'), 1)
                self.assertIn(".nd-head-text .nd-addr { font-size: 1.6cqw; margin-top: 3px; margin-bottom: 6px;", html)
                self.assertIn("white-space: nowrap", html.split(".nd-addr {")[1].split("}")[0])
                self.assertIn("container-type: inline-size", html)

    def test_nilai_isian_karo_reguler(self):
        html = self.halaman("pakln:generate_nd_karo")
        self.assertIn("  .nd-dyn { font-weight: 400; }", html)
        self.assertNotIn(".nd-dyn { font-weight: 700; }", html)
        self.assertIn(".nd-pegawai-table tbody td { font-weight: 400; }", html)

    def test_nilai_hal_dan_tanggal_kabag_reguler_tetapi_paragraf_isi_tidak_berubah(self):
        html = self.halaman("pakln:generate_nd_kabag")
        self.assertIn(".nd-meta .nd-dyn { font-weight: 400; }", html)
        self.assertIn("  .nd-dyn { font-weight: 700; }", html)              # paragraf isi: tetap tebal seperti PDF
        self.assertIn(".nd-sign-block > div:first-child .nd-dyn { font-weight: 400; }", html)
