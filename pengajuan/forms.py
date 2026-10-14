import itertools
import re
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.core.validators import FileExtensionValidator
from django.db import models
from django.forms.models import BaseInlineFormSet, ModelChoiceIterator, inlineformset_factory
from django.utils import timezone

from paspor.kalender import AKHIR_PEKAN, hitung_hari_kerja
from paspor.validators import MAKS_UKURAN, PDF_ACCEPT, validate_pdf, validate_pdf_laporan, validate_ukuran
from paspor.models import (
    TIPE_KEGIATAN_BPSDM, DasarKegiatan, HariLibur, KategoriPerjalanan, Kegiatan, Negara, SumberPembiayaan,
    berlaku_untuk_tipe, kategori_pendidikan, kategori_untuk_bpsdm,
)

from .models import (
    DetailPdln, DokumenBko, DokumenBpsdm, DokumenPakln, DokumenPegawai, DokumenTemplate, DokumenUnor, Pengajuan,
    LaporanPdln, PengaturanDokumen,
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
            raise forms.ValidationError("Tanggal kembali tidak boleh sebelum tanggal keberangkatan")

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
    """Formulir Pengajuan PDLN — field umum di `Pengajuan`; data kegiatan
    (penyelenggara/universitas, negara, kota, periode kegiatan) diambil dari
    objek Kegiatan yang dipilih dan di-snapshot ke `DetailPdln`
    (EVENT_IMPLEMENTATION_PLAN.MD §5.3, §7.4). Tidak ada validasi sisa cuti
    (perjalanan dinas).

    Kegiatan boleh kosong selama draft (mis. usulan kegiatan masih menunggu
    persetujuan) — pengiriman ke Admin Unor menolaknya (aturan B1)."""

    LABEL_KEGIATAN = {
        "T1": ("Tgl Mulai Agenda", "Tgl Selesai Agenda"),
        "T3": ("Tgl Mulai Agenda", "Tgl Selesai Agenda"),
        "T2P": ("Tgl Mulai Perkuliahan", "Tgl Selesai Perkuliahan"),
        "T2L": ("Tgl Mulai Pelatihan", "Tgl Selesai Pelatihan"),
    }

    kategori = forms.ModelChoiceField(
        queryset=KategoriPerjalanan.objects.none(), empty_label="— Pilih Kategori —",
    )
    kegiatan = forms.ModelChoiceField(
        queryset=Kegiatan.objects.none(), required=False, empty_label="— Pilih Kegiatan —",
    )
    pernyataan_benar = forms.BooleanField(
        label="Saya menyatakan data dan formulir yang diisi telah benar.",
        error_messages={"required": "Centang pernyataan kebenaran pengisian formulir."},
    )

    class Meta:
        model = Pengajuan
        fields = ["kategori", "kegiatan", "tujuan_negara", "sumber_pembiayaan", "tgl_berangkat", "tgl_kembali"]
        widgets = {
            "tujuan_negara": forms.SelectMultiple(
                attrs={"data-multiselect": "Pilih satu atau lebih negara tujuan…"}
            ),
            "tgl_berangkat": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
            "tgl_kembali": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
        }
        labels = {"tgl_kembali": "Tanggal Kepulangan", "tgl_berangkat": "Tanggal Keberangkatan"}

    def __init__(self, *args, tipe, **kwargs):
        self.tipe = tipe
        super().__init__(*args, **kwargs)
        instance = self.instance
        detail = instance.detail if instance.pk else None

        negara = Negara.objects.filter(is_active=True)
        if instance.pk:
            selected = instance.tujuan_negara.values_list("pk", flat=True)
            negara = Negara.objects.filter(models.Q(is_active=True) | models.Q(pk__in=selected))
        self.fields["tujuan_negara"].queryset = negara
        # Wajib setelah negara kegiatan ditambahkan otomatis (lihat clean).
        self.fields["tujuan_negara"].required = False

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

        # Kegiatan yang dapat dipilih (B2, B14) + kegiatan yang sudah
        # terpilih sebelumnya walau kini nonaktif/lewat, agar tidak hilang.
        ids = list(Kegiatan.objects.dapat_dipilih(tipe=tipe).values_list("pk", flat=True))
        if instance.kegiatan_id:
            ids.append(instance.kegiatan_id)
        self.kegiatan_qs = (
            Kegiatan.objects.filter(pk__in=ids)
            .prefetch_related("kategori", "skema_pendanaan", "negara").order_by("tgl_mulai", "nama")
        )
        self.fields["kegiatan"].queryset = self.kegiatan_qs
        self.fields["kegiatan"].label_from_instance = lambda k: k.label_opsi

        if detail and not self.is_bound:
            self.initial["pernyataan_benar"] = detail.pernyataan_benar

    @property
    def label_mulai_selesai(self):
        return self.LABEL_KEGIATAN.get(self.tipe, ("Tgl Mulai Kegiatan", "Tgl Selesai Kegiatan"))

    @property
    def label_penyelenggara(self):
        return "Universitas" if self.tipe == "T2P" else "Penyelenggara"

    def opsi_kegiatan(self):
        """Data per kegiatan untuk isian otomatis & penyaringan di browser
        (dirender lewat `json_script`)."""
        return {
            str(k.pk): {
                "kategori": [x.pk for x in k.kategori.all()],
                "skema": [x.pk for x in k.skema_pendanaan.all()],
                "negara": [x.pk for x in k.negara.all()],
                "negara_nama": k.negara_display,
                "penyelenggara": k.penyelenggara,
                "kota": k.kota,
                "mulai": k.tgl_mulai.isoformat(),
                "selesai": k.tgl_selesai.isoformat(),
                "periode": f"{k.tgl_mulai:%d %b %Y} – {k.tgl_selesai:%d %b %Y}",
                "tahun": k.tahun_pelaksanaan,
            }
            for k in self.kegiatan_qs
        }

    def clean(self):
        cleaned = super().clean()
        berangkat, kembali = cleaned.get("tgl_berangkat"), cleaned.get("tgl_kembali")
        kegiatan = cleaned.get("kegiatan")
        kategori = cleaned.get("kategori")
        sumber = cleaned.get("sumber_pembiayaan")
        if berangkat and kembali and kembali < berangkat:
            self.add_error("tgl_kembali", "Tanggal kepulangan tidak boleh sebelum tanggal keberangkatan.")

        negara = list(cleaned.get("tujuan_negara") or [])
        if kegiatan:
            if kategori and not kegiatan.kategori.filter(pk=kategori.pk).exists():
                self.add_error("kegiatan", "Kegiatan ini tidak tersedia untuk kategori yang dipilih.")
            if sumber and not kegiatan.skema_pendanaan.filter(pk=sumber.pk).exists():
                self.add_error("sumber_pembiayaan", "Sumber pembiayaan harus salah satu skema pendanaan kegiatan.")
            # B7: semua negara kegiatan otomatis menjadi negara tujuan.
            ada = {n.pk for n in negara}
            negara += [n for n in kegiatan.negara.all() if n.pk not in ada]
            cleaned["tujuan_negara"] = negara
            if berangkat and kembali and (kegiatan.tgl_mulai < berangkat or kegiatan.tgl_selesai > kembali):
                self.add_error(None, (
                    f"Periode kegiatan ({kegiatan.tgl_mulai:%d %b %Y} – {kegiatan.tgl_selesai:%d %b %Y}) harus "
                    "berada di dalam periode perjalanan (tanggal keberangkatan s.d. kepulangan)."
                ))
        if not negara:
            self.add_error("tujuan_negara", "Pilih minimal satu negara tujuan.")
        self.instance.jumlah_hari_kerja = hitung_hari_kerja(berangkat, kembali)
        return cleaned

    def save_detail(self, pengajuan):
        from .kegiatan import snapshot

        detail, _ = DetailPdln.objects.get_or_create(pengajuan=pengajuan)
        detail.pernyataan_benar = self.cleaned_data["pernyataan_benar"]
        detail.save(update_fields=["pernyataan_benar"])
        snapshot(pengajuan)
        return detail


class PdfOnlyMixin:
    """Berkas dokumen pengajuan hanya boleh PDF: validasi di server (ekstensi, MIME type,
    dan isi berkas) plus atribut `accept` agar dialog pilih-berkas hanya menawarkan PDF.
    Validator hanya berjalan untuk berkas yang BARU diunggah, bukan berkas lama."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].validators.append(validate_pdf)  # PDF, maks. 2 MB
        self.fields["file"].widget.attrs["accept"] = PDF_ACCEPT
        self.fields["file"].widget.attrs["data-max-mb"] = "2"


class TanggalSuratMixin:
    """Tanggal Surat tidak boleh melewati hari ini. Batas `max` pada widget
    diisi di __init__ (bukan di deklarasi class) supaya selalu hari ini,
    bukan tanggal saat server dinyalakan."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tanggal_surat"].widget.attrs["max"] = timezone.localdate().isoformat()

    def clean_tanggal_surat(self):
        tanggal = self.cleaned_data.get("tanggal_surat")
        if tanggal and tanggal > timezone.localdate():
            raise forms.ValidationError("Tanggal surat tidak boleh melebihi hari ini")
        return tanggal


