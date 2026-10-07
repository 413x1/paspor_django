"""Isi snapshot `Pengajuan.unit_organisasi` dari profil pegawai untuk
pengajuan yang sudah pernah dikirim (BISNIS_PROSES_PDLN.MD §8.6 langkah 2).
Seluruh data lama sudah otomatis `jenis_perjalanan = "nondinas"` (default
kolom)."""

from django.db import migrations


def backfill(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    PegawaiProfile = apps.get_model("accounts", "PegawaiProfile")
    unit_per_pegawai = dict(
        PegawaiProfile.objects.exclude(unit_organisasi=None).values_list("user_id", "unit_organisasi_id")
    )
    for p in Pengajuan.objects.filter(unit_organisasi=None).exclude(tgl_pengajuan=None).only("id", "pegawai_id"):
        unit_id = unit_per_pegawai.get(p.pegawai_id)
        if unit_id:
            Pengajuan.objects.filter(pk=p.pk).update(unit_organisasi_id=unit_id)


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0018_pdln_fondasi"),
        ("accounts", "0006_alter_user_role_pasporpegawai_dokumenkepegawaian"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
