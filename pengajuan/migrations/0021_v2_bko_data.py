"""PDLN Tipe 2 Pendidikan v2 — data QC ikut pola Admin BKO (keputusan #6,
wiki/instructions/PDLN_TIPE_2_FLOW.MD §8.9):

1. SK Tugas Belajar yang sudah diunggah Admin Biro PAKLN dipindah ke
   DokumenBko (hanya referensi berkas, berkas fisik tidak dipindah).
2. T2P yang sudah pernah diteruskan BPSDM ke Biro PAKLN dibuka track BKO-nya
   (`diunggah` bila SK Tubel ada, selain itu `menunggu`).
"""

from django.db import migrations


def maju(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    DokumenPakln = apps.get_model("pengajuan", "DokumenPakln")
    DokumenBko = apps.get_model("pengajuan", "DokumenBko")

    for dok in DokumenPakln.objects.filter(jenis="sk_tubel"):
        DokumenBko.objects.update_or_create(
            pengajuan_id=dok.pengajuan_id, jenis="sk_tubel",
            defaults={"file": dok.file.name, "tanggal_surat": dok.tanggal_surat},
        )
        # `uploaded_at` auto_now_add — salin nilai lama lewat update().
        DokumenBko.objects.filter(pengajuan_id=dok.pengajuan_id, jenis="sk_tubel").update(
            uploaded_at=dok.uploaded_at,
        )
        dok.delete()

    ada_sk = set(DokumenBko.objects.filter(jenis="sk_tubel").values_list("pengajuan_id", flat=True))
    for p in Pengajuan.objects.filter(
        jenis_perjalanan="pdln", tipe_pdln="T2P", tgl_masuk_pakln__isnull=False, status_bko="",
    ):
        p.tgl_masuk_bko = p.tgl_masuk_pakln
        p.status_bko = "diunggah" if p.pk in ada_sk else "menunggu"
        p.save(update_fields=["tgl_masuk_bko", "status_bko"])


def mundur(apps, schema_editor):
    DokumenPakln = apps.get_model("pengajuan", "DokumenPakln")
    DokumenBko = apps.get_model("pengajuan", "DokumenBko")
    for dok in DokumenBko.objects.filter(jenis="sk_tubel"):
        DokumenPakln.objects.update_or_create(
            pengajuan_id=dok.pengajuan_id, jenis="sk_tubel",
            defaults={"file": dok.file.name, "tanggal_surat": dok.tanggal_surat},
        )
        dok.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0020_v2_bko_skema"),
    ]

    operations = [
        migrations.RunPython(maju, mundur),
    ]
