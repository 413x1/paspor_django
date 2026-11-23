"""Revisi Pegawai Poin 4: pengajuan ILN (Non-Dinas) dan PDLN boleh berjalan paralel.

Aturan lama "satu pengajuan aktif" (BISNIS_PROSES_PDLN.MD §2.1) dihapus: pegawai boleh memiliki banyak draft dan
pengajuan yang sedang diproses sekaligus. Satu-satunya yang masih menahan pengajuan baru adalah PDLN yang sudah
selesai tetapi laporannya belum disetujui (kewajiban lapor, §4.4). Draft yang dilanjutkan dipilih lewat `?kode=`."""

import json
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from accounts.models import PegawaiProfile, User
from paspor.models import KategoriPerjalanan, SumberPembiayaan

from . import alur
from .models import LaporanPdln, Pengajuan
from .tests_pdln import _Basis

S = Pengajuan.Status


class ParalelBase(_Basis, TestCase):
    def isi_nondinas(self, maksud="Ibadah umrah"):
        """Buat pengajuan Non-Dinas (ILN) BARU lewat formulir (tanpa kode)."""
        kategori = KategoriPerjalanan.objects.filter(jenis_perjalanan="Non-Dinas").first()
        sumber = SumberPembiayaan.objects.filter(tipe_perjalanan="Non-Dinas").first()
        data = {
            "kategori": kategori.pk, "maksud": maksud, "tujuan_negara": [self.jepang.pk], "sumber_pembiayaan": sumber.pk,
            "tgl_berangkat": self.berangkat.isoformat(), "tgl_kembali": (self.berangkat + timedelta(days=4)).isoformat(),
        }
        self.login(self.pegawai)
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas", data)
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["form"].errors)
        return Pengajuan.objects.filter(pegawai=self.pegawai).latest("created_at")

    def beranda(self):
        return self.get(self.pegawai, "pegawai:beranda")

    def pegawai_lain(self):
        user = User.objects.create_user("peg2", password="x", role="pegawai")
        PegawaiProfile.objects.create(
            user=user, nip="1988", nama="Budi", jabatan="Staf", pangkat_golongan="III-a",
            unit_kerja="Biro", unit_organisasi=self.unor, sisa_cuti_tahun_berjalan=12,
        )
        return user


class PembuatanParalelTests(ParalelBase):
    def test_banyak_draft_sekaligus_iln_dan_pdln(self):
        a = self.isi_formulir("T1")
        b = self.isi_nondinas()
        c = self.isi_formulir("T3")
        draft = Pengajuan.objects.filter(pegawai=self.pegawai)
        self.assertEqual(draft.count(), 3)
        self.assertEqual(set(draft.values_list("status", flat=True)), {S.BELUM})
        self.assertEqual({p.kode for p in alur.pengajuan_aktif(self.pegawai)}, {a.kode, b.kode, c.kode})
        self.assertIsNone(alur.penahan_pengajuan_baru(self.pegawai))

    def test_pengajuan_baru_saat_ada_pengajuan_diproses_tidak_dialihkan(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.assertEqual(self.refresh(p).status, S.PROSES)
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query="?jenis=nondinas")
        self.assertEqual(resp.status_code, 200)                     # form baru terbuka, tidak ke beranda
        iln = self.isi_nondinas()
        self.assertEqual(Pengajuan.objects.filter(pegawai=self.pegawai).count(), 2)
        self.assertEqual(self.refresh(p).status, S.PROSES)           # pengajuan lama tidak terganggu
        self.assertEqual(iln.status, S.BELUM)

    def test_iln_dan_pdln_sama_sama_diproses(self):
        pdln = self.isi_formulir("T1")
        self.kirim(pdln)
        iln = self.isi_nondinas()
        self.kirim(iln)
        self.assertEqual((self.refresh(pdln).status, self.refresh(iln).status), (S.PROSES, S.PROSES))
        self.assertEqual({p.kode for p in alur.pengajuan_aktif(self.pegawai)}, {pdln.kode, iln.kode})
        self.assertIsNone(alur.penahan_pengajuan_baru(self.pegawai))

    def test_dua_pdln_diproses_bersamaan(self):
        a = self.isi_formulir("T1")
        self.kirim(a)
        b = self.isi_formulir("T3")
        self.kirim(b)
        self.assertEqual(Pengajuan.objects.filter(pegawai=self.pegawai, status=S.PROSES).count(), 2)

    def test_pengajuan_baru_tidak_menimpa_draft_lama(self):
        lama = self.isi_formulir("T1")
        baru = self.isi_nondinas()
        self.assertNotEqual(lama.pk, baru.pk)
        self.assertEqual((self.refresh(lama).jenis_perjalanan, self.refresh(lama).tipe_pdln), ("pdln", "T1"))

    def test_pegawai_lain_tidak_terpengaruh(self):
        self.isi_formulir("T1")
        lain = self.pegawai_lain()
        self.assertEqual(alur.pengajuan_aktif(lain), [])
        self.assertIsNone(alur.penahan_pengajuan_baru(lain))


