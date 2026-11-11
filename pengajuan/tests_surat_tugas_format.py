"""Surat Tugas Pimpinan Unor (PDLN Tipe 2) — Modul 5: format Surat Tugas otomatis (WeasyPrint)."""

from datetime import date

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from logs.models import ActivityLog

from . import persyaratan, surat_tugas_format
from .models import DokumenBpsdm, Pengajuan
from .tests_surat_tugas_unor import _DasarUnor

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
TIPE2 = ("T2P", "T2L")
_STORAGES_MEMORI = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}


class _DasarFormat(_DasarUnor):
    def izin_prinsip(self, p, tanggal=date(2026, 10, 5)):
        return DokumenBpsdm.objects.create(pengajuan=p, jenis="izin_prinsip", file="ip.pdf", tanggal_surat=tanggal)

    def url_format(self, p):
        return reverse("unor:unduh_format_surat_tugas", kwargs={"kode": p.kode})

    def post_format(self, p, data=None, user=None):
        self.login(user or self.admin_unor)
        return self.client.post(self.url_format(p), data or {}, follow=True)

    def konteks(self, p, isian=None):
        p = Pengajuan.objects.get(pk=p.pk)         # segarkan agar relasi (dokumen BPSDM, profil) terbaca bersih
        return surat_tugas_format.konteks(p, isian)


class TanggalIndonesiaTests(TestCase):
    def test_format_tanggal(self):
        self.assertEqual(surat_tugas_format.tanggal_indonesia(date(2026, 10, 5)), "5 Oktober 2026")
        self.assertEqual(surat_tugas_format.tanggal_indonesia(date(2026, 1, 31)), "31 Januari 2026")
        self.assertEqual(surat_tugas_format.tanggal_indonesia(date(2026, 12, 1)), "1 Desember 2026")


