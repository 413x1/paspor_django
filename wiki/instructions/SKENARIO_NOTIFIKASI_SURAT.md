# SPESIFIKASI DOKUMENTASI SISTEM NOTIFIKASI PENGURUSAN SURAT

| Parameter | Keterangan |
| :--- | :--- |
| **Nama Dokumen** | Spesifikasi Skenario & Arsitektur Notifikasi Pengajuan Surat |
| **Versi** | 1.2.0 |
| **Status** | Ready for Review / Implementation |
| **Aktor Terkait** | Pegawai (Pemohon), Admin Unor (Verifikator 1), Admin PKLN (Verifikator Final) |
| **Teknologi Target** | Web Application (In-App Toast, Notification Center, Email) |

---

## 1. Pendahuluan & Tujuan

Dokumen ini mendefinisikan aturan bisnis, pengikatan status (*status binding*), spesifikasi UI/UX, serta format payload data untuk sistem notifikasi pada modul Pengajuan Surat yang melibatkan **Pegawai**, **Admin Unor (Unit Organisasi)**, dan **Admin PKLN (Pelayanan Kerja Sama Luar Negeri)**.

Tujuan utama dari sistem notifikasi ini adalah:
1. Menyediakan pembaruan status secara *real-time* kepada pemohon dan pengelola surat.
2. Meminimalkan waktu hambatan (*bottleneck*) verifikasi dokumen.
3. Menangani penolakan dan revisi berkas secara transparan.
4. Mencatat jejak audit (*audit trail*) riwayat aktivitas surat dari awal hingga selesai.

---

## 2. Definisi Aktor & Hak Akses Notification Scope

| Role Aktor | Scope / Cakupan Notifikasi | Hak Akses Tindakan |
| :--- | :--- | :--- |
| **Pegawai** | Notifikasi personal berdasarkan `user_id` pemohon. | Mengajukan, merevisi, mengajukan ulang, dan mengunduh surat final. |
| **Admin Unor** | Notifikasi tingkat unit kerja berdasarkan `unor_id` pegawai. | Memeriksa, menyetujui, mengembalikan ke pegawai, dan meneruskan ke PKLN. |
| **Admin PKLN** | Notifikasi tingkat kementerian/global berdasarkan `role_id = ADMIN_PKLN`. | Memeriksa, memproses, menerbitkan, mengembalikan (ke Unor/Pegawai), atau menolak permanen. |

---

## 3. Matriks State Machine & Status Surat

Sistem menggunakan kode status standar berikut untuk memicu (*trigger*) kejadian notifikasi:

| Kode Status | Nama Label Status | Deskripsi |
| :--- | :--- | :--- |
| `DRAFT` | Draft | Surat masih disiapkan oleh Pegawai (Belum ada notifikasi). |
| `SUBMITTED_UNOR` | Menunggu Verifikasi Unor | Surat telah dikirim oleh Pegawai ke Admin Unor. |
| `REJECTED_UNOR` | Dikembalikan Unor | Surat dikembalikan Admin Unor ke Pegawai untuk diperbaiki. |
| `RESUBMITTED_UNOR` | Diajukan Ulang (ke Unor) | Pegawai telah memperbaiki surat dan mengirim ulang ke Admin Unor. |
| `APPROVED_UNOR` | Disetujui Unor / Ke PKLN | Surat disetujui Admin Unor dan diteruskan ke Admin PKLN. |
| `REJECTED_PKLN_UNOR` | Dikembalikan PKLN ke Unor | Admin PKLN mengembalikan surat ke Admin Unor (kesalahan rekomendasi/admin Unor). |
| `REJECTED_PKLN_PEGAWAI`| Dikembalikan PKLN ke Pegawai| Admin PKLN mengembalikan surat langsung ke Pegawai (dokumen lampiran pemohon kurang/salah). |
| `RESUBMITTED_PKLN` | Diteruskan Ulang ke PKLN | Admin Unor / Pegawai telah memperbaiki dokumen dan meneruskan kembali ke PKLN. |
| `COMPLETED` | Selesai | Surat disetujui PKLN dan dokumen resmi terbit. |
| `REJECTED_PERMANENT` | Ditolak Permanen | Surat ditolak sepenuhnya dan tidak dapat diajukan ulang. |

---

## 4. Rincian Skenario Notifikasi per Event (Trigger-by-Trigger)

---

### Event 1: Pengajuan Surat Baru oleh Pegawai
* **Kode Event**: `NOTIF_01_SUBMIT_UNOR`
* **Pemicu (Trigger)**: Pegawai menekan tombol *"Kirim Pengajuan Surat"*.
* **Perubahan Status**: `DRAFT` `SUBMITTED_UNOR`
* **Penerima Notifikasi**: Semua User dengan Role **Admin Unor** pada `unor_id` yang sama dengan Pegawai.
* **Kanal & Tampilan UI**: Toast Pop-up (**Info / Biru**) + Notification Center.
* **Format Pesan**:
  * **Judul**: `Pengajuan Surat Baru - [Nomor Registrasi / Jenis Surat]`
  * **Body**: `Pegawai [Nama Pegawai] (NIP: [NIP]) telah mengajukan [Jenis Surat] dengan perihal "[Perihal Surat]". Silakan lakukan verifikasi.`