class MelanjutkanDraftTests(ParalelBase):
    def test_draft_dipilih_lewat_kode(self):
        a = self.isi_formulir("T1")
        b = self.isi_nondinas()
        resp_a = self.get(self.pegawai, "pegawai:formulir_pengajuan", query=f"?kode={a.kode}")
        resp_b = self.get(self.pegawai, "pegawai:formulir_pengajuan", query=f"?kode={b.kode}")
        self.assertEqual((resp_a.status_code, resp_b.status_code), (200, 200))
        self.assertEqual(resp_a.context["form"].instance.pk, a.pk)
        self.assertEqual(resp_a.context["tipe"], "T1")
        self.assertEqual(resp_b.context["form"].instance.pk, b.pk)

    def test_tanpa_kode_selalu_pengajuan_baru(self):
        self.isi_formulir("T1")
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query="?jenis=nondinas")
        self.assertIsNone(resp.context["form"].instance.pk)

    def test_simpan_draft_tertentu_tidak_mengubah_draft_lain(self):
        a = self.isi_nondinas("Maksud A")
        b = self.isi_nondinas("Maksud B")
        data = {
            "kategori": a.kategori_id, "maksud": "Maksud A diubah", "tujuan_negara": [self.jepang.pk],
            "sumber_pembiayaan": a.sumber_pembiayaan_id, "tgl_berangkat": a.tgl_berangkat.isoformat(),
            "tgl_kembali": a.tgl_kembali.isoformat(),
        }
        self.login(self.pegawai)
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + f"?kode={a.kode}", data)
        self.assertRedirects(resp, reverse("pegawai:upload_dokumen", kwargs={"kode": a.kode}), fetch_redirect_response=False)
        self.assertEqual(Pengajuan.objects.filter(pegawai=self.pegawai).count(), 2)
        self.assertEqual((self.refresh(a).maksud, self.refresh(b).maksud), ("Maksud A diubah", "Maksud B"))

    def test_kode_tidak_ada_atau_milik_orang_lain_404(self):
        lain = self.pegawai_lain()
        milik_lain = Pengajuan.objects.create(pegawai=lain, form_saved=True, jenis_perjalanan="nondinas")
        for kode in ("PLN01-010199-001", milik_lain.kode):
            with self.subTest(kode=kode):
                resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query=f"?kode={kode}")
                self.assertEqual(resp.status_code, 404)

    def test_pengajuan_terkirim_tidak_bisa_dibuka_lewat_formulir(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query=f"?kode={p.kode}")
        self.assertRedirects(resp, reverse("pegawai:beranda"))

    def test_upload_tanpa_form_tersimpan_diarahkan_ke_formulir_draft_itu(self):
        p = Pengajuan.objects.create(pegawai=self.pegawai, form_saved=False, jenis_perjalanan="nondinas")
        resp = self.get(self.pegawai, "pegawai:upload_dokumen", kode=p.kode)
        self.assertRedirects(resp, reverse("pegawai:formulir_pengajuan") + f"?kode={p.kode}", fetch_redirect_response=False)

    def test_tombol_kembali_dan_usulkan_kegiatan_membawa_kode(self):
        p = self.isi_formulir("T1")
        upload = self.get(self.pegawai, "pegawai:upload_dokumen", kode=p.kode).content.decode()
        self.assertIn(f'href="{reverse("pegawai:formulir_pengajuan")}?kode={p.kode}" class="button is-light"', upload)
        formulir = self.get(self.pegawai, "pegawai:formulir_pengajuan", query=f"?kode={p.kode}").content.decode()
        self.assertIn(f"?tipe=T1&amp;kode={p.kode}", formulir)             # "Usulkan kegiatan baru"
        usul = self.get(self.pegawai, "pegawai:usulkan_kegiatan", query=f"?tipe=T1&kode={p.kode}")
        self.assertEqual(usul.context["kembali_url"], reverse("pegawai:formulir_pengajuan") + f"?kode={p.kode}")
        self.assertContains(usul, f'<input type="hidden" name="kode" value="{p.kode}">')