class DokumenPegawaiForm(PdfOnlyMixin, TanggalSuratMixin, forms.ModelForm):
    class Meta:
        model = DokumenPegawai
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenUnorForm(PdfOnlyMixin, TanggalSuratMixin, forms.ModelForm):
    class Meta:
        model = DokumenUnor
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenBpsdmForm(PdfOnlyMixin, TanggalSuratMixin, forms.ModelForm):
    class Meta:
        model = DokumenBpsdm
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenBkoForm(PdfOnlyMixin, TanggalSuratMixin, forms.ModelForm):
    class Meta:
        model = DokumenBko
        fields = ["file", "tanggal_surat"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "tanggal_surat": forms.DateInput(attrs={"type": "date"}),
        }


class DokumenPaklnForm(PdfOnlyMixin, TanggalSuratMixin, forms.ModelForm):
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
            "file": forms.FileInput(attrs={"class": "file-input", "accept": ".pdf,.docx", "data-max-mb": "2"}),
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

    def clean_file(self):
        berkas = self.cleaned_data.get("file")
        # Hanya berkas yang baru diunggah (punya `content_type`), bukan berkas lama.
        if berkas and hasattr(berkas, "content_type"):
            validate_ukuran(berkas)  # maks. 2 MB
        return berkas

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

    MAKS_UKURAN = MAKS_UKURAN  # 2 MB, sama dengan unggahan lain (paspor.validators)

    berkas = forms.FileField(
        label="Berkas Excel",
        validators=[FileExtensionValidator(allowed_extensions=["xlsx", "csv"])],
        widget=forms.FileInput(attrs={"accept": ".xlsx,.csv", "class": "file-input", "data-max-mb": "2"}),
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


class LaporanPdlnForm(forms.ModelForm):
    """Formulir Pelaporan PDLN oleh Pegawai (Bagian B: uraian, Bagian C: biaya dan dokumen).

    Dua tombol di halaman: "Simpan" (draft, isian boleh kosong) dan "Laporkan" (kirim ke Biro
    PAKLN, `kirim=True`). Pada "Laporkan" SEMUA isian wajib terisi: keempat uraian, estimasi dan
    realisasi biaya, serta dokumen laporan; bila laporan sebelumnya dikembalikan
    (`perlu_catatan=True`), catatan perbaikan juga wajib.

    Estimasi/realisasi biaya diketik berformat Rupiah ("10.000.000"); karakter non-angka dibuang
    di server (`clean_*`) sebelum disimpan sebagai angka bulat.
    """

    URAIAN = ("tujuan_kegiatan", "materi_kegiatan", "tindak_lanjut", "dampak_rekomendasi")
    BIAYA_MAKS_DIGIT = 15

    estimasi_biaya = forms.CharField(
        required=False, label="Estimasi Biaya",
        widget=forms.TextInput(attrs={
            "class": "input input-rupiah", "inputmode": "numeric", "autocomplete": "off", "placeholder": "Biaya Estimasi",
        }),
    )
    realisasi_biaya = forms.CharField(
        required=False, label="Realisasi Biaya",
        widget=forms.TextInput(attrs={
            "class": "input input-rupiah", "inputmode": "numeric", "autocomplete": "off", "placeholder": "Biaya Realisasi",
        }),
    )
    dokumen_laporan = forms.FileField(
        required=False, label="Dokumen Laporan Kegiatan", validators=[validate_pdf_laporan],  # PDF, maks. 10 MB
        widget=forms.ClearableFileInput(attrs={
            "accept": PDF_ACCEPT, "data-pdf-only": "", "data-max-mb": "10", "class": "file-input",
        }),
    )
    catatan_perbaikan = forms.CharField(
        required=False, label="Catatan perbaikan untuk Biro PAKLN",
        widget=forms.Textarea(attrs={"class": "textarea", "rows": 3}),
    )

    class Meta:
        model = LaporanPdln
        fields = ["tujuan_kegiatan", "materi_kegiatan", "tindak_lanjut", "dampak_rekomendasi"]
        widgets = {nama: forms.Textarea(attrs={"class": "textarea", "rows": 4}) for nama in (
            "tujuan_kegiatan", "materi_kegiatan", "tindak_lanjut", "dampak_rekomendasi",
        )}

    def __init__(self, *args, kirim=False, perlu_catatan=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.kirim = kirim
        self.perlu_catatan = perlu_catatan
        self._berkas_lama = ""
        if not perlu_catatan:
            del self.fields["catatan_perbaikan"]
        if self.instance.pk and not self.is_bound:
            for nama in ("estimasi_biaya", "realisasi_biaya"):
                nilai = getattr(self.instance, nama)
                if nilai is not None:
                    self.initial[nama] = format_rupiah(nilai)

    # --- Biaya: "10.000.000" -> 10000000 ---------------------------------
    @classmethod
    def _angka(cls, mentah):
        # Rupiah utuh: bagian setelah koma desimal (bila ada) diabaikan; sisanya hanya digit.
        digit = re.sub(r"\D", "", (mentah or "").split(",")[0])
        if not digit:
            return None
        if len(digit) > cls.BIAYA_MAKS_DIGIT:
            raise forms.ValidationError("Nilai biaya terlalu besar.")
        return Decimal(digit)

    def clean_estimasi_biaya(self):
        return self._angka(self.cleaned_data.get("estimasi_biaya"))

    def clean_realisasi_biaya(self):
        return self._angka(self.cleaned_data.get("realisasi_biaya"))

    def clean(self):
        cleaned = super().clean()
        if self.kirim:
            for nama in self.URAIAN:
                if not (cleaned.get(nama) or "").strip() and nama not in self.errors:
                    self.add_error(nama, "Wajib diisi untuk melaporkan.")
            for nama in ("estimasi_biaya", "realisasi_biaya"):
                # Nilai 0 sah (mis. realisasi nol); yang ditolak hanya kolom yang dikosongkan.
                if cleaned.get(nama) is None and nama not in self.errors:
                    self.add_error(nama, "Wajib diisi untuk melaporkan.")
            if not cleaned.get("dokumen_laporan") and not self.instance.file and "dokumen_laporan" not in self.errors:
                self.add_error("dokumen_laporan", "Dokumen laporan wajib diunggah untuk melaporkan.")
            if self.perlu_catatan and not (cleaned.get("catatan_perbaikan") or "").strip():
                self.add_error("catatan_perbaikan", "Isi catatan perbaikan untuk Biro PAKLN sebelum melaporkan ulang.")
        return cleaned

    def save(self, commit=True):
        """Terapkan isian ke instance. Berkas lama (bila diganti) dicatat di `_berkas_lama`
        dan dihapus lewat `bersihkan_berkas_lama()` SETELAH instance tersimpan."""
        laporan = super().save(commit=False)
        laporan.estimasi_biaya = self.cleaned_data.get("estimasi_biaya")
        laporan.realisasi_biaya = self.cleaned_data.get("realisasi_biaya")
        baru = self.cleaned_data.get("dokumen_laporan")
        if baru:
            self._berkas_lama = laporan.file.name if laporan.file else ""
            laporan.file = baru
        if commit:
            laporan.save()
            self.bersihkan_berkas_lama(laporan)
        return laporan

    def bersihkan_berkas_lama(self, laporan):
        if self._berkas_lama and self._berkas_lama != laporan.file.name:
            laporan.file.storage.delete(self._berkas_lama)
        self._berkas_lama = ""


def format_rupiah(nilai):
    """10000000 -> '10.000.000' (tanpa awalan Rp)."""
    return f"{int(nilai):,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Kegiatan PDLN (wiki/instructions/EVENT_IMPLEMENTATION_PLAN.MD §7–§8)
# ---------------------------------------------------------------------------

class KegiatanForm(forms.ModelForm):
    """Tambah/sunting Kegiatan — dipakai Admin Biro PAKLN, Admin BPSDM
    (`peran="admin_bpsdm"`: kategori hanya pendidikan/pelatihan, B10a), dan
    Pegawai saat mengusulkan. `kode_pintar` hanya untuk Admin Biro PAKLN."""

    class Meta:
        model = Kegiatan
        fields = [
            "nama", "deskripsi", "negara", "kota", "penyelenggara", "tgl_mulai", "tgl_selesai",
            "tahun_pelaksanaan", "kategori", "skema_pendanaan", "kode_pintar",
        ]
        widgets = {
            "nama": forms.TextInput(attrs={"class": "input", "placeholder": "cth. ASEAN Ministerial Meeting on Infrastructure 2027"}),
            "deskripsi": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Uraian singkat agenda/program (opsional)"}),
            "negara": forms.SelectMultiple(attrs={"data-multiselect": "Pilih negara pelaksanaan…"}),
            "kota": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Tokyo (multi-negara: Tokyo, Seoul)"}),
            "penyelenggara": forms.TextInput(attrs={"class": "input", "placeholder": "cth. ASEAN Secretariat / Delft University of Technology"}),
            "tgl_mulai": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
            "tgl_selesai": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
            "tahun_pelaksanaan": forms.NumberInput(attrs={"class": "input", "placeholder": "Otomatis dari tanggal mulai"}),
            "kategori": forms.SelectMultiple(attrs={"data-multiselect": "Pilih kategori kegiatan…"}),
            "skema_pendanaan": forms.SelectMultiple(attrs={"data-multiselect": "Pilih skema pendanaan…"}),
            "kode_pintar": forms.TextInput(attrs={"class": "input", "placeholder": "Opsional — ID kegiatan di Aplikasi PINTAR"}),
        }
        labels = {"tahun_pelaksanaan": "Tahun Pelaksanaan"}

    def __init__(self, *args, peran="admin_pakln", **kwargs):
        self.peran = peran
        super().__init__(*args, **kwargs)
        instance = self.instance

        def terpilih(nama):
            return list(getattr(instance, nama).values_list("pk", flat=True)) if instance.pk else []

        self.fields["negara"].queryset = Negara.objects.filter(
            models.Q(is_active=True) | models.Q(pk__in=terpilih("negara"))
        )
        kategori = KategoriPerjalanan.objects.filter(
            models.Q(jenis_perjalanan=KategoriPerjalanan.JenisPerjalanan.PDLN, is_active=True)
            | models.Q(pk__in=terpilih("kategori"))
        ).order_by("nama_kategori")
        if peran == "admin_bpsdm":
            kategori = KategoriPerjalanan.objects.filter(
                pk__in=[k.pk for k in kategori if kategori_untuk_bpsdm(k)]
            ).order_by("nama_kategori")
        self.fields["kategori"].queryset = kategori
        skema = SumberPembiayaan.objects.filter(
            models.Q(tipe_perjalanan=SumberPembiayaan.TipePerjalanan.PDLN, is_active=True)
            | models.Q(pk__in=terpilih("skema_pendanaan"))
        ).order_by("nama")
        if peran == "admin_bpsdm":
            skema = SumberPembiayaan.objects.filter(pk__in=[
                s.pk for s in skema if any(berlaku_untuk_tipe(s, t) for t in TIPE_KEGIATAN_BPSDM)
            ]).order_by("nama")
        self.fields["skema_pendanaan"].queryset = skema
        self.fields["tahun_pelaksanaan"].required = False
        self.fields["deskripsi"].required = False
        if peran != "admin_pakln":
            del self.fields["kode_pintar"]
        else:
            self.fields["kode_pintar"].required = False

    def clean_kode_pintar(self):
        # NULL (bukan "") agar unique hanya berlaku untuk kode yang terisi.
        return (self.cleaned_data.get("kode_pintar") or "").strip() or None

    def clean(self):
        cleaned = super().clean()
        mulai, selesai = cleaned.get("tgl_mulai"), cleaned.get("tgl_selesai")
        if mulai and selesai and selesai < mulai:
            self.add_error("tgl_selesai", "Tanggal selesai tidak boleh sebelum tanggal mulai.")
        if mulai and not cleaned.get("tahun_pelaksanaan"):
            cleaned["tahun_pelaksanaan"] = mulai.year  # B9
        kategori = list(cleaned.get("kategori") or [])
        if kategori:
            if any(k.jenis_perjalanan != KategoriPerjalanan.JenisPerjalanan.PDLN for k in kategori):
                self.add_error("kategori", "Kategori kegiatan harus kategori PDLN.")
            elif any(kategori_pendidikan(k) for k in kategori) and len(kategori) > 1:
                self.add_error("kategori", "Kegiatan pendidikan hanya boleh memiliki satu kategori.")  # B4
            elif self.peran == "admin_bpsdm" and not all(kategori_untuk_bpsdm(k) for k in kategori):
                self.add_error("kategori", "Admin BPSDM hanya dapat membuat kegiatan pendidikan atau pelatihan.")  # B10a
        skema = list(cleaned.get("skema_pendanaan") or [])
        if any(s.tipe_perjalanan != SumberPembiayaan.TipePerjalanan.PDLN for s in skema):
            self.add_error("skema_pendanaan", "Skema pendanaan harus sumber pembiayaan PDLN.")  # B6
        return cleaned

    def save(self, commit=True):
        kegiatan = super().save(commit=False)
        kegiatan.tahun_pelaksanaan = self.cleaned_data.get("tahun_pelaksanaan") or kegiatan.tgl_mulai.year
        if commit:
            kegiatan.save()
            self.save_m2m()
        return kegiatan


class DasarKegiatanForm(forms.ModelForm):
    """Satu baris dasar kegiatan (B15): field kunci mengikuti `jenis`
    (lihat `DasarKegiatan.FIELD_WAJIB`), berkas PDF opsional maks. 2 MB."""

    class Meta:
        model = DasarKegiatan
        fields = ["jenis", "nomor_surat", "tgl_surat", "tautan", "kode_pintar", "keterangan", "berkas"]
        widgets = {
            "jenis": forms.Select(attrs={"data-dasar-jenis": ""}),
            "nomor_surat": forms.TextInput(attrs={"class": "input", "placeholder": "cth. 123/ASEAN/IX/2027"}),
            "tgl_surat": forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"),
            "tautan": forms.URLInput(attrs={"class": "input", "placeholder": "https://…"}),
            "kode_pintar": forms.TextInput(attrs={"class": "input", "placeholder": "ID di Aplikasi PINTAR"}),
            "keterangan": forms.TextInput(attrs={"class": "input", "placeholder": "cth. Nota dinas Kepala Biro No. …"}),
            "berkas": forms.FileInput(attrs={
                "class": "file-input", "accept": PDF_ACCEPT, "data-pdf-only": "", "data-max-mb": "2",
            }),
        }

    def __init__(self, *args, peran="admin_pakln", **kwargs):
        super().__init__(*args, **kwargs)
        jenis = list(DasarKegiatan.Jenis.choices)
        if peran == "pegawai":
            # Pegawai tidak memakai Aplikasi PINTAR sebagai dasar usulan; kode
            # PINTAR hanya diisi Admin (atau sinkron PINTAR, §7.5).
            jenis = [c for c in jenis if c[0] != DasarKegiatan.Jenis.PINTAR]
            del self.fields["kode_pintar"]
        self.fields["jenis"].choices = [("", "— Pilih jenis dasar —")] + jenis
        self.fields["berkas"].validators.append(validate_pdf)  # PDF, maks. 2 MB


class BaseDasarKegiatanFormSet(BaseInlineFormSet):
    default_error_messages = {
        "too_few_forms": "Isi minimal satu dasar kegiatan (nomor surat, tautan, data PINTAR, atau lainnya).",
    }


def dasar_formset(data=None, files=None, instance=None, prefix="dasar", peran="admin_pakln"):
    """Formset dasar kegiatan — minimal satu baris (B15); baris pertama
    kegiatan baru wajib diisi. Pegawai tidak mendapat jenis "Aplikasi PINTAR"."""
    FormSet = inlineformset_factory(
        Kegiatan, DasarKegiatan, form=DasarKegiatanForm, formset=BaseDasarKegiatanFormSet,
        extra=0, min_num=1, validate_min=True, can_delete=True,
    )
    return FormSet(data, files, instance=instance or Kegiatan(), prefix=prefix, form_kwargs={"peran": peran})


class KeputusanKegiatanForm(forms.Form):
    """Putus usulan kegiatan (Admin Biro PAKLN): tolak wajib catatan (B11)."""

    keputusan = forms.ChoiceField(choices=[("setujui", "Setujui"), ("tolak", "Tolak")])
    catatan = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "textarea", "rows": 3}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("keputusan") == "tolak" and not (cleaned.get("catatan") or "").strip():
            self.add_error("catatan", "Isi catatan penolakan untuk pengusul.")
        return cleaned
