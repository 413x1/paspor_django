from django.contrib.auth.models import AbstractUser
from django.db import models

# Model referensi UnitOrganisasi (tabel `org_units`) berada di app `paspor`.


class User(AbstractUser):
    """
    User kustom dengan field `role`, merepresentasikan 5 peran pada PASPOR:
    Pegawai, Admin Unor, Admin BPSDM (khusus PDLN Tipe 2), Admin Biro PAKLN,
    dan Admin BKO (SK Tugas Belajar PDLN Tipe 2 Pendidikan) — lihat
    wiki/instructions/BISNIS_PROSES_PDLN.MD §3 & PDLN_TIPE_2_FLOW.MD §8.
    """

    class Role(models.TextChoices):
        PEGAWAI = "pegawai", "Pegawai"
        ADMIN_UNOR = "admin_unor", "Admin Unor"
        ADMIN_BPSDM = "admin_bpsdm", "Admin BPSDM"
        ADMIN_PAKLN = "admin_pakln", "Admin Biro PAKLN"
        ADMIN_BKO = "admin_bko", "Admin BKO"

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

    # --- Kontak (IMPROVEMENT_PLAN_19102026.MD AB-14..AB-19) ---
    # Nomor HP disimpan ternormalisasi `62…` (accounts.validators.normalisasi_no_hp).
    no_hp = models.CharField("Nomor HP (WhatsApp)", max_length=20, blank=True, db_index=True)
    # Pengenal unik dari penyedia SSO; kaitan SSO tidak putus saat username diganti.
    sso_sub = models.CharField(max_length=100, null=True, blank=True, unique=True, editable=False)

    class SumberAkun(models.TextChoices):
        SSO = "sso", "SSO"
        LOKAL = "lokal", "Lokal"

    sumber_akun = models.CharField(max_length=10, choices=SumberAkun.choices, default=SumberAkun.LOKAL)
    # Di-set saat Admin Biro PAKLN mengoreksi nilainya: sinkronisasi e-HRM tidak menimpanya (AB-18).
    email_dikunci = models.BooleanField(default=False)
    no_hp_dikunci = models.BooleanField(default=False)
    ehrm_sinkron_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Peran aktif (PeranAktifMiddleware) hanya menimpa `role` di memori;
        # nilai di database tetap peran default/terakhir dipilih.
        role_db = self.__dict__.get("_role_db")
        if role_db is not None and self.role != role_db:
            aktif, self.role = self.role, role_db
            try:
                return super().save(*args, **kwargs)
            finally:
                self.role = aktif
        return super().save(*args, **kwargs)

    def punya_sso(self):
        return bool(self.sso_sub)

    def tersinkron_ehrm(self):
        """Akun yang datanya bersumber dari e-HRM (sudah tertaut SSO, atau
        dibuat dari e-HRM lewat SSO/pra-daftar). Kontak yang dikoreksi Admin
        Biro PAKLN pada akun ini dikunci (AB-18)."""
        return self.punya_sso() or self.sumber_akun == self.SumberAkun.SSO

    def metode_login_display(self):
        if self.punya_sso() and self.has_usable_password():
            return "SSO + Username & Password"
        if self.punya_sso():
            return "SSO"
        if self.has_usable_password():
            return "Username & Password"
        return "SSO (belum tertaut)"

    # --- Role ganda (lihat PeranUser & accounts.middleware) ---
    def daftar_peran(self):
        """Role aktif milik user (dari PeranUser), terurut `URUTAN_PERAN`."""
        cache = self.__dict__.get("_cache_peran")
        if cache is None:
            dimiliki = set()
            if self.pk:
                dimiliki = set(self.peran_list.filter(is_active=True).values_list("role", flat=True))
            if not dimiliki:
                # User tanpa baris PeranUser (data transisi): pakai kolom role.
                role_db = self.__dict__.get("_role_db") or self.role
                dimiliki = {role_db} if role_db else set()
            cache = [r for r in URUTAN_PERAN if r in dimiliki]
            self._cache_peran = cache
        return cache

    def punya_peran(self, role):
        return role in self.daftar_peran()

    def reset_cache_peran(self):
        self.__dict__.pop("_cache_peran", None)
        self.__dict__.pop("_cache_unit_admin", None)

    def unit_admin_id(self):
        """Unit organisasi yang dikelola sebagai Admin Unor (PeranUser);
        fallback ke `User.unit_organisasi` untuk data lama."""
        if "_cache_unit_admin" not in self.__dict__:
            uid = None
            if self.pk:
                uid = (
                    self.peran_list.filter(role=self.Role.ADMIN_UNOR, is_active=True)
                    .values_list("unit_organisasi_id", flat=True).first()
                )
            self._cache_unit_admin = uid or self.unit_organisasi_id
        return self.__dict__["_cache_unit_admin"]

    def is_pegawai(self):
        return self.role == self.Role.PEGAWAI

    def is_admin_unor(self):
        return self.role == self.Role.ADMIN_UNOR

    def is_admin_bpsdm(self):
        return self.role == self.Role.ADMIN_BPSDM

    def is_admin_pakln(self):
        return self.role == self.Role.ADMIN_PAKLN

    def is_admin_bko(self):
        return self.role == self.Role.ADMIN_BKO

    def get_unit_organisasi(self):
        """Unit organisasi efektif menurut peran aktif: dari PegawaiProfile
        untuk Pegawai, unit yang dikelola (PeranUser) untuk Admin Unor, dan
        field `unit_organisasi` untuk role lainnya."""
        if self.is_pegawai():
            profile = getattr(self, "profile", None)
            if profile and profile.unit_organisasi_id:
                return profile.unit_organisasi
        if self.is_admin_unor():
            uid = self.unit_admin_id()
            if uid and uid != self.unit_organisasi_id:
                from paspor.models import UnitOrganisasi

                return UnitOrganisasi.objects.filter(pk=uid).first()
        return self.unit_organisasi

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


