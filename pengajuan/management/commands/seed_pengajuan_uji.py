"""Seed data UJI: 10 pengajuan untuk tiap user ber-peran Pegawai, dengan
status alur dan status Pelaporan PDLN yang bervariasi.

Skenario per pegawai (variasi bergilir menurut urutan pegawai, sehingga
setiap kombinasi muncul di beberapa pegawai):

     1. Non-Kedinasan — draft (belum diajukan)
     2. Non-Kedinasan — selesai, perjalanan 2–3 bulan lalu
     3. Non-Kedinasan — di Admin Unor / dikembalikan ke pegawai / dibatalkan
     4. PDLN T1 — dalam proses Biro PAKLN
     5. PDLN T2L — dalam proses BPSDM
     6. PDLN T1 — selesai, perjalanan ±6 bulan lalu (lampau);
        laporan disetujui / belum melapor (terlambat)
     7. PDLN T1 — selesai, perjalanan 1–2 bulan lalu; laporan bergilir
     8. PDLN T3 — selesai, perjalanan ±2 bulan lalu; laporan bergilir
     9. PDLN T2L — selesai, pelatihan berakhir 1–2 bulan lalu; laporan bergilir
    10. PDLN T2P — studi masih berjalan (belum selesai, belum waktunya lapor) /
        studi telah selesai (laporan belum dikumpulkan / disetujui) /
        dalam proses Biro PAKLN menunggu SK Tubel

Laporan bergilir: belum melapor, draft, menunggu verifikasi, dikembalikan, disetujui.

Semua data ditandai awalan "[UJI]" (maksud pengajuan & nama kegiatan) dan
tanggal dihitung relatif terhadap hari ini. Pegawai yang sudah punya data
uji dilewati; pakai --hapus untuk membersihkan lalu buat ulang.

Laporan yang sudah dilaporkan memakai satu PDF contoh bersama yang
diunggah ke storage default (bucket S3), jadi storage harus bisa dijangkau.
Tidak ada email/notifikasi yang dikirim dan sisa cuti tidak diubah.

    python manage.py seed_pengajuan_uji
    python manage.py seed_pengajuan_uji --hapus          # hapus data uji saja
    python manage.py seed_pengajuan_uji --hapus --buat   # hapus lalu buat ulang
"""

import datetime
import random
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import PeranUser, User
from paspor.kalender import hitung_hari_kerja
from paspor.models import DasarKegiatan, KategoriPerjalanan, Kegiatan, Negara, SumberPembiayaan
from pengajuan.models import (
    DetailPdln, LaporanPdln, Pengajuan, PermohonanPembatalan, RiwayatPengajuan,
)

S = Pengajuan.Status
SB = Pengajuan.StatusBko
L = LaporanPdln.Status
A = RiwayatPengajuan.Aksi
R = User.Role
JP = Pengajuan.JenisPerjalanan

PENANDA = "[UJI]"
BERKAS_LAPORAN = "uji/laporan_pdln_uji.pdf"

