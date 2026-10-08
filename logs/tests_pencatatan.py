"""Tes pemasangan pencatatan: dekorator `@log_aktivitas`, `catat_riwayat`,
dan titik-titik pencatatan di view (unggah/hapus dokumen, master, formulir)."""

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import User
from paspor.models import Negara

from .models import ActivityLog
from .utils import catat_riwayat, log_aktivitas


class DekoratorTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.user = User.objects.create_user(username="admin.uji", password="x", role="admin_pakln")

    def _panggil(self, view, method="post", **kwargs):
        request = getattr(self.rf, method)("/uji/")
        request.user = self.user
        return view(request, **kwargs)

    def test_get_tidak_dicatat(self):
        @log_aktivitas("master.ubah", "x")
        def view(request):
            return HttpResponse("ok")
        self._panggil(view, method="get")
        self.assertEqual(ActivityLog.objects.count(), 0)

    def test_status_di_bawah_400_berhasil(self):
        @log_aktivitas("master.ubah", "Menghapus X", target_type="x", target_kwarg="x_id")
        def view(request, x_id):
            return JsonResponse({"ok": True})
        self._panggil(view, x_id=7)
        log = ActivityLog.objects.get()
        self.assertEqual((log.aktivitas, log.status, log.target_type, log.target_id), ("master.ubah", "success", "x", "7"))
        self.assertEqual(log.username, "admin.uji")

    def test_status_400_gagal(self):
        @log_aktivitas("master.ubah", "x")
        def view(request):
            return JsonResponse({"ok": False}, status=400)
        self._panggil(view)
        log = ActivityLog.objects.get()
        self.assertEqual((log.status, log.detail), ("failed", "HTTP 400"))

    def test_sukses_redirect_hanya_3xx(self):
        @log_aktivitas("master.ubah", "x", sukses_redirect=True)
        def view(request, redirect):
            return HttpResponseRedirect("/") if redirect else HttpResponse("form dirender ulang")
        self._panggil(view, redirect=True)
        self._panggil(view, redirect=False)
        hasil = list(ActivityLog.objects.order_by("pk").values_list("status", "detail"))
        self.assertEqual(hasil, [("success", ""), ("failed", "Validasi formulir gagal")])

    def test_exception_dicatat_dan_dilempar_ulang(self):
        @log_aktivitas("master.ubah", "x")
        def view(request):
            raise PermissionDenied
        with self.assertRaises(PermissionDenied):
            self._panggil(view)
        log = ActivityLog.objects.get()
        self.assertEqual((log.status, log.detail), ("failed", "Exception: PermissionDenied"))


class CatatRiwayatTests(TestCase):
    def test_pemetaan_aksi_riwayat(self):
        from pengajuan.models import RiwayatPengajuan
        Aksi = RiwayatPengajuan.Aksi
        request = RequestFactory().post("/uji/")
        request.user = User.objects.create_user(username="peg", password="x", role="pegawai")

        class P:  # cukup memiliki `kode`
            kode = "PLN01-071026-001"

        for aksi, kode in (
            (Aksi.DIKIRIM, "pengajuan.kirim"), (Aksi.DITERUSKAN_PAKLN, "pengajuan.teruskan"),
            (Aksi.DIKEMBALIKAN_UNOR, "pengajuan.kembalikan"), (Aksi.SELESAI, "pengajuan.selesai"),
            (Aksi.LAPORAN_DIUNGGAH, "dokumen.unggah"), (Aksi.PEMBATALAN_DIAJUKAN, "pengajuan.proses"),
        ):
            log = catat_riwayat(request, P, aksi)
            self.assertEqual(log.aktivitas, kode, aksi)
            self.assertIn("PLN01-071026-001", log.deskripsi)
            self.assertEqual((log.target_type, log.target_id), ("pengajuan", "PLN01-071026-001"))


