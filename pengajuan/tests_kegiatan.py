"""Kegiatan PDLN — wiki/instructions/EVENT_IMPLEMENTATION_PLAN.MD §13."""

import io
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from notifications.models import Notification
from paspor.models import KategoriPerjalanan, Kegiatan, SumberPembiayaan

from .forms import KegiatanForm, dasar_formset
from .models import Pengajuan
from .tests_pdln import _Basis

MB = 1024 * 1024


class _KegiatanBasis(_Basis):
    def kat(self, nama):
        return KategoriPerjalanan.objects.get(jenis_perjalanan="PDLN", nama_kategori=nama)

    def skema(self, nama):
        return SumberPembiayaan.objects.get(tipe_perjalanan="PDLN", nama=nama)

    def data_kegiatan(self, kategori, skema=None, negara=None, dasar=None, **lain):
        mulai = self.berangkat + timedelta(days=1)
        data = {
            "nama": "Workshop Uji", "deskripsi": "", "kota": "Tokyo", "penyelenggara": "JICA",
            "tgl_mulai": mulai.isoformat(), "tgl_selesai": (mulai + timedelta(days=3)).isoformat(),
            "negara": [n.pk for n in (negara or [self.jepang])],
            "kategori": [k.pk for k in kategori],
            "skema_pendanaan": [s.pk for s in (skema or [self.skema("Beasiswa Lainnya")])],
            "dasar-TOTAL_FORMS": "1", "dasar-INITIAL_FORMS": "0", "dasar-MIN_NUM_FORMS": "1", "dasar-MAX_NUM_FORMS": "1000",
            "dasar-0-jenis": "surat", "dasar-0-nomor_surat": "UND/2027/01",
        }
        data.update(dasar or {})
        data.update(lain)
        return data

    def form_valid(self, data, peran="admin_pakln", files=None):
        form = KegiatanForm(data, files, peran=peran)
        formset = dasar_formset(data, files)
        return form, formset, form.is_valid() and formset.is_valid()


