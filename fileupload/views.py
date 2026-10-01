import os
import uuid

from django.contrib import messages
from django.core.files.storage import default_storage
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PdfUploadForm
from .models import UploadedFile

UPLOAD_FOLDER = "public"


def upload_view(request):
    """Halaman publik (tanpa login) untuk mengunggah berkas PDF ke bucket S3
    lewat `default_storage`, lihat wiki/instructions/S3BUCKET_FILE_UPLOAD.MD."""
    if request.method == "POST":
        form = PdfUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            # Nama asli diganti UUID untuk mencegah collision & path traversal.
            ext = os.path.splitext(uploaded.name)[1].lower()
            try:
                object_name = default_storage.save(f"{UPLOAD_FOLDER}/{uuid.uuid4()}{ext}", uploaded)
            except Exception as exc:
                messages.error(request, f"Gagal mengunggah berkas ke penyimpanan: {exc}")
            else:
                UploadedFile.objects.create(
                    original_filename=uploaded.name,
                    object_name=object_name,
                    content_type=uploaded.content_type or "application/pdf",
                    size=uploaded.size,
                )
                messages.success(request, f'Berkas "{uploaded.name}" berhasil diunggah.')
                return redirect("fileupload:upload")
        else:
            messages.error(request, "Berkas tidak valid. Pastikan berformat PDF dan maksimal 10MB.")
    else:
        form = PdfUploadForm()

    files = UploadedFile.objects.all()[:50]
    return render(request, "fileupload/upload.html", {"form": form, "files": files})


def view_file(request, pk):
    """Redirect ke presigned URL S3 (berlaku S3_QUERYSTRING_EXPIRE detik).
    Bucket tetap privat — tanpa tanda tangan yang valid object tidak bisa
    diakses."""
    obj = get_object_or_404(UploadedFile, pk=pk)
    if not default_storage.exists(obj.object_name):
        raise Http404("Berkas tidak ditemukan di penyimpanan.")
    url = default_storage.url(
        obj.object_name,
        parameters={
            "ResponseContentType": obj.content_type or "application/pdf",
            "ResponseContentDisposition": f'inline; filename="{obj.original_filename}"',
        },
    )
    return redirect(url)


def delete_view(request, pk):
    obj = get_object_or_404(UploadedFile, pk=pk)
    if request.method == "POST":
        try:
            default_storage.delete(obj.object_name)
        except Exception as exc:
            messages.error(request, f"Gagal menghapus berkas: {exc}")
        else:
            obj.delete()
            messages.success(request, "Berkas berhasil dihapus.")
    return redirect("fileupload:upload")
