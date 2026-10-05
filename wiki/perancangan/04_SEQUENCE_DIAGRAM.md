# 04 — Sequence Diagram

Menggambarkan interaksi antara pengguna, view Django, modul layanan
(`pengajuan/alur.py`, `pengajuan/persyaratan.py`, `pengajuan/riwayat.py`,
`notifications/services.py`, `paspor/integrasi/pintar.py`), dan database.
Nama modul mengikuti rancangan di
[BISNIS_PROSES_PDLN.MD §6.5, §12, §13](../instructions/BISNIS_PROSES_PDLN.MD#13-tahapan-implementasi).

## 4.1 Pegawai mengisi formulir PDLN Tipe 2 (dengan Aplikasi PINTAR)

```mermaid
sequenceDiagram
    autonumber
    actor P as Pegawai
    participant V as views_pegawai
    participant A as alur.pengajuan_belum_tuntas
    participant PT as integrasi.pintar
    participant X as Aplikasi PINTAR
    participant DB as Database

    P->>V: GET /pegawai/formulir/?jenis=pdln&tipe=T2P
    V->>A: pengajuan_belum_tuntas(pegawai)
    A->>DB: query Pengajuan + LaporanPdln
    DB-->>A: None
    V->>PT: daftar_pencalonan_selesai(nip, "pendidikan")
    alt PINTAR_API_URL diisi
        PT->>X: GET pencalonan berstatus Selesai
        X-->>PT: daftar pencalonan
    else Stub (API belum tersedia)
        PT->>DB: baca data seed lokal
        DB-->>PT: daftar pencalonan
    end
    PT-->>V: [Pencalonan]
    V-->>P: Formulir T2P + droplist beasiswa
    P->>V: POST formulir
    V->>A: cek ulang pengajuan_belum_tuntas
    V->>DB: simpan Pengajuan (jenis=pdln, tipe=T2P, status=belum)<br/>+ DetailPdln (beasiswa_pintar_id, beasiswa_nama)
    V-->>P: redirect ke Unggah Dokumen
```

## 4.2 Pegawai mengirim / mengirim ulang pengajuan

```mermaid
sequenceDiagram
    autonumber
    actor P as Pegawai
    participant V as views_pegawai.upload_dokumen
    participant S as persyaratan
    participant R as riwayat
    participant N as notifications.services
    participant DB as Database

    P->>V: POST kirim (+ catatan bila kirim ulang)
    V->>S: dokumen_lengkap(pengajuan, "pegawai")
    S->>DB: baca DokumenPegawai
    S-->>V: True
    alt pernah dikembalikan dan catatan kosong
        V-->>P: error "Isi catatan perbaikan"
    else valid
        V->>DB: BEGIN, select_for_update(Pengajuan)
        V->>DB: status=proses, tgl_pengajuan, unit_organisasi (snapshot),<br/>catatan_unor=""
        V->>R: catat(DIKIRIM / DIKIRIM_ULANG, catatan)
        R->>DB: insert RiwayatPengajuan
        V->>DB: COMMIT
        V->>N: notify_submit_unor / notify_resubmit_unor(catatan)
        N->>DB: insert Notification (Admin Unor)
        V-->>P: redirect Monitor Progres
    end
```

## 4.3 Admin Unor meneruskan pengajuan (Tipe 2 → BPSDM, lainnya → PAKLN)

```mermaid
sequenceDiagram
    autonumber
    actor U as Admin Unor
    participant V as views_unor.upload_dokumen
    participant AL as alur
    participant S as persyaratan
    participant R as riwayat
    participant N as notifications.services
    participant DB as Database

    U->>V: POST teruskan (+ catatan bila teruskan ulang)
    V->>DB: BEGIN, select_for_update(Pengajuan)
    V->>DB: cek status = proses & tidak ada pembatalan terbuka
    V->>S: dokumen_lengkap(pengajuan, "unor")
    S-->>V: True
    V->>AL: tahap_berikut(pengajuan)
    alt tipe T2P / T2L
        AL-->>V: proses_bpsdm
        V->>DB: status=proses_bpsdm, tgl_masuk_bpsdm
        V->>R: catat(DITERUSKAN_BPSDM / DITERUSKAN_ULANG_BPSDM)
    else T1 / T3 / Non-Dinas
        AL-->>V: proses_pakln
        V->>DB: status=proses_pakln, tgl_masuk_pakln
        V->>R: catat(DITERUSKAN_PAKLN / DITERUSKAN_ULANG)
    end
    V->>DB: COMMIT
    V->>N: notifikasi ke tahap berikut (+ catatan balasan) & info ke Pegawai
    V-->>U: redirect dasbor
```

## 4.4 Admin PAKLN menyelesaikan pengajuan (aturan visa)

```mermaid
sequenceDiagram
    autonumber
    actor K as Admin PAKLN
    participant V as views_pakln.upload_dokumen
    participant S as persyaratan
    participant DB as Database
    participant R as riwayat
    participant N as notifications.services

    K->>V: POST selesaikan
    V->>S: syarat_untuk(pengajuan, "pakln")
    S->>DB: Pengajuan.perlu_visa?<br/>(tujuan_negara.perlu_visa)
    DB-->>S: True / False
    S-->>V: daftar syarat (visa wajib atau opsional)
    V->>S: dokumen_lengkap(pengajuan, "pakln")
    alt belum lengkap
        S-->>V: False + dokumen kurang
        V-->>K: error, sebutkan dokumen yang kurang
    else lengkap
        V->>DB: BEGIN, status=selesai, tgl_selesai
        V->>R: catat(SELESAI)
        V->>DB: COMMIT
        V->>N: notify_complete_pkln (Pegawai, Admin Unor)
        V-->>K: redirect dasbor
    end
```

## 4.5 Unggah dan verifikasi Laporan PDLN

```mermaid
sequenceDiagram
    autonumber
    actor P as Pegawai
    actor K as Admin PAKLN
    participant VP as views_pegawai.pelaporan
    participant VK as views_pakln.verifikasi_laporan
    participant R as riwayat
    participant N as notifications.services
    participant DB as Database

    P->>VP: POST unggah laporan (+ catatan bila ulang)
    VP->>DB: cek Pengajuan PDLN status=selesai
    VP->>DB: upsert LaporanPdln(status=menunggu, file)
    VP->>R: catat(LAPORAN_DIUNGGAH, catatan)
    VP->>N: LAPORAN_PDLN_DIUNGGAH → Admin PAKLN (+ info Admin Unor)
    K->>VK: GET antrean Menunggu Verifikasi
    K->>VK: POST setujui / kembalikan (catatan)
    alt kembalikan
        VK->>DB: status=dikembalikan, catatan_pakln
        VK->>R: catat(LAPORAN_DIKEMBALIKAN, catatan)
        VK->>N: LAPORAN_PDLN_DIKEMBALIKAN → Pegawai
    else setujui
        VK->>DB: status=disetujui, tgl_disetujui, diverifikasi_oleh
        VK->>R: catat(LAPORAN_DISETUJUI)
        VK->>N: LAPORAN_PDLN_DISETUJUI → Pegawai
        Note over P,DB: Pengajuan tuntas — Pegawai dapat mengajukan perjalanan baru
    end
```

## 4.6 Pembatalan berjenjang

```mermaid
sequenceDiagram
    autonumber
    actor P as Pegawai
    actor U as Admin Unor
    actor K as Admin PAKLN
    participant VB as views_pembatalan
    participant R as riwayat
    participant N as notifications.services
    participant DB as Database

    P->>VB: POST ajukan pembatalan (alasan wajib)
    VB->>DB: BEGIN, select_for_update(Pengajuan)
    VB->>DB: cek belum tuntas & tidak ada permohonan terbuka
    VB->>DB: insert PermohonanPembatalan(status=menunggu_unor)
    VB->>R: catat(PEMBATALAN_DIAJUKAN, alasan)
    VB->>DB: COMMIT
    VB->>N: PEMBATALAN_DIAJUKAN → Admin Unor

    U->>VB: POST putuskan jenjang 1
    alt tolak (catatan wajib)
        VB->>DB: status=ditolak, unor_*
        VB->>R: catat(PEMBATALAN_DITOLAK_UNOR, catatan)
        VB->>N: PEMBATALAN_DITOLAK → Pegawai
    else setuju
        VB->>DB: status=menunggu_pakln, unor_*
        VB->>R: catat(PEMBATALAN_DISETUJUI_UNOR)
        VB->>N: PEMBATALAN_MENUNGGU_PAKLN → Admin PAKLN, info Pegawai
        K->>VB: POST putuskan jenjang akhir
        alt tolak (catatan wajib)
            VB->>DB: status=ditolak, pakln_*
            VB->>R: catat(PEMBATALAN_DITOLAK_PAKLN, catatan)
            VB->>N: PEMBATALAN_DITOLAK → Pegawai, Admin Unor
        else setuju
            VB->>DB: BEGIN, permohonan=disetujui,<br/>Pengajuan.status=dibatalkan, tgl_dibatalkan
            VB->>R: catat(DIBATALKAN, status_ke=dibatalkan)
            VB->>DB: COMMIT
            VB->>N: PEMBATALAN_DISETUJUI → Pegawai, Admin Unor (+ BPSDM bila T2)
        end
    end
```

Bila diajukan oleh **Admin Unor**, langkah "putuskan jenjang 1" dilewati:
permohonan langsung dibuat berstatus `menunggu_pakln` dengan kolom
`unor_*` diisi dari pengaju.

## 4.7 Export database terpadu

```mermaid
sequenceDiagram
    autonumber
    actor A as Admin (Unor/BPSDM/PAKLN)
    participant V as views_report.export
    participant Q as report.queryset_untuk
    participant DB as Database

    A->>V: GET /export/?jenis=&tipe=&status=&periode=&format=xlsx
    V->>Q: queryset_untuk(user, filter)
    Q->>Q: terapkan cakupan role<br/>(unor sendiri / Tipe 2 / semua)
    Q->>DB: Pengajuan + DetailPdln + LaporanPdln<br/>+ agregasi Riwayat & PermohonanPembatalan
    DB-->>Q: baris data
    Q-->>V: queryset
    V->>V: tulis sheet Data + sheet Ringkasan (openpyxl)
    V-->>A: file .xlsx / .csv
```
