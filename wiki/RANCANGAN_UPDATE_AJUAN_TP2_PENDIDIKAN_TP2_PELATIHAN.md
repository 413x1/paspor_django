# Rancangan Perubahan Alur PDLN Tipe 2: Surat Tugas Pimpinan Unor setelah Izin Prinsip Menteri

Nov 10, 2026 · @Muhammad Sholeh

## Latar Belakang dan Ruang Lingkup

Pada PDLN Tipe 2, Surat Tugas Pimpinan Unor dipindahkan dari tahap awal Admin Unor ke jalur paralel yang terbuka setelah Admin BPSDM mengunggah Izin Prinsip Menteri. Admin BPSDM tidak menunggu Surat Tugas untuk meneruskan. Biro PAKLN dapat menerima dan meninjau berkas, tetapi baru dapat mengunggah SP Setneg dan dokumen PAKLN lainnya setelah Surat Tugas dikirim dan sesuai; bila tidak sesuai, Surat Tugas dikembalikan ke Admin Unor.

Pengunggah Surat Tugas tetap Admin Unor, dan berkasnya tetap disimpan sebagai dokumen Unor. Perubahan berlaku sama untuk Tipe 2 Pendidikan (T2P) dan Tipe 2 Pelatihan (T2L). Non-Kedinasan, PDLN Tipe 1, dan Tipe 3 tidak berubah.

## Alur Saat Ini

Saat ini Surat Tugas menjadi syarat Admin Unor meneruskan ke BPSDM, sehingga terbit sebelum Izin Prinsip Menteri. Urutan status T2P dan T2L adalah `belum` → `proses` → `proses_bpsdm` → `proses_pakln` → `selesai`.

1. **Pegawai** (`belum`) mengisi formulir dan mengunggah dokumen pegawai, lalu mengirim ke Admin Unor.
2. **Admin Unor** (`proses`) mengunggah Nota Dinas Sekretaris Unor ke Sekretaris BPSDM, **Surat Tugas Pimpinan Unor**, dan DRH ttd Pimpinan Unor (khusus T2P). Tombol Teruskan ke Admin BPSDM terkunci selama salah satunya belum ada.
3. **Admin BPSDM** (`proses_bpsdm`) mengunggah Izin Prinsip Menteri, Perjanjian Ikatan Dinas ttd (khusus T2P), dan Nota Dinas Sekretaris BPSDM ke Kepala Biro PAKLN, lalu meneruskan ke Biro PAKLN.
4. **Admin Biro PAKLN** (`proses_pakln`) memproses SP Setneg, paspor dinas, exit permit, dan Rekomendasi Visa. Pada T2P, SK Tugas Belajar diunggah Admin BKO pada jalur paralel.

## Alur Usulan

&#91;embedded content: alur PDLN Tipe 2 · saat ini dan usulan\]

Status pengajuan tetap lima tahap. Jalur Surat Tugas dibuka oleh Izin Prinsip, dikirim Admin Unor ke Biro PAKLN, dan dapat dikembalikan bila tidak sesuai. Admin BPSDM tidak tertahan, sedangkan Biro PAKLN baru mengunggah dokumen PAKLN setelah Surat Tugas diterima.

### Flowchart PDLN Tipe 2 Pendidikan (T2P)

&#91;embedded content: flowchart T2P · jalur Surat Tugas dan jalur Admin BKO\]

Admin BPSDM meneruskan ke Biro PAKLN dan Admin BKO tanpa menunggu Surat Tugas. Biro PAKLN dapat meninjau berkas, tetapi unggah SP Setneg dan dokumen PAKLN lainnya terkunci sampai Surat Tugas dikirim dan dinilai sesuai. Selesai juga menunggu jalur Admin BKO tuntas.

### Flowchart PDLN Tipe 2 Pelatihan (T2L)

&#91;embedded content: flowchart T2L · jalur Surat Tugas, tanpa jalur Admin BKO\]

Alurnya sama dengan T2P, tetapi tanpa DRH ttd, Perjanjian Ikatan Dinas, dan jalur Admin BKO. Unggah dokumen PAKLN juga terkunci sampai Surat Tugas dikirim dan dinilai sesuai.

## Perubahan Aturan Bisnis

Status utama tidak bertambah: Surat Tugas berjalan pada jalur paralel milik Admin Unor, seperti jalur SK Tugas Belajar milik Admin BKO.

