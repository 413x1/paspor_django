from django import forms

from paspor.validators import validate_pdf


class PdfUploadForm(forms.Form):
    file = forms.FileField(
        label="Berkas PDF",
        widget=forms.FileInput(attrs={
            "accept": ".pdf,application/pdf", "data-pdf-only": "", "data-max-mb": "2", "class": "file-input",
        }),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        validate_pdf(f)  # ekstensi, MIME type, isi berkas (%PDF-), dan ukuran maks. 2 MB
        return f
