# Generated manually — mengubah `Pengajuan.kategori` dan
# `DokumenTemplate.kategori` dari pilihan tetap (CharField + choices)
# menjadi ForeignKey ke `paspor.KategoriPerjalanan`, agar Formulir
# Pengajuan memakai dropdown (dikelompokkan per jenis perjalanan) dengan
# data dari database, dan Admin Biro PAKLN bisa mengelolanya lewat menu
# Manajemen Kategori Perjalanan.
#
# Data lama dipertahankan: nilai teks pada kedua kolom lama
# dicocokkan/dibuatkan padanan barisnya di tabel KategoriPerjalanan, baru
# kolom lama dihapus.

import django.db.models.deletion
from django.db import migrations, models


def migrate_kategori_forward(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    DokumenTemplate = apps.get_model("pengajuan", "DokumenTemplate")
    KategoriPerjalanan = apps.get_model("paspor", "KategoriPerjalanan")

    def resolve(nama):
        nama = nama.strip()
        if not nama:
            return None
        kategori = KategoriPerjalanan.objects.filter(nama_kategori__iexact=nama).first()
        if kategori is None:
            kategori = KategoriPerjalanan.objects.create(nama_kategori=nama, jenis_perjalanan="Non-Dinas")
        return kategori

    for p in Pengajuan.objects.exclude(kategori_legacy=""):
        kategori = resolve(p.kategori_legacy)
        if kategori:
            p.kategori = kategori
            p.save(update_fields=["kategori"])

    for t in DokumenTemplate.objects.exclude(kategori_legacy=""):
        kategori = resolve(t.kategori_legacy)
        if kategori:
            t.kategori = kategori
            t.save(update_fields=["kategori"])


def migrate_kategori_backward(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    DokumenTemplate = apps.get_model("pengajuan", "DokumenTemplate")

    for p in Pengajuan.objects.exclude(kategori__isnull=True):
        p.kategori_legacy = p.kategori.nama_kategori
        p.save(update_fields=["kategori_legacy"])

    for t in DokumenTemplate.objects.exclude(kategori__isnull=True):
        t.kategori_legacy = t.kategori.nama_kategori
        t.save(update_fields=["kategori_legacy"])


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0007_pengajuan_sumber_pembiayaan_fk"),
        ("paspor", "0004_kategoriperjalanan"),
    ]

    operations = [
        migrations.RenameField(
            model_name="pengajuan", old_name="kategori", new_name="kategori_legacy",
        ),
        migrations.RenameField(
            model_name="dokumentemplate", old_name="kategori", new_name="kategori_legacy",
        ),
        migrations.AddField(
            model_name="pengajuan",
            name="kategori",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="pengajuan_list", to="paspor.kategoriperjalanan", verbose_name="Kategori Perjalanan",
            ),
        ),
        migrations.AddField(
            model_name="dokumentemplate",
            name="kategori",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="dokumen_template_list", to="paspor.kategoriperjalanan",
                verbose_name="Kategori Perjalanan Tertentu",
                help_text="Kosongkan agar berlaku untuk seluruh kategori perjalanan.",
            ),
        ),
        migrations.RunPython(migrate_kategori_forward, migrate_kategori_backward),
        migrations.RemoveField(model_name="pengajuan", name="kategori_legacy"),
        migrations.RemoveField(model_name="dokumentemplate", name="kategori_legacy"),
    ]
