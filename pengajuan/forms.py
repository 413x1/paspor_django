import itertools
from datetime import timedelta

from django import forms
from django.core.validators import FileExtensionValidator
from django.db import models
from django.forms.models import ModelChoiceIterator

from paspor.kalender import AKHIR_PEKAN, hitung_hari_kerja
from paspor.models import HariLibur, KategoriPerjalanan, Negara, SumberPembiayaan, berlaku_untuk_tipe

from .models import (
    DetailPdln, DokumenBpsdm, DokumenPakln, DokumenPegawai, DokumenTemplate, DokumenUnor, Pengajuan,
    PengaturanDokumen,
)

TIPE_PDLN_CHOICES = Pengajuan.TipePdln.choices


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
        ]
        widgets = {
            "maksud": forms.Textarea(
                attrs={"rows": 3, "class": "textarea", "placeholder": "Contoh: Menunaikan ibadah umrah bersama keluarga"}
            ),
            "tujuan_negara": forms.SelectMultiple(
                attrs={"data-multiselect": "Pilih satu atau lebih negara tujuan…"}
            ),
            "sumber_pembiayaan": forms.Select(),
            "tgl_berangkat": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
            "tgl_kembali": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
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
        """Jumlah hari kerja selalu dihitung ulang di server dari tanggal &
        kalender libur (nilai kiriman browser tidak dipercaya), lalu
        divalidasi terhadap sisa cuti tahun berjalan."""
        cleaned = super().clean()
        berangkat = cleaned.get("tgl_berangkat")
        kembali = cleaned.get("tgl_kembali")
        if berangkat and kembali and kembali < berangkat:
            raise forms.ValidationError("Tanggal kembali tidak boleh sebelum tanggal keberangkatan.")

        hari_kerja = hitung_hari_kerja(berangkat, kembali)
        self.instance.jumlah_hari_kerja = hari_kerja
        if hari_kerja is not None and self.profile is not None:
            sisa = self.profile.sisa_cuti_tahun_berjalan
            if hari_kerja > sisa:
                raise forms.ValidationError(
                    f"Jumlah hari kerja ({hari_kerja} hari) melebihi sisa cuti tahun berjalan ({sisa} hari)."
                )
        return cleaned


def _filter_tipe(queryset, tipe, terpilih_id=None):
    """Saring master Kategori/Sumber PDLN yang berlaku untuk `tipe`
    (field JSON list — disaring di Python agar portabel lintas DB), tetap
    sertakan pilihan lama yang sudah terpilih."""
    ids = [obj.pk for obj in queryset if berlaku_untuk_tipe(obj, tipe) or obj.pk == terpilih_id]
    return queryset.model.objects.filter(pk__in=ids)


class PdlnForm(forms.ModelForm):
    """Formulir Pengajuan PDLN — field umum di `Pengajuan`, field khusus
    tipe di `DetailPdln` (BISNIS_PROSES_PDLN.MD §5). Tidak ada validasi
    sisa cuti (perjalanan dinas)."""

    # Field per tipe: (nama field, label, berlaku untuk tipe)
    FIELD_TIPE = {
        "penyelenggara": ("T1", "T3", "T2L"),
        "perguruan_tinggi": ("T2P",),
        "beasiswa": ("T2P", "T2L"),
    }
    LABEL_KEGIATAN = {
        "T1": ("Tgl Mulai Agenda (sesuai Undangan)", "Tgl Selesai Agenda (sesuai Undangan)"),
        "T3": ("Tgl Mulai Agenda (sesuai Undangan)", "Tgl Selesai Agenda (sesuai Undangan)"),
        "T2P": ("Tgl Mulai Perkuliahan", "Tgl Selesai Perkuliahan"),
        "T2L": ("Tgl Mulai Pelatihan", "Tgl Selesai Pelatihan"),
    }

    kategori = forms.ModelChoiceField(
        queryset=KategoriPerjalanan.objects.none(), empty_label="— Pilih Kategori —",
    )
    beasiswa = forms.ChoiceField(label="Nama Beasiswa (Aplikasi PINTAR)", required=False)
    penyelenggara = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "cth. ASEAN Secretariat"}),
    )
    perguruan_tinggi = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "cth. Delft University of Technology"}),
    )
    kota_tujuan = forms.CharField(
        max_length=150, widget=forms.TextInput(attrs={"class": "input", "placeholder": "cth. Jenewa"}),
    )
    tgl_mulai_kegiatan = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
    )
    tgl_selesai_kegiatan = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
    )
    pernyataan_benar = forms.BooleanField(
        label="Saya menyatakan data dan formulir yang diisi telah benar.",
        error_messages={"required": "Centang pernyataan kebenaran pengisian formulir."},
    )

    class Meta:
        model = Pengajuan
        fields = ["kategori", "tujuan_negara", "sumber_pembiayaan", "tgl_berangkat", "tgl_kembali"]
        widgets = {
            "tujuan_negara": forms.SelectMultiple(
                attrs={"data-multiselect": "Pilih satu atau lebih negara tujuan…"}
            ),
            "tgl_berangkat": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
            "tgl_kembali": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
        }
        labels = {"tgl_kembali": "Tanggal Kepulangan", "tgl_berangkat": "Tanggal Keberangkatan"}

    def __init__(self, *args, tipe, pencalonan=(), **kwargs):
        self.tipe = tipe
        self.pencalonan = {p.id: p for p in pencalonan}
        super().__init__(*args, **kwargs)
        instance = self.instance
        detail = instance.detail if instance.pk else None

        negara = Negara.objects.filter(is_active=True)
        if instance.pk:
            selected = instance.tujuan_negara.values_list("pk", flat=True)
            negara = Negara.objects.filter(models.Q(is_active=True) | models.Q(pk__in=selected))
        self.fields["tujuan_negara"].queryset = negara
        self.fields["tujuan_negara"].required = True

        kategori = KategoriPerjalanan.objects.filter(
            jenis_perjalanan=KategoriPerjalanan.JenisPerjalanan.PDLN, is_active=True,
        )
        if instance.kategori_id:
            kategori = KategoriPerjalanan.objects.filter(
                models.Q(jenis_perjalanan=KategoriPerjalanan.JenisPerjalanan.PDLN, is_active=True)
                | models.Q(pk=instance.kategori_id)
            )
        self.fields["kategori"].queryset = _filter_tipe(kategori, tipe, instance.kategori_id)

        sumber = SumberPembiayaan.objects.filter(
            tipe_perjalanan=SumberPembiayaan.TipePerjalanan.PDLN, is_active=True,
        )
        if instance.sumber_pembiayaan_id:
            sumber = SumberPembiayaan.objects.filter(
                models.Q(tipe_perjalanan=SumberPembiayaan.TipePerjalanan.PDLN, is_active=True)
                | models.Q(pk=instance.sumber_pembiayaan_id)
            )
        self.fields["sumber_pembiayaan"].queryset = _filter_tipe(sumber, tipe, instance.sumber_pembiayaan_id)
        self.fields["sumber_pembiayaan"].required = True
        self.fields["tgl_berangkat"].required = True
        self.fields["tgl_kembali"].required = True

        pilihan = [("", "— Pilih beasiswa —")] + [(p.id, p.label) for p in pencalonan]
        if detail and detail.beasiswa_pintar_id and detail.beasiswa_pintar_id not in self.pencalonan:
            pilihan.append((detail.beasiswa_pintar_id, detail.beasiswa_nama))
        self.fields["beasiswa"].choices = pilihan

        mulai, selesai = self.LABEL_KEGIATAN.get(tipe, ("Tgl Mulai Kegiatan", "Tgl Selesai Kegiatan"))
        self.fields["tgl_mulai_kegiatan"].label = mulai
        self.fields["tgl_selesai_kegiatan"].label = selesai

        for nama, tipe_berlaku in self.FIELD_TIPE.items():
            if tipe not in tipe_berlaku:
                del self.fields[nama]
            else:
                self.fields[nama].required = True
        if "beasiswa" in self.fields:
            self.fields["beasiswa"].error_messages["required"] = "Pilih beasiswa dari Aplikasi PINTAR."

        if detail and not self.is_bound:
            for nama in ("penyelenggara", "perguruan_tinggi", "kota_tujuan",
                         "tgl_mulai_kegiatan", "tgl_selesai_kegiatan", "pernyataan_benar"):
                if nama in self.fields:
                    self.initial[nama] = getattr(detail, nama)
            if "beasiswa" in self.fields:
                self.initial["beasiswa"] = detail.beasiswa_pintar_id

    def clean(self):
        cleaned = super().clean()
        berangkat, kembali = cleaned.get("tgl_berangkat"), cleaned.get("tgl_kembali")
        mulai, selesai = cleaned.get("tgl_mulai_kegiatan"), cleaned.get("tgl_selesai_kegiatan")
        if berangkat and kembali and kembali < berangkat:
            self.add_error("tgl_kembali", "Tanggal kepulangan tidak boleh sebelum tanggal keberangkatan.")
        if mulai and selesai and selesai < mulai:
            self.add_error("tgl_selesai_kegiatan", "Tanggal selesai tidak boleh sebelum tanggal mulai.")
        if berangkat and kembali and mulai and selesai and (mulai < berangkat or selesai > kembali):
            raise forms.ValidationError(
                "Periode kegiatan harus berada di dalam periode perjalanan (tanggal keberangkatan s.d. kepulangan)."
            )
        self.instance.jumlah_hari_kerja = hitung_hari_kerja(berangkat, kembali)
        return cleaned

    def save_detail(self, pengajuan):
        data = self.cleaned_data
        detail, _ = DetailPdln.objects.get_or_create(pengajuan=pengajuan)
        detail.kota_tujuan = data["kota_tujuan"]
        detail.tgl_mulai_kegiatan = data["tgl_mulai_kegiatan"]
        detail.tgl_selesai_kegiatan = data["tgl_selesai_kegiatan"]
        detail.pernyataan_benar = data["pernyataan_benar"]
        detail.penyelenggara = data.get("penyelenggara", "")
        detail.perguruan_tinggi = data.get("perguruan_tinggi", "")
        if "beasiswa" in self.fields:
            pilih = data.get("beasiswa", "")
            calon = self.pencalonan.get(pilih)
            detail.beasiswa_pintar_id = pilih
            if calon:
                detail.beasiswa_nama = calon.label[:255]
        detail.save()
        return detail


