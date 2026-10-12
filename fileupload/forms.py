from django import forms

from paspor.validators import validate_pdf

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB, selaras dengan DATA_UPLOAD_MAX_MEMORY_SIZE


class PdfUploadForm(forms.Form):
    file = forms.FileField(label="Berkas PDF")

    def clean_file(self):
        f = self.cleaned_data["file"]
        validate_pdf(f)  # ekstensi, MIME type, dan isi berkas (%PDF-)
        if f.size > MAX_FILE_SIZE:
            raise forms.ValidationError("Ukuran berkas maksimal 10MB.")
        return f