# Prioritas peran aktif saat sesi baru bila peran terakhir (User.role) tidak
# lagi dimiliki — IMPROVEMENT_PLAN_19102026.MD §6.2.
URUTAN_PERAN = [
    User.Role.ADMIN_PAKLN,
    User.Role.ADMIN_UNOR,
    User.Role.ADMIN_BKO,
    User.Role.ADMIN_BPSDM,
    User.Role.PEGAWAI,
]


class PeranUser(models.Model):
    """Satu role yang dimiliki user. Satu user dapat memiliki beberapa role
    (mis. Pegawai + Admin Unor); peran yang dipakai pada sesi ditentukan
    `accounts.middleware.PeranAktifMiddleware`. Mencabut role = `is_active=False`
    (baris tidak dihapus, demi jejak audit)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="peran_list")
    role = models.CharField(max_length=20, choices=User.Role.choices)
    # Wajib untuk admin_unor: unit organisasi yang dikelola (bisa berbeda dari
    # unit tempat user bertugas sebagai pegawai).
    unit_organisasi = models.ForeignKey(
        "paspor.UnitOrganisasi", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="Unit Organisasi",
    )
    is_active = models.BooleanField(default=True)
    diberikan_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "role")
        verbose_name = "Peran User"
        verbose_name_plural = "Peran User"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.role == User.Role.ADMIN_UNOR and not self.unit_organisasi_id:
            raise ValidationError({"unit_organisasi": "Admin Unor wajib memiliki unit organisasi."})
        if self.role == User.Role.PEGAWAI and not PegawaiProfile.objects.filter(user_id=self.user_id).exists():
            raise ValidationError({"role": "Role Pegawai wajib memiliki data kepegawaian (PegawaiProfile)."})

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()}"


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


# ---------------------------------------------------------------------------
# Menu Profil (wiki/instructions/BISNIS_PROSES_PDLN.MD §8.3)
# ---------------------------------------------------------------------------

class PasporPegawai(models.Model):
    """Data paspor milik pegawai (Profil → Data Paspor)."""

    class Jenis(models.TextChoices):
        BIASA = "biasa", "Paspor Biasa"
        DINAS = "dinas", "Paspor Dinas"
        DIPLOMATIK = "diplomatik", "Paspor Diplomatik"

    pegawai = models.ForeignKey(User, on_delete=models.CASCADE, related_name="paspor_list")
    nomor = models.CharField("Nomor Paspor", max_length=20)
    jenis = models.CharField("Jenis Paspor", max_length=20, choices=Jenis.choices, default=Jenis.BIASA)
    tgl_expired = models.DateField("Tanggal Expired")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-tgl_expired"]
        verbose_name = "Paspor Pegawai"
        verbose_name_plural = "Paspor Pegawai"

    def __str__(self):
        return f"{self.nomor} ({self.get_jenis_display()})"


def dokumen_kepegawaian_path(instance, filename):
    return f"kepegawaian/{instance.user_id}/{instance.jenis}/{filename}"


class DokumenKepegawaian(models.Model):
    """Dokumen kepegawaian (Profil) — satu berkas per jenis per user. SK
    Penugasan dipakai oleh akun admin."""

    class Jenis(models.TextChoices):
        KTP = "ktp", "KTP"
        KK = "kk", "Kartu Keluarga"
        KARTU_PEGAWAI = "kartu_pegawai", "Kartu Pegawai/SK Pengangkatan PNS"
        IJAZAH = "ijazah", "Akta Kelahiran/Ijazah Terakhir"
        SK_PANGKAT = "sk_pangkat", "SK Kenaikan Pangkat Terakhir"
        PAS_FOTO = "pas_foto", "Pas Foto (4x6 latar putih)"
        SK_PENUGASAN = "sk_penugasan", "SK Penugasan Admin"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dokumen_kepegawaian")
    jenis = models.CharField(max_length=20, choices=Jenis.choices)
    file = models.FileField(upload_to=dokumen_kepegawaian_path)
    uploaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "jenis")
        verbose_name = "Dokumen Kepegawaian"
        verbose_name_plural = "Dokumen Kepegawaian"

    def __str__(self):
        return f"{self.user} — {self.get_jenis_display()}"