class DokumenPegawaiForm(forms.ModelForm):
    class Meta:
        model = DokumenPegawai
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenUnorForm(forms.ModelForm):
    class Meta:
        model = DokumenUnor
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenBpsdmForm(forms.ModelForm):
    class Meta:
        model = DokumenBpsdm
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenPaklnForm(forms.ModelForm):
    class Meta:
        model = DokumenPakln
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenTemplateForm(forms.ModelForm):
    """Form Manajemen Template (Admin Biro PAKLN). Saat mengedit template
    yang sudah punya berkas, `file` opsional — kosongkan untuk
    mempertahankan berkas lama."""

    class Meta:
        model = DokumenTemplate
        fields = [
            "nama", "keterangan", "file",
            "untuk_pegawai", "untuk_admin_unor", "untuk_admin_bpsdm",
            "jenis_perjalanan", "unit_organisasi", "kategori", "aktif",
        ]
        widgets = {
            "nama": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Contoh Formulir Izin Luar Negeri"}),
            "keterangan": forms.TextInput(attrs={"class": "input", "placeholder": "Opsional"}),
            "unit_organisasi": forms.CheckboxSelectMultiple(),
        }
        labels = {
            "untuk_pegawai": "Tampilkan untuk Pegawai",
            "untuk_admin_unor": "Tampilkan untuk Admin Unor",
            "untuk_admin_bpsdm": "Tampilkan untuk Admin BPSDM",
            "jenis_perjalanan": "Batasi untuk Jenis Perjalanan tertentu",
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
        if not (cleaned.get("untuk_pegawai") or cleaned.get("untuk_admin_unor") or cleaned.get("untuk_admin_bpsdm")):
            raise forms.ValidationError(
                "Pilih minimal salah satu target: Pegawai, Admin Unor, atau Admin BPSDM."
            )
        return cleaned


class NegaraForm(forms.ModelForm):
    """Form Manajemen Negara (Admin Biro PAKLN) — sumber data dropdown
    multi-select "Tujuan Negara" pada Formulir Pengajuan."""

    class Meta:
        model = Negara
        fields = ["nama_negara", "kode_negara", "is_active", "perlu_visa"]
        widgets = {
            "nama_negara": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Arab Saudi"}),
            "kode_negara": forms.TextInput(attrs={"class": "input", "placeholder": "cth. SA (opsional)"}),
        }
        labels = {
            "is_active": "Tampilkan pada Formulir Pengajuan",
            "perlu_visa": "Memerlukan visa (Rekomendasi Visa wajib pada PDLN)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kode_negara"].required = False


class TambahHariLiburForm(forms.Form):
    """Form tambah Setting Kalender (Admin Biro PAKLN). Jika `tanggal_selesai`
    diisi, satu baris `HariLibur` dibuat per tanggal dalam rentang (lihat
    `simpan`)."""

    MAKS_RENTANG = 31

    tanggal = forms.DateField(
        label="Tanggal Mulai", widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )
    tanggal_selesai = forms.DateField(
        label="Tanggal Selesai", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
        help_text="Opsional — isi untuk libur beberapa hari berturut-turut (maks. 31 hari).",
    )
    keterangan = forms.CharField(
        label="Keterangan", max_length=150,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "cth. Hari Kemerdekaan RI"}),
    )
    jenis = forms.ChoiceField(label="Jenis", choices=HariLibur.Jenis.choices)
    lewati_akhir_pekan = forms.BooleanField(
        label="Lewati Sabtu & Minggu dalam rentang", required=False, initial=True,
    )

    def clean(self):
        cleaned = super().clean()
        mulai = cleaned.get("tanggal")
        selesai = cleaned.get("tanggal_selesai")
        if mulai and selesai:
            if selesai < mulai:
                self.add_error("tanggal_selesai", "Tanggal selesai tidak boleh sebelum tanggal mulai.")
            elif (selesai - mulai).days + 1 > self.MAKS_RENTANG:
                self.add_error("tanggal_selesai", f"Rentang maksimal {self.MAKS_RENTANG} hari per input.")
        return cleaned

    def daftar_tanggal(self):
        mulai = self.cleaned_data["tanggal"]
        selesai = self.cleaned_data.get("tanggal_selesai") or mulai
        rentang = selesai != mulai
        tanggal_list = []
        for i in range((selesai - mulai).days + 1):
            d = mulai + timedelta(days=i)
            if rentang and self.cleaned_data.get("lewati_akhir_pekan") and d.weekday() in AKHIR_PEKAN:
                continue
            tanggal_list.append(d)
        return tanggal_list


