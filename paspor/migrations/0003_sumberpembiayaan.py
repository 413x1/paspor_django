# Generated manually (mengikuti pola paspor/migrations/0002_negara.py)

from django.db import migrations, models

# Data awal tabel SumberPembiayaan — 3 pilihan lama pada alur Non-Kedinasan
# (dulu tersimpan sebagai TextChoices di Pengajuan.SumberPembiayaan).
SUMBER_PEMBIAYAAN = [
    ("Non-Dinas", "Biaya Sendiri", ""),
    ("Non-Dinas", "Sponsor/Penyelenggara", ""),
    ("Non-Dinas", "Negara/Lembaga Lain", ""),
]


def seed_sumber_pembiayaan(apps, schema_editor):
    SumberPembiayaan = apps.get_model("paspor", "SumberPembiayaan")
    for tipe_perjalanan, nama, keterangan in SUMBER_PEMBIAYAAN:
        SumberPembiayaan.objects.update_or_create(
            nama=nama, tipe_perjalanan=tipe_perjalanan, defaults={"keterangan": keterangan}
        )


def unseed_sumber_pembiayaan(apps, schema_editor):
    apps.get_model("paspor", "SumberPembiayaan").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("paspor", "0002_negara"),
    ]

    operations = [
        migrations.CreateModel(
            name="SumberPembiayaan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipe_perjalanan", models.CharField(
                    choices=[("PDLN", "PDLN (Perjalanan Dinas Luar Negeri)"), ("Non-Dinas", "Non-Dinas")],
                    default="Non-Dinas", max_length=20, verbose_name="Tipe Perjalanan",
                )),
                ("nama", models.CharField(max_length=100, verbose_name="Nama")),
                ("keterangan", models.TextField(blank=True, verbose_name="Keterangan")),
                ("is_active", models.BooleanField(default=True, verbose_name="Aktif")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sumber Pembiayaan",
                "verbose_name_plural": "Sumber Pembiayaan",
                "ordering": ["tipe_perjalanan", "nama"],
            },
        ),
        migrations.RunPython(seed_sumber_pembiayaan, unseed_sumber_pembiayaan),
    ]