class BerandaDanRiwayatTests(ParalelBase):
    def test_tombol_tambah_aktif_dan_semua_pengajuan_aktif_tampil(self):
        a = self.isi_formulir("T1")
        b = self.isi_nondinas()
        self.kirim(a)
        html = self.beranda().content.decode()
        self.assertIn('data-modal-open="jenisModal"', html)                   # tombol tambah aktif
        self.assertIn('id="jenisModal"', html)                                # modal pilihan jenis tersedia
        self.assertNotIn("belum dapat mengajukan perjalanan baru", html)
        aktif = html.split("Pengajuan Aktif")[1]
        self.assertIn(a.kode, aktif)
        self.assertIn(b.kode, aktif)
        self.assertIn('<span class="badge-auto">2</span>', aktif)
        self.assertIn(reverse("pegawai:upload_dokumen", kwargs={"kode": b.kode}), aktif)     # draft: lanjutkan unggah
        self.assertIn(reverse("pegawai:monitor_progres", kwargs={"kode": a.kode}), aktif)    # diproses: lihat progres

    def test_draft_yang_formulirnya_belum_tersimpan_dilanjutkan_lewat_kode(self):
        p = Pengajuan.objects.create(pegawai=self.pegawai, form_saved=False, jenis_perjalanan="nondinas")
        html = self.beranda().content.decode()
        self.assertIn(f'{reverse("pegawai:formulir_pengajuan")}?kode={p.kode}', html)

    def test_catatan_perbaikan_unor_tampil_per_pengajuan(self):
        a = self.isi_formulir("T1")
        b = self.isi_nondinas()
        Pengajuan.objects.filter(pk=a.pk).update(catatan_unor="Lengkapi surat tugas A", tgl_pengajuan=date.today())
        Pengajuan.objects.filter(pk=b.pk).update(catatan_unor="Perbaiki maksud B", tgl_pengajuan=date.today())
        html = self.beranda().content.decode()
        for kode, catatan in ((a.kode, "Lengkapi surat tugas A"), (b.kode, "Perbaiki maksud B")):
            self.assertIn(f"Dikembalikan oleh Admin Unor untuk diperbaiki ({kode}):</strong> {catatan}", html)

    def test_riwayat_hanya_memuat_yang_tuntas_dan_tidak_duplikat_dengan_aktif(self):
        aktif = self.isi_nondinas()
        selesai = Pengajuan.objects.create(
            pegawai=self.pegawai, form_saved=True, jenis_perjalanan="nondinas", status=S.SELESAI,
            tgl_pengajuan=date.today(), tgl_berangkat=date.today(), tgl_kembali=date.today(),
        )
        batal = Pengajuan.objects.create(
            pegawai=self.pegawai, form_saved=True, jenis_perjalanan="nondinas", status=S.DIBATALKAN, tgl_pengajuan=date.today(),
        )
        self.login(self.pegawai)
        data = self.client.get(reverse("pegawai:riwayat_data"), {"draw": 1, "start": 0, "length": 25, "jenis": "nondinas"}).json()
        teks = json.dumps(data["data"])
        self.assertIn(selesai.kode, teks)
        self.assertIn(batal.kode, teks)
        self.assertNotIn(aktif.kode, teks)
        self.assertEqual(data["recordsTotal"], 2)

    def test_pelaporan_tetap_menampilkan_pdln_selesai_walau_ada_pengajuan_lain(self):
        self.isi_nondinas()
        resp = self.get(self.pegawai, "pegawai:pelaporan")
        self.assertEqual(resp.status_code, 200)


class HalamanDetailAmanTests(ParalelBase):
    """Semua halaman detail memakai `kode`, jadi banyak pengajuan sekaligus tidak memicu MultipleObjectsReturned."""

    def test_semua_halaman_per_pengajuan_terbuka_untuk_setiap_kode(self):
        daftar = [self.isi_formulir("T1"), self.isi_nondinas(), self.isi_formulir("T3"), self.isi_formulir("T2P")]
        self.kirim(daftar[0])
        for p in daftar:
            for nama in ("upload_dokumen", "monitor_progres"):
                with self.subTest(kode=p.kode, halaman=nama):
                    resp = self.get(self.pegawai, f"pegawai:{nama}", kode=p.kode)
                    self.assertIn(resp.status_code, (200, 302))
                    if resp.status_code == 200:
                        self.assertContains(resp, p.kode)

    def test_halaman_lain_tetap_terbuka_dengan_banyak_pengajuan(self):
        for _ in range(2):
            self.isi_nondinas()
        self.isi_formulir("T1")
        for nama in ("beranda", "pelaporan", "pembatalan"):
            with self.subTest(halaman=nama):
                self.assertEqual(self.get(self.pegawai, f"pegawai:{nama}").status_code, 200)