| Aspek | Saat ini | Usulan |
| --- | --- | --- |
| Waktu unggah Surat Tugas Pimpinan Unor | Tahap Admin Unor (`proses`), sebelum diteruskan ke BPSDM | Setelah Admin BPSDM mengunggah Izin Prinsip Menteri, selama status `proses_bpsdm` atau `proses_pakln` |
| Pengunggah Surat Tugas | Admin Unor | Admin Unor (tetap) |
| Syarat Admin Unor meneruskan ke BPSDM | Nota Dinas ke Sekretaris BPSDM, Surat Tugas, DRH ttd (T2P) | Nota Dinas ke Sekretaris BPSDM, DRH ttd (T2P) |
| Syarat Admin BPSDM meneruskan ke Biro PAKLN dan Admin BKO | Dokumen BPSDM lengkap | Dokumen BPSDM lengkap; tidak menunggu Surat Tugas |
| Pemeriksa Surat Tugas | Admin BPSDM, lalu Biro PAKLN, melalui pratinjau berjenjang | Admin Biro PAKLN. Surat Tugas dapat dikembalikan ke Admin Unor dengan catatan tanpa mengubah status pengajuan |
| Syarat Biro PAKLN mengunggah SP Setneg dan dokumen PAKLN lainnya | Pengajuan sudah diteruskan Admin BPSDM ke Biro PAKLN | Ditambah Surat Tugas sudah dikirim Admin Unor dan tidak sedang dikembalikan. Sebelum itu Biro PAKLN hanya dapat meninjau berkas |
| Syarat Biro PAKLN menyelesaikan | Dokumen PAKLN lengkap (+ jalur BKO pada T2P) | Ditambah Surat Tugas sudah dikirim dan tidak sedang dikembalikan |
| Penguncian dokumen | Dokumen hanya dapat diubah selama pengajuan berada di tahap pengunggahnya | Tetap. Surat Tugas terkunci setelah dikirim Admin Unor dan terbuka lagi hanya bila dikembalikan Biro PAKLN. Izin Prinsip yang diganti sebelum diteruskan tidak mewajibkan Surat Tugas diunggah ulang |
| Tanggal Izin Prinsip | Tidak dicatat | Admin BPSDM mengisi Tanggal Surat saat mengunggah Izin Prinsip; tanggal ini dimuat otomatis di format Surat Tugas |
| Notifikasi | Admin Unor → Admin BPSDM saat diteruskan | Tambahan: ke Admin Unor saat Izin Prinsip diunggah dan saat Surat Tugas dikembalikan; ke Admin Biro PAKLN saat Surat Tugas dikirim |
| Batas waktu unggah Surat Tugas | Tidak ada | Tidak ada |

Alternatif menambah status baru tidak dipilih karena membuat pengajuan bolak-balik BPSDM → Unor → BPSDM. Alternatif menjadikan Surat Tugas syarat Admin BPSDM meneruskan juga tidak dipilih, karena Admin BPSDM tidak perlu menunggunya. Penantian ditempatkan di Biro PAKLN: berkas dapat ditinjau sejak diterima, tetapi unggah dokumen PAKLN baru terbuka setelah Surat Tugas dikirim.

## Dampak pada Sistem

Perubahan mengikuti pola jalur Admin BKO (`pengajuan/bko.py`) dan memerlukan satu migrasi skema untuk status jalur Surat Tugas. Berkasnya tetap disimpan di `DokumenUnor` dengan jenis `surat_tugas`.

