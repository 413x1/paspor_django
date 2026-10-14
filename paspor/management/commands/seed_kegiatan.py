"""Seed contoh Kegiatan PDLN — 5 kegiatan untuk tiap tipe PDLN (T1, T2P,
T2L, T3) beserta dasar kegiatannya, ditambah 2 usulan yang menunggu
persetujuan (dari Pegawai demo dan Admin BPSDM demo bila akunnya ada).
Lihat wiki/instructions/EVENT_IMPLEMENTATION_PLAN.MD.

Idempoten: kegiatan dicari berdasarkan nama; yang sudah ada tidak diubah.
Tanggal dihitung relatif terhadap hari ini agar kegiatan selalu dapat dipilih.

    python manage.py seed_kegiatan
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from paspor.models import DasarKegiatan, KategoriPerjalanan, Kegiatan, Negara, SumberPembiayaan

D = DasarKegiatan.Jenis

# (nama, penyelenggara, [(negara, kode)], kota, mulai (hari dari sekarang), durasi (hari),
#  [kategori], [skema], deskripsi, (jenis dasar, nilai), kode_pintar)
KEGIATAN = {
    "T1": [
        ("ASEAN Ministerial Meeting on Infrastructure", "ASEAN Secretariat", [("Malaysia", "MY")], "Kuala Lumpur",
         45, 3, ["Pertemuan Bilateral/Regional/Multilateral"], ["DIPA Kementerian PU", "Donor Penyelenggara"],
         "Pertemuan tingkat menteri ASEAN membahas konektivitas dan pembiayaan infrastruktur kawasan.",
         (D.SURAT, "ASEC/INF/123/2026"), None),
        ("World Water Forum ke-11", "World Water Council", [("Arab Saudi", "SA")], "Riyadh",
         60, 6, ["Pertemuan Bilateral/Regional/Multilateral", "Pameran/Expo"], ["DIPA Kementerian PU"],
         "Forum air dunia: sesi tingkat tinggi dan pameran teknologi sumber daya air.",
         (D.TAUTAN, "https://www.worldwaterforum.org"), None),
        ("Pertemuan Bilateral Infrastruktur Indonesia–Jepang", "Ministry of Land, Infrastructure, Transport and Tourism",
         [("Jepang", "JP")], "Tokyo", 75, 2, ["Pertemuan Bilateral/Regional/Multilateral"],
         ["DIPA Kementerian PU", "Donor Penyelenggara"],
         "Joint Committee kerja sama infrastruktur jalan, jembatan, dan pengendalian banjir.",
         (D.SURAT, "MLIT/INT/2026/045"), None),
        ("Smart City Expo World Congress", "Fira Barcelona", [("Spanyol", "ES")], "Barcelona",
         90, 3, ["Pameran/Expo"], ["DIPA Kementerian PU", "DIPA K/L Lain"],
         "Pameran dan kongres kota cerdas; paviliun Indonesia menampilkan proyek IKN.",
         (D.TAUTAN, "https://www.smartcityexpo.com"), None),
        ("APEC Transportation Ministerial Meeting", "APEC Secretariat", [("Singapura", "SG")], "Singapura",
         110, 2, ["Pertemuan Bilateral/Regional/Multilateral"], ["DIPA Kementerian PU"],
         "Pertemuan menteri transportasi APEC — sesi konektivitas dan ketahanan infrastruktur.",
         (D.SURAT, "APEC/TMM/2026/017"), None),
    ],
    "T3": [
        ("Advis Teknis Rehabilitasi Jembatan Pascagempa", "Ministério das Obras Públicas Timor-Leste",
         [("Timor-Leste", "TL")], "Dili", 40, 10, ["Pemberian Advis Teknis"], ["DIPA Kementerian PU"],
         "Penugasan khusus tim ahli jembatan untuk asesmen dan rekomendasi rehabilitasi.",
         (D.SURAT, "MOP-TL/2026/088"), None),
        ("Pendampingan Delegasi RI pada UN-Habitat Assembly", "UN-Habitat", [("Kenya", "KE")], "Nairobi",
         55, 5, ["Pendampingan"], ["DIPA Kementerian PU", "DIPA K/L Lain"],
         "Pendampingan delegasi RI pada sidang UN-Habitat Assembly.",
         (D.SURAT, "B-1234/KL/IX/2026"), None),
        ("Misi Teknis Pembangunan Bendungan", "Ministry of Energy and Mines Lao PDR", [("Laos", "LA")], "Vientiane",
         70, 7, ["Pemberian Advis Teknis"], ["DIPA Kementerian PU", "Donor Penyelenggara"],
         "Advis teknis keamanan bendungan dan operasi waduk.",
         (D.LAINNYA, "Nota dinas Kepala Biro PAKLN tentang misi teknis bendungan"), None),
        ("Pendampingan Kunjungan Kerja Menteri ke Korea Selatan dan Jepang", "Kementerian Pekerjaan Umum",
         [("Korea Selatan", "KR"), ("Jepang", "JP")], "Seoul, Tokyo", 85, 6, ["Pendampingan"],
         ["DIPA Kementerian PU"],
         "Kegiatan multi-negara: pendampingan kunjungan kerja menteri ke Seoul lalu Tokyo.",
         (D.SURAT, "UM.0101-Mn/2026/310"), None),
        ("Advis Teknis Sistem Irigasi", "Ministry of Waterways and Environment Fiji", [("Fiji", "FJ")], "Suva",
         120, 8, ["Pemberian Advis Teknis"], ["DIPA Kementerian PU", "Donor Penyelenggara"],
         "Asistensi teknis perencanaan dan rehabilitasi jaringan irigasi.",
         (D.SURAT, "MWE-FJ/2026/021"), None),
    ],
    "T2P": [
        ("Master of Science in Water Management", "IHE Delft Institute for Water Education", [("Belanda", "NL")],
         "Delft", 120, 540, ["Master"], ["Beasiswa LPDP", "Beasiswa/Donor Luar Negeri"],
         "Program magister 18 bulan bidang pengelolaan sumber daya air.",
         (D.PINTAR, "PINTAR-P-2027-001"), "PINTAR-P-2027-001"),
        ("Doctor of Philosophy in Civil Engineering", "The University of Tokyo", [("Jepang", "JP")], "Tokyo",
         150, 1460, ["Doctoral"], ["Beasiswa/Donor Luar Negeri", "Beasiswa Lainnya"],
         "Program doktor teknik sipil (MEXT) — riset rekayasa gempa.",
         (D.TAUTAN, "https://www.u-tokyo.ac.jp/en/prospective-students/graduate_course.html"), None),
        ("Master of Urban Planning", "The University of Melbourne", [("Australia", "AU")], "Melbourne",
         130, 730, ["Master"], ["Beasiswa/Donor Luar Negeri", "Beasiswa LPDP"],
         "Program magister perencanaan kota (Australia Awards).",
         (D.TAUTAN, "https://study.unimelb.edu.au/find/courses/graduate/master-of-urban-planning/"), None),
        ("Master of Science in Transport", "Imperial College London", [("Inggris", "GB")], "London",
         125, 365, ["Master"], ["Beasiswa LPDP"],
         "Program magister transportasi satu tahun (Chevening/LPDP).",
         (D.SURAT, "LoA/ICL/2026/7781"), None),
        ("Doctor of Philosophy in Hydrology", "Korea Advanced Institute of Science and Technology", [("Korea Selatan", "KR")],
         "Daejeon", 160, 1460, ["Doctoral"], ["Beasiswa/Donor Luar Negeri"],
         "Program doktor hidrologi dan pengelolaan banjir (KGSP).",
         (D.PINTAR, "PINTAR-P-2027-002"), "PINTAR-P-2027-002"),
    ],
    "T2L": [
        ("JICA Knowledge Co-Creation Program: Road Asset Management", "Japan International Cooperation Agency",
         [("Jepang", "JP")], "Tokyo", 50, 21, ["Short Course-Training"], ["Beasiswa/Donor Luar Negeri"],
         "Pelatihan manajemen aset jalan dan pemeliharaan preventif.",
         (D.PINTAR, "PINTAR-L-2026-014"), "PINTAR-L-2026-014"),
        ("International Workshop on Dam Safety", "International Commission on Large Dams", [("Austria", "AT")],
         "Wina", 65, 4, ["Workshop", "Seminar/Lokakarya"], ["Beasiswa/Donor Luar Negeri", "Beasiswa Lainnya"],
         "Lokakarya keamanan bendungan dan manajemen risiko.",
         (D.TAUTAN, "https://www.icold-cigb.org"), None),
        ("KOICA Fellowship: Smart Water Management", "K-water Academy", [("Korea Selatan", "KR")], "Daejeon",
         80, 14, ["Short Course-Training"], ["Beasiswa/Donor Luar Negeri"],
         "Pelatihan pengelolaan air cerdas berbasis IoT.",
         (D.SURAT, "KOICA/FS/2026/552"), None),
        ("International Symposium on Coastal Engineering", "American Society of Civil Engineers", [("Singapura", "SG")],
         "Singapura", 95, 5, ["Simposium/Konferensi Internasional"], ["Beasiswa Lainnya"],
         "Simposium teknik pantai: perlindungan pesisir dan adaptasi perubahan iklim.",
         (D.TAUTAN, "https://www.asce.org"), None),
        ("Seminar on Sustainable Construction", "Building and Construction Authority", [("Singapura", "SG")],
         "Singapura", 105, 3, ["Seminar/Lokakarya", "Workshop"], ["Beasiswa/Donor Luar Negeri", "Beasiswa Lainnya"],
         "Seminar dan lokakarya konstruksi berkelanjutan serta bangunan hijau.",
         (D.SURAT, "BCA/ACAD/2026/119"), None),
    ],
}

USULAN = [
    # (username pengusul, sumber_data, data kegiatan)
    ("andra.wibisono", Kegiatan.SumberData.USULAN_PEGAWAI,
     ("Regional Workshop on Flood Risk Management", "Asian Disaster Preparedness Center", [("Thailand", "TH")],
      "Bangkok", 100, 4, ["Workshop"], ["Beasiswa/Donor Luar Negeri"],
      "Lokakarya regional manajemen risiko banjir.", (D.SURAT, "ADPC/WS/2026/031"), None)),
    ("admin.bpsdm", Kegiatan.SumberData.USULAN_BPSDM,
     ("Short Course on Tunnel Engineering", "Norwegian University of Science and Technology", [("Norwegia", "NO")],
      "Trondheim", 115, 10, ["Short Course-Training"], ["Beasiswa Lainnya"],
      "Kursus singkat rekayasa terowongan.", (D.TAUTAN, "https://www.ntnu.edu"), None)),
]


class Command(BaseCommand):
    help = "Seed contoh Kegiatan PDLN: 5 kegiatan per tipe PDLN + 2 usulan menunggu persetujuan."

    def _buat(self, data, hari_ini, status=Kegiatan.Status.DISETUJUI, sumber=None, pengusul=None):
        (nama, penyelenggara, negara, kota, mulai, durasi, kategori, skema, deskripsi, dasar, kode_pintar) = data
        if Kegiatan.objects.filter(nama=nama).exists():
            return None
        kat = list(KategoriPerjalanan.objects.filter(jenis_perjalanan="PDLN", nama_kategori__in=kategori))
        sk = list(SumberPembiayaan.objects.filter(tipe_perjalanan="PDLN", nama__in=skema))
        if not kat or not sk:
            self.stdout.write(self.style.WARNING(f"Lewati '{nama}': master kategori/sumber PDLN belum ada."))
            return None
        tgl_mulai = hari_ini + timedelta(days=mulai)
        kegiatan = Kegiatan.objects.create(
            nama=nama, deskripsi=deskripsi, kota=kota, penyelenggara=penyelenggara,
            tgl_mulai=tgl_mulai, tgl_selesai=tgl_mulai + timedelta(days=durasi),
            tahun_pelaksanaan=tgl_mulai.year, status=status,
            sumber_data=sumber or (Kegiatan.SumberData.PINTAR if kode_pintar else Kegiatan.SumberData.MANUAL),
            kode_pintar=kode_pintar if not Kegiatan.objects.filter(kode_pintar=kode_pintar).exists() else None,
            diusulkan_oleh=pengusul,
        )
        kegiatan.negara.set([
            Negara.objects.get_or_create(nama_negara=n, defaults={"kode_negara": k})[0] for n, k in negara
        ])
        kegiatan.kategori.set(kat)
        kegiatan.skema_pendanaan.set(sk)
        jenis, nilai = dasar
        field = DasarKegiatan.FIELD_WAJIB[jenis][0]
        DasarKegiatan.objects.create(kegiatan=kegiatan, jenis=jenis, **{field: nilai}, ditambahkan_oleh=pengusul)
        return kegiatan

    @transaction.atomic
    def handle(self, *args, **options):
        hari_ini = timezone.localdate()
        jumlah = 0
        for tipe, daftar in KEGIATAN.items():
            for data in daftar:
                if self._buat(data, hari_ini):
                    jumlah += 1
        for username, sumber, data in USULAN:
            pengusul = User.objects.filter(username=username).first()
            if pengusul and self._buat(data, hari_ini, status=Kegiatan.Status.MENUNGGU, sumber=sumber, pengusul=pengusul):
                jumlah += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seed kegiatan selesai: {jumlah} kegiatan baru (total {Kegiatan.objects.count()})."
        ))