class AturanKegiatanTests(_KegiatanBasis, TestCase):
    def test_pakln_buat_kegiatan_dua_kategori_non_pendidikan(self):  # #1
        data = self.data_kegiatan([self.kat("Workshop"), self.kat("Seminar/Lokakarya")])
        resp = self.post(self.admin_pakln, "pakln:tambah_kegiatan", data)
        self.assertEqual(resp.status_code, 302)
        k = Kegiatan.objects.get(nama="Workshop Uji")
        self.assertEqual(k.status, Kegiatan.Status.DISETUJUI)
        self.assertEqual(k.sumber_data, Kegiatan.SumberData.MANUAL)
        self.assertEqual(k.tahun_pelaksanaan, (self.berangkat + timedelta(days=1)).year)  # B9
        self.assertEqual(k.dasar_list.get().nomor_surat, "UND/2027/01")

    def test_pendidikan_hanya_satu_kategori(self):  # #2 (B4)
        form, _, ok = self.form_valid(self.data_kegiatan([self.kat("Master"), self.kat("Pameran/Expo")]))
        self.assertFalse(ok)
        self.assertIn("kategori", form.errors)

    def test_kategori_dan_skema_non_dinas_ditolak(self):  # #3
        nd_kat = KategoriPerjalanan.objects.create(nama_kategori="Ibadah Uji", jenis_perjalanan="Non-Dinas")
        nd_skema = SumberPembiayaan.objects.create(nama="Biaya Sendiri Uji", tipe_perjalanan="Non-Dinas")
        form, _, ok = self.form_valid(self.data_kegiatan([nd_kat], skema=[nd_skema]))
        self.assertFalse(ok)
        self.assertIn("kategori", form.errors)
        self.assertIn("skema_pendanaan", form.errors)

    def test_tanggal_selesai_sebelum_mulai(self):  # #4
        data = self.data_kegiatan([self.kat("Workshop")], tgl_selesai=self.berangkat.isoformat())
        form, _, ok = self.form_valid(data)
        self.assertFalse(ok)
        self.assertIn("tgl_selesai", form.errors)

    def test_tanpa_dasar_ditolak(self):  # #20 (B15)
        data = self.data_kegiatan([self.kat("Workshop")], dasar={"dasar-0-jenis": "", "dasar-0-nomor_surat": ""})
        _, formset, ok = self.form_valid(data)
        self.assertFalse(ok)

    def test_dasar_wajib_sesuai_jenis(self):  # #21
        for dasar in ({"dasar-0-jenis": "surat", "dasar-0-nomor_surat": ""},
                      {"dasar-0-jenis": "tautan", "dasar-0-nomor_surat": "", "dasar-0-tautan": "bukan url"}):
            with self.subTest(dasar=dasar):
                _, formset, ok = self.form_valid(self.data_kegiatan([self.kat("Workshop")], dasar=dasar))
                self.assertFalse(ok)
                self.assertTrue(formset.forms[0].errors)

    def test_berkas_dasar_maks_2mb_dan_pdf(self):  # #22
        data = self.data_kegiatan([self.kat("Workshop")])
        for berkas in (SimpleUploadedFile("a.pdf", b"%PDF-1.4" + b"0" * (2 * MB), content_type="application/pdf"),
                       SimpleUploadedFile("a.docx", b"isi", content_type="application/msword")):
            with self.subTest(berkas=berkas.name):
                _, formset, ok = self.form_valid(data, files={"dasar-0-berkas": berkas})
                self.assertFalse(ok)
                self.assertIn("berkas", formset.forms[0].errors)

    def test_hapus_dasar_terakhir_ditolak(self):  # #23
        self.post(self.admin_pakln, "pakln:tambah_kegiatan", self.data_kegiatan([self.kat("Workshop")]))
        k = Kegiatan.objects.get(nama="Workshop Uji")
        dasar = k.dasar_list.get()
        data = self.data_kegiatan([self.kat("Workshop")], **{
            "dasar-INITIAL_FORMS": "1", "dasar-0-id": str(dasar.pk), "dasar-0-kegiatan": str(k.pk), "dasar-0-DELETE": "on",
        })
        resp = self.post(self.admin_pakln, "pakln:edit_kegiatan", data, pk=k.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(k.dasar_list.exists())

    def test_kode_pintar_unik(self):  # #19
        data = self.data_kegiatan([self.kat("Workshop")], kode_pintar="PINTAR-1")
        self.post(self.admin_pakln, "pakln:tambah_kegiatan", data)
        form, _, ok = self.form_valid(data)
        self.assertFalse(ok)
        self.assertIn("kode_pintar", form.errors)


class UsulanKegiatanTests(_KegiatanBasis, TestCase):
    def test_pegawai_usulkan_lalu_disetujui(self):  # #5, #6
        resp = self.post(self.pegawai, "pegawai:usulkan_kegiatan", self.data_kegiatan([self.kat("Workshop")]))
        self.assertEqual(resp.status_code, 302)
        k = Kegiatan.objects.get(nama="Workshop Uji")
        self.assertEqual((k.status, k.sumber_data, k.diusulkan_oleh), (Kegiatan.Status.MENUNGGU, Kegiatan.SumberData.USULAN_PEGAWAI, self.pegawai))
        self.assertTrue(Notification.objects.filter(recipient=self.admin_pakln, event=Notification.Event.KEGIATAN_DIUSULKAN).exists())
        self.assertNotIn(k, Kegiatan.objects.dapat_dipilih(tipe="T2L"))
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query="?jenis=pdln&tipe=T2L")
        self.assertNotIn(k, resp.context["form"].fields["kegiatan"].queryset)
        self.assertContains(resp, "menunggu persetujuan")

        self.post(self.admin_pakln, "pakln:putuskan_kegiatan", {"keputusan": "setujui"}, pk=k.pk)
        k.refresh_from_db()
        self.assertEqual(k.status, Kegiatan.Status.DISETUJUI)
        self.assertIn(k, Kegiatan.objects.dapat_dipilih(tipe="T2L"))
        self.assertTrue(Notification.objects.filter(recipient=self.pegawai, event=Notification.Event.KEGIATAN_DISETUJUI).exists())

    def test_pegawai_tanpa_pilihan_aplikasi_pintar(self):
        resp = self.get(self.pegawai, "pegawai:usulkan_kegiatan")
        jenis = [c[0] for c in resp.context["formset"].forms[0].fields["jenis"].choices]
        self.assertNotIn("pintar", jenis)
        self.assertNotContains(resp, "Aplikasi PINTAR")
        data = self.data_kegiatan([self.kat("Workshop")], dasar={"dasar-0-jenis": "pintar", "dasar-0-kode_pintar": "X-1"})
        self.assertEqual(self.post(self.pegawai, "pegawai:usulkan_kegiatan", data).status_code, 200)
        self.assertFalse(Kegiatan.objects.exists())
        # Admin tetap dapat memakai dasar PINTAR.
        self.assertIn("pintar", [c[0] for c in self.get(self.admin_pakln, "pakln:tambah_kegiatan")
                                 .context["formset"].forms[0].fields["jenis"].choices])

    def test_tolak_wajib_catatan(self):  # #7
        self.post(self.pegawai, "pegawai:usulkan_kegiatan", self.data_kegiatan([self.kat("Workshop")]))
        k = Kegiatan.objects.get(nama="Workshop Uji")
        self.post(self.admin_pakln, "pakln:putuskan_kegiatan", {"keputusan": "tolak"}, pk=k.pk)
        k.refresh_from_db()
        self.assertEqual(k.status, Kegiatan.Status.MENUNGGU)
        self.post(self.admin_pakln, "pakln:putuskan_kegiatan", {"keputusan": "tolak", "catatan": "Gunakan kegiatan X"}, pk=k.pk)
        k.refresh_from_db()
        self.assertEqual((k.status, k.catatan_keputusan), (Kegiatan.Status.DITOLAK, "Gunakan kegiatan X"))
        notif = Notification.objects.get(recipient=self.pegawai, event=Notification.Event.KEGIATAN_DITOLAK)
        self.assertIn("Gunakan kegiatan X", notif.body)
        self.assertContains(self.get(self.pegawai, "pegawai:beranda"), "Gunakan kegiatan X")

    def test_bpsdm_usulkan_pelatihan(self):  # #24, #26
        resp = self.post(self.admin_bpsdm, "bpsdm:tambah_kegiatan",
                         self.data_kegiatan([self.kat("Workshop"), self.kat("Seminar/Lokakarya")]))
        self.assertEqual(resp.status_code, 302)
        k = Kegiatan.objects.get(nama="Workshop Uji")
        self.assertEqual((k.status, k.sumber_data), (Kegiatan.Status.MENUNGGU, Kegiatan.SumberData.USULAN_BPSDM))
        self.assertNotIn(k, Kegiatan.objects.dapat_dipilih(tipe="T2L"))
        self.post(self.admin_pakln, "pakln:putuskan_kegiatan", {"keputusan": "setujui"}, pk=k.pk)
        self.assertIn(k, Kegiatan.objects.dapat_dipilih(tipe="T2L"))
        self.assertTrue(Notification.objects.filter(recipient=self.admin_bpsdm, event=Notification.Event.KEGIATAN_DISETUJUI).exists())

    def test_bpsdm_tidak_boleh_kategori_t1_t3(self):  # #25 (B10a)
        form, _, ok = self.form_valid(self.data_kegiatan([self.kat("Pertemuan Bilateral/Regional/Multilateral")]), peran="admin_bpsdm")
        self.assertFalse(ok)
        self.assertIn("kategori", form.errors)

    def test_bpsdm_tidak_boleh_sunting_usulan_diputus_atau_milik_lain(self):  # #27
        self.post(self.admin_bpsdm, "bpsdm:tambah_kegiatan", self.data_kegiatan([self.kat("Workshop")]))
        k = Kegiatan.objects.get(nama="Workshop Uji")
        lain = User.objects.create_user("bpsdm2", password="x", role="admin_bpsdm")
        self.assertEqual(self.post(lain, "bpsdm:edit_kegiatan", self.data_kegiatan([self.kat("Workshop")]), pk=k.pk).status_code, 403)
        self.post(self.admin_pakln, "pakln:putuskan_kegiatan", {"keputusan": "setujui"}, pk=k.pk)
        self.assertEqual(self.post(self.admin_bpsdm, "bpsdm:edit_kegiatan", self.data_kegiatan([self.kat("Workshop")]), pk=k.pk).status_code, 403)
        self.assertEqual(self.get(self.admin_bpsdm, "bpsdm:edit_kegiatan", pk=k.pk).status_code, 200)  # read-only

    def test_halaman_daftar_dan_data(self):
        self.buat_kegiatan("T2L")
        for user, halaman, data in ((self.admin_pakln, "pakln:kelola_kegiatan", "pakln:kegiatan_data"),
                                    (self.admin_bpsdm, "bpsdm:kegiatan", "bpsdm:kegiatan_data")):
            with self.subTest(halaman=halaman):
                self.assertEqual(self.get(user, halaman).status_code, 200)
                self.assertEqual(self.get(user, data).json()["recordsTotal"], 1)
        self.assertEqual(self.get(self.admin_pakln, "pakln:kegiatan_data", query="?tab=menunggu").json()["recordsTotal"], 0)
        self.assertEqual(self.get(self.pegawai, "pakln:kelola_kegiatan").status_code, 403)


