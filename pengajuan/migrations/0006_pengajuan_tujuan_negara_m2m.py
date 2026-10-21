# Generated manually — mengubah `Pengajuan.tujuan_negara` dari teks bebas
# (CharField) menjadi ManyToManyField ke `paspor.Negara`, agar Formulir
# Pengajuan bisa memakai dropdown multi-select dengan data dari database
# (lihat wiki/instructions terkait fitur "Field Tujuan Negara").
#
# Data lama dipertahankan: nilai teks pada kolom lama dicocokkan/dibuatkan
# padanan barisnya di tabel Negara, baru kolom lama dihapus.

import django.db.models.deletion
from django.db import migrations, models


def migrate_tujuan_negara_forward(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    Negara = apps.get_model("paspor", "Negara")

    for p in Pengajuan.objects.exclude(tujuan_negara_legacy=""):
        nama = p.tujuan_negara_legacy.strip()
        if not nama:
            continue
        negara = Negara.objects.filter(nama_negara__iexact=nama).first()
        if negara is None:
            negara = Negara.objects.create(nama_negara=nama)
        p.tujuan_negara.add(negara)


def migrate_tujuan_negara_backward(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    for p in Pengajuan.objects.all():
        nama_list = list(p.tujuan_negara.values_list("nama_negara", flat=True))
        if nama_list:
            p.tujuan_negara_legacy = ", ".join(nama_list)
            p.save(update_fields=["tujuan_negara_legacy"])


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0005_dokumenunorpendukung"),
        ("paspor", "0002_negara"),
    ]

    operations = [
        migrations.RenameField(
            model_name="pengajuan", old_name="tujuan_negara", new_name="tujuan_negara_legacy",
        ),
        migrations.AddField(
            model_name="pengajuan",
            name="tujuan_negara",
            field=models.ManyToManyField(
                blank=True, related_name="pengajuan_list", to="paspor.negara", verbose_name="Tujuan Negara",
            ),
        ),
        migrations.RunPython(migrate_tujuan_negara_forward, migrate_tujuan_negara_backward),
        migrations.RemoveField(model_name="pengajuan", name="tujuan_negara_legacy"),
    ]
