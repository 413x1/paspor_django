import io
from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import PegawaiProfile, User
from pengajuan.forms import PengajuanForm
from pengajuan.models import Pengajuan

from .kalender import hitung_hari_kalender, hitung_hari_kerja, rincian_hari
from .models import HariLibur, KategoriPerjalanan, Negara, SumberPembiayaan


class KalenderTests(TestCase):
    def setUp(self):
        HariLibur.objects.create(tanggal=date(2026, 8, 17), keterangan="Hari Kemerdekaan RI")  # Senin

    def test_satu_hari_kerja(self):
        self.assertEqual(hitung_hari_kerja(date(2026, 8, 18), date(2026, 8, 18)), 1)

    def test_jumat_rabu_dengan_dan_tanpa_libur(self):
        berangkat, kembali = date(2026, 8, 14), date(2026, 8, 19)
        self.assertEqual(hitung_hari_kalender(berangkat, kembali), 6)
        self.assertEqual(hitung_hari_kerja(berangkat, kembali), 3)
        HariLibur.objects.all().delete()
        self.assertEqual(hitung_hari_kerja(berangkat, kembali), 4)

    def test_hanya_akhir_pekan(self):
        self.assertEqual(hitung_hari_kerja(date(2026, 8, 15), date(2026, 8, 16)), 0)

    def test_libur_di_akhir_pekan_tidak_dikurangi_dua_kali(self):
        HariLibur.objects.create(tanggal=date(2026, 8, 16), keterangan="Libur di hari Minggu")
        self.assertEqual(hitung_hari_kerja(date(2026, 8, 14), date(2026, 8, 19)), 3)

    def test_libur_nonaktif_tidak_dihitung(self):
        HariLibur.objects.update(is_active=False)
        self.assertEqual(hitung_hari_kerja(date(2026, 8, 14), date(2026, 8, 19)), 4)

    def test_lintas_tahun(self):
        HariLibur.objects.create(tanggal=date(2027, 1, 1), keterangan="Tahun Baru Masehi")
        self.assertEqual(hitung_hari_kerja(date(2026, 12, 29), date(2027, 1, 3)), 3)

    def test_rentang_tidak_valid(self):
        self.assertIsNone(hitung_hari_kerja(date(2026, 8, 19), date(2026, 8, 14)))
        self.assertIsNone(hitung_hari_kerja(None, date(2026, 8, 14)))
        self.assertIsNone(hitung_hari_kalender(date(2026, 8, 19), date(2026, 8, 14)))

    def test_rincian_dan_tahun_belum_diatur(self):
        r = rincian_hari(date(2026, 12, 29), date(2027, 1, 3))
        self.assertEqual(r["hari_kalender"], 6)
        self.assertEqual(r["akhir_pekan"], 2)
        self.assertEqual(r["hari_kerja"], 4)
        self.assertEqual(r["tahun_belum_diatur"], [2027])

        r = rincian_hari(date(2026, 8, 14), date(2026, 8, 19))
        self.assertEqual(r["libur"], [{"tanggal": "2026-08-17", "keterangan": "Hari Kemerdekaan RI"}])
        self.assertEqual(r["tahun_belum_diatur"], [])


class _DataMixin:
    def buat_pegawai(self, sisa_cuti=12):
        user = User.objects.create_user("pegawai1", password="x", role="pegawai")
        PegawaiProfile.objects.create(
            user=user, nip="1990", nama="Pegawai Satu", jabatan="Staf",
            pangkat_golongan="III-a", unit_kerja="Biro", sisa_cuti_tahun_berjalan=sisa_cuti,
        )
        return user

    def data_form(self, **override):
        kategori = KategoriPerjalanan.objects.create(nama_kategori="Kategori Uji")
        negara = Negara.objects.create(nama_negara="Negara Uji")
        sumber = SumberPembiayaan.objects.create(nama="Sumber Uji")
        data = {
            "kategori": kategori.pk,
            "maksud": "Umrah",
            "tujuan_negara": [negara.pk],
            "sumber_pembiayaan": sumber.pk,
            "tgl_berangkat": "2026-08-14",
            "tgl_kembali": "2026-08-19",
            "jumlah_hari_kerja": "99",  # nilai palsu dari klien — harus diabaikan
        }
        data.update(override)
        return data


class PengajuanFormHariKerjaTests(_DataMixin, TestCase):
    def setUp(self):
        HariLibur.objects.create(tanggal=date(2026, 8, 17), keterangan="Hari Kemerdekaan RI")

    def test_hari_kerja_dihitung_server(self):
        user = self.buat_pegawai()
        form = PengajuanForm(self.data_form(), profile=user.profile)
        self.assertTrue(form.is_valid(), form.errors)
        pengajuan = form.save(commit=False)
        pengajuan.pegawai = user
        pengajuan.save()
        self.assertEqual(pengajuan.jumlah_hari_kerja, 3)

    def test_melebihi_sisa_cuti(self):
        user = self.buat_pegawai(sisa_cuti=2)
        form = PengajuanForm(self.data_form(), profile=user.profile)
        self.assertFalse(form.is_valid())
        self.assertIn("melebihi sisa cuti", str(form.non_field_errors()))

    def test_snapshot_tidak_berubah_setelah_kalender_diubah(self):
        user = self.buat_pegawai()
        pengajuan = Pengajuan.objects.create(
            pegawai=user, tgl_berangkat=date(2026, 8, 14), tgl_kembali=date(2026, 8, 19),
            jumlah_hari_kerja=3, status=Pengajuan.Status.PROSES,
        )
        HariLibur.objects.all().delete()
        pengajuan.refresh_from_db()
        self.assertEqual(pengajuan.jumlah_hari_kerja, 3)