* **Redirect Action (Deep Link)**: `/admin-unor/surat/verifikasi/{id_surat}`

---

### Event 2A: Verifikasi Disetujui oleh Admin Unor (Diteruskan ke PKLN)
* **Kode Event**: `NOTIF_02A_APPROVE_UNOR`
* **Pemicu (Trigger)**: Admin Unor menekan tombol *"Setujui & Teruskan ke PKLN"*.
* **Perubahan Status**: `SUBMITTED_UNOR` / `RESUBMITTED_UNOR`  `APPROVED_UNOR`
* **Penerima Notifikasi**:
  1. **Pegawai (Pemohon)**:
     * **Judul**: `Pengajuan Surat Disetujui Unor`
     * **Body**: `Surat Anda perihal "[Perihal Surat]" telah disetujui oleh Admin Unor dan diteruskan ke Admin PKLN.`
     * **Redirect**: `/pegawai/surat/detail/{id_surat}`
  2. **Seluruh Admin PKLN**:
     * **Judul**: `Penugasan Verifikasi Surat PKLN Baru`
     * **Body**: `Diterima pengajuan surat dari Unor [Nama Unor] atas nama [Nama Pegawai] perihal "[Perihal Surat]".`
     * **Redirect**: `/admin-pkln/surat/verifikasi/{id_surat}`

---

### Event 2B: Penolakan / Minta Revisi oleh Admin Unor ke Pegawai
* **Kode Event**: `NOTIF_02B_REJECT_UNOR`
* **Pemicu (Trigger)**: Admin Unor mengisi kolom *Catatan Revisi* dan menekan tombol **"Kembalikan ke Pegawai"**.
* **Perubahan Status**: `SUBMITTED_UNOR` `REJECTED_UNOR`
* **Penerima Notifikasi**: **Pegawai (Pemohon)**
* **Kanal & Tampilan UI**: Toast Pop-up (**Warning / Kuning**) + Notification Center.
* **Format Pesan**:
  * **Judul**: `Pengajuan Surat Dikembalikan oleh Admin Unor`
  * **Body**: `Surat [Jenis Surat] perihal "[Perihal Surat]" dikembalikan. Catatan Unor: "[Isi Catatan Revisi]". Silakan lakukan perbaikan.`
* **Redirect Action (Deep Link)**: `/pegawai/surat/edit/{id_surat}`

---

### Event 2C: Pengajuan Ulang (Resubmit) oleh Pegawai ke Admin Unor
* **Kode Event**: `NOTIF_02C_RESUBMIT_UNOR`
* **Pemicu (Trigger)**: Pegawai memperbarui berkas/data lalu menekan tombol **"Kirim Perbaikan"**.
* **Perubahan Status**: `REJECTED_UNOR` `RESUBMITTED_UNOR`
* **Penerima Notifikasi**: **Admin Unor**
* **Kanal & Tampilan UI**: Toast Pop-up (**Info / Biru**) + Notification Center.
* **Format Pesan**:
  * **Judul**: `Perbaikan Surat Diterima - [Nama Pegawai]`
  * **Body**: `Pegawai [Nama Pegawai] telah mengirimkan perbaikan surat perihal "[Perihal Surat]". Silakan periksa kembali.`
* **Redirect Action (Deep Link)**: `/admin-unor/surat/verifikasi/{id_surat}`

---

### Event 3A: Penyelesaian & Penerbitan Surat oleh Admin PKLN
* **Kode Event**: `NOTIF_03A_COMPLETE_PKLN`
* **Pemicu (Trigger)**: Admin PKLN menekan tombol *"Selesai / Terbitkan Surat"*.
* **Perubahan Status**: `APPROVED_UNOR` / `RESUBMITTED_PKLN` `COMPLETED`
* **Penerima Notifikasi**:
  1. **Pegawai (Pemohon)**:
     * **Judul**: `Pengajuan Surat Selesai (Siap Unduh)`
     * **Body**: `Selamat, surat Anda perihal "[Perihal Surat]" telah selesai diproses oleh Admin PKLN. Silakan unduh dokumen resmi.`
     * **Redirect**: `/pegawai/surat/detail/{id_surat}`
  2. **Admin Unor**:
     * **Judul**: `Proses Surat PKLN Selesai`
     * **Body**: `Pengajuan surat milik [Nama Pegawai] perihal "[Perihal Surat]" telah selesai diproses oleh Admin PKLN.`
     * **Redirect**: `/admin-unor/surat/detail/{id_surat}`

