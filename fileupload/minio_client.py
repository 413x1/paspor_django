"""Klien MinIO untuk fitur unggah berkas publik.

Mengikuti mekanisme pada `wiki/UPLOAD_FILE.MD`: object storage tidak pernah
diakses langsung dari browser — semua lewat proxy view Django
(`fileupload.views.view_file`) — dan nama file asli diganti UUID untuk
mencegah collision & path traversal.
"""

import io
import os
import uuid

import urllib3
from django.conf import settings
from minio import Minio

_client = None

# Batas waktu koneksi/baca ke MinIO — tanpa ini, endpoint yang tidak bisa
# dijangkau (mis. beda jaringan/VPN) akan membuat request menggantung lama
# sebelum akhirnya gagal.
_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 30.0


def get_client():
    global _client
    if _client is None:
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT),
            retries=urllib3.Retry(total=1, backoff_factor=0.2),
        )
        _client = Minio(
            f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}",
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
            http_client=http_client,
        )
    return _client


def _bucket_name():
    bucket = settings.MINIO_BUCKET_NAME
    if not bucket:
        raise ValueError("MINIO_BUCKET_NAME belum dikonfigurasi (lihat .env).")
    return bucket


def ensure_bucket():
    client = get_client()
    bucket = _bucket_name()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def upload_file(django_file, folder="public"):
    """Unggah `UploadedFile` Django ke MinIO dan kembalikan object name-nya."""
    ensure_bucket()
    client = get_client()
    ext = os.path.splitext(django_file.name)[1]
    object_name = f"{folder}/{uuid.uuid4()}{ext}"

    data = django_file.read()
    client.put_object(
        _bucket_name(),
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=django_file.content_type or "application/octet-stream",
    )
    return object_name


def stat_file(object_name):
    return get_client().stat_object(_bucket_name(), object_name)


def open_stream(object_name):
    """Kembalikan response streaming MinIO. Caller wajib memanggil
    `.close()` dan `.release_conn()` setelah selesai (lihat views.view_file)."""
    return get_client().get_object(_bucket_name(), object_name)


def delete_file(object_name):
    get_client().remove_object(_bucket_name(), object_name)
