import django.core.validators
import django.db.models.deletion
import pengajuan.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("paspor", "0001_initial"),
        ("pengajuan", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DokumenTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nama", models.CharField(max_length=150, verbose_name="Nama Template")),
                ("keterangan", models.CharField(blank=True, max_length=255, verbose_name="Keterangan")),
                (
                    "file",
                    models.FileField(
                        upload_to=pengajuan.models.dokumen_template_path,
                        validators=[django.core.validators.FileExtensionValidator(allowed_extensions=["pdf", "docx"])],
                        verbose_name="Berkas",
                    ),
                ),
                ("untuk_pegawai", models.BooleanField(default=True, verbose_name="Untuk Pegawai")),
                ("untuk_admin_unor", models.BooleanField(default=True, verbose_name="Untuk Admin Unor")),
                (
                    "kategori",
                    models.CharField(
                        blank=True,
                        choices=[("Ibadah", "Ibadah"), ("Pendidikan", "Pendidikan"), ("Keperluan Pribadi", "Keperluan Pribadi"), ("Lainnya", "Lainnya")],
                        help_text="Kosongkan agar berlaku untuk seluruh kategori perjalanan.",
                        max_length=30,
                        verbose_name="Kategori Perjalanan Tertentu",
                    ),
                ),
                ("aktif", models.BooleanField(default=True, verbose_name="Tampilkan")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "diunggah_oleh",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "unit_organisasi",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Kosongkan agar berlaku untuk seluruh unit organisasi.",
                        related_name="dokumen_template_list",
                        to="paspor.unitorganisasi",
                        verbose_name="Unit Organisasi Tertentu",
                    ),
                ),
            ],
            options={
                "verbose_name": "Template Dokumen",
                "verbose_name_plural": "Template Dokumen",
                "ordering": ["nama"],
            },
        ),
    ]