class PemasanganViewTests(TestCase):
    def setUp(self):
        self.pakln = User.objects.create_user(username="adm.pakln", password="x", role="admin_pakln")
        self.client.force_login(self.pakln)
        ActivityLog.objects.all().delete()  # force_login memicu signal login

    def test_master_negara_tambah_toggle_hapus(self):
        self.client.post(reverse("pakln:kelola_negara"), {"nama_negara": "Negara Uji", "is_active": "on"})
        negara = Negara.objects.get(nama_negara="Negara Uji")
        self.client.post(reverse("pakln:toggle_negara", args=[negara.pk]))
        self.client.post(reverse("pakln:hapus_negara", args=[negara.pk]))
        hasil = list(ActivityLog.objects.order_by("pk").values_list("deskripsi", "status", "target_id"))
        self.assertEqual(hasil, [
            ("Menambah negara", "success", ""),
            ("Mengaktifkan/menonaktifkan negara", "success", str(negara.pk)),
            ("Menghapus negara", "success", str(negara.pk)),
        ])

    def test_master_form_tidak_valid_dicatat_gagal(self):
        self.client.post(reverse("pakln:kelola_negara"), {"nama_negara": ""})
        log = ActivityLog.objects.get()
        self.assertEqual((log.aktivitas, log.status, log.detail), ("master.ubah", "failed", "Validasi formulir gagal"))

    def test_membuka_halaman_master_tidak_dicatat(self):
        self.client.get(reverse("pakln:kelola_negara"))
        self.assertEqual(ActivityLog.objects.count(), 0)


class AlurPengajuanTerlogTests(TestCase):
    """Alur kirim -> kembalikan -> teruskan -> selesai meninggalkan jejak di Log Sistem."""

    def setUp(self):
        from pengajuan.tests import _AlurMixin  # pakai ulang data uji alur yang sudah ada

        class Alur(_AlurMixin, TestCase):
            def runTest(self):
                pass

        self.alur = Alur()
        self.alur.client = self.client
        self.alur.setUp()
        ActivityLog.objects.all().delete()

    def test_transisi_status_tercatat_berurutan(self):
        a = self.alur
        a.kirim()
        a.kembalikan_unor()
        a.kirim()
        a.teruskan()
        a.selesaikan()
        kode = a.pengajuan.kode
        urut = [
            (l.aktivitas, l.username, l.status)
            for l in ActivityLog.objects.exclude(aktivitas__startswith="auth.").order_by("pk")
        ]
        self.assertEqual(urut, [
            ("pengajuan.kirim", "pegawai1", "success"),
            ("pengajuan.kembalikan", "unor1", "success"),
            ("pengajuan.kirim", "pegawai1", "success"),
            ("pengajuan.teruskan", "unor1", "success"),
            ("pengajuan.selesai", "pakln1", "success"),
        ])
        self.assertTrue(all(kode in l.deskripsi and l.target_id == kode for l in ActivityLog.objects.exclude(aktivitas__startswith="auth.")))

    def test_catatan_tidak_disalin_ke_log(self):
        from pengajuan.tests import PESAN_UNOR
        a = self.alur
        a.kirim()
        a.kembalikan_unor()
        isi = " ".join(f"{l.deskripsi} {l.detail}" for l in ActivityLog.objects.all())
        self.assertNotIn(PESAN_UNOR, isi)

    def test_unggah_dokumen_tanggal_surat_masa_depan_dicatat_gagal(self):
        from datetime import timedelta

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils import timezone

        from pengajuan import persyaratan

        a = self.alur
        p = a.pengajuan
        p.status = "belum"
        p.save()
        jenis = next(s.jenis for s in persyaratan.daftar_syarat(p, "pegawai") if s.tanggal_surat)
        besok = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.client.force_login(a.pegawai)
        ActivityLog.objects.all().delete()
        r = self.client.post(
            reverse("pegawai:upload_dokumen", args=[p.kode]),
            {"jenis": jenis, "tanggal_surat": besok, "file": SimpleUploadedFile("a.pdf", b"%PDF-1.4", "application/pdf")},
            follow=True,
        )
        self.assertContains(r, "Tanggal surat tidak boleh melebihi hari ini")
        log = ActivityLog.objects.exclude(aktivitas__startswith="auth.").get()
        self.assertEqual((log.aktivitas, log.status, log.target_id), ("dokumen.unggah", "failed", p.kode))
        self.assertIn("tanggal_surat", log.detail)  # nama field, bukan nilainya
        self.assertNotIn(besok, log.detail)