---

### Event 3B: Penolakan / Pengembalian oleh Admin PKLN ke Admin Unor
* **Kode Event**: `NOTIF_03B_REJECT_PKLN_TO_UNOR`
* **Pemicu (Trigger)**: Admin PKLN menekan tombol **"Kembalikan ke Admin Unor"** *(Terjadi jika kesalahan pada rekomendasi/admin Unor)*.
* **Perubahan Status**: `APPROVED_UNOR` `REJECTED_PKLN_UNOR`
* **Penerima Notifikasi**:
  1. **Admin Unor (Target Utama)**:
     * **Judul**: `Berkas Surat Dikembalikan oleh Admin PKLN`
     * **Body**: `Surat pengajuan [Nama Pegawai] dikembalikan oleh PKLN. Catatan PKLN: "[Isi Catatan PKLN]". Mohon diperbaiki.`
     * **Redirect**: `/admin-unor/surat/edit-rekomendasi/{id_surat}`
  2. **Pegawai (CC / Info Only)**:
     * **Judul**: `Status Pengajuan Surat (Dalam Penanganan Unor)`
     * **Body**: `Pengajuan surat Anda perihal "[Perihal Surat]" membutuhkan penyesuaian dari Admin Unor.`
     * **Redirect**: `/pegawai/surat/detail/{id_surat}`

---

### Event 3C: Penolakan / Pengembalian oleh Admin PKLN Langsung ke Pegawai
* **Kode Event**: `NOTIF_03C_REJECT_PKLN_TO_PEGAWAI`
* **Pemicu (Trigger)**: Admin PKLN menekan tombol **"Kembalikan ke Pegawai"** *(Terjadi jika berkas pribadi pemohon buram/salah)*.
* **Perubahan Status**: `APPROVED_UNOR` `REJECTED_PKLN_PEGAWAI`
* **Penerima Notifikasi**:
  1. **Pegawai (Target Utama)**:
     * **Judul**: `Pengajuan Surat Memerlukan Revisi Berkas (PKLN)`
     * **Body**: `Surat perihal "[Perihal Surat]" dikembalikan oleh Admin PKLN. Catatan PKLN: "[Isi Catatan PKLN]". Silakan unggah ulang berkas.`
     * **Redirect**: `/pegawai/surat/edit/{id_surat}`
  2. **Admin Unor (CC / Info Only)**:
     * **Judul**: `Surat Ditolak PKLN (Dikembalikan ke Pegawai)`
     * **Body**: `Surat milik [Nama Pegawai] dikembalikan oleh PKLN ke pemohon untuk revisi dokumen.`
     * **Redirect**: `/admin-unor/surat/detail/{id_surat}`

---

### Event 3D: Resubmit ke Admin PKLN setelah Revisi
* **Kode Event**: `NOTIF_03D_RESUBMIT_PKLN`
* **Pemicu (Trigger)**: Admin Unor atau Pegawai menekan tombol **"Kirim Ulang ke PKLN"**.
* **Perubahan Status**: `REJECTED_PKLN_UNOR` / `REJECTED_PKLN_PEGAWAI` `RESUBMITTED_PKLN`
* **Penerima Notifikasi**: **Admin PKLN**
* **Kanal & Tampilan UI**: Toast Pop-up (**Info / Biru**) + Notification Center.
* **Payload Notifikasi**:
  * **Judul**: `Perbaikan Surat PKLN Diterima`
  * **Body**: `Perbaikan surat atas nama [Nama Pegawai] (Unor: [Nama Unor]) telah dikirim ulang. Silakan lakukan verifikasi.`
* **Redirect Action (Deep Link)**: `/admin-pkln/surat/verifikasi/{id_surat}`

---

### Event 4: Penolakan Permanen (Total Rejection)
* **Kode Event**: `NOTIF_04_REJECT_PERMANENT`
* **Pemicu (Trigger)**: Admin Unor atau Admin PKLN menekan tombol **"Tolak Permanen"** *(Tidak dapat diperbaiki/diakses lagi)*.
* **Perubahan Status**: `SUBMITTED_UNOR` / `APPROVED_UNOR` `REJECTED_PERMANENT`
* **Penerima Notifikasi**: **Pegawai (Pemohon)** & **Admin Unor** (jika penolakan dari PKLN).
* **Kanal & Tampilan UI**: Toast Pop-up (**Danger / Merah**) + Notification Center.
* **Payload Notifikasi**:
  * **Judul**: `Pengajuan Surat Ditolak`
  * **Body**: `Pengajuan surat perihal "[Perihal Surat]" ditolak secara permanen. Alasan Penolakan: "[Alasan Penolakan]".`
* **Redirect Action (Deep Link)**: `/pegawai/surat/detail/{id_surat}`