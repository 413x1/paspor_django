import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Lepas model UnitOrganisasi dari state app `accounts` dan arahkan
    ForeignKey `User.unit_organisasi` / `PegawaiProfile.unit_organisasi`
    ke `paspor.UnitOrganisasi`.

    Tabel `org_units` dan kolom FK tidak berubah di database — hanya
    kepemilikan model pada state migrasi yang berpindah ke app `paspor`
    (lihat `paspor/0001_initial`)."""

    dependencies = [
        ("accounts", "0004_user_unit_kerja"),
        ("paspor", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="user",
                    name="unit_organisasi",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="paspor.unitorganisasi",
                        verbose_name="Unit Organisasi",
                    ),
                ),
                migrations.AlterField(
                    model_name="pegawaiprofile",
                    name="unit_organisasi",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="paspor.unitorganisasi",
                        verbose_name="Unit Organisasi",
                    ),
                ),
                migrations.DeleteModel(name="UnitOrganisasi"),
            ],
            database_operations=[],
        ),
    ]