| Komponen | Perubahan |
| --- | --- |
| `pengajuan/models.py` | Field baru pada `Pengajuan`: `status_surat_tugas` (kosong, `menunggu`, `dikirim`, `dikembalikan`) dan `catatan_surat_tugas`, beserta migrasi |
| Modul baru `pengajuan/surat_tugas.py` | Satu-satunya tempat perubahan `status_surat_tugas`, dengan penguncian baris seperti `bko.py`. Jalur dibuka saat Izin Prinsip pertama kali diunggah, menjadi `dikirim` saat Admin Unor mengirim, dan `dikembalikan` saat Biro PAKLN mengembalikan |
| `pengajuan/persyaratan.py` | `surat_tugas` dikeluarkan dari daftar (T2P/T2L, `unor`) tahap awal; `izin_prinsip` pada (T2P/T2L, `bpsdm`) diberi `tanggal_surat=True` |
| Halaman Admin Unor | Bagian Surat Tugas pada pengajuan `proses_bpsdm` atau `proses_pakln` yang jalurnya terbuka: unduh format, unggah atau ganti berkas, lalu Kirim. Setelah dikirim, berkas terkunci kecuali dikembalikan |
| Format Surat Tugas | Diisi otomatis dengan Tanggal Surat Izin Prinsip. Karena `DokumenTemplate` saat ini berupa berkas statis, format ini dibangkitkan sistem dengan pola Generate ND |
| `views_bpsdm._teruskan` | Tidak berubah; tidak memeriksa Surat Tugas |
| `views_pakln` | Pratinjau menampilkan status Surat Tugas; slot unggah dokumen PAKLN terkunci dan permintaan unggah atau hapus ditolak selama Surat Tugas belum dikirim atau sedang dikembalikan; aksi baru Kembalikan Surat Tugas dengan catatan wajib; `_selesaikan` memeriksa Surat Tugas seperti pemeriksaan jalur BKO |
| Dasbor Admin Unor dan Admin Biro PAKLN | Admin Unor: penanda "Menunggu Surat Tugas" dan "Surat Tugas dikembalikan". Admin Biro PAKLN: penanda "Menunggu Surat Tugas" pada pengajuan yang unggah dokumen PAKLN-nya masih terkunci |
| `pengajuan/alur.py` | Deskripsi timeline T2P/T2L dan sub-keterangan jalur Surat Tugas, seperti sub-keterangan jalur BKO |
| `notifications/services.py` | Tiga notifikasi baru: Izin Prinsip diunggah (ke Admin Unor), Surat Tugas dikirim (ke Admin Biro PAKLN), dan Surat Tugas dikembalikan (ke Admin Unor) |
| `RiwayatPengajuan.Aksi` | Aksi baru `surat_tugas_dikirim` dan `surat_tugas_dikembalikan` |
| Uji dan dokumentasi | `pengajuan/tests_pdln.py` (`AlurTipe2Tests`), uji T2P v2, dan uji baru untuk jalur Surat Tugas; `PDLN_TIPE_2_FLOW.MD` dan `BISNIS_PROSES_PDLN.MD` |

## Kasus Khusus dan Risiko

Rantai pengembalian dan pembatalan utama tidak berubah, karena jalur Surat Tugas berjalan terpisah dari status pengajuan.

| Kasus | Perlakuan |
| --- | --- |
| Biro PAKLN menilai Surat Tugas tidak sesuai | Biro PAKLN mengembalikan Surat Tugas ke Admin Unor dengan catatan. Status pengajuan tetap `proses_pakln`; unggah dokumen PAKLN kembali terkunci sampai Admin Unor mengganti berkas lalu mengirim ulang |
| Surat Tugas dikembalikan setelah sebagian dokumen PAKLN diunggah | Dokumen PAKLN yang sudah diunggah tetap tersimpan, tetapi tidak dapat ditambah, diganti, atau dihapus sampai Surat Tugas dikirim ulang |
| Admin BPSDM mengembalikan pengajuan ke Admin Unor (`proses_bpsdm` → `proses`) | Jalur Surat Tugas dan berkasnya tetap. Surat Tugas yang sudah dikirim tetap terkunci |
| Biro PAKLN mengembalikan pengajuan ke Admin BPSDM | Jalur Surat Tugas tidak terpengaruh dan tetap dapat diproses Admin Unor |
| Izin Prinsip diganti sebelum Admin BPSDM meneruskan | Surat Tugas tidak perlu diunggah ulang. Setelah diteruskan, Izin Prinsip terkunci |
| Permohonan pembatalan sedang terbuka | Unggah, kirim, dan pengembalian Surat Tugas ikut dibekukan seperti aksi alur lainnya |
| Admin Unor juga pengaju pengajuan tersebut (role ganda) | Larangan memproses pengajuan sendiri berlaku juga untuk jalur Surat Tugas |
| Pengajuan yang sedang berjalan saat rilis | Pengajuan yang Surat Tugasnya sudah diunggah di tahap Unor ditandai `dikirim` melalui migrasi data. Pengajuan yang masih di tahap Unor tanpa Surat Tugas mengikuti aturan baru |

**Risiko utama:** Biro PAKLN tidak dapat mengunggah dokumen PAKLN maupun menyelesaikan pengajuan selama Admin Unor belum mengirim Surat Tugas, sehingga lama proses di Biro PAKLN bergantung pada Admin Unor. Tidak ada batas waktu unggah, sehingga mitigasinya adalah notifikasi serta penanda di dasbor Admin Unor dan Admin Biro PAKLN.

## Kriteria Penerimaan

Setiap butir berlaku untuk T2P dan T2L dan diuji otomatis sebelum digabungkan.

