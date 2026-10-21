# Ditulis manual (bukan hasil makemigrations otomatis): ND Kabag & ND Karo
# ditandatangani dua pejabat berbeda, jadi field jabatan/nama lama
# (dipakai ND Kabag) diganti nama jadi *_kabag (RenameField, tidak
# menghapus data yang sudah tersimpan admin lewat halaman Setting), lalu
# ditambah pasangan field baru *_karo.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pengajuan', '0012_pengaturandokumen'),
    ]

    operations = [
        migrations.RenameField(
            model_name='pengaturandokumen',
            old_name='jabatan_penandatangan',
            new_name='jabatan_penandatangan_kabag',
        ),
        migrations.RenameField(
            model_name='pengaturandokumen',
            old_name='nama_pejabat',
            new_name='nama_pejabat_kabag',
        ),
        migrations.AlterField(
            model_name='pengaturandokumen',
            name='jabatan_penandatangan_kabag',
            field=models.CharField(blank=True, max_length=150, verbose_name='Jabatan Pejabat Penandatangan (ND Kabag)'),
        ),
        migrations.AlterField(
            model_name='pengaturandokumen',
            name='nama_pejabat_kabag',
            field=models.CharField(blank=True, max_length=150, verbose_name='Nama Pejabat (ND Kabag)'),
        ),
        migrations.AddField(
            model_name='pengaturandokumen',
            name='jabatan_penandatangan_karo',
            field=models.CharField(blank=True, max_length=150, verbose_name='Jabatan Pejabat Penandatangan (ND Karo)'),
        ),
        migrations.AddField(
            model_name='pengaturandokumen',
            name='nama_pejabat_karo',
            field=models.CharField(blank=True, max_length=150, verbose_name='Nama Pejabat (ND Karo)'),
        ),
    ]
