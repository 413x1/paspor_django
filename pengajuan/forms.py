from django import forms

from .models import DokumenPakln, DokumenPegawai, DokumenTemplate, DokumenUnor, Pengajuan


class PengajuanForm(forms.ModelForm):
    """Formulir Pengajuan (bagian "Detail Perjalanan" yang diisi manual
    oleh pegawai — data pegawai lainnya ditampilkan read-only dari
    PegawaiProfile)."""

    class Meta:
        model = Pengajuan
        fields = [
            "kategori",
            "maksud",
            "tujuan_negara",
            "sumber_pembiayaan",
            "tgl_berangkat",
            "tgl_kembali",
            "jumlah_hari_kerja",
        ]
        widgets = {
            "kategori": forms.Select(),
            "maksud": forms.Textarea(
                attrs={"rows": 3, "class": "textarea", "placeholder": "Contoh: Menunaikan ibadah umrah bersama keluarga"}
            ),
            "tujuan_negara": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Arab Saudi"}),
            "sumber_pembiayaan": forms.Select(),
            "tgl_berangkat": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "tgl_kembali": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "jumlah_hari_kerja": forms.NumberInput(attrs={"class": "input", "placeholder": "cth. 5"}),
        }

    def __init__(self, *args, profile=None, **kwargs):
        """`profile` (PegawaiProfile pemohon) dipakai untuk memvalidasi
        jumlah hari kerja terhadap sisa cuti tahun berjalan."""
        self.profile = profile
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        berangkat = cleaned.get("tgl_berangkat")
        kembali = cleaned.get("tgl_kembali")
        if berangkat and kembali and kembali < berangkat:
            raise forms.ValidationError("Tanggal kembali tidak boleh sebelum tanggal keberangkatan.")
        return cleaned

    def clean_jumlah_hari_kerja(self):
        hari_kerja = self.cleaned_data.get("jumlah_hari_kerja")
        if hari_kerja is not None and self.profile is not None:
            sisa = self.profile.sisa_cuti_tahun_berjalan
            if hari_kerja > sisa:
                raise forms.ValidationError(
                    f"Jumlah hari kerja ({hari_kerja} hari) melebihi sisa cuti tahun berjalan ({sisa} hari)."
                )
        return hari_kerja


class DokumenPegawaiForm(forms.ModelForm):
    class Meta:
        model = DokumenPegawai
        fields = ["file"]
        widgets = {"file": forms.ClearableFileInput(attrs={"class": "form-control"})}


class DokumenUnorForm(forms.ModelForm):
    class Meta:
        model = DokumenUnor
        fields = ["file"]
        widgets = {"file": forms.ClearableFileInput(attrs={"class": "form-control"})}


class DokumenPaklnForm(forms.ModelForm):
    class Meta:
        model = DokumenPakln
        fields = ["file"]
        widgets = {"file": forms.ClearableFileInput(attrs={"class": "form-control"})}


class DokumenTemplateForm(forms.ModelForm):
    """Form Manajemen Template (Admin Biro PAKLN). Saat mengedit template
    yang sudah punya berkas, `file` opsional — kosongkan untuk
    mempertahankan berkas lama."""

    class Meta:
        model = DokumenTemplate
        fields = [
            "nama", "keterangan", "file",
            "untuk_pegawai", "untuk_admin_unor",
            "unit_organisasi", "kategori", "aktif",
        ]
        widgets = {
            "nama": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Contoh Formulir Izin Luar Negeri"}),
            "keterangan": forms.TextInput(attrs={"class": "input", "placeholder": "Opsional"}),
            "unit_organisasi": forms.CheckboxSelectMultiple(),
        }
        labels = {
            "untuk_pegawai": "Tampilkan untuk Pegawai",
            "untuk_admin_unor": "Tampilkan untuk Admin Unor",
            "unit_organisasi": "Batasi untuk Unit Organisasi tertentu",
            "kategori": "Batasi untuk Kategori Perjalanan tertentu",
            "aktif": "Tampilkan ke Pegawai/Admin Unor",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].required = not (self.instance and self.instance.pk)
        self.fields["unit_organisasi"].required = False
        self.fields["kategori"].required = False
        self.fields["kategori"].choices = [("", "— Semua kategori —")] + list(Pengajuan.Kategori.choices)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("untuk_pegawai") and not cleaned.get("untuk_admin_unor"):
            raise forms.ValidationError(
                "Pilih minimal salah satu target: Pegawai atau Admin Unor."
            )
        return cleaned
