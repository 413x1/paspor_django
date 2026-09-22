# Dokumentasi Skenario Notifikasi Sistem Surat

## 1. Overview
Dokumen ini mengatur aturan bisnis, trigger, dan muatan pesan notifikasi untuk alur pengajuan surat yang melibatkan **Pegawai**, **Admin Unor**, dan **Admin PKLN**.

## 2. Aktor & Peran
* **Pegawai**: Pemohon surat.
* **Admin Unor (Unit Organisasi)**: Verifikator tingkat pertama / internal unit.
* **Admin PKLN (Pelayanan Kerja Sama Luar Negeri)**: Verifikator dan pemroses tingkat akhir.

## 3. Matriks Status Surat
| Status System | Deskripsi |
| :--- | :--- |
| `DRAFT` | Surat belum diajukan |
| `SUBMITTED_UNOR` | Menunggu verifikasi Admin Unor |
| `APPROVED_UNOR` | Disetujui Unor, diteruskan ke PKLN |
| `REJECTED_UNOR` | Dikembalikan / ditolak oleh Admin Unor |
| `IN_REVIEW_PKLN` | Sedang diproses oleh Admin PKLN |
| `COMPLETED` | Selesai diproses oleh Admin PKLN |
| `REJECTED_PKLN` | Dikembalikan / ditolak oleh Admin PKLN |