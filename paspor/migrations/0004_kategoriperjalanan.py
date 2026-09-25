# Generated manually (mengikuti pola paspor/migrations/0003_sumberpembiayaan.py)

from django.db import migrations, models

# Data awal tabel KategoriPerjalanan — 4 pilihan lama pada alur
# Non-Kedinasan (dulu tersimpan sebagai TextChoices di Pengajuan.Kategori).
KATEGORI_PERJALANAN = [
    ("Non-Dinas", "Ibadah"),
    ("Non-Dinas", "Pendidikan"),
    ("Non-Dinas", "Keperluan Pribadi"),
    ("Non-Dinas", "Lainnya"),
]


def seed_kategori_perjalanan(apps, schema_editor):
    KategoriPerjalanan = apps.get_model("paspor", "KategoriPerjalanan")
    for jenis_perjalanan, nama_kategori in KATEGORI_PERJALANAN:
        KategoriPerjalanan.objects.update_or_create(
            nama_kategori=nama_kategori, jenis_perjalanan=jenis_perjalanan,
        )


def unseed_kategori_perjalanan(apps, schema_editor):
    apps.get_model("paspor", "KategoriPerjalanan").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("paspor", "0003_sumberpembiayaan"),
    ]

    operations = [
        migrations.CreateModel(
            name="KategoriPerjalanan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("jenis_perjalanan", models.CharField(
                    choices=[("PDLN", "PDLN (Perjalanan Dinas Luar Negeri)"), ("Non-Dinas", "Perjalanan Non Dinas Luar Negeri")],
                    default="Non-Dinas", max_length=20, verbose_name="Jenis Perjalanan",
                )),
                ("nama_kategori", models.CharField(max_length=100, verbose_name="Nama Kategori")),
                ("is_active", models.BooleanField(default=True, verbose_name="Aktif")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Kategori Perjalanan",
                "verbose_name_plural": "Kategori Perjalanan",
                "ordering": ["jenis_perjalanan", "nama_kategori"],
            },
        ),
        migrations.RunPython(seed_kategori_perjalanan, unseed_kategori_perjalanan),
    ]
