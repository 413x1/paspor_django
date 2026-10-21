# 03 — State Diagram

Acuan: [BISNIS_PROSES_PDLN.MD §4.1, §4.4, §4.5](../instructions/BISNIS_PROSES_PDLN.MD#41-status).

## 3.1 Status `Pengajuan` — Non-Dinas, PDLN Tipe 1 & Tipe 3

```mermaid
stateDiagram-v2
    direction LR
    [*] --> belum: Pegawai simpan formulir
    belum --> proses: dikirim / dikirim_ulang
    proses --> belum: dikembalikan_unor
    proses --> proses_pakln: diteruskan_pakln / diteruskan_ulang
    proses_pakln --> proses: dikembalikan_pakln
    proses_pakln --> selesai: selesai

    belum --> dibatalkan: pembatalan disetujui
    proses --> dibatalkan: pembatalan disetujui
    proses_pakln --> dibatalkan: pembatalan disetujui
    selesai --> dibatalkan: pembatalan disetujui

    selesai --> [*]: Non-Dinas tuntas / PDLN setelah laporan disetujui
    dibatalkan --> [*]
```

## 3.2 Status `Pengajuan` — PDLN Tipe 2 (T2P/T2L)

```mermaid
stateDiagram-v2
    direction LR
    [*] --> belum: Pegawai simpan formulir
    belum --> proses: dikirim / dikirim_ulang
    proses --> belum: dikembalikan_unor
    proses --> proses_bpsdm: diteruskan_bpsdm / diteruskan_ulang_bpsdm
    proses_bpsdm --> proses: dikembalikan_bpsdm
    proses_bpsdm --> proses_pakln: diteruskan_pakln / diteruskan_ulang
    proses_pakln --> proses_bpsdm: dikembalikan_pakln
    proses_pakln --> selesai: selesai

    state "dibatalkan" as batal
    belum --> batal
    proses --> batal
    proses_bpsdm --> batal
    proses_pakln --> batal
    selesai --> batal

    selesai --> [*]: setelah Laporan PDLN disetujui
    batal --> [*]
```

Catatan:

- Transisi ke `dibatalkan` hanya terjadi saat **Admin PAKLN menyetujui**
  permohonan pembatalan (3.4). Draft yang belum pernah dikirim dapat
  langsung dibatalkan pegawai.
- Selama permohonan pembatalan terbuka, **tidak ada transisi lain** yang
  boleh terjadi (status dibekukan).

## 3.3 Status `LaporanPdln`

Berjalan di dalam `Pengajuan.status = selesai` (khusus PDLN).

```mermaid
stateDiagram-v2
    direction LR
    [*] --> belum_ada: Pengajuan PDLN selesai
    belum_ada --> menunggu: Pegawai unggah
    menunggu --> dikembalikan: Admin PAKLN kembalikan (catatan wajib)
    dikembalikan --> menunggu: Pegawai unggah ulang (catatan balasan wajib)
    menunggu --> disetujui: Admin PAKLN setujui
    disetujui --> [*]: Pengajuan tuntas

    note right of belum_ada
        Turunan, bukan baris tabel:
        belum ada record LaporanPdln.
        Ditandai Terlambat bila lewat
        tgl_kembali + batas hari.
    end note
```

## 3.4 Status `PermohonanPembatalan`

```mermaid
stateDiagram-v2
    direction LR
    [*] --> menunggu_unor: diajukan Pegawai
    [*] --> menunggu_pakln: diajukan Admin Unor
    menunggu_unor --> menunggu_pakln: Admin Unor setuju
    menunggu_unor --> ditolak: Admin Unor tolak (catatan wajib)
    menunggu_pakln --> disetujui: Admin PAKLN setuju
    menunggu_pakln --> ditolak: Admin PAKLN tolak (catatan wajib)
    menunggu_unor --> ditarik: pengaju menarik
    menunggu_pakln --> ditarik: pengaju menarik
    disetujui --> [*]: Pengajuan.status = dibatalkan
    ditolak --> [*]: alur utama dilanjutkan
    ditarik --> [*]: alur utama dilanjutkan
```

## 3.5 Matriks aksi per status (siapa boleh melakukan apa)

| Status `Pengajuan` | Pegawai | Admin Unor | Admin BPSDM | Admin PAKLN |
|---|---|---|---|---|
| `belum` (draft) | Edit, unggah, kirim, batalkan draft | — | — | — |
| `belum` (dikembalikan) | Perbaiki, kirim ulang (catatan), ajukan batal | Ajukan batal | — | — |
| `proses` | Lihat, ajukan batal | Pratinjau, kembalikan, unggah, teruskan, ajukan batal | — | — |
| `proses_bpsdm` | Lihat, ajukan batal | Lihat, ajukan batal | Pratinjau, kembalikan, unggah, teruskan | — |
| `proses_pakln` | Lihat, ajukan batal | Lihat, ajukan batal | Lihat (T2) | Pratinjau, kembalikan, unggah, selesaikan |
| `selesai` (Non-Dinas) | Unduh ILN, ajukan batal (s.d. tgl berangkat) | Ajukan batal | — | — |
| `selesai` (PDLN) | Unggah laporan, unduh dokumen, ajukan batal (selama laporan belum disetujui) | Ajukan batal, monitor laporan | Lihat (T2) | Verifikasi laporan |
| `dibatalkan` | Lihat | Lihat | Lihat (T2) | Lihat |
| *Permohonan pembatalan terbuka* | Tarik (jika pengaju) | Putuskan jenjang 1 / tarik (jika pengaju) | Lihat | Putuskan jenjang akhir |