class ImporHariLiburForm(forms.Form):
    """Form impor Setting Kalender dari Excel/CSV (lihat `paspor.impor_libur`)."""

    MAKS_UKURAN = 2 * 1024 * 1024

    berkas = forms.FileField(
        label="Berkas Excel",
        validators=[FileExtensionValidator(allowed_extensions=["xlsx", "csv"])],
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx,.csv"}),
        help_text="Format .xlsx (atau .csv), maks. 2 MB, kolom: tanggal, keterangan, jenis.",
    )
    timpa = forms.BooleanField(
        label="Timpa keterangan & jenis untuk tanggal yang sudah ada", required=False,
    )

    def clean_berkas(self):
        berkas = self.cleaned_data["berkas"]
        if berkas.size > self.MAKS_UKURAN:
            raise forms.ValidationError("Ukuran berkas maksimal 2 MB.")
        return berkas


class HariLiburForm(forms.ModelForm):
    """Form edit satu tanggal pada Setting Kalender (Admin Biro PAKLN)."""

    class Meta:
        model = HariLibur
        fields = ["tanggal", "keterangan", "jenis", "is_active"]
        widgets = {
            "tanggal": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
            "keterangan": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Hari Kemerdekaan RI"}),
        }
        labels = {"is_active": "Aktif (dihitung sebagai bukan hari kerja)"}


