from django.db import migrations


def tandai_dikirim(apps, schema_editor):
    """Pengajuan PDLN Tipe 2 yang Surat Tugasnya sudah diunggah di tahap Admin Unor (aturan lama)
    ditandai `dikirim`, sehingga tetap bisa diproses di aturan baru. Sengaja memakai update()
    agar `updated_at` (dasar filter Rekap Progres) tidak berubah."""
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    DokumenUnor = apps.get_model("pengajuan", "DokumenUnor")
    ada_surat_tugas = DokumenUnor.objects.filter(
        jenis="surat_tugas", pengajuan__jenis_perjalanan="pdln", pengajuan__tipe_pdln__in=["T2P", "T2L"],
    ).values_list("pengajuan_id", flat=True)
    Pengajuan.objects.filter(pk__in=list(ada_surat_tugas), status_surat_tugas="").update(
        status_surat_tugas="dikirim"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0031_surat_tugas_jalur"),
    ]

    operations = [
        # Tanpa pembalikan: kolom `status_surat_tugas` dihapus oleh migrasi 0031 bila di-rollback.
        migrations.RunPython(tandai_dikirim, migrations.RunPython.noop),
    ]