class HitungHariEndpointTests(_DataMixin, TestCase):
    def test_json(self):
        user = self.buat_pegawai()
        self.client.force_login(user)
        resp = self.client.get(reverse("pegawai:hitung_hari"), {"berangkat": "2026-08-14", "kembali": "2026-08-19"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["hari_kerja"], 4)

    def test_input_tidak_valid(self):
        self.client.force_login(self.buat_pegawai())
        url = reverse("pegawai:hitung_hari")
        self.assertEqual(self.client.get(url, {"berangkat": "x", "kembali": "2026-08-19"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"berangkat": "2026-08-19", "kembali": "2026-08-14"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"berangkat": "2026-01-01", "kembali": "2028-01-01"}).status_code, 400)

    def test_formulir_tampil_dengan_kolom_otomatis(self):
        self.client.force_login(self.buat_pegawai())
        resp = self.client.get(reverse("pegawai:formulir_pengajuan"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="hari_kerja"')
        self.assertContains(resp, reverse("pegawai:hitung_hari"))

    def test_harus_login(self):
        resp = self.client.get(reverse("pegawai:hitung_hari"))
        self.assertEqual(resp.status_code, 302)


class SettingKalenderTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("pakln", password="x", role="admin_pakln")

    def test_tambah_rentang_lewati_akhir_pekan_dan_duplikat(self):
        HariLibur.objects.create(tanggal=date(2026, 8, 18), keterangan="Sudah ada")
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("pakln:kelola_kalender"), {
            "tanggal": "2026-08-14", "tanggal_selesai": "2026-08-19",
            "keterangan": "Cuti bersama", "jenis": "cuti_bersama", "lewati_akhir_pekan": "on",
        })
        self.assertEqual(resp.status_code, 302)
        tanggal = set(HariLibur.objects.values_list("tanggal", flat=True))
        self.assertEqual(tanggal, {date(2026, 8, d) for d in (14, 17, 18, 19)})
        self.assertEqual(HariLibur.objects.get(tanggal=date(2026, 8, 18)).keterangan, "Sudah ada")

    def test_toggle_dan_hapus(self):
        libur = HariLibur.objects.create(tanggal=date(2026, 8, 17), keterangan="HUT RI")
        self.client.force_login(self.admin)
        self.client.post(reverse("pakln:toggle_hari_libur", args=[libur.pk]))
        libur.refresh_from_db()
        self.assertFalse(libur.is_active)
        self.client.post(reverse("pakln:hapus_hari_libur", args=[libur.pk]))
        self.assertFalse(HariLibur.objects.exists())

    def test_halaman_dan_data(self):
        HariLibur.objects.create(tanggal=date(2026, 8, 17), keterangan="HUT RI")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("pakln:kelola_kalender")).status_code, 200)
        resp = self.client.get(reverse("pakln:kalender_data"), {"tahun": 2026})
        self.assertEqual(resp.json()["recordsTotal"], 1)

    def test_non_admin_pakln_ditolak(self):
        pegawai = User.objects.create_user("peg", password="x", role="pegawai")
        self.client.force_login(pegawai)
        self.assertEqual(self.client.get(reverse("pakln:kelola_kalender")).status_code, 403)


class SeedHariLiburTests(TestCase):
    def test_seed_bawaan_idempoten(self):
        from django.core.management import call_command

        call_command("seed_hari_libur", stdout=io.StringIO())
        self.assertEqual(HariLibur.objects.filter(tanggal__year=2026).count(), 25)
        self.assertEqual(HariLibur.objects.filter(tanggal__year=2027).count(), 26)
        self.assertEqual(
            HariLibur.objects.filter(tanggal__year=2026, jenis=HariLibur.Jenis.CUTI_BERSAMA).count(), 8,
        )
        call_command("seed_hari_libur", stdout=io.StringIO())
        self.assertEqual(HariLibur.objects.count(), 51)
        # 16–27 Maret 2026: Nyepi & Idulfitri beserta cuti bersamanya.
        self.assertEqual(hitung_hari_kerja(date(2026, 3, 16), date(2026, 3, 27)), 5)


