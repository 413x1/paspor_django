"""Revisi Pegawai Non-Dinas Poin 3: hasil hitung hari kerja kurang dari 1 hari (0 hari kerja) tidak boleh diproses.

Seluruh rentang tanggal jatuh pada Sabtu/Minggu atau tanggal merah: tidak ada hari kerja yang terpakai, jadi izin
luar negeri tidak perlu diajukan. Aturan dijaga di server (`PengajuanForm.clean`) dan ditampilkan sebagai alert
di browser (templates/pegawai/formulir.html)."""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from paspor.kalender import hitung_hari_kerja
from paspor.models import HariLibur, KategoriPerjalanan, SumberPembiayaan

from .forms import PengajuanForm
from .models import Pengajuan
from .tests_pdln import _Basis

PESAN = PengajuanForm.PESAN_NOL_HARI_KERJA
SABTU, MINGGU = date(2026, 12, 26), date(2026, 12, 27)
SENIN = date(2026, 12, 28)
RABU_LIBUR = date(2027, 2, 3)
JUMAT_LIBUR, SABTU2, MINGGU2, SENIN2 = date(2027, 2, 5), date(2027, 2, 6), date(2027, 2, 7), date(2027, 2, 8)


class HariKerjaNolBase(_Basis, TestCase):
    def setUp(self):
        super().setUp()
        self.kategori = KategoriPerjalanan.objects.filter(jenis_perjalanan="Non-Dinas").first()
        self.sumber = SumberPembiayaan.objects.filter(tipe_perjalanan="Non-Dinas").first()
        self.assertIsNotNone(self.kategori)
        self.assertIsNotNone(self.sumber)

    def data(self, berangkat, kembali, **ubah):
        data = {
            "kategori": self.kategori.pk, "maksud": "Ibadah umrah", "tujuan_negara": [self.jepang.pk],
            "sumber_pembiayaan": self.sumber.pk, "tgl_berangkat": berangkat.isoformat(), "tgl_kembali": kembali.isoformat(),
        }
        data.update(ubah)
        return data

    def kirim_form(self, berangkat, kembali):
        self.login(self.pegawai)
        return self.client.post(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas", self.data(berangkat, kembali))

    def assertDitolak(self, resp):
        self.assertEqual(resp.status_code, 200)               # form ditampilkan ulang, tidak berpindah halaman
        self.assertIn(PESAN, [str(e) for e in resp.context["form"].non_field_errors()])
        self.assertContains(resp, PESAN)
        self.assertFalse(Pengajuan.objects.filter(pegawai=self.pegawai).exists())


class ValidasiServerTests(HariKerjaNolBase):
    def test_prasyarat_tanggal_uji(self):
        self.assertEqual((SABTU.weekday(), MINGGU.weekday(), SENIN.weekday()), (5, 6, 0))
        self.assertEqual(hitung_hari_kerja(SABTU, MINGGU), 0)
        self.assertEqual(hitung_hari_kerja(SENIN, SENIN), 1)

    def test_pesan_sesuai_tiket_dan_tanpa_emoji(self):
        self.assertEqual(
            PESAN, "Hasil perhitungan hari kerja adalah 0 hari. Untuk 0 hari kerja tidak perlu mengajukan izin luar negeri.",
        )
        self.assertIsNone(re.search("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]", PESAN))

    def test_sabtu_dan_minggu_saja_ditolak(self):
        self.assertDitolak(self.kirim_form(SABTU, MINGGU))

    def test_satu_hari_sabtu_ditolak(self):
        self.assertDitolak(self.kirim_form(SABTU, SABTU))

    def test_satu_hari_minggu_ditolak(self):
        self.assertDitolak(self.kirim_form(MINGGU, MINGGU))

    def test_tanggal_merah_hari_kerja_ditolak(self):
        HariLibur.objects.create(tanggal=RABU_LIBUR, keterangan="Libur Uji")
        self.assertEqual(RABU_LIBUR.weekday(), 2)
        self.assertDitolak(self.kirim_form(RABU_LIBUR, RABU_LIBUR))

    def test_libur_nonaktif_tidak_dihitung_sehingga_diterima(self):
        HariLibur.objects.create(tanggal=RABU_LIBUR, keterangan="Libur Uji", is_active=False)
        resp = self.kirim_form(RABU_LIBUR, RABU_LIBUR)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Pengajuan.objects.get(pegawai=self.pegawai).jumlah_hari_kerja, 1)

    def test_jumat_libur_ditambah_akhir_pekan_ditolak_tapi_dengan_senin_diterima(self):
        HariLibur.objects.create(tanggal=JUMAT_LIBUR, keterangan="Libur Uji")
        self.assertEqual((JUMAT_LIBUR.weekday(), SABTU2.weekday(), MINGGU2.weekday(), SENIN2.weekday()), (4, 5, 6, 0))
        self.assertDitolak(self.kirim_form(JUMAT_LIBUR, MINGGU2))
        resp = self.kirim_form(JUMAT_LIBUR, SENIN2)           # Senin menambah 1 hari kerja
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Pengajuan.objects.get(pegawai=self.pegawai).jumlah_hari_kerja, 1)

    def test_satu_hari_kerja_diterima(self):
        resp = self.kirim_form(SENIN, SENIN)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Pengajuan.objects.get(pegawai=self.pegawai).jumlah_hari_kerja, 1)

    def test_hari_kerja_banyak_tetap_diterima_dan_aturan_sisa_cuti_tidak_berubah(self):
        self.assertEqual(self.kirim_form(SENIN, date(2026, 12, 30)).status_code, 302)       # 3 hari kerja
        Pengajuan.objects.all().delete()
        self.pegawai.profile.sisa_cuti_tahun_berjalan = 2
        self.pegawai.profile.save()
        self.login(self.pegawai)
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas", self.data(SENIN, date(2026, 12, 30)))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("melebihi sisa cuti", str(resp.context["form"].non_field_errors()))

    def test_nilai_hari_kerja_dari_klien_tidak_dipercaya(self):
        """Browser bisa dimanipulasi: jumlah hari kerja palsu tidak boleh melewati validasi."""
        self.login(self.pegawai)
        resp = self.client.post(
            reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas",
            self.data(SABTU, MINGGU, jumlah_hari_kerja="5"),
        )
        self.assertDitolak(resp)

    def test_ubah_draft_menjadi_nol_hari_kerja_ditolak_dan_data_lama_utuh(self):
        self.assertEqual(self.kirim_form(SENIN, date(2026, 12, 30)).status_code, 302)
        p = Pengajuan.objects.get(pegawai=self.pegawai)
        self.login(self.pegawai)
        resp = self.client.post(reverse("pegawai:formulir_pengajuan"), self.data(SABTU, MINGGU))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(PESAN, [str(e) for e in resp.context["form"].non_field_errors()])
        p.refresh_from_db()
        self.assertEqual((p.tgl_berangkat, p.tgl_kembali, p.jumlah_hari_kerja), (SENIN, date(2026, 12, 30), 3))

    def test_form_langsung_tanpa_view(self):
        form = PengajuanForm(self.data(SABTU, MINGGU), profile=self.pegawai.profile)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors(), [PESAN])
        self.assertTrue(PengajuanForm(self.data(SENIN, SENIN), profile=self.pegawai.profile).is_valid())


