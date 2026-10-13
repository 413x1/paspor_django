"""Integrasi PDLN — wiki/instructions/BISNIS_PROSES_PDLN.MD (alur per tipe,
BPSDM, visa, pelaporan, aturan satu pengajuan aktif, pembatalan, report)."""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from accounts.models import PegawaiProfile, User
from notifications.models import Notification
from paspor.models import KategoriPerjalanan, Negara, SumberPembiayaan, UnitOrganisasi

from . import alur, persyaratan, riwayat
from .models import (
    DetailPdln, LaporanPdln, Pengajuan, PermohonanPembatalan, RiwayatPengajuan,
)

S = Pengajuan.Status
Aksi = RiwayatPengajuan.Aksi


class _Basis:
    def setUp(self):
        self.unor, self.unor_lain = UnitOrganisasi.objects.all()[:2]
        self.pegawai = User.objects.create_user("peg1", password="x", role="pegawai")
        PegawaiProfile.objects.create(
            user=self.pegawai, nip="1987", nama="Andra", jabatan="Kasi", pangkat_golongan="III-d",
            unit_kerja="Dit. Bina Teknik", unit_organisasi=self.unor, sisa_cuti_tahun_berjalan=12,
        )
        self.admin_unor = User.objects.create_user("unor1", password="x", role="admin_unor", unit_organisasi=self.unor)
        self.admin_bpsdm = User.objects.create_user("bpsdm1", password="x", role="admin_bpsdm")
        self.admin_pakln = User.objects.create_user("pakln1", password="x", role="admin_pakln")
        self.admin_bko = User.objects.create_user("bko1", password="x", role="admin_bko")
        self.jepang = Negara.objects.create(nama_negara="Jepang Uji", perlu_visa=True)
        self.singapura = Negara.objects.create(nama_negara="Singapura Uji", perlu_visa=False)
        self.berangkat = date.today() + timedelta(days=30)

    # --- helper ---------------------------------------------------------
    def login(self, user):
        self.client.force_login(user)

    def post(self, user, url_name, data=None, **kwargs):
        self.login(user)
        return self.client.post(reverse(url_name, kwargs=kwargs or None), data or {})

    def get(self, user, url_name, query="", **kwargs):
        self.login(user)
        return self.client.get(reverse(url_name, kwargs=kwargs or None) + query)

    def kategori(self, tipe):
        return next(
            k for k in KategoriPerjalanan.objects.filter(jenis_perjalanan="PDLN")
            if not k.tipe_pdln or tipe in k.tipe_pdln
        )

    def sumber(self, tipe):
        return next(
            s for s in SumberPembiayaan.objects.filter(tipe_perjalanan="PDLN")
            if not s.tipe_pdln or tipe in s.tipe_pdln
        )

    def isi_formulir(self, tipe, negara=None):
        negara = negara or self.singapura
        data = {
            "kategori": self.kategori(tipe).pk,
            "tujuan_negara": [negara.pk],
            "sumber_pembiayaan": self.sumber(tipe).pk,
            "tgl_berangkat": self.berangkat.isoformat(),
            "tgl_kembali": (self.berangkat + timedelta(days=6)).isoformat(),
            "kota_tujuan": "Kota Uji",
            "tgl_mulai_kegiatan": (self.berangkat + timedelta(days=1)).isoformat(),
            "tgl_selesai_kegiatan": (self.berangkat + timedelta(days=5)).isoformat(),
            "penyelenggara": "Penyelenggara Uji",
            "perguruan_tinggi": "Universitas Uji",
            "beasiswa": "STUB-P-001" if tipe == "T2P" else "STUB-L-001",
            "pernyataan_benar": "on",
        }
        self.login(self.pegawai)
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + f"?jenis=pdln&tipe={tipe}", data)
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["form"].errors)
        return Pengajuan.objects.filter(pegawai=self.pegawai).latest("created_at")

    def lengkapi(self, p, tahap, kecuali=()):
        model = persyaratan.TAHAP_MODEL[tahap]
        for s in persyaratan.daftar_syarat(p, tahap):
            if s.jenis not in kecuali:
                model.objects.get_or_create(
                    pengajuan=p, jenis=s.jenis, defaults={"file": "x.pdf", "tanggal_surat": date.today()},
                )

    def kirim(self, p, catatan=""):
        self.lengkapi(p, "pegawai")
        return self.post(self.pegawai, "pegawai:upload_dokumen", {"kirim": "1", "agree": "on", "catatan": catatan}, kode=p.kode)

    def unor_teruskan(self, p, catatan=""):
        self.post(self.admin_unor, "unor:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.lengkapi(p, "unor")
        return self.post(self.admin_unor, "unor:upload_dokumen", {"teruskan": "1", "agree": "on", "catatan": catatan}, kode=p.kode)

    def bpsdm_teruskan(self, p, catatan=""):
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.lengkapi(p, "bpsdm")
        return self.post(self.admin_bpsdm, "bpsdm:upload_dokumen", {"teruskan": "1", "agree": "on", "catatan": catatan}, kode=p.kode)

    def bko_unggah(self, p):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.login(self.admin_bko)
        return self.client.post(reverse("bko:proses", kwargs={"kode": p.kode}), {
            "jenis": "sk_tubel", "tanggal_surat": date.today().isoformat(),
            "file": SimpleUploadedFile("sk_tubel.pdf", b"%PDF-1.4 sk", content_type="application/pdf"),
        })

    def pakln_selesai(self, p, kecuali=()):
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.lengkapi(p, "pakln", kecuali=kecuali)
        return self.post(self.admin_pakln, "pakln:upload_dokumen", {"selesaikan": "1", "agree": "on"}, kode=p.kode)

    def unggah_laporan(self, p, catatan=""):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.login(self.pegawai)
        return self.client.post(
            reverse("pegawai:laporan_form", kwargs={"kode": p.kode}),
            {
                "action": "submit",
                "tujuan_kegiatan": "Mengikuti pertemuan", "materi_kegiatan": "Materi inti", "tindak_lanjut": "Tindak lanjut",
                "dampak_rekomendasi": "Dampak dan rekomendasi", "estimasi_biaya": "10.000.000", "realisasi_biaya": "9.500.000",
                "dokumen_laporan": SimpleUploadedFile("laporan.pdf", b"%PDF-1.4 uji", content_type="application/pdf"),
                "catatan_perbaikan": catatan,
            },
        )

    def refresh(self, p):
        p.refresh_from_db()
        return p


class AlurTipe1Tests(_Basis, TestCase):
    def test_kode_dan_detail_pdln(self):
        p = self.isi_formulir("T1")
        self.assertTrue(p.kode.startswith(f"PDLN{self.unor.code}-1-{date.today():%d%m%y}-"))
        self.assertEqual(p.jenis_perjalanan, "pdln")
        self.assertEqual(DetailPdln.objects.get(pengajuan=p).penyelenggara, "Penyelenggara Uji")

    def test_alur_penuh_sampai_laporan_disetujui(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.assertEqual(self.refresh(p).status, S.PROSES)
        self.assertEqual(p.unit_organisasi, self.unor)
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        self.pakln_selesai(p, kecuali=("visa",))  # Singapura tidak perlu visa -> opsional
        self.assertEqual(self.refresh(p).status, S.SELESAI)
        # PDLN tidak memotong cuti.
        self.assertEqual(self.pegawai.profile.__class__.objects.get(user=self.pegawai).sisa_cuti_tahun_berjalan, 12)
        self.assertFalse(p.tuntas)
        self.assertEqual(alur.pengajuan_belum_tuntas(self.pegawai), p)

        self.unggah_laporan(p)
        self.assertEqual(self.refresh(p).laporan.status, LaporanPdln.Status.MENUNGGU)
        self.post(self.admin_pakln, "pakln:verifikasi_laporan", {"keputusan": "setujui"}, kode=p.kode)
        self.refresh(p)
        self.assertEqual(p.laporan.status, LaporanPdln.Status.DISETUJUI)
        self.assertTrue(p.tuntas)
        self.assertIsNone(alur.pengajuan_belum_tuntas(self.pegawai))
        self.assertTrue(Notification.objects.filter(recipient=self.pegawai, event=Notification.Event.LAPORAN_DISETUJUI).exists())

    def test_visa_wajib_bila_negara_memerlukan_visa(self):
        p = self.isi_formulir("T1", negara=self.jepang)
        self.kirim(p)
        self.unor_teruskan(p)
        self.pakln_selesai(p, kecuali=("visa",))
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        self.lengkapi(p, "pakln")
        self.post(self.admin_pakln, "pakln:upload_dokumen", {"selesaikan": "1", "agree": "on"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.SELESAI)

    def test_laporan_dikembalikan_wajib_catatan_dan_unggah_ulang_wajib_catatan(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.unor_teruskan(p)
        self.pakln_selesai(p)
        self.unggah_laporan(p)
        self.post(self.admin_pakln, "pakln:verifikasi_laporan", {"keputusan": "kembalikan"}, kode=p.kode)
        self.assertEqual(self.refresh(p).laporan.status, LaporanPdln.Status.MENUNGGU)
        self.post(self.admin_pakln, "pakln:verifikasi_laporan", {"keputusan": "kembalikan", "catatan": "Lengkapi foto"}, kode=p.kode)
        self.assertEqual(self.refresh(p).laporan.status, LaporanPdln.Status.DIKEMBALIKAN)
        self.unggah_laporan(p)  # tanpa catatan -> ditolak
        self.assertEqual(self.refresh(p).laporan.status, LaporanPdln.Status.DIKEMBALIKAN)
        self.unggah_laporan(p, catatan="Foto ditambahkan")
        self.assertEqual(self.refresh(p).laporan.status, LaporanPdln.Status.MENUNGGU)
        self.assertEqual(p.riwayat.filter(aksi=Aksi.LAPORAN_DIUNGGAH).last().catatan, "Foto ditambahkan")


class AlurTipe2Tests(_Basis, TestCase):
    def test_alur_t2p_melalui_bpsdm_dan_pengembalian_ke_tahap_sebelumnya(self):
        p = self.isi_formulir("T2P")
        self.assertEqual(p.detail.beasiswa_pintar_id, "STUB-P-001")
        self.kirim(p)
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_BPSDM)
        self.assertIsNotNone(p.tgl_masuk_bpsdm)

        # BPSDM mengembalikan ke Unor; Unor wajib catatan saat meneruskan ulang.
        self.post(self.admin_bpsdm, "bpsdm:preview", {"kembalikan": "1", "catatan": "DRH belum ditandatangani"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.PROSES)
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES)
        self.unor_teruskan(p, catatan="DRH sudah ditandatangani")
        self.assertEqual(self.refresh(p).status, S.PROSES_BPSDM)

        self.bpsdm_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)

        # PAKLN mengembalikan ke BPSDM (tahap tepat sebelumnya untuk Tipe 2).
        self.post(self.admin_pakln, "pakln:preview", {"kembalikan": "1", "catatan": "ND belum sesuai"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.PROSES_BPSDM)
        self.bpsdm_teruskan(p, catatan="ND diperbaiki")
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        self.bko_unggah(p)
        self.pakln_selesai(p)
        self.assertEqual(self.refresh(p).status, S.SELESAI)

        aksi = list(p.riwayat.values_list("aksi", flat=True))
        self.assertEqual(aksi, [
            Aksi.DIKIRIM, Aksi.DITERUSKAN_BPSDM, Aksi.DIKEMBALIKAN_BPSDM, Aksi.DITERUSKAN_ULANG_BPSDM,
            Aksi.DITERUSKAN_PAKLN, Aksi.DITERUSKAN_BKO, Aksi.DIKEMBALIKAN_PAKLN, Aksi.DITERUSKAN_ULANG,
            Aksi.SK_TUBEL_DIUNGGAH, Aksi.SELESAI,
        ])
        # Timeline Tipe 2 berisi 5 tahap.
        self.assertEqual([s["status"] for s in p.timeline],
                         [S.BELUM, S.PROSES, S.PROSES_BPSDM, S.PROSES_PAKLN, S.SELESAI])

        # Pegawai tidak membaca catatan antar-admin, BPSDM membaca semuanya.
        pesan_pegawai = {e["aksi"]: e["catatan"] for e in riwayat.riwayat_untuk(p, self.pegawai)}
        self.assertEqual(pesan_pegawai[Aksi.DIKEMBALIKAN_BPSDM], "")
        self.assertEqual(pesan_pegawai[Aksi.DIKEMBALIKAN_PAKLN], "")
        pesan_bpsdm = {e["aksi"]: e["catatan"] for e in riwayat.riwayat_untuk(p, self.admin_bpsdm)}
        self.assertEqual(pesan_bpsdm[Aksi.DIKEMBALIKAN_PAKLN], "ND belum sesuai")

    def test_t2_wajib_beasiswa(self):
        self.login(self.pegawai)
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + "?jenis=pdln&tipe=T2L", {
            "kategori": self.kategori("T2L").pk, "tujuan_negara": [self.singapura.pk],
            "sumber_pembiayaan": self.sumber("T2L").pk, "tgl_berangkat": self.berangkat.isoformat(),
            "tgl_kembali": (self.berangkat + timedelta(days=3)).isoformat(), "kota_tujuan": "X",
            "tgl_mulai_kegiatan": self.berangkat.isoformat(), "tgl_selesai_kegiatan": self.berangkat.isoformat(),
            "penyelenggara": "JICA", "pernyataan_benar": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("beasiswa", resp.context["form"].errors)

    def test_cakupan_bpsdm_hanya_tipe2(self):
        p1 = self.isi_formulir("T1")
        self.kirim(p1)
        self.assertEqual(self.get(self.admin_bpsdm, "bpsdm:preview", kode=p1.kode).status_code, 404)
        lain = User.objects.create_user("unor2", password="x", role="admin_unor", unit_organisasi=self.unor_lain)
        self.assertEqual(self.get(lain, "unor:preview", kode=p1.kode).status_code, 404)


class AlurT2PBkoTests(_Basis, TestCase):
    """PDLN Tipe 2 Pendidikan v2 — track paralel Admin BKO
    (wiki/instructions/PDLN_TIPE_2_FLOW.MD §8)."""

    SB = Pengajuan.StatusBko

    def sampai_pakln(self, tipe="T2P"):
        p = self.isi_formulir(tipe)
        self.kirim(p)
        self.unor_teruskan(p)
        self.bpsdm_teruskan(p)
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.lengkapi(p, "pakln")
        return self.refresh(p)

    def selesai(self, p):
        return self.post(self.admin_pakln, "pakln:upload_dokumen", {"selesaikan": "1", "agree": "on"}, kode=p.kode)

    def tutup(self, p, catatan="Pencalonan beasiswa belum ditetapkan"):
        return self.post(self.admin_bko, "bko:proses", {"tutup": "1", "catatan": catatan}, kode=p.kode)

    def pesan(self, p, user, aksi):
        return next(e["catatan"] for e in riwayat.riwayat_untuk(p, user) if e["aksi"] == aksi)

    def test_bpsdm_teruskan_membuka_track_bko_dan_notifikasi(self):
        p = self.sampai_pakln()
        self.assertEqual(p.status, S.PROSES_PAKLN)
        self.assertEqual(p.status_bko, self.SB.MENUNGGU)
        self.assertIsNotNone(p.tgl_masuk_bko)
        self.assertTrue(p.riwayat.filter(aksi=Aksi.DITERUSKAN_BKO).exists())
        self.assertTrue(Notification.objects.filter(
            recipient=self.admin_bko, event=Notification.Event.FORWARD_BKO, pengajuan=p).exists())
        self.assertNotIn("sk_tubel", [s.jenis for s in persyaratan.daftar_syarat(p, "pakln")])

    def test_t2l_tidak_memakai_bko(self):
        p = self.sampai_pakln("T2L")
        self.assertEqual(p.status_bko, "")
        self.assertEqual(self.get(self.admin_bko, "bko:proses", kode=p.kode).status_code, 404)
        self.selesai(p)
        self.assertEqual(self.refresh(p).status, S.SELESAI)

    def test_selesai_menunggu_sk_tubel_lalu_berhasil(self):
        p = self.sampai_pakln()
        self.selesai(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)

        self.bko_unggah(p)
        self.assertEqual(self.refresh(p).status_bko, self.SB.DIUNGGAH)
        self.assertTrue(Notification.objects.filter(
            recipient=self.admin_pakln, event=Notification.Event.SK_TUBEL_DIUNGGAH).exists())
        self.selesai(p)
        self.assertEqual(self.refresh(p).status, S.SELESAI)
        # SK Tubel dari BKO dapat diunduh pegawai.
        resp = self.get(self.pegawai, "pegawai:unduh_hasil", kode=p.kode, jenis="sk_tubel")
        self.assertEqual(resp.status_code, 200)

    def test_hapus_sk_tubel_kembali_menunggu(self):
        p = self.sampai_pakln()
        self.bko_unggah(p)
        self.post(self.admin_bko, "bko:hapus_dokumen", kode=p.kode, jenis="sk_tubel")
        self.assertEqual(self.refresh(p).status_bko, self.SB.MENUNGGU)
        self.assertFalse(p.dokumen_bko.exists())

    def test_tutup_wajib_catatan_dan_terlihat_semua_pihak(self):
        p = self.sampai_pakln()
        self.tutup(p, catatan="")
        self.assertEqual(self.refresh(p).status_bko, self.SB.MENUNGGU)
        self.tutup(p)
        p = self.refresh(p)
        self.assertEqual(p.status_bko, self.SB.DITUTUP)
        self.assertEqual(p.catatan_bko, "Pencalonan beasiswa belum ditetapkan")
        for user in (self.pegawai, self.admin_unor, self.admin_bpsdm, self.admin_pakln, self.admin_bko):
            with self.subTest(role=user.role):
                self.assertEqual(self.pesan(p, user, Aksi.DITUTUP_BKO), "Pencalonan beasiswa belum ditetapkan")
        penerima = set(Notification.objects.filter(event=Notification.Event.BKO_DITUTUP).values_list("recipient", flat=True))
        self.assertEqual(penerima, {self.pegawai.pk, self.admin_unor.pk, self.admin_bpsdm.pk, self.admin_pakln.pk})
        self.assertContains(self.get(self.pegawai, "pegawai:monitor_progres", kode=p.kode), "Pencalonan beasiswa belum ditetapkan")

    def test_ditutup_selesai_normal_ditolak_lanjutkan_tanpa_sk_tubel(self):
        p = self.sampai_pakln()
        self.tutup(p)
        resp = self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode)
        for teks in ("Pencalonan beasiswa belum ditetapkan", "Buka Kembali Pemrosesan BKO",
                     "Lanjutkan tanpa SK Tubel", "Hentikan Pengajuan"):
            self.assertContains(resp, teks)
        for user, nama in ((self.admin_unor, "unor:preview"), (self.admin_bpsdm, "bpsdm:preview")):
            self.assertContains(self.get(user, nama, kode=p.kode), "Pencalonan beasiswa belum ditetapkan")
        self.selesai(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        # Catatan wajib.
        self.post(self.admin_pakln, "pakln:upload_dokumen", {"selesaikan_tanpa_sk_tubel": "1", "agree": "on"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        self.post(self.admin_pakln, "pakln:upload_dokumen",
                  {"selesaikan_tanpa_sk_tubel": "1", "agree": "on", "catatan": "Disetujui pimpinan tanpa SK"}, kode=p.kode)
        p = self.refresh(p)
        self.assertEqual(p.status, S.SELESAI)
        self.assertTrue(p.riwayat.filter(aksi=Aksi.SELESAI_TANPA_SK_TUBEL).exists())
        # Catatan hanya terlihat Admin PAKLN.
        self.assertEqual(self.pesan(p, self.admin_pakln, Aksi.SELESAI_TANPA_SK_TUBEL), "Disetujui pimpinan tanpa SK")
        for user in (self.pegawai, self.admin_unor, self.admin_bpsdm, self.admin_bko):
            with self.subTest(role=user.role):
                self.assertEqual(self.pesan(p, user, Aksi.SELESAI_TANPA_SK_TUBEL), "")
        self.assertEqual(p.timeline[-1]["sub"], "Diselesaikan tanpa SK Tugas Belajar")
        for body in Notification.objects.filter(pengajuan=p).values_list("body", flat=True):
            self.assertNotIn("Disetujui pimpinan", body)
        # Track terkunci setelah selesai.
        self.post(self.admin_bko, "bko:proses", {"buka_kembali": "1", "catatan": "x"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status_bko, self.SB.DITUTUP)

    def test_lanjutkan_tanpa_sk_tubel_hanya_saat_ditutup(self):
        p = self.sampai_pakln()
        self.post(self.admin_pakln, "pakln:upload_dokumen",
                  {"selesaikan_tanpa_sk_tubel": "1", "agree": "on", "catatan": "x"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)

    def test_buka_kembali_oleh_bko_dan_pakln_saja(self):
        p = self.sampai_pakln()
        self.tutup(p)
        for user, url in ((self.admin_unor, "unor:upload_dokumen"), (self.admin_bpsdm, "bpsdm:upload_dokumen")):
            self.post(user, url, {"buka_kembali_bko": "1", "catatan": "x"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status_bko, self.SB.DITUTUP)

        self.post(self.admin_bko, "bko:proses", {"buka_kembali": "1", "catatan": ""}, kode=p.kode)
        self.assertEqual(self.refresh(p).status_bko, self.SB.DITUTUP)
        self.post(self.admin_bko, "bko:proses", {"buka_kembali": "1", "catatan": "Beasiswa sudah ditetapkan"}, kode=p.kode)
        p = self.refresh(p)
        self.assertEqual(p.status_bko, self.SB.MENUNGGU)
        self.assertEqual(p.catatan_bko, "")

        self.tutup(p)
        self.post(self.admin_pakln, "pakln:upload_dokumen", {"buka_kembali_bko": "1", "catatan": "Mohon diproses ulang"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status_bko, self.SB.MENUNGGU)
        self.assertEqual(self.pesan(p, self.pegawai, Aksi.DIBUKA_ULANG_BKO), "Beasiswa sudah ditetapkan")
        self.assertTrue(Notification.objects.filter(
            recipient=self.admin_bko, event=Notification.Event.BKO_DIBUKA).exists())

    def test_hentikan_oleh_pakln_hanya_saat_ditutup(self):
        p = self.sampai_pakln()
        self.post(self.admin_pakln, "pakln:upload_dokumen", {"hentikan": "1", "alasan": "x"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)
        self.tutup(p)
        self.post(self.admin_pakln, "pakln:upload_dokumen", {"hentikan": "1", "alasan": "SK tidak terbit"}, kode=p.kode)
        p = self.refresh(p)
        self.assertEqual(p.status, S.DIBATALKAN)
        m = p.permohonan_pembatalan.get()
        self.assertEqual((m.diajukan_role, m.status), ("admin_pakln", PermohonanPembatalan.Status.DISETUJUI))
        self.assertTrue(Notification.objects.filter(
            recipient=self.admin_bko, event=Notification.Event.PEMBATALAN_DISETUJUI).exists())

    def test_pengembalian_tidak_menyentuh_track_dan_bko_tetap_bisa_unggah(self):
        p = self.sampai_pakln()
        self.post(self.admin_pakln, "pakln:preview", {"kembalikan": "1", "catatan": "ND belum sesuai"}, kode=p.kode)
        p = self.refresh(p)
        self.assertEqual(p.status, S.PROSES_BPSDM)
        self.assertEqual(p.status_bko, self.SB.MENUNGGU)
        self.bko_unggah(p)
        self.assertEqual(self.refresh(p).status_bko, self.SB.DIUNGGAH)
        tgl_masuk = p.tgl_masuk_bko
        self.bpsdm_teruskan(p, catatan="ND diperbaiki")
        p = self.refresh(p)
        self.assertEqual((p.status, p.status_bko, p.tgl_masuk_bko), (S.PROSES_PAKLN, self.SB.DIUNGGAH, tgl_masuk))
        self.assertEqual(p.riwayat.filter(aksi=Aksi.DITERUSKAN_BKO).count(), 1)
        self.assertTrue(p.dokumen_bko.exists())

    def test_aksi_bko_dibekukan_saat_pembatalan_terbuka(self):
        p = self.sampai_pakln()
        self.post(self.pegawai, "pegawai:ajukan_pembatalan", {"alasan": "Batal berangkat"}, kode=p.kode)
        self.assertIsNotNone(self.refresh(p).pembatalan_terbuka)
        self.bko_unggah(p)
        self.tutup(p)
        self.assertEqual(self.refresh(p).status_bko, self.SB.MENUNGGU)
        self.assertFalse(p.dokumen_bko.exists())

    def test_cakupan_dan_halaman_bko(self):
        p = self.sampai_pakln()
        t1 = Pengajuan.objects.create(pegawai=self.pegawai, jenis_perjalanan="pdln", tipe_pdln="T1",
                                      status=S.PROSES_PAKLN, tgl_pengajuan=date.today())
        for nama in ("bko:dashboard", "bko:pembatalan", "bko:rekap", "bko:export"):
            with self.subTest(nama=nama):
                self.assertEqual(self.get(self.admin_bko, nama).status_code, 200)
        data = self.get(self.admin_bko, "bko:dashboard_data").json()
        self.assertEqual(data["recordsTotal"], 1)
        self.assertEqual(self.get(self.admin_bko, "bko:proses", kode=t1.kode).status_code, 404)
        resp = self.get(self.admin_bko, "bko:proses", kode=p.kode)
        self.assertContains(resp, "Tutup Pemrosesan")
        self.assertContains(resp, "Letter of Guarantee")
        self.assertRedirects(self.get(self.admin_bko, "home"), reverse("bko:dashboard"), fetch_redirect_response=False)
        # Role lain tidak dapat membuka halaman BKO.
        self.assertNotEqual(self.get(self.admin_unor, "bko:proses", kode=p.kode).status_code, 200)

    def test_timeline_sub_keterangan_bko(self):
        p = self.sampai_pakln()
        langkah = {s["status"]: s for s in p.timeline}
        self.assertEqual(len(langkah), 5)
        self.assertEqual(langkah[S.PROSES_PAKLN]["sub"], "SK Tugas Belajar (Admin BKO): Menunggu")
        self.tutup(p)
        sub = {s["status"]: s for s in self.refresh(p).timeline}[S.PROSES_PAKLN]["sub"]
        self.assertIn("Pencalonan beasiswa belum ditetapkan", sub)

    def test_migrasi_data_memindah_sk_tubel_pakln(self):
        from importlib import import_module

        from django.apps import apps

        from .models import DokumenBko, DokumenPakln

        p = self.sampai_pakln()
        p.status_bko, p.tgl_masuk_bko = "", None
        p.save()
        DokumenPakln.objects.create(pengajuan=p, jenis="sk_tubel", file="lama/sk.pdf", tanggal_surat=date.today())
        import_module("pengajuan.migrations.0021_v2_bko_data").maju(apps, None)
        p = self.refresh(p)
        self.assertEqual((p.status_bko, p.tgl_masuk_bko), (self.SB.DIUNGGAH, p.tgl_masuk_pakln))
        self.assertEqual(DokumenBko.objects.get(pengajuan=p).file.name, "lama/sk.pdf")
        self.assertFalse(DokumenPakln.objects.filter(pengajuan=p, jenis="sk_tubel").exists())


class SatuPengajuanAktifTests(_Basis, TestCase):
    def test_tidak_bisa_mengajukan_baru_sampai_tuntas(self):
        p = self.isi_formulir("T3")
        self.kirim(p)
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query="?jenis=nondinas")
        self.assertRedirects(resp, reverse("pegawai:beranda"))
        self.assertEqual(Pengajuan.objects.filter(pegawai=self.pegawai).count(), 1)

        beranda = self.get(self.pegawai, "pegawai:beranda")
        self.assertContains(beranda, "belum dapat mengajukan perjalanan baru")


class PembatalanTests(_Basis, TestCase):
    def _pengajuan_terkirim(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        return self.refresh(p)

    def test_alasan_wajib_dan_jenjang_unor_lalu_pakln(self):
        p = self._pengajuan_terkirim()
        self.post(self.pegawai, "pegawai:ajukan_pembatalan", {"alasan": "  "}, kode=p.kode)
        self.assertFalse(p.permohonan_pembatalan.exists())

        self.post(self.pegawai, "pegawai:ajukan_pembatalan", {"alasan": "Agenda diundur"}, kode=p.kode)
        m = p.permohonan_pembatalan.get()
        self.assertEqual(m.status, PermohonanPembatalan.Status.MENUNGGU_UNOR)

        # Aksi alur utama dibekukan selama permohonan terbuka.
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES)

        self.post(self.admin_unor, "unor:putuskan_pembatalan", {"keputusan": "setuju"}, pk=m.pk)
        m.refresh_from_db()
        self.assertEqual(m.status, PermohonanPembatalan.Status.MENUNGGU_PAKLN)

        self.post(self.admin_pakln, "pakln:putuskan_pembatalan", {"keputusan": "tolak"}, pk=m.pk)
        m.refresh_from_db()
        self.assertEqual(m.status, PermohonanPembatalan.Status.MENUNGGU_PAKLN)  # tolak tanpa catatan ditolak

        self.post(self.admin_pakln, "pakln:putuskan_pembatalan", {"keputusan": "setuju"}, pk=m.pk)
        m.refresh_from_db()
        self.assertEqual(m.status, PermohonanPembatalan.Status.DISETUJUI)
        self.assertEqual(self.refresh(p).status, S.DIBATALKAN)
        self.assertTrue(p.tuntas)
        self.assertIsNone(alur.pengajuan_belum_tuntas(self.pegawai))
        self.assertEqual(p.timeline[-1]["state"], "cancelled")
        # Alasan pembatalan terbaca pegawai.
        pesan = {e["aksi"]: e["catatan"] for e in riwayat.riwayat_untuk(p, self.pegawai)}
        self.assertEqual(pesan[Aksi.PEMBATALAN_DIAJUKAN], "Agenda diundur")

    def test_diajukan_admin_unor_langsung_ke_pakln_dan_ditolak(self):
        p = self._pengajuan_terkirim()
        self.post(self.admin_unor, "unor:ajukan_pembatalan", {"alasan": "Kebutuhan dinas"}, kode=p.kode)
        m = p.permohonan_pembatalan.get()
        self.assertEqual(m.status, PermohonanPembatalan.Status.MENUNGGU_PAKLN)
        self.post(self.admin_pakln, "pakln:putuskan_pembatalan", {"keputusan": "tolak", "catatan": "Tetap berangkat"}, pk=m.pk)
        m.refresh_from_db()
        self.assertEqual(m.status, PermohonanPembatalan.Status.DITOLAK)
        self.assertEqual(self.refresh(p).status, S.PROSES)
        # Setelah ditolak, alur utama berjalan lagi.
        self.unor_teruskan(p)
        self.assertEqual(self.refresh(p).status, S.PROSES_PAKLN)

    def test_pengaju_dapat_menarik(self):
        p = self._pengajuan_terkirim()
        self.post(self.pegawai, "pegawai:ajukan_pembatalan", {"alasan": "Salah tanggal"}, kode=p.kode)
        m = p.permohonan_pembatalan.get()
        self.post(self.pegawai, "pegawai:tarik_pembatalan", pk=m.pk)
        m.refresh_from_db()
        self.assertEqual(m.status, PermohonanPembatalan.Status.DITARIK)
        self.assertIsNone(self.refresh(p).pembatalan_terbuka)

    def test_draft_dibatalkan_langsung(self):
        p = self.isi_formulir("T1")
        self.post(self.pegawai, "pegawai:ajukan_pembatalan", {"alasan": "Tidak jadi"}, kode=p.kode)
        self.assertEqual(self.refresh(p).status, S.DIBATALKAN)
        self.assertFalse(p.permohonan_pembatalan.exists())


class HalamanDanReportTests(_Basis, TestCase):
    def test_halaman_utama_tiap_role_dapat_dibuka(self):
        p = self.isi_formulir("T2L")
        self.kirim(p)
        self.unor_teruskan(p)
        cek = [
            (self.pegawai, "pegawai:beranda", {}), (self.pegawai, "pegawai:pelaporan", {}),
            (self.pegawai, "pegawai:pembatalan", {}), (self.pegawai, "profil", {}),
            (self.pegawai, "pegawai:monitor_progres", {"kode": p.kode}),
            (self.admin_unor, "unor:dashboard", {}), (self.admin_unor, "unor:pembatalan", {}),
            (self.admin_unor, "unor:pelaporan", {}), (self.admin_unor, "unor:rekap", {}),
            (self.admin_unor, "unor:export", {}), (self.admin_unor, "unor:preview", {"kode": p.kode}),
            (self.admin_bpsdm, "bpsdm:dashboard", {}), (self.admin_bpsdm, "bpsdm:preview", {"kode": p.kode}),
            (self.admin_bpsdm, "bpsdm:pembatalan", {}), (self.admin_bpsdm, "bpsdm:rekap", {}),
            (self.admin_pakln, "pakln:dashboard", {}), (self.admin_pakln, "pakln:pelaporan", {}),
            (self.admin_pakln, "pakln:pembatalan", {}), (self.admin_pakln, "pakln:rekap", {}),
            (self.admin_pakln, "pakln:export", {}), (self.admin_pakln, "pakln:preview", {"kode": p.kode}),
        ]
        for user, nama, kw in cek:
            with self.subTest(nama=nama):
                self.assertEqual(self.get(user, nama, **kw).status_code, 200)
        for user, nama in [(self.admin_unor, "unor:dashboard_data"), (self.admin_bpsdm, "bpsdm:dashboard_data"),
                           (self.admin_pakln, "pakln:dashboard_data"), (self.pegawai, "pegawai:riwayat_data")]:
            with self.subTest(nama=nama):
                resp = self.get(user, nama, query="?tab=pdln&jenis=pdln")
                self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.get(self.admin_bpsdm, "bpsdm:dashboard_data").json()["recordsTotal"], 1)

    def test_dashboard_data_bpsdm_saat_masih_di_unor(self):
        p = self.isi_formulir("T2P")
        self.kirim(p)
        resp = self.get(self.admin_bpsdm, "bpsdm:dashboard_data")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Menunggu Admin Unor", resp.json()["data"][0][8])

    def test_halaman_formulir_dan_unggah_tiap_tahap(self):
        for tipe in ("T1", "T2P", "T2L", "T3"):
            with self.subTest(tipe=tipe):
                resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query=f"?jenis=pdln&tipe={tipe}")
                self.assertEqual(resp.status_code, 200)
        p = self.isi_formulir("T2P", negara=self.jepang)
        self.assertContains(self.get(self.pegawai, "pegawai:upload_dokumen", kode=p.kode), "Letter of Guarantee")
        self.kirim(p)
        self.post(self.admin_unor, "unor:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.assertContains(self.get(self.admin_unor, "unor:upload_dokumen", kode=p.kode), "Teruskan ke Admin BPSDM")
        self.unor_teruskan(p)
        self.post(self.admin_bpsdm, "bpsdm:preview", {"lanjutkan": "1"}, kode=p.kode)
        self.assertContains(self.get(self.admin_bpsdm, "bpsdm:upload_dokumen", kode=p.kode), "Izin Prinsip Menteri")
        self.bpsdm_teruskan(p)
        self.post(self.admin_pakln, "pakln:preview", {"lanjutkan": "1"}, kode=p.kode)
        resp = self.get(self.admin_pakln, "pakln:upload_dokumen", kode=p.kode)
        self.assertContains(resp, "SK Tugas Belajar")
        self.assertContains(resp, "Jepang Uji memerlukan visa")

    def test_export_csv_xlsx_mengikuti_cakupan(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        csv_unor = self.get(self.admin_unor, "unor:export", query="?format=csv").content.decode("utf-8-sig")
        self.assertIn(p.kode, csv_unor)
        csv_bpsdm = self.get(self.admin_bpsdm, "bpsdm:export", query="?format=csv").content.decode("utf-8-sig")
        self.assertNotIn(p.kode, csv_bpsdm)
        xlsx = self.get(self.admin_pakln, "pakln:export", query="?format=xlsx&jenis=pdln")
        self.assertEqual(xlsx.status_code, 200)
        self.assertTrue(xlsx.content.startswith(b"PK"))
        rekap = self.get(self.admin_pakln, "pakln:rekap", query="?tab=waktu")
        self.assertContains(rekap, "Waktu Proses per Tahap")
