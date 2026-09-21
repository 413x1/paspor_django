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