class _TipePdlnMixin:
    """Field multi-checkbox "Berlaku untuk Tipe PDLN" (JSON list di model);
    kosong = semua tipe. Hanya relevan bila jenis/tipe perjalanan = PDLN."""

    def _init_tipe_pdln(self):
        self.fields["tipe_pdln"] = forms.MultipleChoiceField(
            choices=TIPE_PDLN_CHOICES, required=False, widget=forms.CheckboxSelectMultiple(),
            label="Berlaku untuk Tipe PDLN",
            help_text="Hanya untuk PDLN. Kosongkan agar berlaku untuk semua tipe PDLN.",
            initial=self.instance.tipe_pdln if self.instance and self.instance.pk else [],
        )

    def clean_tipe_pdln(self):
        return list(self.cleaned_data.get("tipe_pdln") or [])


class SumberPembiayaanForm(_TipePdlnMixin, forms.ModelForm):
    """Form Manajemen Sumber Pembiayaan (Admin Biro PAKLN) — sumber data
    dropdown "Sumber Pembiayaan" pada Formulir Pengajuan."""

    class Meta:
        model = SumberPembiayaan
        fields = ["tipe_perjalanan", "nama", "tipe_pdln", "keterangan", "is_active"]
        widgets = {
            "tipe_perjalanan": forms.Select(),
            "nama": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Biaya Sendiri"}),
            "keterangan": forms.Textarea(attrs={"rows": 2, "class": "textarea", "placeholder": "Opsional"}),
        }
        labels = {"is_active": "Tampilkan pada Formulir Pengajuan"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["keterangan"].required = False
        self._init_tipe_pdln()


class PengaturanDokumenForm(forms.ModelForm):
    """Form menu "Setting" (Admin Biro PAKLN) — default "Jabatan Pejabat
    Penandatangan" & "Nama Pejabat" untuk form Generate ND Kabag & ND Karo
    (dua pejabat penandatangan yang berbeda, field terpisah)."""

    class Meta:
        model = PengaturanDokumen
        fields = [
            "jabatan_penandatangan_kabag", "nama_pejabat_kabag",
            "jabatan_penandatangan_karo", "nama_pejabat_karo",
        ]
        widgets = {
            "jabatan_penandatangan_kabag": forms.TextInput(
                attrs={"class": "input", "placeholder": "cth. Plt. Kepala Bagian Kerja Sama Luar Negeri"}
            ),
            "nama_pejabat_kabag": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Muhammad Faris Al Bassam, S.E."}),
            "jabatan_penandatangan_karo": forms.TextInput(
                attrs={"class": "input", "placeholder": "cth. Kepala Biro Perencanaan Anggaran dan Kerja Sama Luar Negeri"}
            ),
            "nama_pejabat_karo": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Reiza Setiawan"}),
        }


class KategoriPerjalananForm(_TipePdlnMixin, forms.ModelForm):
    """Form Manajemen Kategori Perjalanan (Admin Biro PAKLN) — sumber data
    dropdown "Kategori Perjalanan" pada Formulir Pengajuan."""

    class Meta:
        model = KategoriPerjalanan
        fields = ["jenis_perjalanan", "nama_kategori", "tipe_pdln", "is_active"]
        widgets = {
            "jenis_perjalanan": forms.Select(),
            "nama_kategori": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Ibadah"}),
        }
        labels = {"is_active": "Tampilkan pada Formulir Pengajuan"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_tipe_pdln()
