# 02 — Flowchart / Activity Diagram

Acuan: [BISNIS_PROSES_PDLN.MD §2.1, §4, §7](../instructions/BISNIS_PROSES_PDLN.MD#4-alur-proses-per-tipe).
Setiap kotak keputusan yang mengubah status juga mencatat
`RiwayatPengajuan` dan mengirim notifikasi (tidak digambar ulang di
setiap flowchart agar ringkas).

## 2.1 Memulai pengajuan baru (aturan satu pengajuan aktif)

```mermaid
flowchart TD
    A([Pegawai buka Beranda]) --> B{"Ada pengajuan<br/>belum tuntas?"}
    B -- "Ya, draft belum dikirim" --> C["Lanjutkan draft tersebut"]
    B -- "Ya, sedang diproses / menunggu laporan" --> D["Tombol Tambah Usulan Baru nonaktif<br/>+ keterangan alasan"]
    D --> Z1([Selesai])
    B -- Tidak --> E["Klik Tambah Usulan Baru"]
    E --> F{"Pilih jenis perjalanan"}
    F -- Non-Dinas --> G["Formulir Non-Dinas"]
    F -- PDLN --> H{"Pilih tipe PDLN"}
    H -- "Tipe 1 / Tipe 3" --> I["Formulir T1/T3"]
    H -- "Tipe 2 Pendidikan" --> J["Formulir T2P"]
    H -- "Tipe 2 Pelatihan" --> K["Formulir T2L"]
    J & K --> L[["Ambil daftar beasiswa<br/>dari Aplikasi PINTAR"]]
    G & I & L --> M["Isi & simpan formulir"]
    M --> N{"Validasi server"}
    N -- Gagal --> M
    N -- "Lolos (cek ulang aturan satu aktif)" --> O["Draft tersimpan<br/>status = belum"]
    O --> P([Ke Unggah Dokumen])
```

**Definisi "tuntas"** (pengajuan yang tidak lagi menghalangi pengajuan baru):

```mermaid
flowchart LR
    S{"Status pengajuan"} -- dibatalkan --> T1([Tuntas])
    S -- "selesai & Non-Dinas" --> T1
    S -- "selesai & PDLN" --> Q{"Laporan PDLN<br/>disetujui?"}
    Q -- Ya --> T1
    Q -- Tidak --> T0([Belum tuntas])
    S -- "belum / proses / proses_bpsdm / proses_pakln" --> T0
```

## 2.2 Alur utama — Non-Dinas, PDLN Tipe 1, PDLN Tipe 3

```mermaid
flowchart TD
    subgraph PEG["Pegawai"]
        P1["Unggah dokumen wajib tahap Pegawai"] --> P2{"Lengkap &<br/>pernyataan dicentang?"}
        P2 -- Tidak --> P1
        P2 -- Ya --> P3{"Pernah dikembalikan?"}
        P3 -- Ya --> P4["Isi catatan perbaikan (wajib)"] --> P5
        P3 -- Tidak --> P5["Kirim ke Admin Unor"]
    end

    subgraph UNOR["Admin Unor"]
        U1["Pratinjau formulir & berkas"] --> U2{"Sesuai?"}
        U2 -- Tidak --> U3["Kembalikan + catatan wajib"]
        U2 -- Ya --> U4["Unggah dokumen administrasi Unor"]
        U4 --> U5{"Lengkap?"}
        U5 -- Tidak --> U4
        U5 -- Ya --> U6{"Pernah dikembalikan PAKLN?"}
        U6 -- Ya --> U7["Isi catatan perbaikan (wajib)"] --> U8
        U6 -- Tidak --> U8["Teruskan ke Biro PAKLN"]
    end

    subgraph PAKLN["Admin Biro PAKLN"]
        K1["Pratinjau seluruh berkas"] --> K2{"Sesuai?"}
        K2 -- Tidak --> K3["Kembalikan ke Unor + catatan wajib"]
        K2 -- Ya --> K4["Unggah / generate dokumen PAKLN"]
        K4 --> K5{"Dokumen wajib lengkap?<br/>(visa wajib jika negara<br/>tujuan perlu visa)"}
        K5 -- Tidak --> K4
        K5 -- Ya --> K6["Selesai"]
    end

    P5 -- "status: proses" --> U1
    U3 -- "status: belum" --> P1
    U8 -- "status: proses_pakln" --> K1
    K3 -- "status: proses" --> U1
    K6 -- "status: selesai" --> X{"Jenis?"}
    X -- Non-Dinas --> END1([Tuntas — pegawai dapat<br/>mengunduh ILN])
    X -- "PDLN T1/T3" --> END2([Lanjut Pelaporan PDLN — 2.4])
```

## 2.3 Alur PDLN Tipe 2 (Pendidikan & Pelatihan) — dengan BPSDM

```mermaid
flowchart TD
    P["Pegawai: kirim / kirim ulang"] -- "proses" --> U["Admin Unor:<br/>pratinjau & administrasi Unor"]
    U -- "kembalikan + catatan" --> P
    U -- "teruskan / teruskan ulang + catatan<br/>status: proses_bpsdm" --> B["Admin BPSDM:<br/>pratinjau"]
    B --> B2{"Sesuai?"}
    B2 -- "Tidak — kembalikan + catatan" --> U
    B2 -- Ya --> B3["Unggah Izin Prinsip Menteri,<br/>generate Ikatan Dinas/SK Tubel (T2P),<br/>ND Sekretaris BPSDM"]
    B3 --> B4{"Lengkap?"}
    B4 -- Tidak --> B3
    B4 -- "Ya — teruskan<br/>status: proses_pakln" --> K["Admin PAKLN:<br/>pratinjau"]
    K --> K2{"Sesuai?"}
    K2 -- "Tidak — kembalikan ke BPSDM + catatan" --> B
    K2 -- Ya --> K3["SP Setneg, Paspor Dinas, Exit Permit,<br/>Visa*, SK Tubel (T2P), ND Karo"]
    K3 --> K4{"Lengkap?"}
    K4 -- Tidak --> K3
    K4 -- "Ya — status: selesai" --> L([Lanjut Pelaporan PDLN — 2.4])
```

*Visa wajib bila salah satu negara tujuan bertanda `perlu_visa`.

## 2.4 Pelaporan PDLN

```mermaid
flowchart TD
    A([PDLN status selesai]) --> B["Pegawai buka Pelaporan PDLN"]
    B --> C{"Laporan sudah ada?"}
    C -- Belum --> D["Unggah laporan"]
    C -- "Ya, dikembalikan" --> E["Baca catatan Admin PAKLN"] --> F["Unggah ulang + catatan balasan (wajib)"]
    D & F --> G["Laporan: menunggu<br/>notifikasi ke Admin PAKLN"]
    G --> H["Admin PAKLN tinjau laporan"]
    H --> I{"Laporan sesuai?"}
    I -- "Tidak — kembalikan + catatan wajib" --> J["Laporan: dikembalikan<br/>notifikasi ke Pegawai"] --> B
    I -- Ya --> K["Laporan: disetujui"]
    K --> L([Pengajuan TUNTAS —<br/>pegawai dapat mengajukan lagi])
```

## 2.5 Pembatalan (mekanisme interim)

```mermaid
flowchart TD
    A([Pegawai / Admin Unor<br/>klik Ajukan Pembatalan]) --> B{"Pengajuan pernah dikirim?"}
    B -- "Tidak (draft)" --> C{"Diajukan Pegawai?"}
    C -- Ya --> C1["Isi alasan (wajib)"] --> C2([Langsung dibatalkan])
    C -- Tidak --> X1([Tidak tersedia])
    B -- Ya --> D{"Sudah tuntas / dibatalkan /<br/>ada permohonan terbuka?"}
    D -- Ya --> X2([Tombol nonaktif])
    D -- Tidak --> E["Isi alasan pembatalan (wajib)"]
    E --> F["Simpan permohonan<br/>+ BEKUKAN aksi alur utama"]
    F --> G{"Pengaju?"}
    G -- Pegawai --> H["menunggu_unor"]
    G -- "Admin Unor" --> I["menunggu_pakln"]

    H --> H1{"Admin Unor memutuskan"}
    H1 -- "Tolak + catatan wajib" --> R["ditolak"]
    H1 -- "Setuju (catatan opsional)" --> I
    I --> I1{"Admin PAKLN memutuskan"}
    I1 -- "Tolak + catatan wajib" --> R
    I1 -- "Setuju (catatan opsional)" --> S["disetujui<br/>Pengajuan.status = dibatalkan"]
    H & I -. "Pengaju menarik" .-> T["ditarik"]

    R & T --> U([Buka kembali aksi alur utama<br/>lanjut dari status semula])
    S --> V([Pengajuan TUNTAS — dokumen diarsipkan])
```

## 2.6 Kirim/teruskan — validasi umum di server

Diterapkan pada semua tombol transisi (Kirim, Teruskan, Selesai, Kembalikan).

```mermaid
flowchart TD
    A([POST aksi transisi]) --> B{"Role & cakupan<br/>berhak atas pengajuan?"}
    B -- Tidak --> E1([403 / 404])
    B -- Ya --> C["Kunci baris Pengajuan<br/>select_for_update"]
    C --> D{"Status saat ini sesuai<br/>tahap role?"}
    D -- Tidak --> E2([Pesan: sudah diproses pihak lain])
    D -- Ya --> F{"Ada permohonan<br/>pembatalan terbuka?"}
    F -- Ya --> E3([Pesan: pengajuan dibekukan])
    F -- Tidak --> G{"Syarat aksi terpenuhi?<br/>dokumen wajib / catatan wajib / centang"}
    G -- Tidak --> E4([Pesan error, tetap di halaman])
    G -- Ya --> H["Ubah status & tanggal tahap"]
    H --> I["riwayat.catat(...)"]
    I --> J["Commit transaksi"]
    J --> K["Kirim notifikasi"]
    K --> L([Redirect ke dasbor / monitor])
```