class KonteksFormatTests(_DasarFormat, TestCase):
    def test_terisi_otomatis_dari_data_pengajuan(self):
        for tipe in TIPE2:
            p = self.pengajuan(tipe, S.PROSES_BPSDM, SS.MENUNGGU)
            self.izin_prinsip(p)
            k = self.konteks(p)
            self.assertEqual(k["pegawai_nama"], "Andra", tipe)
            self.assertEqual(k["pegawai_nip"], "1987")
            self.assertEqual(k["pegawai_pangkat"], "III-d")
            self.assertEqual(k["pegawai_jabatan"], "Kasi")
            self.assertEqual(k["unit_organisasi"], self.unor.name.upper())
            self.assertEqual(k["jenis_tugas"], p.jenis_label)
            self.assertIn("s.d.", k["rentang_tanggal"])
            self.assertIn("(7 hari)", k["rentang_tanggal"])
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_memuat_tanggal_surat_izin_prinsip(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.izin_prinsip(p, date(2026, 10, 5))
        self.assertEqual(self.konteks(p)["tanggal_izin_prinsip"], "5 Oktober 2026")

    def test_tanpa_izin_prinsip_memakai_teks_pengganti(self):
        p = self.pengajuan(jalur="")
        self.assertEqual(self.konteks(p)["tanggal_izin_prinsip"], surat_tugas_format.KOSONG_IZIN_PRINSIP)
        self.assertIsNone(surat_tugas_format.tanggal_izin_prinsip(Pengajuan.objects.get(pk=p.pk)))

    def test_isian_admin_unor_dipakai_dan_yang_kosong_diganti_pengganti(self):
        p = self.pengajuan(jalur=SS.MENUNGGU)
        k = self.konteks(p, {
            "nomor_surat": " ST/12/2026 ", "kota": "Bandung", "tanggal_surat": "2026-11-09",
            "nama_pimpinan": "Dr. Budi", "jabatan_pimpinan": "Sekretaris Direktorat Jenderal",
        })
        self.assertEqual((k["nomor_surat"], k["kota"], k["tanggal_surat"]), ("ST/12/2026", "Bandung", "9 November 2026"))
        self.assertEqual((k["nama_pimpinan"], k["jabatan_pimpinan"]), ("Dr. Budi", "Sekretaris Direktorat Jenderal"))
        kosong = self.konteks(p, {})
        self.assertEqual(kosong["nomor_surat"], surat_tugas_format.KOSONG_NOMOR)
        self.assertEqual(kosong["nama_pimpinan"], surat_tugas_format.KOSONG_NAMA_PIMPINAN)
        self.assertEqual(kosong["jabatan_pimpinan"], surat_tugas_format.KOSONG_JABATAN_PIMPINAN)
        self.assertEqual(kosong["kota"], surat_tugas_format.KOTA_DEFAULT)

    def test_tanggal_surat_tidak_valid_jatuh_ke_hari_ini(self):
        from django.utils import timezone
        p = self.pengajuan(jalur=SS.MENUNGGU)
        hari_ini = surat_tugas_format.tanggal_indonesia(timezone.localdate())
        for salah in ("bukan-tanggal", "", "31/12/2026"):
            self.assertEqual(self.konteks(p, {"tanggal_surat": salah})["tanggal_surat"], hari_ini, salah)

    def test_html_memuat_isi_penting_dan_di_escape(self):
        self.pegawai.profile.nama = "<b>Andra</b>"
        self.pegawai.profile.save()
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.izin_prinsip(p, date(2026, 10, 5))
        html = surat_tugas_format.render_html(Pengajuan.objects.get(pk=p.pk), {"nama_pimpinan": "<i>X</i>"})
        self.assertIn("SURAT TUGAS", html)
        self.assertIn("5 Oktober 2026", html)
        self.assertIn("&lt;b&gt;Andra&lt;/b&gt;", html)
        self.assertIn("&lt;i&gt;X&lt;/i&gt;", html)
        self.assertNotIn("<b>Andra</b>", html)


@override_settings(STORAGES=_STORAGES_MEMORI)
class UnduhFormatTests(_DasarFormat, TestCase):
    def siap(self, tipe="T2P"):
        p = self.pengajuan(tipe, S.PROSES_BPSDM, SS.MENUNGGU)
        self.izin_prinsip(p)
        return p

    def pdf_atau_lewati(self, p, data=None):
        self.login(self.admin_unor)
        resp = self.client.post(self.url_format(p), data or {})
        if resp.status_code == 302:                        # pustaka native WeasyPrint tidak ada di mesin ini
            self.skipTest("WeasyPrint tidak dapat membuat PDF di lingkungan ini")
        return resp

    def test_unduhan_berupa_pdf_dengan_nama_berkas_kode_pengajuan(self):
        for tipe in TIPE2:
            p = self.siap(tipe)
            resp = self.pdf_atau_lewati(p, {"nama_pimpinan": "Dr. Budi"})
            self.assertEqual(resp.status_code, 200, tipe)
            self.assertEqual(resp["Content-Type"], "application/pdf")
            self.assertIn(f'filename="Surat_Tugas_{p.kode}.pdf"', resp["Content-Disposition"])
            self.assertTrue(resp.content.startswith(b"%PDF"))
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_unduhan_dicatat_di_log_sistem(self):
        p = self.siap()
        self.pdf_atau_lewati(p)
        self.assertTrue(ActivityLog.objects.filter(
            aktivitas=ActivityLog.Aktivitas.GENERATE_ND, target_id=p.kode, username=self.admin_unor.username,
        ).exists())

    def test_hanya_metode_post(self):
        p = self.siap()
        self.login(self.admin_unor)
        self.assertEqual(self.client.get(self.url_format(p)).status_code, 405)

    def test_belum_login_pegawai_dan_admin_lain_ditolak(self):
        p = self.siap()
        self.assertEqual(self.client.post(self.url_format(p)).status_code, 302)
        for user in (self.pegawai, self.admin_pakln, self.admin_bpsdm):
            self.assertEqual(self.post_format(p, user=user).status_code, 403, user.role)

    def test_admin_unor_unit_lain_dan_tipe_lain_mendapat_404(self):
        lain = User.objects.create_user("unor2", password="x", role="admin_unor", unit_organisasi=self.unor_lain)
        p = self.siap()
        self.assertEqual(self.post_format(p, user=lain).status_code, 404)
        t1 = self.pengajuan("T1", S.PROSES_PAKLN, "")
        self.assertEqual(self.post_format(t1).status_code, 404)

    def test_ditolak_sebelum_izin_prinsip_ada(self):
        p = self.pengajuan(jalur="")
        resp = self.post_format(p)
        self.assertContains(resp, "setelah Admin BPSDM mengunggah Izin Prinsip")
        self.assertNotEqual(resp.get("Content-Type"), "application/pdf")

    def test_admin_unor_tidak_boleh_untuk_pengajuan_milik_sendiri(self):
        p = self.pengajuan(jalur=SS.MENUNGGU, pegawai=self.admin_unor)
        self.izin_prinsip(p)
        self.assertEqual(self.post_format(p).status_code, 403)


@override_settings(STORAGES=_STORAGES_MEMORI)
class HalamanFormatTests(_DasarFormat, TestCase):
    def test_kotak_format_tampil_selama_surat_tugas_belum_dikirim(self):
        for jalur in (SS.MENUNGGU, SS.DIKEMBALIKAN):
            p = self.pengajuan(jalur=jalur)
            self.izin_prinsip(p)
            resp = self.halaman(p)
            self.assertContains(resp, "Format Surat Tugas Otomatis", msg_prefix=jalur)
            self.assertContains(resp, self.url_format(p))
            self.assertContains(resp, "05 Okt 2026")
            Pengajuan.objects.filter(pk=p.pk).update(status=S.SELESAI)

    def test_kotak_format_tersembunyi_setelah_dikirim_atau_tanpa_izin_prinsip(self):
        terkirim = self.pengajuan(jalur=SS.DIKIRIM)
        self.izin_prinsip(terkirim)
        self.assertNotContains(self.halaman(terkirim), "Format Surat Tugas Otomatis")
        Pengajuan.objects.filter(pk=terkirim.pk).update(status=S.SELESAI)
        tanpa = self.pengajuan(jalur=SS.MENUNGGU)
        self.assertNotContains(self.halaman(tanpa), "Format Surat Tugas Otomatis")

    def test_syarat_surat_tugas_tidak_lagi_menyebut_template_dokumen(self):
        for tipe in TIPE2:
            (syarat,) = persyaratan.daftar_syarat(Pengajuan(jenis_perjalanan="pdln", tipe_pdln=tipe), "surat_tugas")
            self.assertIsNone(syarat.aksi, tipe)
        p = self.pengajuan(jalur=SS.MENUNGGU)
        self.izin_prinsip(p)
        self.assertNotContains(self.halaman(p), "Format tersedia pada")
