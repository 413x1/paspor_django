import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import PegawaiProfile, User
from paspor.models import KategoriPerjalanan, Negara, SumberPembiayaan, UnitOrganisasi
from pengajuan.models import Pengajuan

# Data awal unit organisasi eselon I Kementerian PU (tabel org_units).
ORG_UNITS = [
    ("00", "MENTERI", "Menteri Pekerjaan Umum"),
    ("01", "SETJEN", "Sekretariat Jenderal"),
    ("02", "ITJEN", "Inspektorat Jenderal"),
    ("03", "DJSDA", "Direktorat Jenderal Sumber Daya Air"),
    ("04", "DJPS", "Direktorat Jenderal Prasarana Strategis"),
    ("05", "DJCK", "Direktorat Jenderal Cipta Karya"),
    ("06", "DJBM", "Direktorat Jenderal Bina Marga"),
    ("07", "DJPI", "Direktorat Jenderal Pembiayaan Infrastruktur"),
    ("08", "DJBK", "Direktorat Jenderal Bina Konstruksi"),
    ("09", "BPIW", "Badan Pengembangan Infrastruktur Wilayah"),
    ("10", "BPSDM", "Badan Pengembangan Sumber Daya Manusia"),
]


class Command(BaseCommand):
    help = (
        "Membuat akun demo (Pegawai, Admin Unor, Admin Biro PAKLN) beserta "
        "contoh data pengajuan, meniru data dummy pada mockup PASPOR "
        "Tahap 1 (alur Non-Kedinasan)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Unit organisasi (org_units) -----------------------------
        for code, alias, name in ORG_UNITS:
            UnitOrganisasi.objects.update_or_create(
                code=code, defaults={"alias": alias, "name": name}
            )
        djsda = UnitOrganisasi.objects.get(code="03")  # Ditjen Sumber Daya Air

        # --- Pegawai --------------------------------------------------
        pegawai, created = User.objects.get_or_create(
            username="andra.wibisono",
            defaults={
                "first_name": "Andra",
                "last_name": "Wibisono",
                "role": User.Role.PEGAWAI,
            },
        )
        if created:
            pegawai.set_password("paspor123")
        pegawai.unit_kerja = "Direktorat Bina Teknik Sumber Daya Air"
        pegawai.unit_organisasi = djsda
        pegawai.save()
        if created:
            self.stdout.write(self.style.SUCCESS("User pegawai 'andra.wibisono' dibuat."))

        PegawaiProfile.objects.update_or_create(
            user=pegawai,
            defaults={
                "nip": "198703142011011007",
                "nama": "Andra Wibisono, S.T.",
                "jabatan": "Kepala Seksi Perencanaan Teknis",
                "pangkat_golongan": "Penata Tk. I / III-d",
                "unit_kerja": "Direktorat Bina Teknik Sumber Daya Air",
                "unit_organisasi": djsda,
                "sisa_cuti_tahun_berjalan": 12,
            },
        )

        # --- Admin Unor -------------------------------------------------
        admin_unor, created = User.objects.get_or_create(
            username="admin.unor",
            defaults={"first_name": "Admin", "last_name": "Unor", "role": User.Role.ADMIN_UNOR},
        )
        if created:
            admin_unor.set_password("paspor123")
        # Admin Unor mengelola satu unit organisasi — samakan dengan unit
        # organisasi pegawai demo agar pengajuan tampil di dasbornya.
        admin_unor.unit_kerja = "Sekretariat Ditjen Sumber Daya Air"
        admin_unor.unit_organisasi = djsda
        admin_unor.save()
        if created:
            self.stdout.write(self.style.SUCCESS("User 'admin.unor' dibuat."))

        # --- Admin Biro PAKLN --------------------------------------------
        admin_pakln, created = User.objects.get_or_create(
            username="admin.pakln",
            defaults={"first_name": "Admin", "last_name": "Biro PAKLN", "role": User.Role.ADMIN_PAKLN},
        )
        if created:
            admin_pakln.set_password("paspor123")
            admin_pakln.save()
            self.stdout.write(self.style.SUCCESS("User 'admin.pakln' dibuat."))

        # --- Contoh riwayat pengajuan (status selesai) -------------------
        # `tujuan_negara` adalah ManyToManyField — tidak bisa masuk
        # `defaults` pada get_or_create(), jadi diisi lewat `.set()` setelah
        # baris Pengajuan ada.
        arab_saudi, _ = Negara.objects.get_or_create(
            nama_negara="Arab Saudi", defaults={"kode_negara": "SA"}
        )
        singapura, _ = Negara.objects.get_or_create(
            nama_negara="Singapura", defaults={"kode_negara": "SG"}
        )
        biaya_sendiri, _ = SumberPembiayaan.objects.get_or_create(
            nama="Biaya Sendiri", tipe_perjalanan=SumberPembiayaan.TipePerjalanan.NON_DINAS,
        )
        kategori_ibadah, _ = KategoriPerjalanan.objects.get_or_create(
            nama_kategori="Ibadah", jenis_perjalanan=KategoriPerjalanan.JenisPerjalanan.NON_DINAS,
        )
        kategori_pribadi, _ = KategoriPerjalanan.objects.get_or_create(
            nama_kategori="Keperluan Pribadi", jenis_perjalanan=KategoriPerjalanan.JenisPerjalanan.NON_DINAS,
        )

        pengajuan_umrah, _ = Pengajuan.objects.get_or_create(
            kode="PSP-2026-0091",
            defaults={
                "pegawai": pegawai,
                "kategori": kategori_ibadah,
                "maksud": "Menunaikan ibadah umrah bersama keluarga",
                "sumber_pembiayaan": biaya_sendiri,
                "tgl_berangkat": datetime.date(2026, 6, 1),
                "tgl_kembali": datetime.date(2026, 6, 8),
                "jumlah_hari_kerja": 5,
                "kanal": Pengajuan.Kanal.MOBILE,
                "status": Pengajuan.Status.SELESAI,
                "form_saved": True,
                "submitted": True,
                "preview_unor_agree": True,
                "preview_pakln_agree": True,
                "tgl_pengajuan": datetime.date(2026, 6, 2),
                "tgl_masuk_pakln": datetime.date(2026, 6, 3),
                "tgl_selesai": datetime.date(2026, 6, 2),
            },
        )
        pengajuan_umrah.tujuan_negara.set([arab_saudi])

        pengajuan_keluarga, _ = Pengajuan.objects.get_or_create(
            kode="PSP-2026-0114",
            defaults={
                "pegawai": pegawai,
                "kategori": kategori_pribadi,
                "maksud": "Menghadiri acara keluarga",
                "sumber_pembiayaan": biaya_sendiri,
                "tgl_berangkat": datetime.date(2026, 7, 12),
                "tgl_kembali": datetime.date(2026, 7, 19),
                "jumlah_hari_kerja": 5,
                "kanal": Pengajuan.Kanal.WEB,
                "status": Pengajuan.Status.SELESAI,
                "form_saved": True,
                "submitted": True,
                "preview_unor_agree": True,
                "preview_pakln_agree": True,
                "tgl_pengajuan": datetime.date(2026, 7, 13),
                "tgl_masuk_pakln": datetime.date(2026, 7, 14),
                "tgl_selesai": datetime.date(2026, 7, 19),
            },
        )
        pengajuan_keluarga.tujuan_negara.set([singapura])

        self.stdout.write(self.style.SUCCESS(
            "\nSelesai. Akun demo (password sama untuk semua: 'paspor123'):\n"
            "  - andra.wibisono   -> role Pegawai\n"
            "  - admin.unor       -> role Admin Unor\n"
            "  - admin.pakln      -> role Admin Biro PAKLN\n"
        ))
