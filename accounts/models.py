from django.contrib.auth.models import AbstractUser
from django.db import models

# Model referensi UnitOrganisasi (tabel `org_units`) berada di app `paspor`.


class User(AbstractUser):
    """
    User kustom dengan field `role`, merepresentasikan 3 peran pada PASPOR:
    Pegawai, Admin Unor, dan Admin Biro PAKLN.

    Role tambahan "Admin BPSDM" untuk alur PDLN (Perjalanan Dinas Luar
    Negeri) akan ditambahkan pada tahap pengembangan berikutnya.
    """

    class Role(models.TextChoices):
        PEGAWAI = "pegawai", "Pegawai"
        ADMIN_UNOR = "admin_unor", "Admin Unor"
        ADMIN_PAKLN = "admin_pakln", "Admin Biro PAKLN"

    role = models.CharField(max_length=20, choices=Role.choices)

    # Unit kerja tempat user bertugas (teks bebas), diisi untuk Pegawai
    # maupun Admin Unor.
    unit_kerja = models.CharField("Unit Kerja", max_length=150, blank=True)

    # Unit organisasi yang dikelola. Relevan untuk role Admin Unor: seorang
    # Admin Unor hanya memproses pengajuan pegawai pada unit organisasi yang
    # sama. Untuk Pegawai, data unit organisasi ada di PegawaiProfile.
    unit_organisasi = models.ForeignKey(
        "paspor.UnitOrganisasi",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Unit Organisasi",
    )

    def is_pegawai(self):
        return self.role == self.Role.PEGAWAI

    def is_admin_unor(self):
        return self.role == self.Role.ADMIN_UNOR

    def is_admin_pakln(self):
        return self.role == self.Role.ADMIN_PAKLN

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class PegawaiProfile(models.Model):
    """
    Data kepegawaian yang pada mockup disimulasikan sebagai "otomatis dari
    database kepegawaian". Pada implementasi produksi, model ini idealnya
    disinkronkan (atau digantikan) oleh integrasi ke sistem database
    kepegawaian Kementerian PU, bukan diinput manual.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    nip = models.CharField("NIP", max_length=20, unique=True)
    nama = models.CharField("Nama Pegawai", max_length=150)
    jabatan = models.CharField(max_length=150)
    pangkat_golongan = models.CharField("Pangkat/Golongan", max_length=100)
    unit_kerja = models.CharField(max_length=150)
    unit_organisasi = models.ForeignKey(
        "paspor.UnitOrganisasi",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Unit Organisasi",
    )
    sisa_cuti_tahun_berjalan = models.PositiveIntegerField("Sisa Cuti Tahun Berjalan (hari)", default=12)

    class Meta:
        verbose_name = "Profil Pegawai"
        verbose_name_plural = "Profil Pegawai"

    def __str__(self):
        return f"{self.nama} ({self.nip})"
