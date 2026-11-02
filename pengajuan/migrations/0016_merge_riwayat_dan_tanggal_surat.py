from django.db import migrations


class Migration(migrations.Migration):
    """Menggabungkan dua cabang migrasi: riwayat pengajuan (0014/0015 dari
    branch riwayat-pemrosesan-ajuan) dan tanggal surat dokumen (0014/0015
    dari main). Tidak ada operasi — keduanya tidak saling bergantung."""

    dependencies = [
        ("pengajuan", "0015_backfill_riwayat"),
        ("pengajuan", "0015_dokumenpakln_tanggal_surat_and_more"),
    ]

    operations = []