# Kegiatan uji, dibagi bersama semua pegawai.
# kunci: (tipe, nama, penyelenggara, [(negara, kode)], kota, mulai (hari dari hari ini), durasi (hari),
#         kategori, [skema])
KEGIATAN_UJI = {
    "t1_lampau": ("T1", "Konferensi Jalan Asia-Pasifik", "Road Engineering Association of Asia and Australasia",
                  [("Malaysia", "MY")], "Kuala Lumpur", -190, 4,
                  "Pertemuan Bilateral/Regional/Multilateral", ["DIPA Kementerian PU"]),
    "t1_lalu": ("T1", "ASEAN Infrastructure Forum", "ASEAN Secretariat", [("Thailand", "TH")], "Bangkok",
                -50, 3, "Pertemuan Bilateral/Regional/Multilateral", ["DIPA Kementerian PU", "Donor Penyelenggara"]),
    "t1_depan": ("T1", "Pertemuan Bilateral Infrastruktur Indonesia–Korea", "Ministry of Land, Infrastructure and Transport",
                 [("Korea Selatan", "KR")], "Seoul", 45, 3,
                 "Pertemuan Bilateral/Regional/Multilateral", ["DIPA Kementerian PU"]),
    "t3_lalu": ("T3", "Advis Teknis Rehabilitasi Irigasi", "Ministério das Obras Públicas Timor-Leste",
                [("Timor-Leste", "TL")], "Dili", -68, 7, "Pemberian Advis Teknis", ["DIPA Kementerian PU"]),
    "t2l_lalu": ("T2L", "JICA Training: Integrated Flood Management", "Japan International Cooperation Agency",
                 [("Jepang", "JP")], "Tokyo", -75, 21, "Short Course-Training", ["Beasiswa/Donor Luar Negeri"]),
    "t2l_depan": ("T2L", "International Workshop on Dam Safety", "International Commission on Large Dams",
                  [("Austria", "AT")], "Wina", 50, 5, "Workshop", ["Beasiswa Lainnya"]),
    "t2p_berjalan": ("T2P", "Master of Science in Hydraulic Engineering", "IHE Delft Institute for Water Education",
                     [("Belanda", "NL")], "Delft", -120, 540, "Master", ["Beasiswa LPDP"]),
    "t2p_lulus": ("T2P", "Master of Urban Planning", "The University of Melbourne", [("Australia", "AU")],
                  "Melbourne", -760, 730, "Master", ["Beasiswa/Donor Luar Negeri"]),
    "t2p_depan": ("T2P", "Doctor of Philosophy in Civil Engineering", "The University of Tokyo", [("Jepang", "JP")],
                  "Tokyo", 90, 1460, "Doctoral", ["Beasiswa/Donor Luar Negeri"]),
}

NEGARA_NONDINAS = ["Arab Saudi", "Singapura", "Malaysia", "Jepang", "Turki", "Korea Selatan", "Thailand"]
MAKSUD_NONDINAS = {
    "Ibadah": "Menunaikan ibadah umrah bersama keluarga",
    "Keperluan Pribadi": "Menghadiri acara pernikahan keluarga",
    "Lainnya": "Berlibur bersama keluarga",
}
LAPORAN_BERGILIR = [None, L.DRAFT, L.MENUNGGU, L.DIKEMBALIKAN, L.DISETUJUI]


def _waktu(tanggal, jam=9):
    return timezone.make_aware(datetime.datetime.combine(tanggal, datetime.time(jam, 0)))


def _nama(user):
    profile = getattr(user, "profile", None)
    return (profile.nama if profile and profile.nama else user.get_full_name()) or user.username


