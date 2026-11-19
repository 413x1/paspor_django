"""Pelaporan PDLN Admin PAKLN — DataTables server-side (`pakln:pelaporan_data`)."""

from datetime import date, timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import PegawaiProfile, User
from paspor.models import Negara

from . import report
from .models import LaporanPdln, Pengajuan
from .tests_laporan_form import ISI, LaporanFormBase
from .views_pakln import _hitung_pelaporan, _qs_pelaporan
from .views_unor import _konteks_pelaporan

S = LaporanPdln.Status


class PelaporanServerSideBase(LaporanFormBase):
    """`self.p` (dari LaporanFormBase) = PDLN Selesai milik "Pegawai Satu", tanpa laporan."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_pakln)
        self.url_data = reverse("pakln:pelaporan_data")
        self.hari_ini = timezone.localdate()

    def pegawai_baru(self, nama, nip):
        user = User.objects.create_user(f"peg{nip}", password="x", role="pegawai")
        PegawaiProfile.objects.create(
            user=user, nip=nip, nama=nama, jabatan="Staf", pangkat_golongan="III-a",
            unit_kerja="Biro", unit_organisasi=self.unor,
        )
        return user

    def pdln(self, *, pegawai=None, tgl_selesai=date(2026, 9, 20), tgl_kembali=None, negara=(),
             laporan=None, unor=None, jenis="pdln", status=Pengajuan.Status.SELESAI):
        p = Pengajuan.objects.create(
            pegawai=pegawai or self.pegawai, form_saved=True, jenis_perjalanan=jenis,
            tipe_pdln="T1" if jenis == "pdln" else "", status=status, unit_organisasi=unor or self.unor,
            tgl_pengajuan=date(2026, 9, 1), tgl_kembali=tgl_kembali, tgl_selesai=tgl_selesai,
        )
        p.tujuan_negara.set(negara)
        if laporan:
            LaporanPdln.objects.create(
                pengajuan=p, status=laporan, file="laporan.pdf", estimasi_biaya=1000, realisasi_biaya=900, **ISI,
            )
        return p

    def ambil(self, **param):
        return self.client.get(self.url_data, {"draw": 3, "start": 0, "length": 10, **param}).json()

    def kode_baris(self, json):
        return [next(k for k in (p.kode for p in Pengajuan.objects.all()) if f">{k}</a>" in b[2]) for b in json["data"]]


class FormatEndpointTests(PelaporanServerSideBase):
    def test_format_standar_datatables(self):
        json = self.ambil()
        self.assertEqual(set(json), {"draw", "recordsTotal", "recordsFiltered", "data"})
        self.assertEqual(json["draw"], 3)
        self.assertEqual((json["recordsTotal"], json["recordsFiltered"]), (1, 1))
        self.assertEqual(len(json["data"][0]), 8)   # 8 kolom sesuai tabel

    def test_isi_kolom_sama_dengan_tabel_lama(self):
        self.p.tujuan_negara.set([Negara.objects.create(nama_negara="Uji Zentoria")])
        baris = self.ambil()["data"][0]
        self.assertIn("Pegawai Satu", baris[0])
        self.assertIn('<span class="cell-muted">1990</span>', baris[0])
        self.assertEqual(baris[1], self.unor.alias)
        self.assertIn(f'href="{reverse("pakln:preview", args=[self.p.kode])}"', baris[2])
        self.assertIn(self.p.jenis_label, baris[2])
        self.assertEqual(baris[3], "Uji Zentoria")
        self.assertEqual(baris[4], "08 Okt 2026")
        self.assertIn("Belum melapor", baris[5])
        self.assertEqual(baris[6], "—")

    def test_hanya_pdln_berstatus_selesai(self):
        self.pdln(status=Pengajuan.Status.PROSES_PAKLN)
        self.pdln(jenis="nondinas")
        json = self.ambil()
        self.assertEqual(json["recordsTotal"], 1)
        self.assertEqual(self.kode_baris(json), [self.p.kode])

    def test_nilai_html_di_escape(self):
        pegawai = self.pegawai_baru("<script>alert(1)</script>", "7777")
        self.pdln(pegawai=pegawai, tgl_selesai=date(2026, 9, 30))
        baris = self.ambil(**{"search[value]": "7777"})["data"][0]
        self.assertNotIn("<script>", baris[0])
        self.assertIn("&lt;script&gt;", baris[0])


class StatusDanAksiTests(PelaporanServerSideBase):
    def test_terlambat_hanya_untuk_yang_belum_melapor(self):
        lama = self.hari_ini - timedelta(days=report.BATAS_HARI_LAPORAN + 1)
        self.p.delete()
        belum = self.pdln(tgl_kembali=lama, tgl_selesai=date(2026, 9, 3))
        sudah = self.pdln(tgl_kembali=lama, tgl_selesai=date(2026, 9, 2), laporan=S.MENUNGGU)
        baru = self.pdln(tgl_kembali=self.hari_ini, tgl_selesai=date(2026, 9, 1))
        json = self.ambil()
        status = {kode: b[5] for kode, b in zip(self.kode_baris(json), json["data"])}
        self.assertIn("Terlambat", status[belum.kode])
        self.assertNotIn("Terlambat", status[sudah.kode])
        self.assertIn("Menunggu Verifikasi", status[sudah.kode])
        self.assertNotIn("Terlambat", status[baru.kode])

    def test_draft_dihitung_belum_melapor_tanpa_tombol(self):
        self.p.delete()
        self.pdln(laporan=S.DRAFT)
        baris = self.ambil()["data"][0]
        self.assertIn("Belum melapor", baris[5])
        self.assertEqual(baris[6], "—")
        for tidak_ada in ("btn-verifikasi", "btn-revisi", "data-doc-preview", "ringkasan-"):
            self.assertNotIn(tidak_ada, baris[7])

    def test_tombol_verifikasi_dan_ringkasan_hanya_untuk_menunggu(self):
        self.p.delete()
        menunggu = self.pdln(laporan=S.MENUNGGU, tgl_selesai=date(2026, 9, 5))
        disetujui = self.pdln(laporan=S.DISETUJUI, tgl_selesai=date(2026, 9, 4))
        json = self.ambil()
        aksi = {kode: b[7] for kode, b in zip(self.kode_baris(json), json["data"])}
        pk = menunggu.laporan_pdln.pk
        self.assertIn('class="button is-small is-success btn-verifikasi"', aksi[menunggu.kode])
        self.assertIn('class="button is-small is-warning btn-revisi"', aksi[menunggu.kode])
        self.assertIn(f'<div hidden id="ringkasan-{pk}">', aksi[menunggu.kode])
        self.assertIn(ISI["tujuan_kegiatan"], aksi[menunggu.kode])
        self.assertIn("data-doc-preview", aksi[disetujui.kode])        # tetap bisa dilihat
        self.assertNotIn("btn-verifikasi", aksi[disetujui.kode])
        self.assertNotIn("ringkasan-", aksi[disetujui.kode])


    def test_laporan_menunggu_tanpa_berkas_tidak_menggagalkan_tabel(self):
        """Data janggal (menunggu tanpa berkas) tidak boleh membuat endpoint error 500."""
        self.p.delete()
        p = self.pdln(laporan=S.MENUNGGU)
        LaporanPdln.objects.filter(pengajuan=p).update(file="")
        resp = self.client.get(self.url_data, {"draw": 1, "start": 0, "length": 10})
        self.assertEqual(resp.status_code, 200)
        aksi = resp.json()["data"][0][7]
        self.assertIn("btn-verifikasi", aksi)
        self.assertIn("Tidak ada berkas", aksi)
        self.assertNotIn("data-doc-preview", aksi)

class PencarianTests(PelaporanServerSideBase):
    def setUp(self):
        super().setUp()
        # Nama negara buatan: data negara asli sudah terisi lewat migrasi data.
        self.jepang = Negara.objects.create(nama_negara="Uji Zentoria")
        self.japan_mirip = Negara.objects.create(nama_negara="Uji Zentoria Selatan")
        self.budi = self.pegawai_baru("Budi Santoso", "198001012005011001")
        self.p_budi = self.pdln(pegawai=self.budi, unor=self.unor_lain, negara=[self.jepang, self.japan_mirip])

    def cari(self, nilai):
        json = self.ambil(**{"search[value]": nilai})
        return json, self.kode_baris(json)

    def test_cari_nama_nip_kode_unor_negara(self):
        for nilai in ("budi", "198001012005", self.p_budi.kode, self.unor_lain.alias, "zentoria"):
            with self.subTest(cari=nilai):
                json, kode = self.cari(nilai)
                self.assertEqual(kode, [self.p_budi.kode])
                self.assertEqual(json["recordsTotal"], 2)        # total tidak ikut pencarian
                self.assertEqual(json["recordsFiltered"], 1)

    def test_negara_banyak_tidak_menggandakan_baris(self):
        json, kode = self.cari("Zentoria")                       # cocok dua negara pada satu pengajuan
        self.assertEqual(kode, [self.p_budi.kode])
        self.assertEqual(json["recordsFiltered"], 1)
        self.assertEqual(json["data"][0][3], "Uji Zentoria, Uji Zentoria Selatan")

    def test_tidak_ada_yang_cocok(self):
        json, kode = self.cari("tidak-ada-xyz")
        self.assertEqual((kode, json["recordsFiltered"]), ([], 0))


class UrutanDanPaginasiTests(PelaporanServerSideBase):
    def setUp(self):
        super().setUp()
        self.p.delete()
        self.a = self.pdln(pegawai=self.pegawai_baru("Andi", "11"), tgl_selesai=date(2026, 9, 10), tgl_kembali=date(2026, 8, 1))
        self.b = self.pdln(pegawai=self.pegawai_baru("Citra", "22"), tgl_selesai=date(2026, 9, 30), tgl_kembali=date(2026, 8, 20))
        self.c = self.pdln(pegawai=self.pegawai_baru("Bayu", "33"), tgl_selesai=date(2026, 9, 20), tgl_kembali=date(2026, 8, 10))

    def urut(self, kolom, arah):
        return self.kode_baris(self.ambil(**{"order[0][column]": kolom, "order[0][dir]": arah}))

    def test_default_tanpa_parameter_urut_tgl_selesai_terbaru(self):
        self.assertEqual(self.kode_baris(self.ambil()), [self.b.kode, self.c.kode, self.a.kode])

    def test_urut_tgl_kembali(self):
        self.assertEqual(self.urut(4, "desc"), [self.b.kode, self.c.kode, self.a.kode])
        self.assertEqual(self.urut(4, "asc"), [self.a.kode, self.c.kode, self.b.kode])

    def test_urut_nama_pegawai(self):
        self.assertEqual(self.urut(0, "asc"), [self.a.kode, self.c.kode, self.b.kode])   # Andi, Bayu, Citra

    def test_kolom_tak_terurutkan_kembali_ke_default(self):
        for kolom in (3, 5, 7):
            with self.subTest(kolom=kolom):
                self.assertEqual(self.urut(kolom, "asc"), [self.b.kode, self.c.kode, self.a.kode])

    def test_paginasi(self):
        json = self.ambil(start=1, length=1)
        self.assertEqual((json["recordsTotal"], json["recordsFiltered"]), (3, 3))
        self.assertEqual(self.kode_baris(json), [self.c.kode])

    def test_jumlah_query_tidak_bertambah_per_baris(self):
        negara = Negara.objects.create(nama_negara="Uji Korvania")
        for i in range(6):
            self.pdln(pegawai=self.pegawai_baru(f"Peg {i}", f"9{i}"), negara=[negara], laporan=S.MENUNGGU)
        self.ambil()   # request pertama setelah login menyimpan sesi (3 query) — jangan ikut dihitung
        with CaptureQueriesContext(connection) as dua:
            self.ambil(length=2)
        with CaptureQueriesContext(connection) as delapan:
            self.ambil(length=8)
        self.assertEqual(len(dua), len(delapan))


class KartuRingkasanTests(PelaporanServerSideBase):
    def setUp(self):
        super().setUp()
        lama = self.hari_ini - timedelta(days=report.BATAS_HARI_LAPORAN + 1)
        Pengajuan.objects.filter(pk=self.p.pk).update(tgl_kembali=lama)   # self.p: belum + terlambat
        self.pdln(tgl_kembali=lama)                          # belum + terlambat
        self.pdln(tgl_kembali=lama, laporan=S.DRAFT)         # draft = belum + terlambat
        self.pdln(tgl_kembali=self.hari_ini)                 # belum, belum terlambat
        self.pdln(tgl_kembali=lama, laporan=S.MENUNGGU)
        self.pdln(laporan=S.DIKEMBALIKAN)
        self.pdln(laporan=S.DISETUJUI)
        self.pdln(status=Pengajuan.Status.PROSES_PAKLN)    # bukan Selesai: tidak dihitung

    def test_agregasi_sama_dengan_perhitungan_lama(self):
        qs = _qs_pelaporan(self.admin_pakln)
        lama = _konteks_pelaporan(qs)["hitung"]
        self.assertEqual(_hitung_pelaporan(qs), lama)
        self.assertEqual(
            lama,
            {"selesai": 7, "belum": 4, "menunggu": 1, "dikembalikan": 1, "disetujui": 1, "terlambat": 3},
        )

    def test_kartu_di_halaman_dan_satu_query_agregasi(self):
        with CaptureQueriesContext(connection) as q:
            _hitung_pelaporan(_qs_pelaporan(self.admin_pakln))
        self.assertEqual(len(q), 1)
        resp = self.client.get(reverse("pakln:pelaporan"))
        self.assertEqual(resp.context["hitung"]["selesai"], 7)
        self.assertEqual(resp.context["hitung"]["terlambat"], 3)


class HalamanDanAksesTests(PelaporanServerSideBase):
    def test_halaman_pakln_memakai_server_side_tanpa_baris(self):
        html = self.client.get(reverse("pakln:pelaporan")).content.decode()
        self.assertIn('id="tabelPelaporan"', html)
        self.assertIn("serverSide: true", html)
        self.assertIn(self.url_data, html)
        self.assertIn("dataTables.min.js", html)
        self.assertNotIn(self.p.kode, html)                 # baris tidak dirender di HTML
        # kolom cari: placeholder ringkas (tidak terpotong), ikon, dan keterangan cakupan pencarian
        self.assertIn("searchPlaceholder: 'Cari pegawai, NIP, kode…'", html)
        self.assertIn("addClass('dt-cari')", html)
        # panah urut dibuat jelas + petunjuk pada header kolom yang bisa diurutkan
        self.assertIn("class=\"table data-table sortir-jelas is-fullwidth is-hoverable\"", html)
        self.assertIn("Klik untuk mengurutkan", html)
        self.assertIn("Pencarian mencakup nama pegawai, NIP, kode pengajuan, unor, dan negara tujuan.", html)
        # tombol aksi dibuat ulang tiap tabel digambar: event delegation
        self.assertIn("$(document).on('click', '.btn-verifikasi'", html)
        self.assertIn("$(document).on('click', '.btn-revisi'", html)
        for modal in ('id="modal-verifikasi"', 'id="modal-revisi"'):
            self.assertIn(modal, html)

    def test_admin_unor_tetap_tabel_html_biasa(self):
        self.client.force_login(self.admin_unor)
        html = self.client.get(reverse("unor:pelaporan")).content.decode()
        self.assertIn(self.p.kode, html)                    # baris dirender langsung
        for tidak_ada in ('id="tabelPelaporan"', "serverSide", "dataTables.min.js", "pelaporan/data/", "Pencarian mencakup", "sortir-jelas"):
            self.assertNotIn(tidak_ada, html)

    def test_endpoint_hanya_untuk_admin_pakln(self):
        for user in (self.admin_unor, self.pegawai):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                resp = self.client.get(self.url_data)
                self.assertNotEqual(resp.status_code, 200)
