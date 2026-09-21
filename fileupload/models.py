from django.db import models


class UploadedFile(models.Model):
    """Catatan berkas yang tersimpan di bucket MinIO. `object_name` adalah
    kunci object di MinIO (bukan nama file asli), dipakai proxy view untuk
    streaming & hapus."""

    original_filename = models.CharField("Nama Berkas", max_length=255)
    object_name = models.CharField(max_length=255, unique=True)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField("Ukuran (byte)", default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Berkas Terunggah"
        verbose_name_plural = "Berkas Terunggah"

    def __str__(self):
        return self.original_filename