class Command(BaseCommand):
    help = "Seed data uji: 10 pengajuan per pegawai dengan status & pelaporan PDLN bervariasi."

    def add_arguments(self, parser):
        parser.add_argument("--hapus", action="store_true", help="Hapus seluruh data uji ([UJI]).")
        parser.add_argument("--buat", action="store_true", help="Bersama --hapus: buat ulang setelah dihapus.")
        parser.add_argument("--pegawai", nargs="*", metavar="USERNAME", help="Batasi ke username tertentu.")

    def handle(self, *args, **options):
        self.hari_ini = timezone.localdate()
        if options["hapus"]:
            self._hapus()
            if not options["buat"]:
                return

        pegawai = self._daftar_pegawai(options["pegawai"])
        if not pegawai:
            raise CommandError("Tidak ada user ber-peran Pegawai. Jalankan seed_pegawai_org_units lebih dulu.")

        with transaction.atomic():
            self._siapkan_master()
            dibuat = 0
            for i, user in enumerate(pegawai):
                if Pengajuan.objects.filter(pegawai=user, maksud__startswith=PENANDA).exists():
                    self.stdout.write(f"  - {user.username}: sudah punya data uji, dilewati.")
                    continue
                self._seed_pegawai(i, user)
                dibuat += 1
                self.stdout.write(f"  + {user.username}: 10 pengajuan uji dibuat.")

        self.stdout.write(self.style.SUCCESS(
            f"Selesai. Data uji dibuat untuk {dibuat} dari {len(pegawai)} pegawai."
        ))

    # --- Persiapan ----------------------------------------------------

    def _hapus(self):
        with transaction.atomic():
            jumlah, _ = Pengajuan.objects.filter(maksud__startswith=PENANDA).delete()
            Kegiatan.objects.filter(nama__startswith=PENANDA).delete()
        self.stdout.write(self.style.WARNING(f"Data uji dihapus ({jumlah} baris termasuk turunannya)."))

    def _daftar_pegawai(self, usernames):
        qs = User.objects.filter(
            peran_list__role=R.PEGAWAI, peran_list__is_active=True, profile__isnull=False,
        ).select_related("profile", "profile__unit_organisasi", "unit_organisasi").distinct().order_by("username")
        if usernames:
            qs = qs.filter(username__in=usernames)
        return list(qs)

    def _siapkan_master(self):
        self.admin_pakln = self._admin(R.ADMIN_PAKLN)
        self.admin_bpsdm = self._admin(R.ADMIN_BPSDM)
        self.admin_bko = self._admin(R.ADMIN_BKO)
        self.admin_unor_default = self._admin(R.ADMIN_UNOR)
        self.admin_unor_per_unit = {
            p.unit_organisasi_id: p.user
            for p in PeranUser.objects.filter(role=R.ADMIN_UNOR, is_active=True).select_related("user")
        }

        self.kategori_nd = {k.nama_kategori: k for k in KategoriPerjalanan.objects.filter(jenis_perjalanan="Non-Dinas")}
        self.biaya_sendiri = SumberPembiayaan.objects.filter(tipe_perjalanan="Non-Dinas", nama="Biaya Sendiri").first()
        self.negara_nd = list(Negara.objects.filter(nama_negara__in=NEGARA_NONDINAS))
        if not self.kategori_nd or not self.biaya_sendiri or not self.negara_nd:
            raise CommandError("Master kategori/sumber pembiayaan/negara Non-Dinas belum ada. Jalankan migrate.")

        self.kegiatan = {kunci: self._kegiatan(data) for kunci, data in KEGIATAN_UJI.items()}
        self.berkas_laporan = self._berkas_laporan()

    def _admin(self, role):
        peran = PeranUser.objects.filter(role=role, is_active=True).select_related("user").first()
        return peran.user if peran else User.objects.filter(role=role).first()

    def _kegiatan(self, data):
        tipe, nama, penyelenggara, negara, kota, mulai, durasi, kategori, skema = data
        nama = f"{PENANDA} {nama}"
        kegiatan = Kegiatan.objects.filter(nama=nama).first()
        if kegiatan:
            return kegiatan
        kat = KategoriPerjalanan.objects.filter(jenis_perjalanan="PDLN", nama_kategori=kategori).first()
        sk = list(SumberPembiayaan.objects.filter(tipe_perjalanan="PDLN", nama__in=skema))
        if not kat or not sk:
            raise CommandError(f"Master kategori/sumber PDLN untuk '{nama}' belum ada. Jalankan migrate.")
        tgl_mulai = self.hari_ini + timedelta(days=mulai)
        kegiatan = Kegiatan.objects.create(
            nama=nama, deskripsi=f"Kegiatan contoh untuk pengujian ({tipe}).", kota=kota,
            penyelenggara=penyelenggara, tgl_mulai=tgl_mulai, tgl_selesai=tgl_mulai + timedelta(days=durasi),
            tahun_pelaksanaan=tgl_mulai.year, status=Kegiatan.Status.DISETUJUI,
            sumber_data=Kegiatan.SumberData.MANUAL,
        )
        kegiatan.negara.set([Negara.objects.get_or_create(nama_negara=n, defaults={"kode_negara": k})[0] for n, k in negara])
        kegiatan.kategori.set([kat])
        kegiatan.skema_pendanaan.set(sk)
        DasarKegiatan.objects.create(kegiatan=kegiatan, jenis=DasarKegiatan.Jenis.LAINNYA, keterangan="Data uji")
        return kegiatan

    def _berkas_laporan(self):
        try:
            if not default_storage.exists(BERKAS_LAPORAN):
                from weasyprint import HTML

                pdf = HTML(string=(
                    "<h1>Laporan Perjalanan Dinas Luar Negeri</h1>"
                    "<p>Berkas contoh untuk data uji PASPOR.</p>"
                )).write_pdf()
                return default_storage.save(BERKAS_LAPORAN, ContentFile(pdf))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Gagal menyiapkan PDF laporan contoh di storage: {exc}") from exc
        return BERKAS_LAPORAN

    # --- Skenario per pegawai ----------------------------------------

    def _seed_pegawai(self, i, user):
        self.user = user
        self.unit = user.profile.unit_organisasi or user.unit_organisasi
        self.admin_unor = self.admin_unor_per_unit.get(getattr(self.unit, "pk", None)) or self.admin_unor_default
        self.acak = random.Random(user.pk)
        h = self.hari_ini

        self._nondinas(berangkat=h + timedelta(days=self.acak.randint(45, 70)), akhir="draft")
        self._nondinas(berangkat=h - timedelta(days=self.acak.randint(70, 90)), akhir="selesai")
        self._nondinas(berangkat=h + timedelta(days=self.acak.randint(25, 40)),
                       akhir=["proses", "dikembalikan_unor", "dibatalkan"][i % 3])
        self._pdln("t1_depan", akhir="proses_pakln")
        self._pdln("t2l_depan", akhir="proses_bpsdm")
        self._pdln("t1_lampau", akhir="selesai", laporan=[L.DISETUJUI, None][i % 2])
        self._pdln("t1_lalu", akhir="selesai", laporan=LAPORAN_BERGILIR[i % 5])
        self._pdln("t3_lalu", akhir="selesai", laporan=LAPORAN_BERGILIR[(i + 1) % 5])
        self._pdln("t2l_lalu", akhir="selesai", laporan=LAPORAN_BERGILIR[(i + 2) % 5])
        if i % 3 == 0:
            self._pdln("t2p_berjalan", akhir="selesai")  # studi berjalan: belum waktunya melapor
        elif i % 3 == 1:
            self._pdln("t2p_lulus", akhir="selesai", laporan=[None, L.DISETUJUI][(i // 3) % 2])
        else:
            self._pdln("t2p_depan", akhir="proses_pakln")  # menunggu SK Tubel dari Admin BKO

    # --- Pembuat pengajuan --------------------------------------------

    def _nondinas(self, berangkat, akhir):
        nama_kategori = self.acak.choice(list(MAKSUD_NONDINAS))
        kategori = self.kategori_nd.get(nama_kategori) or next(iter(self.kategori_nd.values()))
        kembali = berangkat + timedelta(days=self.acak.randint(5, 10))
        p = Pengajuan(
            pegawai=self.user, jenis_perjalanan=JP.NONDINAS, unit_organisasi=self.unit, kategori=kategori,
            maksud=f"{PENANDA} {MAKSUD_NONDINAS.get(nama_kategori, 'Perjalanan pribadi')}",
            sumber_pembiayaan=self.biaya_sendiri, tgl_berangkat=berangkat, tgl_kembali=kembali,
            kanal=self.acak.choice([Pengajuan.Kanal.WEB, Pengajuan.Kanal.MOBILE]),
        )
        self._jalankan_alur(p, akhir, [self.acak.choice(self.negara_nd)])
        return p

    def _pdln(self, kunci, akhir, laporan=None):
        kegiatan = self.kegiatan[kunci]
        tipe = KEGIATAN_UJI[kunci][0]
        p = Pengajuan(
            pegawai=self.user, jenis_perjalanan=JP.PDLN, tipe_pdln=tipe, unit_organisasi=self.unit,
            kategori=kegiatan.kategori.first(), kegiatan=kegiatan,
            maksud=f"{PENANDA} {kegiatan.nama.removeprefix(PENANDA).strip()}",
            sumber_pembiayaan=kegiatan.skema_pendanaan.first(),
            tgl_berangkat=kegiatan.tgl_mulai - timedelta(days=1),
            tgl_kembali=kegiatan.tgl_selesai + timedelta(days=1),
        )
        self._jalankan_alur(p, akhir, list(kegiatan.negara.all()), detail_dari=kegiatan)
        if laporan is not None:
            self._laporan(p, laporan)
        return p

    def _jalankan_alur(self, p, akhir, negara, detail_dari=None):
        """Simpan pengajuan lalu tulis status, tanggal, flag, dan riwayat sesuai
        tahap akhir `akhir`, meniru urutan yang dilalui lewat aplikasi."""
        h = self.hari_ini
        p.jumlah_hari_kerja = hitung_hari_kerja(p.tgl_berangkat, p.tgl_kembali)
        p.form_saved = True
        selesai = akhir == "selesai"
        # Pengajuan selesai dikirim ±1 bulan sebelum berangkat; yang masih berjalan baru beberapa hari lalu.
        tgl_kirim = min(p.tgl_berangkat - timedelta(days=30), h - timedelta(days=20)) if selesai else \
            h - timedelta(days=self.acak.randint(6, 12))
        tgl_dibuat = tgl_kirim - timedelta(days=2) if akhir != "draft" else h - timedelta(days=self.acak.randint(1, 4))
        p.kode = self._kode(p, tgl_dibuat)
        p.save()
        p.tujuan_negara.set(negara)
        Pengajuan.objects.filter(pk=p.pk).update(created_at=_waktu(tgl_dibuat, 8))
        if detail_dari is not None:
            self._detail(p, detail_dari)

        if akhir == "draft":
            return

        tanggal = tgl_kirim
        p.submitted = True
        p.tgl_pengajuan = tanggal
        self._riwayat(p, A.DIKIRIM, self.user, R.PEGAWAI, S.BELUM, S.PROSES, tanggal)
        p.status = S.PROSES

        if akhir == "dikembalikan_unor":
            tanggal += timedelta(days=2)
            p.status, p.submitted = S.BELUM, False
            p.catatan_unor = "Formulir Izin Luar Negeri belum ditandatangani atasan langsung. Mohon diunggah ulang."
            self._riwayat(p, A.DIKEMBALIKAN_UNOR, self.admin_unor, R.ADMIN_UNOR, S.PROSES, S.BELUM, tanggal,
                          p.catatan_unor)
            return self._simpan(p)

        if akhir == "dibatalkan":
            self._batalkan(p, tanggal + timedelta(days=1))
            return self._simpan(p)

        if akhir == "proses":
            return self._simpan(p)

        # Admin Unor meneruskan.
        tanggal += timedelta(days=2)
        p.preview_unor_agree = True
        if p.is_tipe2:
            p.status, p.tgl_masuk_bpsdm = S.PROSES_BPSDM, tanggal
            self._riwayat(p, A.DITERUSKAN_BPSDM, self.admin_unor, R.ADMIN_UNOR, S.PROSES, S.PROSES_BPSDM, tanggal)
            if akhir == "proses_bpsdm":
                return self._simpan(p)
            tanggal += timedelta(days=3)
            p.preview_bpsdm_agree = True
            p.status, p.tgl_masuk_pakln = S.PROSES_PAKLN, tanggal
            self._riwayat(p, A.DITERUSKAN_PAKLN, self.admin_bpsdm, R.ADMIN_BPSDM, S.PROSES_BPSDM, S.PROSES_PAKLN,
                          tanggal)
            if p.pakai_bko:
                p.tgl_masuk_bko, p.status_bko = tanggal, SB.MENUNGGU
                self._riwayat(p, A.DITERUSKAN_BKO, self.admin_bpsdm, R.ADMIN_BPSDM, S.PROSES_PAKLN,
                              S.PROSES_PAKLN, tanggal)
        else:
            p.status, p.tgl_masuk_pakln = S.PROSES_PAKLN, tanggal
            self._riwayat(p, A.DITERUSKAN_PAKLN, self.admin_unor, R.ADMIN_UNOR, S.PROSES, S.PROSES_PAKLN, tanggal)

        if akhir == "proses_pakln":
            return self._simpan(p)

        if p.pakai_bko:
            tanggal += timedelta(days=2)
            p.status_bko = SB.DIUNGGAH
            self._riwayat(p, A.SK_TUBEL_DIUNGGAH, self.admin_bko, R.ADMIN_BKO, S.PROSES_PAKLN, S.PROSES_PAKLN,
                          tanggal)

        # Biro PAKLN menyelesaikan.
        tanggal += timedelta(days=3)
        p.preview_pakln_agree = True
        p.status, p.tgl_selesai = S.SELESAI, tanggal
        self._riwayat(p, A.SELESAI, self.admin_pakln, R.ADMIN_PAKLN, S.PROSES_PAKLN, S.SELESAI, tanggal)
        self._simpan(p)

    def _simpan(self, p):
        p.save()

    def _kode(self, p, tanggal):
        """Seperti `Pengajuan._generate_kode`, tetapi memakai tanggal pengajuan uji."""
        kepala = p._kepala_kode()
        pola = rf"^{kepala}[0-9]{{4}}{tanggal:%y}-[0-9]+$"
        terakhir = max(
            (int(k.rsplit("-", 1)[1]) for k in Pengajuan.objects.filter(kode__regex=pola).values_list("kode", flat=True)),
            default=0,
        )
        return f"{kepala}{tanggal:%d%m%y}-{terakhir + 1:03d}"

    def _detail(self, p, kegiatan):
        tipe = p.tipe_pdln
        DetailPdln.objects.create(
            pengajuan=p,
            penyelenggara="" if tipe == "T2P" else kegiatan.penyelenggara,
            perguruan_tinggi=kegiatan.penyelenggara if tipe == "T2P" else "",
            kota_tujuan=kegiatan.kota,
            keterangan_sumber_pembiayaan="Ditanggung penuh sesuai skema pendanaan kegiatan.",
            tgl_mulai_kegiatan=kegiatan.tgl_mulai, tgl_selesai_kegiatan=kegiatan.tgl_selesai,
            beasiswa_nama=p.sumber_pembiayaan.nama if p.is_tipe2 and p.sumber_pembiayaan else "",
            kegiatan_nama=kegiatan.nama, kegiatan_tahun=kegiatan.tahun_pelaksanaan,
            pernyataan_benar=True,
        )

    def _batalkan(self, p, tanggal):
        alasan = "Rencana perjalanan batal karena ada penugasan kantor pada tanggal yang sama."
        PermohonanPembatalan.objects.create(
            pengajuan=p, diajukan_oleh=self.user, diajukan_role=R.PEGAWAI, alasan=alasan,
            status=PermohonanPembatalan.Status.DISETUJUI, status_pengajuan_saat_diajukan=S.PROSES,
            unor_oleh=self.admin_unor, unor_waktu=_waktu(tanggal, 10),
            pakln_oleh=self.admin_pakln, pakln_waktu=_waktu(tanggal + timedelta(days=1), 10),
            created_at=_waktu(tanggal),
        )
        self._riwayat(p, A.PEMBATALAN_DIAJUKAN, self.user, R.PEGAWAI, S.PROSES, S.PROSES, tanggal, alasan)
        self._riwayat(p, A.PEMBATALAN_DISETUJUI_UNOR, self.admin_unor, R.ADMIN_UNOR, S.PROSES, S.PROSES,
                      tanggal, jam=10)
        tanggal += timedelta(days=1)
        self._riwayat(p, A.DIBATALKAN, self.admin_pakln, R.ADMIN_PAKLN, S.PROSES, S.DIBATALKAN, tanggal, alasan)
        p.status, p.tgl_dibatalkan = S.DIBATALKAN, tanggal

    def _laporan(self, p, status):
        """Laporan PDLN dengan status `status`; tanggal setelah kepulangan."""
        tgl_lapor = min(p.tgl_kembali + timedelta(days=self.acak.randint(3, 10)), self.hari_ini - timedelta(days=4))
        estimasi = Decimal(self.acak.randrange(25, 90) * 1_000_000)
        isi = {
            "tujuan_kegiatan": f"Mengikuti {p.kegiatan.nama.removeprefix(PENANDA).strip()} sebagai perwakilan unit.",
            "materi_kegiatan": "Paparan kebijakan, diskusi panel, dan kunjungan lapangan.",
            "tindak_lanjut": "Menyusun rekomendasi teknis untuk pimpinan unit kerja.",
            "dampak_rekomendasi": "Penerapan praktik baik pada perencanaan program tahun berikutnya.",
            "estimasi_biaya": estimasi,
            "realisasi_biaya": estimasi - Decimal(self.acak.randrange(0, 10) * 1_000_000),
        }
        if status == L.DRAFT:
            # Draft: isian belum lengkap, belum ada berkas.
            isi = {k: isi[k] for k in ("tujuan_kegiatan", "estimasi_biaya")}
        laporan = LaporanPdln.objects.create(
            pengajuan=p, status=status, diunggah_oleh=self.user, uploaded_at=_waktu(tgl_lapor, 14),
            file=self.berkas_laporan if status != L.DRAFT else "", **isi,
        )
        if status == L.DRAFT:
            return
        self._riwayat(p, A.LAPORAN_DIUNGGAH, self.user, R.PEGAWAI, S.SELESAI, S.SELESAI, tgl_lapor, jam=14)
        tgl_verif = min(tgl_lapor + timedelta(days=3), self.hari_ini)
        if status == L.DIKEMBALIKAN:
            laporan.catatan_pakln = "Realisasi biaya belum dilengkapi bukti pendukung. Mohon unggah ulang."
            laporan.diverifikasi_oleh = self.admin_pakln
            self._riwayat(p, A.LAPORAN_DIKEMBALIKAN, self.admin_pakln, R.ADMIN_PAKLN, S.SELESAI, S.SELESAI,
                          tgl_verif, laporan.catatan_pakln, jam=10)
        elif status == L.DISETUJUI:
            laporan.diverifikasi_oleh = self.admin_pakln
            laporan.tgl_disetujui = _waktu(tgl_verif, 10)
            self._riwayat(p, A.LAPORAN_DISETUJUI, self.admin_pakln, R.ADMIN_PAKLN, S.SELESAI, S.SELESAI,
                          tgl_verif, jam=10)
        laporan.save()

    def _riwayat(self, p, aksi, aktor, role, dari, ke, tanggal, catatan="", jam=9):
        # Tanpa akun admin terkait, aktor dicatat atas nama sistem agar riwayat tetap lengkap.
        RiwayatPengajuan.objects.create(
            pengajuan=p, aksi=aksi, status_dari=dari, status_ke=ke, aktor=aktor, aktor_role=role,
            aktor_nama=(_nama(aktor) if aktor else "Sistem (data uji)")[:150], catatan=catatan,
            created_at=_waktu(tanggal, jam),
        )
