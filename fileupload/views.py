from django.contrib import messages
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from . import minio_client
from .forms import PdfUploadForm
from .models import UploadedFile


def upload_view(request):
    """Halaman publik (tanpa login) untuk mengunggah berkas PDF ke MinIO,
    mengikuti mekanisme pada wiki/UPLOAD_FILE.MD."""
    if request.method == "POST":
        form = PdfUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            try:
                object_name = minio_client.upload_file(uploaded)
            except Exception as exc:
                messages.error(request, f"Gagal mengunggah berkas ke MinIO: {exc}")
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
    """Proxy viewer — file di-stream dari MinIO, bucket tidak pernah
    diekspos langsung ke publik."""
    obj = get_object_or_404(UploadedFile, pk=pk)
    try:
        stream = minio_client.open_stream(obj.object_name)
    except Exception:
        raise Http404("Berkas tidak ditemukan di penyimpanan.")

    def chunks():
        try:
            for chunk in stream.stream(64 * 1024):
                yield chunk
        finally:
            stream.close()
            stream.release_conn()

    response = StreamingHttpResponse(chunks(), content_type=obj.content_type or "application/pdf")
    response["Content-Disposition"] = f'inline; filename="{obj.original_filename}"'
    return response


def delete_view(request, pk):
    obj = get_object_or_404(UploadedFile, pk=pk)
    if request.method == "POST":
        try:
            minio_client.delete_file(obj.object_name)
        except Exception as exc:
            messages.error(request, f"Gagal menghapus berkas: {exc}")
        else:
            obj.delete()
            messages.success(request, "Berkas berhasil dihapus.")
    return redirect("fileupload:upload")
