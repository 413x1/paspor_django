"""
Backfill RiwayatPengajuan untuk pengajuan yang sudah berjalan sebelum
fitur riwayat ada (wiki/instructions/RIWAYAT_PEMROSESAN_PENGAJUAN.MD §7).

Baris yang dibuat hanya *perkiraan* dari tanggal & catatan yang tersisa;
pesan pengembalian yang dulu sudah dikosongkan tidak bisa dipulihkan.
"""

from datetime import datetime, time

from django.db import migrations
from django.utils import timezone

DATA_LAMA = "(data lama)"


def _awal_hari(tanggal):
    return timezone.make_aware(datetime.combine(tanggal, time.min))


def _nama_pegawai(pengajuan):
    profile = getattr(pengajuan.pegawai, "profile", None)
    if profile is not None and profile.nama:
        return profile.nama
    user = pengajuan.pegawai
    return f"{user.first_name} {user.last_name}".strip() or user.username


def backfill(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    RiwayatPengajuan = apps.get_model("pengajuan", "RiwayatPengajuan")

    sudah_ada = set(RiwayatPengajuan.objects.values_list("pengajuan_id", flat=True))
    baris = []
    for p in Pengajuan.objects.select_related("pegawai", "pegawai__profile").iterator():
        if p.pk in sudah_ada:
            continue

        # (aksi, status_dari, status_ke, waktu, aktor, aktor_role, aktor_nama, catatan)
        # Urutan daftar = urutan logis; waktu dijaga tidak mundur agar
        # urutan tampil (created_at, id) tetap benar.
        kandidat = []
        if p.tgl_pengajuan:
            kandidat.append((
                "dikirim", "belum", "proses", _awal_hari(p.tgl_pengajuan),
                p.pegawai, "pegawai", _nama_pegawai(p), "",
            ))
        if p.tgl_masuk_pakln:
            kandidat.append((
                "diteruskan_pakln", "proses", "proses_pakln", _awal_hari(p.tgl_masuk_pakln),
                None, "admin_unor", DATA_LAMA, "",
            ))
        if p.catatan_pakln:
            kandidat.append((
                "dikembalikan_pakln", "proses_pakln", "proses", p.updated_at,
                None, "admin_pakln", DATA_LAMA, p.catatan_pakln,
            ))
        if p.catatan_unor:
            kandidat.append((
                "dikembalikan_unor", "proses", "belum", p.updated_at,
                None, "admin_unor", DATA_LAMA, p.catatan_unor,
            ))
        if p.tgl_selesai:
            kandidat.append((
                "selesai", "proses_pakln", "selesai", _awal_hari(p.tgl_selesai),
                None, "admin_pakln", DATA_LAMA, "",
            ))

        terakhir = None
        for aksi, dari, ke, waktu, aktor, role, nama, catatan in kandidat:
            if terakhir and waktu < terakhir:
                waktu = terakhir
            terakhir = waktu
            baris.append(RiwayatPengajuan(
                pengajuan_id=p.pk, aksi=aksi, status_dari=dari, status_ke=ke,
                aktor=aktor, aktor_role=role, aktor_nama=nama[:150],
                catatan=catatan, created_at=waktu,
            ))

    RiwayatPengajuan.objects.bulk_create(baris)


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0014_riwayatpengajuan"),
        ("accounts", "0005_move_unitorganisasi_to_paspor"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
