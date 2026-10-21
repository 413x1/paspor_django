"""Seed master Kategori Perjalanan & Sumber Pembiayaan untuk alur PDLN,
sesuai wiki/instructions/BISNIS_PROSES_PDLN.MD §5 (daftar pilihan per tipe
pada mockup Tahap 2). Idempoten: baris yang sudah ada tidak diubah kecuali
`tipe_pdln`-nya masih kosong."""

from django.db import migrations

KATEGORI_PDLN = [
    ("Pertemuan Bilateral/Regional/Multilateral", ["T1", "T3"]),
    ("Pameran/Expo", ["T1", "T3"]),
    ("Pemberian Advis Teknis", ["T1", "T3"]),
    ("Pendampingan", ["T1", "T3"]),
    ("Master", ["T2P"]),
    ("Doctoral", ["T2P"]),
    ("Short Course-Training", ["T2L"]),
    ("Seminar/Lokakarya", ["T2L"]),
    ("Workshop", ["T2L"]),
    ("Simposium/Konferensi Internasional", ["T2L"]),
]

SUMBER_PDLN = [
    ("DIPA Kementerian PU", []),
    ("DIPA K/L Lain", []),
    ("Donor Penyelenggara", ["T1", "T3"]),
    ("Beasiswa LPDP", ["T2P"]),
    ("Beasiswa/Donor Luar Negeri", ["T2P", "T2L"]),
    ("Beasiswa Lainnya", ["T2P", "T2L"]),
]


def seed(apps, schema_editor):
    KategoriPerjalanan = apps.get_model("paspor", "KategoriPerjalanan")
    SumberPembiayaan = apps.get_model("paspor", "SumberPembiayaan")

    for nama, tipe in KATEGORI_PDLN:
        obj, created = KategoriPerjalanan.objects.get_or_create(
            jenis_perjalanan="PDLN", nama_kategori=nama, defaults={"tipe_pdln": tipe},
        )
        if not created and not obj.tipe_pdln:
            obj.tipe_pdln = tipe
            obj.save(update_fields=["tipe_pdln"])

    for nama, tipe in SUMBER_PDLN:
        obj, created = SumberPembiayaan.objects.get_or_create(
            tipe_perjalanan="PDLN", nama=nama, defaults={"tipe_pdln": tipe},
        )
        if not created and not obj.tipe_pdln:
            obj.tipe_pdln = tipe
            obj.save(update_fields=["tipe_pdln"])


class Migration(migrations.Migration):

    dependencies = [
        ("paspor", "0006_pdln_master"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
