"""Tombol "Generate ND" di halaman Unggah Dokumen Administrasi Biro PAKLN."""

from django.test import TestCase
from django.urls import reverse

from .models import Pengajuan
from .tests import _AlurMixin


class TombolGenerateNdTests(_AlurMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.pengajuan.status = Pengajuan.Status.PROSES_PAKLN
        self.pengajuan.preview_pakln_agree = True
        self.pengajuan.save()
        self.client.force_login(self.admin_pakln)
        self.url = reverse("pakln:upload_dokumen", args=[self.pengajuan.kode])

    def test_tampil_saat_dalam_proses_pakln_dan_buka_tab_baru(self):
        html = self.client.get(self.url).content.decode()
        kode = self.pengajuan.kode
        for rute in ("pakln:generate_nd_kabag", "pakln:generate_nd_karo"):
            self.assertIn(f'href="{reverse(rute)}?pengajuan={kode}"', html)
        self.assertEqual(html.count('target="_blank" rel="noopener">ND K'), 2)
        self.assertIn("📄 Generate ND", html)

    def test_tidak_tampil_bila_bukan_dalam_proses_pakln(self):
        Pengajuan.objects.filter(pk=self.pengajuan.pk).update(status=Pengajuan.Status.SELESAI)
        html = self.client.get(self.url).content.decode()
        self.assertNotIn("📄 Generate ND", html)
        self.assertNotIn("generate-nd-kabag", html)
        self.assertNotIn("generate-nd-karo", html)

    def test_halaman_tujuan_menerima_kode_pengajuan(self):
        r = self.client.get(f'{reverse("pakln:generate_nd_kabag")}?pengajuan={self.pengajuan.kode}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["kode_terpilih"], [self.pengajuan.kode])
