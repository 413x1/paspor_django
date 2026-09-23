import itertools

from django import forms
from django.db import models
from django.forms.models import ModelChoiceIterator

from paspor.models import KategoriPerjalanan, Negara, SumberPembiayaan

from .models import DokumenPakln, DokumenPegawai, DokumenTemplate, DokumenUnor, Pengajuan


class GroupedModelChoiceIterator(ModelChoiceIterator):
    """Seperti ModelChoiceIterator bawaan, tapi mengelompokkan baris
    menjadi <optgroup> berdasarkan `field.group_by(obj)`. Queryset WAJIB
    terurut per hasil `group_by` (grouping hanya berlaku pada baris yang
    berurutan, mengikuti perilaku `itertools.groupby`)."""

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        queryset = self.queryset
        if not queryset._prefetch_related_lookups:
            queryset = queryset.iterator()
        for group, objs in itertools.groupby(queryset, key=self.field.group_by):
            yield (group, [self.choice(obj) for obj in objs])


class GroupedModelChoiceField(forms.ModelChoiceField):
    """ModelChoiceField yang merender <optgroup> (mis. Kategori Perjalanan
    dikelompokkan per Jenis Perjalanan)."""

    iterator = GroupedModelChoiceIterator

    def __init__(self, *args, group_by, **kwargs):
        self.group_by = group_by
        super().__init__(*args, **kwargs)


class PengajuanForm(forms.ModelForm):
    """Formulir Pengajuan (bagian "Detail Perjalanan" yang diisi manual
    oleh pegawai — data pegawai lainnya ditampilkan read-only dari
    PegawaiProfile)."""

    # Field eksplisit (bukan auto-generate dari Meta) supaya bisa memakai
    # GroupedModelChoiceField — dropdown Kategori Perjalanan dikelompokkan
    # per Jenis Perjalanan (<optgroup>). Queryset diisi ulang di __init__.
    kategori = GroupedModelChoiceField(
        queryset=KategoriPerjalanan.objects.none(),
        group_by=lambda obj: obj.get_jenis_perjalanan_display(),
        empty_label="— Pilih Kategori Perjalanan —",
    )

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

        # Formulir ini khusus alur Non-Kedinasan — tawarkan hanya kategori
        # bertipe "Non-Dinas" (dikelompokkan per Jenis Perjalanan; saat ini
        # praktis hanya satu grup terisi sampai alur PDLN dibangun).
        kategori_queryset = KategoriPerjalanan.objects.filter(
            jenis_perjalanan=KategoriPerjalanan.JenisPerjalanan.NON_DINAS, is_active=True,
        )
        if self.instance and self.instance.kategori_id:
            kategori_queryset = KategoriPerjalanan.objects.filter(
                models.Q(jenis_perjalanan=KategoriPerjalanan.JenisPerjalanan.NON_DINAS, is_active=True)
                | models.Q(pk=self.instance.kategori_id)
            )
        self.fields["kategori"].queryset = kategori_queryset
        self.fields["kategori"].required = True

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
        self.fields["kategori"].empty_label = "— Semua kategori —"
        kategori_queryset = KategoriPerjalanan.objects.filter(is_active=True)
        if self.instance and self.instance.kategori_id:
            kategori_queryset = KategoriPerjalanan.objects.filter(
                models.Q(is_active=True) | models.Q(pk=self.instance.kategori_id)
            )
        self.fields["kategori"].queryset = kategori_queryset

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


class KategoriPerjalananForm(forms.ModelForm):
    """Form Manajemen Kategori Perjalanan (Admin Biro PAKLN) — sumber data
    dropdown "Kategori Perjalanan" pada Formulir Pengajuan."""

    class Meta:
        model = KategoriPerjalanan
        fields = ["jenis_perjalanan", "nama_kategori", "is_active"]
        widgets = {
            "jenis_perjalanan": forms.Select(),
            "nama_kategori": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Ibadah"}),
        }
        labels = {"is_active": "Tampilkan pada Formulir Pengajuan"}
