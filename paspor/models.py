from django.db import models


class UnitOrganisasi(models.Model):
    """Unit organisasi eselon I Kementerian Pekerjaan Umum (tabel
    `org_units`). Dipakai sebagai referensi untuk cakupan kerja Admin Unor
    dan data kepegawaian pegawai."""

    code = models.CharField("Kode", max_length=2, unique=True)
    alias = models.CharField("Alias", max_length=20)
    name = models.CharField("Nama", max_length=150)

    class Meta:
        db_table = "org_units"
        ordering = ["code"]
        verbose_name = "Unit Organisasi"
        verbose_name_plural = "Unit Organisasi"

    def __str__(self):
        return f"{self.alias} — {self.name}"


class Negara(models.Model):
    """Data referensi negara tujuan perjalanan luar negeri. Dikelola oleh
    Admin Biro PAKLN (menu Manajemen Negara) dan dipakai sebagai sumber
    pilihan pada field "Tujuan Negara" di Formulir Pengajuan."""

    nama_negara = models.CharField("Nama Negara", max_length=100, unique=True)
    kode_negara = models.CharField(
        "Kode Negara", max_length=5, blank=True,
        help_text="Opsional, mis. kode ISO 3166-1 alpha-2 (ID, SA, SG, dst.)",
    )
    is_active = models.BooleanField("Aktif", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nama_negara"]
        verbose_name = "Negara"
        verbose_name_plural = "Negara"

    def __str__(self):
        return self.nama_negara


class SumberPembiayaan(models.Model):
    """Data referensi sumber pembiayaan perjalanan luar negeri. Dikelola
    oleh Admin Biro PAKLN (menu Manajemen Sumber Pembiayaan) dan dipakai
    sebagai sumber pilihan pada field "Sumber Pembiayaan" di Formulir
    Pengajuan. `tipe_perjalanan` membedakan untuk alur Non-Kedinasan yang
    sudah berjalan dan alur PDLN (Perjalanan Dinas Luar Negeri) yang akan
    menyusul."""

    class TipePerjalanan(models.TextChoices):
        PDLN = "PDLN", "PDLN (Perjalanan Dinas Luar Negeri)"
        NON_DINAS = "Non-Dinas", "Non-Dinas"

    tipe_perjalanan = models.CharField(
        "Tipe Perjalanan", max_length=20, choices=TipePerjalanan.choices,
        default=TipePerjalanan.NON_DINAS,
    )
    nama = models.CharField("Nama", max_length=100)
    keterangan = models.TextField("Keterangan", blank=True)
    is_active = models.BooleanField("Aktif", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tipe_perjalanan", "nama"]
        verbose_name = "Sumber Pembiayaan"
        verbose_name_plural = "Sumber Pembiayaan"

    def __str__(self):
        return self.nama
