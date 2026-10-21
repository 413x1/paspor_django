"""SK Tugas Belajar tidak lagi diunggah Admin Biro PAKLN (dipindah ke
DokumenBko oleh 0021) — lihat wiki/instructions/PDLN_TIPE_2_FLOW.MD §8."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pengajuan', '0021_v2_bko_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dokumenpakln',
            name='jenis',
            field=models.CharField(choices=[('iln_sekjen', '3.a Izin Luar Negeri (TTD Sekjen a.n. Menteri)'), ('sp_setneg', 'SP Setneg'), ('paspor_dinas', 'Paspor Dinas'), ('exit_permit', 'Exit Permit'), ('visa', 'Rekomendasi Visa'), ('nd_karo_unor', 'Nota Dinas Karo PAKLN ke Sekretaris Unor hal Penyampaian Dokumen PDLN')], max_length=30),
        ),
    ]
