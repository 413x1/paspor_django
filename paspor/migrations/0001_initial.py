from django.db import migrations, models


class Migration(migrations.Migration):
    """Pindahkan model UnitOrganisasi (tabel `org_units`) ke app `paspor`.

    Tabel fisik `org_units` sudah dibuat oleh
    `accounts/0003_unit_organisasi_table`. Migrasi ini hanya mengklaim
    model tersebut ke dalam state app `paspor` tanpa mengubah database
    (dipasangkan dengan `accounts/0005` yang menghapusnya dari state
    `accounts`)."""

    initial = True

    dependencies = [
        ("accounts", "0003_unit_organisasi_table"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="UnitOrganisasi",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("code", models.CharField(max_length=2, unique=True, verbose_name="Kode")),
                        ("alias", models.CharField(max_length=20, verbose_name="Alias")),
                        ("name", models.CharField(max_length=150, verbose_name="Nama")),
                    ],
                    options={
                        "verbose_name": "Unit Organisasi",
                        "verbose_name_plural": "Unit Organisasi",
                        "db_table": "org_units",
                        "ordering": ["code"],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