class KewajibanLaporTetapMenahanTests(ParalelBase):
    def pdln_selesai_tanpa_laporan(self):
        p = self.isi_formulir("T1")
        self.kirim(p)
        self.unor_teruskan(p)
        self.pakln_selesai(p, kecuali=("visa",))
        self.assertEqual(self.refresh(p).status, S.SELESAI)
        return p

    def test_pdln_selesai_dengan_laporan_belum_disetujui_menahan_pengajuan_baru(self):
        p = self.pdln_selesai_tanpa_laporan()
        self.assertEqual(alur.penahan_pengajuan_baru(self.pegawai), p)
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query="?jenis=nondinas")
        self.assertRedirects(resp, reverse("pegawai:beranda"))
        beranda = self.beranda()
        self.assertContains(beranda, "belum dapat mengajukan perjalanan baru")
        self.assertContains(beranda, f"Laporan PDLN untuk {p.kode} belum diunggah.")
        self.assertContains(beranda, 'disabled title="Laporan PDLN untuk')
        self.assertNotContains(beranda, 'id="jenisModal"')

    def test_menyimpan_pengajuan_baru_juga_ditolak_saat_ada_penahan(self):
        self.pdln_selesai_tanpa_laporan()
        sebelum = Pengajuan.objects.filter(pegawai=self.pegawai).count()
        kategori = KategoriPerjalanan.objects.filter(jenis_perjalanan="Non-Dinas").first()
        sumber = SumberPembiayaan.objects.filter(tipe_perjalanan="Non-Dinas").first()
        data = {
            "kategori": kategori.pk, "maksud": "Umrah", "tujuan_negara": [self.jepang.pk], "sumber_pembiayaan": sumber.pk,
            "tgl_berangkat": self.berangkat.isoformat(), "tgl_kembali": (self.berangkat + timedelta(days=4)).isoformat(),
        }
        self.login(self.pegawai)                                    # alur penyelesaian di atas berakhir sebagai Admin PAKLN
        resp = self.client.post(reverse("pegawai:formulir_pengajuan") + "?jenis=nondinas", data)
        self.assertRedirects(resp, reverse("pegawai:beranda"))
        self.assertEqual(Pengajuan.objects.filter(pegawai=self.pegawai).count(), sebelum)

    def test_draft_lama_masih_bisa_dilanjutkan_saat_ada_penahan(self):
        draft = self.isi_nondinas()
        self.pdln_selesai_tanpa_laporan()
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query=f"?kode={draft.kode}")
        self.assertEqual(resp.status_code, 200)                     # melanjutkan draft yang sudah ada tidak diblokir

    def test_laporan_disetujui_membuka_kembali_pengajuan_baru(self):
        p = self.pdln_selesai_tanpa_laporan()
        LaporanPdln.objects.create(pengajuan=p, status=LaporanPdln.Status.DISETUJUI)
        self.assertIsNone(alur.penahan_pengajuan_baru(self.pegawai))
        resp = self.get(self.pegawai, "pegawai:formulir_pengajuan", query="?jenis=nondinas")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(self.beranda(), 'data-modal-open="jenisModal"')

    def test_alasan_mengikuti_status_laporan(self):
        p = self.pdln_selesai_tanpa_laporan()
        for status, kalimat in (
            (LaporanPdln.Status.DRAFT, "masih berupa draft"),
            (LaporanPdln.Status.MENUNGGU, "belum disetujui Admin Biro PAKLN"),
            (LaporanPdln.Status.DIKEMBALIKAN, "perlu diunggah ulang"),
        ):
            with self.subTest(status=status):
                LaporanPdln.objects.update_or_create(pengajuan=p, defaults={"status": status})
                self.assertIn(kalimat, alur.alasan_belum_tuntas(alur.penahan_pengajuan_baru(self.pegawai)))

    def test_iln_selesai_tanpa_laporan_tidak_menahan(self):
        Pengajuan.objects.create(
            pegawai=self.pegawai, form_saved=True, jenis_perjalanan="nondinas", status=S.SELESAI, tgl_pengajuan=date.today(),
        )
        self.assertIsNone(alur.penahan_pengajuan_baru(self.pegawai))
        self.assertEqual(alur.pengajuan_aktif(self.pegawai), [])
