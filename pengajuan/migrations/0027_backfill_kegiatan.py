"""Tautkan pengajuan PDLN lama ke objek Kegiatan
(wiki/instructions/EVENT_IMPLEMENTATION_PLAN.MD §11). Pengajuan dengan data
kegiatan yang sama (nama beasiswa, penyelenggara/perguruan tinggi, kota,
tanggal kegiatan, negara tujuan) dikelompokkan menjadi satu Kegiatan
berstatus disetujui. Non-Kedinasan tidak disentuh."""

from django.db import migrations

KETERANGAN_MIGRASI = "Migrasi data pengajuan"


def backfill(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    Kegiatan = apps.get_model("paspor", "Kegiatan")
    DasarKegiatan = apps.get_model("paspor", "DasarKegiatan")

    kelompok = {}
    qs = (
        Pengajuan.objects.filter(jenis_perjalanan="pdln", kegiatan__isnull=True, detail_pdln__isnull=False)
        .select_related("detail_pdln").prefetch_related("tujuan_negara").order_by("created_at")
    )
    for p in qs:
        d = p.detail_pdln
        mulai = d.tgl_mulai_kegiatan or p.tgl_berangkat
        selesai = d.tgl_selesai_kegiatan or p.tgl_kembali or mulai
        if not mulai:
            continue  # draft tanpa tanggal — pegawai memilih kegiatan saat melanjutkan formulir
        negara = frozenset(n.pk for n in p.tujuan_negara.all())
        penyelenggara = d.penyelenggara or d.perguruan_tinggi
        kunci = (d.beasiswa_nama, penyelenggara, d.kota_tujuan, mulai, selesai, negara)
        kelompok.setdefault(kunci, []).append(p)

    kode_terpakai = set(Kegiatan.objects.exclude(kode_pintar=None).values_list("kode_pintar", flat=True))
    for (nama, penyelenggara, kota, mulai, selesai, negara), daftar in kelompok.items():
        pertama = daftar[0]
        kode = pertama.detail_pdln.beasiswa_pintar_id or None
        if kode in kode_terpakai:
            kode = None
        if kode:
            kode_terpakai.add(kode)
        kegiatan = Kegiatan.objects.create(
            nama=(nama or f"Kegiatan {penyelenggara or kota or pertama.kode} {mulai.year}")[:255],
            kota=kota or "-",
            penyelenggara=penyelenggara or "-",
            tgl_mulai=mulai,
            tgl_selesai=max(selesai, mulai),
            tahun_pelaksanaan=mulai.year,
            status="disetujui",
            sumber_data="pintar" if kode else "manual",
            kode_pintar=kode,
        )
        kegiatan.negara.set(negara)
        kegiatan.kategori.set({p.kategori_id for p in daftar if p.kategori_id})
        kegiatan.skema_pendanaan.set({p.sumber_pembiayaan_id for p in daftar if p.sumber_pembiayaan_id})
        if kode:
            DasarKegiatan.objects.create(kegiatan=kegiatan, jenis="pintar", kode_pintar=kode)
        else:
            DasarKegiatan.objects.create(
                kegiatan=kegiatan, jenis="lainnya", keterangan=f"{KETERANGAN_MIGRASI} {pertama.kode}"[:255],
            )
        for p in daftar:
            p.kegiatan = kegiatan
            p.save(update_fields=["kegiatan"])
            d = p.detail_pdln
            d.kegiatan_nama = kegiatan.nama
            d.kegiatan_tahun = kegiatan.tahun_pelaksanaan
            d.save(update_fields=["kegiatan_nama", "kegiatan_tahun"])


def reverse(apps, schema_editor):
    Pengajuan = apps.get_model("pengajuan", "Pengajuan")
    Kegiatan = apps.get_model("paspor", "Kegiatan")
    DetailPdln = apps.get_model("pengajuan", "DetailPdln")
    ids = set(Pengajuan.objects.exclude(kegiatan=None).values_list("kegiatan_id", flat=True))
    Pengajuan.objects.update(kegiatan=None)
    DetailPdln.objects.update(kegiatan_nama="", kegiatan_tahun=None)
    Kegiatan.objects.filter(pk__in=ids, diusulkan_oleh=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("paspor", "0008_kegiatan"),
        ("pengajuan", "0026_pengajuan_kegiatan"),
    ]

    operations = [
        migrations.RunPython(backfill, reverse),
    ]
