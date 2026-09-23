from django import forms
from django.db import models

from paspor.models import Negara, SumberPembiayaan

from .models import DokumenPakln, DokumenPegawai, DokumenTemplate, DokumenUnor, Pengajuan, PengaturanND


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
            "tujuan_negara": forms.SelectMultiple(
                attrs={"data-multiselect": "Pilih satu atau lebih negara tujuan…"}
            ),
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
        # Sertakan juga negara yang sudah dipilih sebelumnya walau kini
        # dinonaktifkan Admin PKLN, supaya tidak diam-diam hilang saat
        # pegawai membuka ulang formulir & menyimpan tanpa mengubahnya.
        queryset = Negara.objects.filter(is_active=True)
        if self.instance and self.instance.pk:
            selected_ids = self.instance.tujuan_negara.values_list("pk", flat=True)
            queryset = Negara.objects.filter(models.Q(is_active=True) | models.Q(pk__in=selected_ids))
        self.fields["tujuan_negara"].queryset = queryset
        self.fields["tujuan_negara"].required = True

        # Formulir ini khusus alur Non-Kedinasan — tawarkan hanya sumber
        # pembiayaan bertipe "Non-Dinas". Sama seperti tujuan_negara,
        # sertakan pilihan lama yang sudah dinonaktifkan agar tidak hilang.
        sumber_queryset = SumberPembiayaan.objects.filter(
            tipe_perjalanan=SumberPembiayaan.TipePerjalanan.NON_DINAS, is_active=True,
        )
        if self.instance and self.instance.sumber_pembiayaan_id:
            sumber_queryset = SumberPembiayaan.objects.filter(
                models.Q(tipe_perjalanan=SumberPembiayaan.TipePerjalanan.NON_DINAS, is_active=True)
                | models.Q(pk=self.instance.sumber_pembiayaan_id)
            )
        self.fields["sumber_pembiayaan"].queryset = sumber_queryset
        self.fields["sumber_pembiayaan"].required = True

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


class NegaraForm(forms.ModelForm):
    """Form Manajemen Negara (Admin Biro PAKLN) — sumber data dropdown
    multi-select "Tujuan Negara" pada Formulir Pengajuan."""

    class Meta:
        model = Negara
        fields = ["nama_negara", "kode_negara", "is_active"]
        widgets = {
            "nama_negara": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Arab Saudi"}),
            "kode_negara": forms.TextInput(attrs={"class": "input", "placeholder": "cth. SA (opsional)"}),
        }
        labels = {"is_active": "Tampilkan pada Formulir Pengajuan"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kode_negara"].required = False


class SumberPembiayaanForm(forms.ModelForm):
    """Form Manajemen Sumber Pembiayaan (Admin Biro PAKLN) — sumber data
    dropdown "Sumber Pembiayaan" pada Formulir Pengajuan."""

    class Meta:
        model = SumberPembiayaan
        fields = ["tipe_perjalanan", "nama", "keterangan", "is_active"]
        widgets = {
            "tipe_perjalanan": forms.Select(),
            "nama": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Biaya Sendiri"}),
            "keterangan": forms.Textarea(attrs={"rows": 2, "class": "textarea", "placeholder": "Opsional"}),
        }
        labels = {"is_active": "Tampilkan pada Formulir Pengajuan"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["keterangan"].required = False


class PengaturanNDForm(forms.ModelForm):
    """Form Pengaturan Nota Dinas (Admin Biro PAKLN) — nilai pejabat
    penandatangan/paraf yang dipakai saat mengisi template ND."""

    class Meta:
        model = PengaturanND
        fields = [
            "jabatan_plt_kabag_kln",
            "nama_pejabat_plt_kabag_kln",
            "paraf_ketua_tim_aki",
            "nama_karo_pakln",
            "paraf_katim_aki_nd2",
            "paraf_plt_kabag_kln_nd2",
        ]
        widgets = {
            "jabatan_plt_kabag_kln": forms.TextInput(attrs={"class": "input"}),
            "nama_pejabat_plt_kabag_kln": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Budi Santoso"}),
            "paraf_ketua_tim_aki": forms.TextInput(attrs={"class": "input"}),
            "nama_karo_pakln": forms.TextInput(attrs={"class": "input"}),
            "paraf_katim_aki_nd2": forms.TextInput(attrs={"class": "input"}),
            "paraf_plt_kabag_kln_nd2": forms.TextInput(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nama_pejabat_plt_kabag_kln"].required = False
