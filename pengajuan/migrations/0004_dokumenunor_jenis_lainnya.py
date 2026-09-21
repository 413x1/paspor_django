from django.db import migrations, models


class Migration(migrations.Migration):
    """Tambah pilihan jenis 'lainnya' (Dokumen Lainnya) pada DokumenUnor —
    bagian dari skema baru 3 dokumen wajib + 1 berkas pendukung dengan
    checklist. Hanya mengubah `choices` (validasi Python), tidak mengubah
    skema tabel di database."""

    dependencies = [
        ("pengajuan", "0003_pengajuan_catatan_unor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dokumenunor",
            name="jenis",
            field=models.CharField(
                choices=[
                    ("disposisi", "Lembar Disposisi"),
                    ("iln_pimpinan", "Formulir Izin Luar Negeri (TTD Pimpinan Unor)"),
                    ("nd_biropakln", "Nota Dinas ke Biro PAKLN"),
                    ("nd_sekunor", "Nota Dinas Sekretaris Unor"),
                    ("nd_menteri", "Nota Dinas Permohonan Persetujuan Menteri"),
                    ("lainnya", "Dokumen Lainnya"),
                ],
                max_length=20,
            ),
        ),
    ]
