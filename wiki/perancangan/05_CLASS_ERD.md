# 05 — Class Diagram & ERD

Acuan: [BISNIS_PROSES_PDLN.MD §8](../instructions/BISNIS_PROSES_PDLN.MD#8-struktur-data--database).
Penanda: **«baru» / — baru / "baru"** = tabel/field baru; tanpa penanda = sudah ada.

## 5.1 Class diagram — model inti

```mermaid
classDiagram
    direction LR

    class User {
        +username
        +role : pegawai|admin_unor|admin_bpsdm|admin_pakln
        +unit_organisasi : FK UnitOrganisasi
        +is_admin_bpsdm() bool
    }
    class PegawaiProfile {
        +nip
        +nama
        +jabatan
        +pangkat_golongan
        +unit_organisasi : FK
        +sisa_cuti_tahun_berjalan
    }
    class Pengajuan {
        +kode
        +jenis_perjalanan : nondinas|pdln — baru
        +tipe_pdln : T1|T2P|T2L|T3 — baru
        +status : belum|proses|proses_bpsdm|proses_pakln|selesai|dibatalkan
        +unit_organisasi : FK snapshot — baru
        +kategori : FK
        +sumber_pembiayaan : FK
        +tgl_berangkat
        +tgl_kembali
        +jumlah_hari_kerja
        +maksud
        +kanal
        +preview_unor_agree
        +preview_bpsdm_agree — baru
        +preview_pakln_agree
        +catatan_unor
        +catatan_bpsdm — baru
        +catatan_pakln
        +tgl_pengajuan
        +tgl_masuk_bpsdm — baru
        +tgl_masuk_pakln
        +tgl_selesai
        +tgl_dibatalkan — baru
        +perlu_visa() bool
        +pembatalan_terbuka() PermohonanPembatalan
        +timeline() list
    }
    class DetailPdln {
        <<baru>>
        +penyelenggara
        +perguruan_tinggi
        +kota_tujuan
        +tgl_mulai_kegiatan
        +tgl_selesai_kegiatan
        +beasiswa_pintar_id
        +beasiswa_nama
        +pernyataan_benar
    }
    class DokumenPegawai {
        +jenis
        +file
        +tanggal_surat
    }
    class DokumenUnor {
        +jenis
        +file
        +tanggal_surat
    }
    class DokumenBpsdm {
        <<baru>>
        +jenis
        +file
        +tanggal_surat
    }
    class DokumenPakln {
        +jenis
        +file
        +tanggal_surat
    }
    class LaporanPdln {
        <<baru>>
        +file
        +status : menunggu|dikembalikan|disetujui
        +catatan_pakln
        +diunggah_oleh : FK User
        +diverifikasi_oleh : FK User
        +tgl_disetujui
    }
    class PermohonanPembatalan {
        <<baru>>
        +diajukan_oleh : FK User
        +diajukan_role
        +alasan
        +status : menunggu_unor|menunggu_pakln|disetujui|ditolak|ditarik
        +status_pengajuan_saat_diajukan
        +unor_oleh / unor_waktu / unor_catatan
        +pakln_oleh / pakln_waktu / pakln_catatan
    }
    class RiwayatPengajuan {
        +aksi
        +status_dari
        +status_ke
        +aktor : FK User
        +aktor_role
        +aktor_nama
        +catatan
        +created_at
    }
    class Notification {
        +event
        +level
        +title
        +body
        +redirect_url
    }
    class Negara {
        +nama_negara
        +perlu_visa — baru
    }
    class KategoriPerjalanan {
        +jenis_perjalanan
        +tipe_pdln : list — baru
    }
    class SumberPembiayaan {
        +tipe_perjalanan
        +tipe_pdln : list — baru
    }
    class UnitOrganisasi {
        +code
        +alias
        +name
    }
    class PasporPegawai {
        <<baru>>
        +nomor
        +jenis
        +tgl_expired
    }
    class DokumenKepegawaian {
        <<baru>>
        +jenis
        +file
    }

    User "1" -- "0..1" PegawaiProfile
    User "1" -- "*" Pengajuan : pegawai
    User "1" -- "*" PasporPegawai
    User "1" -- "*" DokumenKepegawaian
    PegawaiProfile "*" -- "1" UnitOrganisasi
    Pengajuan "*" -- "0..1" UnitOrganisasi
    Pengajuan "1" *-- "0..1" DetailPdln
    Pengajuan "1" *-- "*" DokumenPegawai
    Pengajuan "1" *-- "*" DokumenUnor
    Pengajuan "1" *-- "*" DokumenBpsdm
    Pengajuan "1" *-- "*" DokumenPakln
    Pengajuan "1" *-- "0..1" LaporanPdln
    Pengajuan "1" *-- "*" PermohonanPembatalan
    Pengajuan "1" *-- "*" RiwayatPengajuan
    Pengajuan "1" -- "*" Notification
    Pengajuan "*" -- "*" Negara : tujuan_negara
    Pengajuan "*" -- "0..1" KategoriPerjalanan
    Pengajuan "*" -- "0..1" SumberPembiayaan
```

## 5.2 Class diagram — modul layanan (non-model)

```mermaid
classDiagram
    direction LR
    class alur {
        <<module pengajuan/alur.py>>
        +ALUR : dict tipe → urutan status
        +tahap_berikut(pengajuan) str
        +tahap_sebelumnya(pengajuan) str
        +pengajuan_belum_tuntas(pegawai) Pengajuan
    }
    class persyaratan {
        <<module pengajuan/persyaratan.py>>
        +PERSYARATAN : dict (tipe, tahap) → list Syarat
        +syarat_untuk(pengajuan, tahap) list
        +dokumen_lengkap(pengajuan, tahap) bool
    }
    class Syarat {
        +jenis
        +wajib : bool | callable
        +tanggal_surat : bool
        +aksi : None|format|generate
    }
    class riwayat {
        <<module pengajuan/riwayat.py>>
        +catat(pengajuan, aksi, aktor, status_dari, catatan)
        +riwayat_untuk(pengajuan, user) list
        +timeline_dengan_riwayat(pengajuan, user) list
        +boleh_lihat_pesan(user, riwayat) bool
        +catatan_perbaikan(pengajuan, aksi) str
    }
    class pembatalan {
        <<module pengajuan/pembatalan.py>>
        +ajukan(pengajuan, user, alasan)
        +putuskan(permohonan, user, setuju, catatan)
        +tarik(permohonan, user)
    }
    class pintar {
        <<module paspor/integrasi/pintar.py>>
        +daftar_pencalonan_selesai(nip, jenis) list
    }
    class services {
        <<module notifications/services.py>>
        +notify_*(pengajuan, catatan)
    }
    persyaratan "1" o-- "*" Syarat
    pembatalan ..> riwayat : catat
    pembatalan ..> services : notifikasi
    alur ..> persyaratan : validasi transisi
```

## 5.3 Entity Relationship Diagram

```mermaid
erDiagram
    accounts_user ||--o| accounts_pegawaiprofile : memiliki
    accounts_user ||--o{ pengajuan_pengajuan : mengajukan
    accounts_user ||--o{ accounts_pasporpegawai : memiliki
    accounts_user ||--o{ accounts_dokumenkepegawaian : memiliki
    org_units ||--o{ accounts_pegawaiprofile : menaungi
    org_units ||--o{ pengajuan_pengajuan : snapshot_unor

    pengajuan_pengajuan ||--o| pengajuan_detailpdln : detail
    pengajuan_pengajuan ||--o{ pengajuan_dokumenpegawai : berkas
    pengajuan_pengajuan ||--o{ pengajuan_dokumenunor : berkas
    pengajuan_pengajuan ||--o| pengajuan_dokumenunorpendukung : berkas
    pengajuan_pengajuan ||--o{ pengajuan_dokumenbpsdm : berkas
    pengajuan_pengajuan ||--o{ pengajuan_dokumenpakln : berkas
    pengajuan_pengajuan ||--o| pengajuan_dokumenpaklnpendukung : berkas
    pengajuan_pengajuan ||--o| pengajuan_laporanpdln : laporan
    pengajuan_pengajuan ||--o{ pengajuan_permohonanpembatalan : pembatalan
    pengajuan_pengajuan ||--o{ pengajuan_riwayatpengajuan : riwayat
    pengajuan_pengajuan ||--o{ notifications_notification : notifikasi
    pengajuan_pengajuan }o--o{ paspor_negara : tujuan
    paspor_kategoriperjalanan ||--o{ pengajuan_pengajuan : kategori
    paspor_sumberpembiayaan ||--o{ pengajuan_pengajuan : sumber

    pengajuan_pengajuan {
        int id PK
        varchar kode UK
        int pegawai_id FK
        varchar jenis_perjalanan "baru, index"
        varchar tipe_pdln "baru"
        varchar status "index"
        int unit_organisasi_id FK "baru, snapshot"
        int kategori_id FK
        int sumber_pembiayaan_id FK
        date tgl_berangkat
        date tgl_kembali
        int jumlah_hari_kerja
        text maksud
        varchar kanal
        bool preview_unor_agree
        bool preview_bpsdm_agree "baru"
        bool preview_pakln_agree
        text catatan_unor
        text catatan_bpsdm "baru"
        text catatan_pakln
        date tgl_pengajuan
        date tgl_masuk_bpsdm "baru"
        date tgl_masuk_pakln
        date tgl_selesai
        date tgl_dibatalkan "baru"
    }
    pengajuan_detailpdln {
        int id PK
        int pengajuan_id FK "unique"
        varchar penyelenggara
        varchar perguruan_tinggi
        varchar kota_tujuan
        date tgl_mulai_kegiatan
        date tgl_selesai_kegiatan
        varchar beasiswa_pintar_id
        varchar beasiswa_nama
        bool pernyataan_benar
    }
    pengajuan_dokumenbpsdm {
        int id PK
        int pengajuan_id FK
        varchar jenis "unique per pengajuan"
        varchar file
        date tanggal_surat
        datetime uploaded_at
    }
    pengajuan_laporanpdln {
        int id PK
        int pengajuan_id FK "unique"
        varchar file
        varchar status "menunggu, dikembalikan, disetujui"
        text catatan_pakln
        int diunggah_oleh_id FK
        datetime uploaded_at
        int diverifikasi_oleh_id FK
        datetime tgl_disetujui
    }
    pengajuan_permohonanpembatalan {
        int id PK
        int pengajuan_id FK
        int diajukan_oleh_id FK
        varchar diajukan_role
        text alasan "wajib"
        varchar status "index"
        varchar status_pengajuan_saat_diajukan
        int unor_oleh_id FK
        datetime unor_waktu
        text unor_catatan
        int pakln_oleh_id FK
        datetime pakln_waktu
        text pakln_catatan
        datetime created_at
    }
    pengajuan_riwayatpengajuan {
        int id PK
        int pengajuan_id FK
        varchar aksi
        varchar status_dari
        varchar status_ke
        int aktor_id FK
        varchar aktor_role
        varchar aktor_nama
        text catatan
        datetime created_at
    }
    paspor_negara {
        int id PK
        varchar nama_negara UK
        bool perlu_visa "baru"
        bool is_active
    }
    accounts_pasporpegawai {
        int id PK
        int pegawai_id FK
        varchar nomor
        varchar jenis
        date tgl_expired
    }
```

## 5.4 Index yang disarankan

| Tabel | Index | Untuk |
|---|---|---|
| `pengajuan_pengajuan` | `(jenis_perjalanan, tipe_pdln, status)` | Dasbor & filter report |
| `pengajuan_pengajuan` | `(unit_organisasi_id, status)` | Cakupan Admin Unor |
| `pengajuan_pengajuan` | `(status, tgl_pengajuan)` | Rekap per periode |
| `pengajuan_pengajuan` | `(pegawai_id, status)` | Aturan satu pengajuan aktif |
| `pengajuan_laporanpdln` | `(status)` | Antrean verifikasi |
| `pengajuan_permohonanpembatalan` | `(pengajuan_id, status)` | Cek permohonan terbuka, antrean |
| `pengajuan_riwayatpengajuan` | `(pengajuan_id, created_at)` *(sudah ada)* | Timeline & SLA |