class TampilanAlertTests(HariKerjaNolBase):
    def halaman(self):
        self.login(self.pegawai)
        return self.client.get(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas").content.decode()

    def test_komponen_alert_pesan_inline_dan_tombol_terkunci_tersedia(self):
        html = self.halaman()
        self.assertIn('id="peringatan_nol_hari"', html)
        self.assertIn('id="btn-simpan-lanjut"', html)
        self.assertIn("pasporAlert({ type: 'warning', title: 'Tidak perlu mengajukan izin'", html)
        self.assertIn(f"var PESAN_NOL = '{PESAN}';", html)             # pesan JS = pesan server
        self.assertIn("$simpan.prop('disabled', nol)", html)
        self.assertIn("if (nolHari) { e.preventDefault();", html)       # cadangan saat disubmit lewat papan ketik

    def test_alert_dipicu_dari_perhitungan_server_bukan_tebakan_klien(self):
        html = self.halaman()
        self.assertIn("aturNolHari(r.hari_kerja < 1);", html)
        self.assertIn("hitung(true);", html)                            # muat awal: senyap, tanpa alert
        self.assertIn("hitung(false);", html)

    def test_pesan_server_tidak_ganda_saat_form_dikirim_ulang(self):
        resp = self.kirim_form(SABTU, MINGGU)
        html = resp.content.decode()
        self.assertIn("galatServerNol = true;", html)
        self.assertEqual(html.count(f"<li>{PESAN}</li>"), 1)

    def test_formulir_pdln_tidak_terpengaruh(self):
        self.login(self.pegawai)
        html = self.client.get(reverse("pegawai:formulir_pengajuan") + "?jenis=pdln&tipe=T1").content.decode()
        self.assertNotIn("peringatan_nol_hari", html)
        self.assertNotIn(PESAN, html)
