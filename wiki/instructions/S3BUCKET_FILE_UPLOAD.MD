# Unggah Berkas ke Bucket S3 (Garage di Synology NAS)

> **Status:** sudah diimplementasikan.
> **Cakupan:** seluruh berkas unggahan aplikasi — dokumen Pegawai, Admin Unor, Admin Biro PAKLN, dokumen hasil generate, template dokumen, dan demo publik `/upload/`.

## Daftar Isi

1. [Ringkasan](#1-ringkasan)
2. [Arsitektur](#2-arsitektur)
3. [Konfigurasi](#3-konfigurasi)
4. [Menyiapkan Garage (sekali saja)](#4-menyiapkan-garage-sekali-saja)
5. [Cara Kerja di Kode](#5-cara-kerja-di-kode)
6. [Memindahkan Berkas Lama ke Bucket](#6-memindahkan-berkas-lama-ke-bucket)
7. [Verifikasi Koneksi](#7-verifikasi-koneksi)
8. [Troubleshooting](#8-troubleshooting)
9. [Catatan Keamanan](#9-catatan-keamanan)

---

## 1. Ringkasan

PASPOR menyimpan seluruh berkas unggahan di bucket **S3-compatible** yang
dijalankan oleh **Garage** pada Synology NAS, bukan lagi di folder `media/`
lokal maupun MinIO. Integrasinya memakai
[`django-storages`](https://django-storages.readthedocs.io/) (backend
`storages.backends.s3.S3Storage`) di atas `boto3`.

Karena backend dipasang sebagai storage **`default`**, semua `FileField`
dan `default_storage` otomatis menulis/membaca ke bucket — tidak ada kode
model/view yang perlu tahu bahwa penyimpanannya S3.

Poin penting:

- Bucket bersifat **privat** (`default_acl = None`). Browser tidak pernah
  mengakses object tanpa tanda tangan.
- Link unduh/pratinjau adalah **presigned URL** yang berlaku
  `S3_QUERYSTRING_EXPIRE` detik (default 1 jam). Setiap render halaman
  menghasilkan link baru.
- `file_overwrite = False`: jika key sudah ada, Django menambahkan sufiks
  acak (mis. `ktp_aB3xYz1.pdf`) alih-alih menimpa berkas lama.

## 2. Arsitektur

```
Browser ──(multipart POST)──▶ Django view / ModelForm
                                   │
                                   ▼
                         FileField.save() / default_storage.save()
                                   │  boto3 (SigV4, path-style)
                                   ▼
                    Garage S3 API  http://10.101.21.55:3900
                                   │
                                   ▼
                         bucket  paspor-uploads
                            ├── pengajuan/<kode>/pegawai/<jenis>/...
                            ├── pengajuan/<kode>/unor/<jenis>/...
                            ├── pengajuan/<kode>/unor/pendukung/...
                            ├── pengajuan/<kode>/pakln/<jenis>/...
                            ├── pengajuan/<kode>/pakln/pendukung/...
                            ├── generate_dokumen/<jenis>/...
                            ├── template_dokumen/...
                            └── public/<uuid>.pdf          (app fileupload)

Lihat/unduh:
  template  {{ dok.file.url }}  ──▶  presigned URL  ──▶ browser GET langsung ke Garage
  /upload/<pk>/lihat/           ──▶  302 redirect ke presigned URL
  pegawai:download_iln          ──▶  Django stream dari S3 (FileResponse)
```

Yang disimpan di database hanyalah **key object** (mis.
`pengajuan/PSP-2026-0001/pegawai/ktp/ktp.pdf`), bukan URL lengkap. Jadi
endpoint/bucket boleh berpindah tanpa mengubah data.

## 3. Konfigurasi

### 3.1 Dependency

Sudah tercantum di `requirements.txt`:

```
django-storages==1.14.6
boto3==1.43.106
botocore==1.43.106
s3transfer==0.19.2
```

Paket `minio` sudah dihapus karena tidak dipakai lagi.

### 3.2 Environment variable (`.env`)

| Variabel | Wajib | Default | Keterangan |
|---|---|---|---|
| `S3_ACCESS_KEY` | ✅ | — | Key ID Garage (diawali `GK...`). Django gagal start (`KeyError`) jika kosong. |
| `S3_SECRET_KEY` | ✅ | — | Secret key pasangan Key ID. |
| `S3_BUCKET_NAME` | | `paspor-uploads` | Nama bucket. |
| `S3_ENDPOINT` | | `http://127.0.0.1:3900` | URL S3 API Garage (port **3900**, bukan port web/admin). |
| `S3_REGION_NAME` | | `garage` | Harus sama dengan `s3_region` di `garage.toml` (default Garage: `garage`). |
| `S3_QUERYSTRING_EXPIRE` | | `3600` | Masa berlaku presigned URL dalam detik. |

Contoh:

```env
S3_ACCESS_KEY=GKxxxxxxxxxxxxxxxxxxxxxxxx
S3_SECRET_KEY=ganti-dengan-secret-key-garage
S3_BUCKET_NAME=paspor-uploads
S3_ENDPOINT=http://10.101.21.55:3900
S3_REGION_NAME=garage
S3_QUERYSTRING_EXPIRE=3600
```

### 3.3 `settings.py`

```python
from botocore.config import Config as BotoConfig

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": S3_ENDPOINT,
            "access_key": os.environ["S3_ACCESS_KEY"],
            "secret_key": os.environ["S3_SECRET_KEY"],
            "bucket_name": S3_BUCKET_NAME,
            "region_name": S3_REGION_NAME,
            "client_config": BotoConfig(
                s3={"addressing_style": "path"},
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": True,
            "querystring_expire": S3_QUERYSTRING_EXPIRE,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
```

Penjelasan opsi:

| Opsi | Alasan |
|---|---|
| `endpoint_url` | Mengarahkan boto3 ke Garage, bukan AWS. |
| `region_name` | Ikut ditandatangani di SigV4; jika beda dengan `s3_region` Garage, request ditolak. |
| `addressing_style: "path"` | URL berbentuk `http://host:3900/bucket/key`. Garage tidak memakai subdomain per bucket (virtual-host) tanpa konfigurasi DNS tambahan. |
| `signature_version: "s3v4"` | Satu-satunya skema tanda tangan yang didukung Garage. |
| `client_config` | **Catatan:** jika `client_config` diisi, django-storages mengabaikan opsi `addressing_style` & `signature_version` di level atas, jadi keduanya diletakkan di dalam `BotoConfig`. Timeout mencegah request menggantung bila NAS tidak terjangkau. |
| `default_acl: None` | Garage tidak mendukung ACL per-object; mengirim ACL hanya menimbulkan error. |
| `file_overwrite: False` | Unggahan dengan nama sama tidak menimpa berkas lain. |
| `querystring_auth` / `querystring_expire` | `.url` menghasilkan presigned URL berumur terbatas. |
| `staticfiles` | Static file (CSS/JS) tetap lokal — hanya media yang ke S3. |

`MEDIA_URL` dan route `static(settings.MEDIA_URL, ...)` di `urls.py` sudah
dihapus karena URL berkas kini berasal dari storage. `MEDIA_ROOT` tetap ada
hanya sebagai sumber command migrasi (§6).

## 4. Menyiapkan Garage (sekali saja)

Jalankan di NAS (container Garage):

```bash
# 1. Buat key aplikasi — catat Key ID & Secret key ke .env
garage key create paspor-app

# 2. Buat bucket
garage bucket create paspor-uploads

# 3. Beri izin key ke bucket (LANGKAH YANG SERING TERLEWAT)
garage bucket allow --read --write --owner paspor-uploads --key paspor-app

# 4. Cek
garage bucket info paspor-uploads
```

Tanpa langkah 3, kredensial tetap valid tetapi setiap operasi akan gagal
dengan `403 Forbidden` / `AccessDenied: Operation is not allowed for this key`.

> Django **tidak** membuat bucket secara otomatis (berbeda dengan
> implementasi MinIO sebelumnya). Bucket harus dibuat lewat CLI Garage.

## 5. Cara Kerja di Kode

### 5.1 Dokumen pengajuan (`FileField`)

Model di `pengajuan/models.py` (`DokumenPegawai`, `DokumenUnor`,
`DokumenUnorPendukung`, `DokumenPakln`, `DokumenPaklnPendukung`,
`DokumenGenerateLog`, `DokumenTemplate`) memakai `models.FileField` dengan
fungsi `upload_to` yang menentukan prefix key. Tidak ada perubahan kode:

```python
# Unggah — ModelForm biasa
form = DokumenPegawaiForm(request.POST, request.FILES, instance=existing)
dok = form.save(commit=False)
dok.save()                        # → PUT object ke bucket

# Simpan hasil generate (bytes)
log.file.save(filename, ContentFile(pdf_bytes), save=False)

# Tampilkan link / pratinjau
{{ dok.file.url }}                # → presigned URL 1 jam

# Unduh lewat Django (mis. download_iln)
FileResponse(dok.file.open("rb"), as_attachment=True, filename=...)

# Hapus
dok.file.delete(save=False)       # → DELETE object
```

Pratinjau di modal (`templates/base.html`, `data-doc-preview`) memuat
presigned URL langsung di `<iframe>`. Garage mengirim `Content-Type` yang
ditebak django-storages dari ekstensi berkas saat unggah, sehingga PDF
tampil inline.

### 5.2 App `fileupload` (demo publik `/upload/`)

`fileupload/views.py` memakai `default_storage` secara langsung:

| View | Aksi |
|---|---|
| `upload_view` | Validasi PDF ≤ 10 MB, simpan ke `public/<uuid>.pdf` via `default_storage.save()`, catat di `UploadedFile` (`object_name` = key). |
| `view_file` | Cek `exists()`, lalu redirect 302 ke presigned URL dengan `ResponseContentDisposition: inline; filename="<nama asli>"` agar nama berkas asli tetap terlihat. |
| `delete_view` | `default_storage.delete(key)` lalu hapus baris `UploadedFile`. |

Modul `fileupload/minio_client.py` sudah dihapus.

### 5.3 Menambah fitur unggah baru

Cukup pakai `FileField` (disarankan) atau `default_storage`:

```python
def lampiran_path(instance, filename):
    return f"lampiran/{instance.pengajuan.kode}/{filename}"

class Lampiran(models.Model):
    file = models.FileField(upload_to=lampiran_path)
```

Jangan memakai `.path` / `open(file.path)` — object S3 tidak punya path
lokal. Gunakan `file.open("rb")`, `file.read()`, atau `file.url`.

## 6. Memindahkan Berkas Lama ke Bucket

Berkas yang diunggah sebelum migrasi masih berada di folder `media/`,
sementara database sudah menyimpan key-nya (mis.
`pengajuan/PSP-.../ktp.pdf`). Unggah semuanya ke bucket dengan key yang
sama:

```powershell
python manage.py sync_media_to_s3 --dry-run   # lihat daftar berkas
python manage.py sync_media_to_s3             # unggah (lewati yang sudah ada)
python manage.py sync_media_to_s3 --overwrite # timpa object yang sudah ada
```

Setelah semua link dokumen lama terverifikasi bisa dibuka, folder `media/`
boleh diarsipkan/dihapus.

> Berkas demo `/upload/` yang dulu tersimpan di **MinIO** tidak ikut
> dipindahkan oleh command ini. Jika masih diperlukan, salin dengan
> `mc mirror` / `rclone` dari bucket MinIO ke bucket Garage dengan key yang
> sama.

## 7. Verifikasi Koneksi

```powershell
python manage.py shell -c "from django.core.files.storage import default_storage as s; from django.core.files.base import ContentFile; n=s.save('healthcheck/test.txt', ContentFile(b'ok')); print(n, s.exists(n), s.url(n)); s.delete(n)"
```

Output yang diharapkan: key, `True`, dan presigned URL
`http://10.101.21.55:3900/paspor-uploads/healthcheck/test.txt?X-Amz-...`.

## 8. Troubleshooting

| Gejala | Penyebab / Solusi |
|---|---|
| `KeyError: 'S3_ACCESS_KEY'` saat start | `S3_ACCESS_KEY`/`S3_SECRET_KEY` belum ada di `.env`. |
| `403 Forbidden` / `AccessDenied: Operation is not allowed for this key` | Key belum diberi izin ke bucket → `garage bucket allow --read --write --owner <bucket> --key <key>` (§4). |
| `NoSuchBucket` | Bucket belum dibuat atau `S3_BUCKET_NAME` salah. |
| `SignatureDoesNotMatch` / `AuthorizationHeaderMalformed` | Secret key salah, atau `S3_REGION_NAME` tidak sama dengan `s3_region` Garage. |
| `ConnectTimeoutError` / `EndpointConnectionError` | NAS tidak terjangkau (beda jaringan/VPN) atau port salah — S3 API Garage di **3900**. |
| Link dokumen lama 404 (`NoSuchKey`) | Berkas belum dipindahkan dari `media/` → jalankan `sync_media_to_s3` (§6). |
| Link pratinjau kedaluwarsa (`Request has expired`) | Halaman dibuka lebih lama dari `S3_QUERYSTRING_EXPIRE`; muat ulang halaman. |
| Pratinjau kosong saat aplikasi diakses via HTTPS | Browser memblokir *mixed content* — presigned URL masih `http://`. Pasang reverse proxy HTTPS untuk Garage dan ubah `S3_ENDPOINT` ke `https://...`. |

## 9. Catatan Keamanan

- Jangan aktifkan *website access* / public-read pada bucket — akses
  hanya lewat presigned URL.
- Presigned URL bisa dibagikan ulang selama masa berlakunya; jaga
  `S3_QUERYSTRING_EXPIRE` tetap pendek untuk dokumen sensitif (KTP, paspor).
- Pengguna harus bisa menjangkau `S3_ENDPOINT` dari browser-nya (bukan hanya
  dari server Django), karena presigned URL diakses langsung oleh browser.
- Gunakan key Garage khusus aplikasi (bukan key admin) dengan izin hanya
  ke bucket ini, dan key/bucket terpisah untuk produksi.
- Jangan commit `.env` — hanya `.env.example` yang masuk git.