- [ ] Admin Unor dapat meneruskan ke Admin BPSDM tanpa Surat Tugas, dan slot Surat Tugas tidak tampil pada tahap `proses`.
- [ ] Sebelum Izin Prinsip Menteri ada, Admin Unor tidak dapat mengunggah Surat Tugas.
- [ ] Admin BPSDM wajib mengisi Tanggal Surat saat mengunggah Izin Prinsip, dan tanggal itu muncul di format Surat Tugas.
- [ ] Setelah Izin Prinsip diunggah, Admin Unor menerima notifikasi dan dapat mengunggah serta mengirim Surat Tugas untuk unit organisasinya.
- [ ] Admin BPSDM dapat meneruskan ke Biro PAKLN dan Admin BKO walaupun Surat Tugas belum ada.
- [ ] Admin Unor tidak dapat mengubah Surat Tugas yang sudah dikirim, kecuali setelah dikembalikan Biro PAKLN.
- [ ] Biro PAKLN dapat mengembalikan Surat Tugas dengan catatan wajib tanpa mengubah status pengajuan, dan Admin Unor menerima notifikasi.
- [ ] Biro PAKLN dapat meninjau berkas sejak diterima, tetapi tidak dapat mengunggah atau menghapus SP Setneg dan dokumen PAKLN lainnya selama Surat Tugas belum dikirim atau sedang dikembalikan, baik pada T2P maupun T2L.
- [ ] Biro PAKLN tidak dapat menyelesaikan pengajuan selama Surat Tugas belum dikirim atau sedang dikembalikan.
- [ ] Selama permohonan pembatalan terbuka, semua aksi jalur Surat Tugas ditolak.
- [ ] Pengajuan lama yang Surat Tugasnya sudah diunggah di tahap Unor tetap dapat diselesaikan.
- [ ] Alur Non-Kedinasan, PDLN Tipe 1, dan Tipe 3 tidak berubah, dan seluruh uji yang ada tetap lulus.

## Keputusan

Seluruh pertanyaan terbuka dijawab pemilik proses pada 10 November 2026.

| No | Pertanyaan | Keputusan |
| --- | --- | --- |
| 1 | Apakah dokumen BPSDM lain baru dapat diunggah setelah Surat Tugas ada? | Tidak. Admin BPSDM memproses dan meneruskan ke Biro PAKLN dan/atau Admin BKO tanpa menunggu Surat Tugas. Biro PAKLN dapat menerima dan meninjau berkas tanpa menunggu, serta dapat mengembalikan Surat Tugas bila tidak valid atau tidak sesuai |
| 2 | Perlukah aksi "minta perbaikan Surat Tugas" bagi Admin BPSDM? | Tidak perlu |
| 3 | Bila Izin Prinsip diganti, wajibkah Surat Tugas diunggah ulang? | Tidak. Dokumen yang sudah diteruskan atau diselesaikan tidak dapat diubah lagi |
| 4 | Perlukah format Surat Tugas memuat data Izin Prinsip secara otomatis? | Ya, tanggalnya saja |
| 5 | Adakah batas waktu bagi Admin Unor untuk mengunggah Surat Tugas? | Tidak ada |
| 6 | Apakah Surat Tugas yang sudah dikirim menjadi syarat Biro PAKLN menekan Selesai? | Ya. Surat Tugas yang sudah dikirim dan tidak sedang dikembalikan menjadi syarat Biro PAKLN melanjutkan proses ke Selesai |
| 7 | Bolehkah Biro PAKLN mengunggah SP Setneg dan dokumen PAKLN lainnya sebelum Surat Tugas ada? | Tidak. Unggah dokumen PAKLN menunggu Surat Tugas Pimpinan Unor dikirim dan tidak sedang dikembalikan; berlaku untuk T2P dan T2L |

## Sumber

- [`pengajuan/persyaratan.py`](https://github.com/413x1/paspor_django/blob/c0ace41/pengajuan/persyaratan.py): registri dokumen per tipe dan tahap
- [`pengajuan/alur.py`](https://github.com/413x1/paspor_django/blob/c0ace41/pengajuan/alur.py): urutan status dan deskripsi timeline
- [`pengajuan/views_bpsdm.py`](https://github.com/413x1/paspor_django/blob/c0ace41/pengajuan/views_bpsdm.py) dan [`pengajuan/views_unor.py`](https://github.com/413x1/paspor_django/blob/c0ace41/pengajuan/views_unor.py): pemeriksaan unggah dan Teruskan
- [`wiki/instructions/PDLN_TIPE_2_FLOW.MD`](https://github.com/413x1/paspor_django/blob/c0ace41/wiki/instructions/PDLN_TIPE_2_FLOW.MD): alur bisnis Tipe 2 dan jalur Admin BKO

Semua tautan mengacu pada *commit* `c0ace41` cabang *development*.
