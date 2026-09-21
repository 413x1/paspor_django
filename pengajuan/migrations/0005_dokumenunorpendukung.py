import django.db.models.deletion
import pengajuan.models
from django.db import migrations, models


class Migration(migrations.Migration):
    """Pisahkan dokumen pendukung Admin Unor (Nota Dinas Sekretaris Unor /
    Nota Dinas Permohonan Persetujuan Menteri / Dokumen Lainnya) dari model
    `DokumenUnor` (yang sekarang hanya menyimpan 3 dokumen wajib) menjadi
    model tersendiri `DokumenUnorPendukung`, sehingga proses unggah berkas
    dan proses mencentang jenisnya berdiri sendiri-sendiri."""

    dependencies = [
        ("pengajuan", "0004_dokumenunor_jenis_lainnya"),
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
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="DokumenUnorPendukung",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(blank=True, upload_to=pengajuan.models.dokumen_unor_pendukung_path)),
                ("uploaded_at", models.DateTimeField(blank=True, null=True)),
                ("nd_sekunor", models.BooleanField(default=False, verbose_name="Nota Dinas Sekretaris Unor")),
                ("nd_menteri", models.BooleanField(default=False, verbose_name="Nota Dinas Permohonan Persetujuan Menteri")),
                ("lainnya", models.BooleanField(default=False, verbose_name="Dokumen Lainnya")),
                (
                    "pengajuan",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dokumen_unor_pendukung",
                        to="pengajuan.pengajuan",
                    ),
                ),
            ],
            options={
                "verbose_name": "Dokumen Pendukung Unor",
                "verbose_name_plural": "Dokumen Pendukung Unor",
            },
        ),
    ]
