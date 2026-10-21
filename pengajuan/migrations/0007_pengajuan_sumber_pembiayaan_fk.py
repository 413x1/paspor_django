# Generated manually — mengubah `Pengajuan.sumber_pembiayaan` dari pilihan
# tetap (CharField + choices) menjadi ForeignKey ke `paspor.SumberPembiayaan`,
# agar Formulir Pengajuan memakai dropdown dengan data dari database dan
# Admin Biro PAKLN bisa mengelolanya lewat menu Manajemen Sumber Pembiayaan.
#
# Data lama dipertahankan: nilai teks pada kolom lama dicocokkan/dibuatkan
# padanan barisnya di tabel SumberPembiayaan, baru kolom lama dihapus.

import django.db.models.deletion
from django.db import migrations, models


def migrate_sumber_pembiayaan_forward(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    SumberPembiayaan = apps.get_model("paspor", "SumberPembiayaan")

    for p in Pengajuan.objects.exclude(sumber_pembiayaan_legacy=""):
        nama = p.sumber_pembiayaan_legacy.strip()
        if not nama:
            continue
        sumber = SumberPembiayaan.objects.filter(nama__iexact=nama).first()
        if sumber is None:
            sumber = SumberPembiayaan.objects.create(nama=nama, tipe_perjalanan="Non-Dinas")
        p.sumber_pembiayaan = sumber
        p.save(update_fields=["sumber_pembiayaan"])


def migrate_sumber_pembiayaan_backward(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    for p in Pengajuan.objects.exclude(sumber_pembiayaan__isnull=True):
        p.sumber_pembiayaan_legacy = p.sumber_pembiayaan.nama
        p.save(update_fields=["sumber_pembiayaan_legacy"])


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0006_pengajuan_tujuan_negara_m2m"),
        ("paspor", "0003_sumberpembiayaan"),
    ]

    operations = [
        migrations.RenameField(
            model_name="pengajuan", old_name="sumber_pembiayaan", new_name="sumber_pembiayaan_legacy",
        ),
        migrations.AddField(
            model_name="pengajuan",
            name="sumber_pembiayaan",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="pengajuan_list", to="paspor.sumberpembiayaan", verbose_name="Sumber Pembiayaan",
            ),
        ),
        migrations.RunPython(migrate_sumber_pembiayaan_forward, migrate_sumber_pembiayaan_backward),
        migrations.RemoveField(model_name="pengajuan", name="sumber_pembiayaan_legacy"),
    ]