class PemilihanKegiatanTests(_KegiatanBasis, TestCase):
    def kirim_formulir(self, tipe, kegiatan, **lain):
        data = {
            "kategori": self.kategori(tipe).pk, "kegiatan": kegiatan.pk if kegiatan else "",
            "tujuan_negara": [self.singapura.pk], "sumber_pembiayaan": self.sumber(tipe).pk,
            "tgl_berangkat": self.berangkat.isoformat(), "tgl_kembali": (self.berangkat + timedelta(days=6)).isoformat(),
            "keterangan_sumber_pembiayaan": "Biaya Uji",   # kolom wajib sejak form PDLN menambahkannya
            "pernyataan_benar": "on",
        }
        data.update(lain)
        self.login(self.pegawai)
        return self.client.post(reverse("pegawai:formulir_pengajuan") + f"?jenis=pdln&tipe={tipe}", data)

    def test_opsi_disaring_aktif_dan_belum_lewat(self):  # #8 (B2, B14)
        k = self.buat_kegiatan("T1")
        self.assertIn(k, Kegiatan.objects.dapat_dipilih(tipe="T1"))
        self.assertNotIn(k, Kegiatan.objects.dapat_dipilih(tipe="T2P"))
        k.is_active = False
        k.save()
        self.assertNotIn(k, Kegiatan.objects.dapat_dipilih(tipe="T1"))
        k.is_active, k.tgl_selesai, k.tgl_mulai = True, self.berangkat - timedelta(days=60), self.berangkat - timedelta(days=61)
        k.save()
        self.assertNotIn(k, Kegiatan.objects.dapat_dipilih(tipe="T1"))

    def test_kegiatan_tanpa_kategori_skema_tidak_ditawarkan(self):  # #18
        k = self.buat_kegiatan("T1")
        k.skema_pendanaan.clear()
        self.assertNotIn(k, Kegiatan.objects.dapat_dipilih(tipe="T1"))

    def test_kategori_bukan_kategori_kegiatan(self):  # #9 (B5)
        k = self.buat_kegiatan("T1")
        lain = next(x for x in KategoriPerjalanan.objects.filter(jenis_perjalanan="PDLN")
                    if "T1" in x.tipe_pdln and x != self.kategori("T1"))
        resp = self.kirim_formulir("T1", k, kategori=lain.pk)
        self.assertIn("kegiatan", resp.context["form"].errors)

    def test_sumber_di_luar_skema(self):  # #10 (B6)
        k = self.buat_kegiatan("T1")
        lain = next(s for s in SumberPembiayaan.objects.filter(tipe_perjalanan="PDLN")
                    if (not s.tipe_pdln or "T1" in s.tipe_pdln) and s != self.sumber("T1"))
        resp = self.kirim_formulir("T1", k, sumber_pembiayaan=lain.pk)
        self.assertIn("sumber_pembiayaan", resp.context["form"].errors)

    def test_negara_kegiatan_masuk_negara_tujuan(self):  # #11 (B7)
        k = self.buat_kegiatan("T1", negara=self.jepang)
        korea = self.jepang.__class__.objects.create(nama_negara="Korea Uji")
        k.negara.add(korea)
        self.assertEqual(self.kirim_formulir("T1", k).status_code, 302)
        p = Pengajuan.objects.get(pegawai=self.pegawai)
        self.assertEqual(set(p.tujuan_negara.all()), {self.singapura, self.jepang, korea})

    def test_pesan_kolom_wajib_menyebut_nama_field(self):
        k = self.buat_kegiatan("T1")
        resp = self.kirim_formulir("T1", k, kategori="", tgl_berangkat="", tgl_kembali="", sumber_pembiayaan="",
                                   keterangan_sumber_pembiayaan="")
        err = resp.context["form"].errors
        self.assertEqual(err["kategori"], ["Kategori Perjalanan Tidak Boleh Kosong"])
        self.assertEqual(err["tgl_berangkat"], ["Tanggal Keberangkatan Tidak Boleh Kosong"])
        self.assertEqual(err["tgl_kembali"], ["Tanggal Kepulangan Tidak Boleh Kosong"])
        self.assertEqual(err["sumber_pembiayaan"], ["Sumber Biaya Tidak Boleh Kosong"])
        self.assertEqual(err["keterangan_sumber_pembiayaan"], ["Keterangan Sumber Pembiayaan Tidak Boleh Kosong"])

    def test_pesan_kategori_wajib_mengikuti_tipe(self):
        for tipe, nama in (("T2P", "Pendidikan"), ("T2L", "Pelatihan")):
            resp = self.kirim_formulir(tipe, self.buat_kegiatan(tipe), kategori="")
            self.assertEqual(resp.context["form"].errors["kategori"], [f"Kategori {nama} Tidak Boleh Kosong"])

    def test_berangkat_setelah_mulai_kegiatan_ditolak(self):  # #12 (B8)
        k = self.buat_kegiatan("T1")
        resp = self.kirim_formulir("T1", k, tgl_berangkat=(k.tgl_mulai + timedelta(days=1)).isoformat())
        form = resp.context["form"]
        self.assertIn("tgl_berangkat", form.errors)
        self.assertNotIn("tgl_kembali", form.errors)
        self.assertIn("tidak boleh melewati tanggal mulai kegiatan", form.errors["tgl_berangkat"][0])
        self.assertFalse(form.non_field_errors())

    def test_kembali_sebelum_selesai_kegiatan_ditolak(self):
        k = self.buat_kegiatan("T1")
        resp = self.kirim_formulir("T1", k, tgl_kembali=(k.tgl_selesai - timedelta(days=1)).isoformat())
        form = resp.context["form"]
        self.assertIn("tgl_kembali", form.errors)
        self.assertNotIn("tgl_berangkat", form.errors)
        self.assertIn("tidak boleh sebelum tanggal selesai kegiatan", form.errors["tgl_kembali"][0])

    def test_kedua_tanggal_salah_menghasilkan_dua_error_terpisah(self):
        k = self.buat_kegiatan("T1")
        resp = self.kirim_formulir("T1", k, tgl_berangkat=(k.tgl_mulai + timedelta(days=1)).isoformat(),
                                   tgl_kembali=(k.tgl_selesai + timedelta(days=-1)).isoformat())
        self.assertTrue({"tgl_berangkat", "tgl_kembali"} <= set(resp.context["form"].errors))

    def test_tanggal_tepat_di_batas_kegiatan_diterima(self):
        k = self.buat_kegiatan("T1")
        resp = self.kirim_formulir("T1", k, tgl_berangkat=k.tgl_mulai.isoformat(), tgl_kembali=k.tgl_selesai.isoformat())
        self.assertEqual(resp.status_code, 302)

    def test_dua_pegawai_kegiatan_sama_dan_snapshot(self):  # #13, #14 (B3, B13)
        p = self.isi_formulir("T1")
        k = p.kegiatan
        self.kirim(p)
        p2_user = User.objects.create_user("peg2", password="x", role="pegawai")
        p2 = Pengajuan.objects.create(pegawai=p2_user, jenis_perjalanan="pdln", tipe_pdln="T1", kegiatan=k)
        self.assertEqual(k.pengajuan_list.count(), 2)
        k.tgl_mulai = k.tgl_mulai + timedelta(days=1)
        k.nama = "Nama Baru"
        k.save()
        p.refresh_from_db()
        self.assertEqual(p.detail.kegiatan_nama, "Kegiatan Uji T1")
        self.assertEqual(p.detail.tgl_mulai_kegiatan, self.berangkat + timedelta(days=1))
        self.assertTrue(p2.pk)

    def test_kegiatan_terpakai_tidak_dapat_dihapus(self):  # #15 (B12)
        p = self.isi_formulir("T1")
        with self.assertRaises(ProtectedError):
            p.kegiatan.delete()
        resp = self.post(self.admin_pakln, "pakln:hapus_kegiatan", pk=p.kegiatan.pk)
        self.assertEqual(resp.status_code, 400)

    def test_draft_tanpa_kegiatan_boleh_tetapi_kirim_ditolak(self):  # #17 (B1)
        self.assertEqual(self.kirim_formulir("T1", None).status_code, 302)
        p = Pengajuan.objects.get(pegawai=self.pegawai)
        self.assertIsNone(p.kegiatan)
        self.kirim(p)
        p.refresh_from_db()
        self.assertEqual(p.status, Pengajuan.Status.BELUM)


class SeedKegiatanTests(TestCase):
    def test_seed_lima_per_tipe_dan_idempoten(self):
        User.objects.create_user("andra.wibisono", password="x", role="pegawai")
        call_command("seed_kegiatan", stdout=io.StringIO())
        self.assertEqual(Kegiatan.objects.filter(status="disetujui").count(), 20)
        self.assertEqual(Kegiatan.objects.filter(status="menunggu").count(), 1)  # admin.bpsdm tidak ada
        self.assertEqual(Kegiatan.objects.dapat_dipilih(tipe="T2P").count(), 5)
        self.assertEqual(Kegiatan.objects.dapat_dipilih(tipe="T2L").count(), 5)
        self.assertTrue(all(k.dasar_list.exists() for k in Kegiatan.objects.all()))
        call_command("seed_kegiatan", stdout=io.StringIO())
        self.assertEqual(Kegiatan.objects.count(), 21)