class PotongCutiTests(_DataMixin, TestCase):
    def test_selesaikan_memotong_hari_kerja(self):
        from pengajuan.models import DokumenPakln

        pegawai = self.buat_pegawai(sisa_cuti=12)
        pengajuan = Pengajuan.objects.create(
            pegawai=pegawai, tgl_berangkat=date(2026, 8, 14), tgl_kembali=date(2026, 8, 19),
            jumlah_hari_kerja=3, status=Pengajuan.Status.PROSES_PAKLN, preview_pakln_agree=True,
        )
        DokumenPakln.objects.create(
            pengajuan=pengajuan, jenis=DokumenPakln.Jenis.ILN_SEKJEN, file="iln.pdf",
        )
        admin = User.objects.create_user("pakln", password="x", role="admin_pakln")
        self.client.force_login(admin)
        self.client.post(
            reverse("pakln:upload_dokumen", args=[pengajuan.kode]), {"selesaikan": "1", "agree": "on"},
        )
        pengajuan.refresh_from_db()
        pegawai.profile.refresh_from_db()
        self.assertEqual(pengajuan.status, Pengajuan.Status.SELESAI)
        # 6 hari kalender, tetapi yang terpotong hanya 3 hari kerja.
        self.assertEqual(pegawai.profile.sisa_cuti_tahun_berjalan, 9)


def _xlsx(rows):
    from openpyxl import Workbook

    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ImporKalenderTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("pakln", password="x", role="admin_pakln")
        self.client.force_login(self.admin)
        self.url = reverse("pakln:impor_kalender")

    def unggah(self, konten, nama="libur.xlsx", **data):
        from django.core.files.uploadedfile import SimpleUploadedFile

        data["berkas"] = SimpleUploadedFile(nama, konten)
        return self.client.post(self.url, data, follow=True)

    def test_impor_excel_valid(self):
        HariLibur.objects.create(tanggal=date(2026, 8, 17), keterangan="Lama")
        resp = self.unggah(_xlsx([
            ["Tanggal", "Keterangan", "Jenis"],
            [date(2026, 8, 17), "Proklamasi Kemerdekaan", "Libur Nasional"],
            ["24-12-2026", "Cuti Bersama Natal", "Cuti Bersama"],
            ["2026-12-25", "Natal", ""],
            [None, None, None],
        ]))
        self.assertContains(resp, "2 ditambahkan, 0 diperbarui, 1 dilewati")
        self.assertEqual(HariLibur.objects.count(), 3)
        self.assertEqual(HariLibur.objects.get(tanggal=date(2026, 12, 24)).jenis, HariLibur.Jenis.CUTI_BERSAMA)
        self.assertEqual(HariLibur.objects.get(tanggal=date(2026, 12, 25)).jenis, HariLibur.Jenis.LIBUR_NASIONAL)
        self.assertEqual(HariLibur.objects.get(tanggal=date(2026, 12, 25)).dibuat_oleh, self.admin)
        # Tanpa "timpa", data lama tidak diubah.
        self.assertEqual(HariLibur.objects.get(tanggal=date(2026, 8, 17)).keterangan, "Lama")

    def test_timpa(self):
        HariLibur.objects.create(tanggal=date(2026, 8, 17), keterangan="Lama")
        self.unggah(_xlsx([
            ["tanggal", "keterangan", "jenis"],
            [date(2026, 8, 17), "Proklamasi Kemerdekaan", "Libur Nasional"],
        ]), timpa="on")
        self.assertEqual(HariLibur.objects.get(tanggal=date(2026, 8, 17)).keterangan, "Proklamasi Kemerdekaan")

    def test_ada_baris_salah_tidak_ada_yang_disimpan(self):
        resp = self.unggah(_xlsx([
            ["tanggal", "keterangan", "jenis"],
            [date(2026, 8, 17), "Proklamasi Kemerdekaan", "Libur Nasional"],
            ["31-02-2026", "Tanggal salah", "Libur Nasional"],
            [date(2026, 8, 17), "Ganda", "Libur Nasional"],
            [date(2026, 12, 25), "", "Hari Kejepit"],
        ]))
        self.assertFalse(HariLibur.objects.exists())
        self.assertContains(resp, "baris 3")
        self.assertContains(resp, "ganda")
        self.assertContains(resp, "keterangan kosong")
        self.assertContains(resp, "tidak dikenal")

    def test_kolom_hilang_dan_berkas_rusak(self):
        resp = self.unggah(_xlsx([["tanggal", "nama"], [date(2026, 8, 17), "x"]]))
        self.assertContains(resp, "kolom keterangan, jenis tidak ditemukan")
        resp = self.unggah(b"bukan excel")
        self.assertContains(resp, "bukan Excel")
        resp = self.unggah(b"x", nama="libur.pdf")
        self.assertFalse(HariLibur.objects.exists())

    def test_impor_csv(self):
        self.unggah(b"tanggal,keterangan,jenis\n2026-08-17,Proklamasi,libur_nasional\n", nama="libur.csv")
        self.assertTrue(HariLibur.objects.filter(tanggal=date(2026, 8, 17)).exists())

    def test_template_bisa_diimpor_ulang(self):
        resp = self.client.get(reverse("pakln:template_kalender"))
        self.assertEqual(resp.status_code, 200)
        self.unggah(resp.content)
        self.assertEqual(HariLibur.objects.count(), 2)

    def test_non_admin_ditolak(self):
        self.client.force_login(User.objects.create_user("peg", password="x", role="pegawai"))
        self.assertEqual(self.client.get(reverse("pakln:template_kalender")).status_code, 403)
