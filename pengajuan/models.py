from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


class Pengajuan(models.Model):
    """
    Satu pengajuan Perjalanan Luar Negeri Non-Kedinasan.

    `status` adalah "sumber kebenaran" siklus proses, identik dengan state
    machine pada mockup:

        belum -> proses -> proses_pakln -> selesai

    - belum          : draft, formulir belum/baru disimpan pegawai.
    - proses          : sudah dikirim pegawai, menunggu diproses Admin Unor.
    - proses_pakln    : diteruskan Admin Unor, menunggu diproses Admin Biro PAKLN.
    - selesai         : seluruh proses administrasi rampung.
    """

    class Kanal(models.TextChoices):
        MOBILE = "mobile", "Mobile App"
        WEB = "web", "Web App"

    class Status(models.TextChoices):
        BELUM = "belum", "Belum Diajukan"
        PROSES = "proses", "Dalam Proses Unor"
        PROSES_PAKLN = "proses_pakln", "Dalam Proses Biro PAKLN"
        SELESAI = "selesai", "Selesai"

    kode = models.CharField("Kode Pengajuan", max_length=20, unique=True, blank=True)
    pegawai = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pengajuan_list"
    )

    # --- Detail perjalanan (diisi pegawai pada Formulir Pengajuan) ---
    kategori = models.ForeignKey(
        "paspor.KategoriPerjalanan", on_delete=models.PROTECT, null=True, blank=True,
        related_name="pengajuan_list", verbose_name="Kategori Perjalanan",
    )
    maksud = models.TextField("Maksud Perjalanan", blank=True)
    tujuan_negara = models.ManyToManyField(
        "paspor.Negara", blank=True, related_name="pengajuan_list", verbose_name="Tujuan Negara",
    )
    sumber_pembiayaan = models.ForeignKey(
        "paspor.SumberPembiayaan", on_delete=models.PROTECT, null=True, blank=True,
        related_name="pengajuan_list", verbose_name="Sumber Pembiayaan",
    )
    tgl_berangkat = models.DateField(null=True, blank=True)
    tgl_kembali = models.DateField(null=True, blank=True)
    # Snapshot hasil hitung sistem (paspor.kalender), bukan input pegawai —
    # lihat `hitung_ulang_hari`.
    jumlah_hari_kerja = models.PositiveIntegerField(null=True, blank=True)

    kanal = models.CharField(max_length=10, choices=Kanal.choices, default=Kanal.WEB)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BELUM)

    # --- Flag alur, identik dengan nama field pada state mockup ---
    form_saved = models.BooleanField(default=False)
    submitted = models.BooleanField(default=False)
    preview_unor_agree = models.BooleanField(default=False)
    preview_pakln_agree = models.BooleanField(default=False)

    # Catatan Admin Unor saat mengembalikan pengajuan ke pegawai (mis. ada
    # dokumen yang perlu diperbaiki) — dikosongkan lagi saat pegawai
    # mengirim ulang pengajuannya.
    catatan_unor = models.TextField("Catatan Admin Unor", blank=True)

    # Catatan Admin Biro PAKLN saat mengembalikan pengajuan ke Admin Unor
    # (mis. rekomendasi/berkas administrasi Unor perlu diperbaiki).
    catatan_pakln = models.TextField("Catatan Admin PKLN", blank=True)

    # --- Tanggal penting untuk pelaporan / monitor progres ---
    tgl_pengajuan = models.DateField(null=True, blank=True)
    tgl_masuk_pakln = models.DateField(null=True, blank=True)
    tgl_selesai = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pengajuan"
        verbose_name_plural = "Pengajuan"

    def save(self, *args, **kwargs):
        if not self.kode:
            self.kode = self._generate_kode()
        super().save(*args, **kwargs)

    def _generate_kode(self):
        """Format PSP-<tahun>-<urutan 4 digit>, mengikuti contoh pada mockup
        (mis. PSP-2026-0142)."""
        year = timezone.now().year
        prefix = f"PSP-{year}-"
        last = (
            Pengajuan.objects.filter(kode__startswith=prefix)
            .order_by("-kode")
            .first()
        )
        next_num = int(last.kode.split("-")[-1]) + 1 if last else 1
        return f"{prefix}{next_num:04d}"

    @property
    def tujuan_negara_display(self):
        """Nama-nama negara tujuan sebagai satu string dipisah koma,
        untuk ditampilkan pada tabel/pratinjau/export yang butuh teks
        tunggal (field aslinya ManyToMany, bisa lebih dari satu negara)."""
        return ", ".join(self.tujuan_negara.values_list("nama_negara", flat=True))

    @property
    def jumlah_hari_kalender(self):
        from paspor.kalender import hitung_hari_kalender
        return hitung_hari_kalender(self.tgl_berangkat, self.tgl_kembali)

    def hitung_ulang_hari(self):
        """Isi ulang `jumlah_hari_kerja` dari tanggal berangkat/kembali dan
        kalender libur saat ini. Hanya dipanggil selama pengajuan masih
        draft (status BELUM) — setelah dikirim angkanya dibekukan
        (snapshot), walau Admin Biro PAKLN kemudian mengubah kalender."""
        from paspor.kalender import hitung_hari_kerja
        self.jumlah_hari_kerja = hitung_hari_kerja(self.tgl_berangkat, self.tgl_kembali)
        return self.jumlah_hari_kerja

    @property
    def timeline(self):
        """Struktur data untuk halaman Monitor Progres pegawai, identik
        dengan 4 tahap pada mockup."""
        order = [self.Status.BELUM, self.Status.PROSES, self.Status.PROSES_PAKLN, self.Status.SELESAI]
        current_index = order.index(self.status) if self.status in order else 0
        steps = [
            ("Diajukan Pegawai", "Pengisian Formulir dan Unggah Berkas untuk disampaikan ke Unor.", self.tgl_pengajuan),
            ("Dalam Proses Unor", "Pratinjau Formulir dan Berkas, permohonan tanda tangan Pimpinan Unor, permohonan persetujuan Menteri, penyampaian berkas ke Biro PAKLN.", None),
            ("Dalam Proses Biro PAKLN", "Permohonan tanda tangan Sekretaris Jenderal a.n. Menteri.", self.tgl_masuk_pakln),
            ("Selesai", "Seluruh proses administrasi perizinan telah rampung.", self.tgl_selesai),
        ]
        result = []
        for idx, (title, desc, tgl) in enumerate(steps):
            if idx < current_index:
                state = "done"
            elif idx == current_index and self.status != self.Status.BELUM:
                state = "current"
            else:
                state = "upcoming"
            result.append({"title": title, "desc": desc, "tanggal": tgl, "state": state})
        return result

    def __str__(self):
        return f"{self.kode} — {self.pegawai}"


# ---------------------------------------------------------------------------
# Dokumen per tahap (Pegawai / Admin Unor / Admin Biro PAKLN)
# ---------------------------------------------------------------------------

def dokumen_pegawai_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/pegawai/{instance.jenis}/{filename}"


def dokumen_unor_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/unor/{instance.jenis}/{filename}"


def dokumen_pakln_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/pakln/{instance.jenis}/{filename}"


class DokumenPegawai(models.Model):
    """4 jenis dokumen yang diunggah pegawai (lihat mockup bagian
    Unggah Dokumen)."""

    class Jenis(models.TextChoices):
        CUTI = "cuti", "1.a Formulir Persetujuan Cuti Pegawai"
        ILN = "iln", "1.b Formulir Izin Luar Negeri"
        NOTADINAS = "notadinas", "1.c Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor"
        PENDUKUNG = "pendukung", "1.d Dokumen Pendukung"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_pegawai")
    jenis = models.CharField(max_length=20, choices=Jenis.choices)
    file = models.FileField(upload_to=dokumen_pegawai_path)
    # Hanya diisi untuk jenis dokumen yang berupa surat (1.a, 1.c) — lewat
    # modal "Tanggal Surat" yang muncul begitu berkasnya dipilih, lihat
    # JENIS_PERLU_TANGGAL_SURAT di base.html.
    tanggal_surat = models.DateField("Tanggal Surat", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("pengajuan", "jenis")
        verbose_name = "Dokumen Pegawai"
        verbose_name_plural = "Dokumen Pegawai"

    def __str__(self):
        return f"{self.pengajuan.kode} — {self.get_jenis_display()}"


class DokumenUnor(models.Model):
    """3 dokumen utama (wajib) yang dilengkapi Admin Unor, satu berkas per
    jenis. Dokumen pendukung lainnya ada pada `DokumenUnorPendukung`."""

    class Jenis(models.TextChoices):
        DISPOSISI = "disposisi", "2.a Lembar Disposisi / Izin Prinsip"
        ILN_PIMPINAN = "iln_pimpinan", "2.b Formulir Izin Luar Negeri (TTD Pimpinan Unor)"
        ND_BIROPAKLN = "nd_biropakln", "2.c Nota Dinas Sekertaris Unor ke Biro PAKLN"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_unor")
    jenis = models.CharField(max_length=20, choices=Jenis.choices)
    file = models.FileField(upload_to=dokumen_unor_path)
    # Hanya diisi untuk jenis dokumen yang berupa surat (2.a, 2.c) — lewat
    # modal "Tanggal Surat" yang muncul begitu berkasnya dipilih, lihat
    # JENIS_PERLU_TANGGAL_SURAT di base.html.
    tanggal_surat = models.DateField("Tanggal Surat", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("pengajuan", "jenis")
        verbose_name = "Dokumen Administrasi Unor"
        verbose_name_plural = "Dokumen Administrasi Unor"

    def __str__(self):
        return f"{self.pengajuan.kode} — {self.get_jenis_display()}"


def dokumen_unor_pendukung_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/unor/pendukung/{filename}"


class DokumenUnorPendukung(models.Model):
    """Satu berkas dokumen pendukung Admin Unor per pengajuan, dengan
    checklist jenis yang tercakup di dalamnya. Mengunggah/mengganti berkas
    dan mencentang/melepas centang salah satu jenis adalah dua proses yang
    berdiri sendiri-sendiri — tidak saling mensyaratkan: berkas bisa
    diunggah kapan pun tanpa jenis dicentang lebih dulu (dan sebaliknya)."""

    pengajuan = models.OneToOneField(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_unor_pendukung")
    file = models.FileField(upload_to=dokumen_unor_pendukung_path, blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)

    nd_sekunor = models.BooleanField("Nota Dinas Sekretaris Unor", default=False)
    nd_menteri = models.BooleanField("Nota Dinas Permohonan Persetujuan Menteri", default=False)
    lainnya = models.BooleanField("Dokumen Lainnya", default=False)

    class Meta:
        verbose_name = "Dokumen Pendukung Unor"
        verbose_name_plural = "Dokumen Pendukung Unor"

    KATEGORI_LABELS = {
        "nd_sekunor": "Nota Dinas Sekretaris Unor",
        "nd_menteri": "Nota Dinas Permohonan Persetujuan Menteri",
        "lainnya": "Dokumen Lainnya",
    }

    def kategori_tercentang(self):
        return [label for field, label in self.KATEGORI_LABELS.items() if getattr(self, field)]

    def is_lengkap(self):
        # Checklist jenis dokumen dihapus dari UI Unggah Dokumen Unor —
        # berkas terunggah saja sudah cukup. Field `nd_sekunor`/`nd_menteri`/
        # `lainnya` tetap ada (dibaca Admin PAKLN di halaman Pratinjau untuk
        # submission lama), hanya tidak lagi jadi syarat kelengkapan di sini.
        return bool(self.file)

    def __str__(self):
        return f"{self.pengajuan.kode} — Dokumen Pendukung Unor"


class DokumenPakln(models.Model):
    """Dokumen administrasi wajib yang dilengkapi Admin Biro PAKLN. Dokumen
    pendukung lainnya (opsional) ada pada `DokumenPaklnPendukung`."""

    class Jenis(models.TextChoices):
        ILN_SEKJEN = "iln_sekjen", "3.a Izin Luar Negeri (TTD Sekjen a.n. Menteri)"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_pakln")
    jenis = models.CharField(max_length=20, choices=Jenis.choices)
    file = models.FileField(upload_to=dokumen_pakln_path)
    # Hanya diisi untuk jenis dokumen yang berupa surat (3.a) — lewat modal
    # "Tanggal Surat" yang muncul begitu berkasnya dipilih, lihat
    # JENIS_PERLU_TANGGAL_SURAT di base.html.
    tanggal_surat = models.DateField("Tanggal Surat", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("pengajuan", "jenis")
        verbose_name = "Dokumen Administrasi Biro PAKLN"
        verbose_name_plural = "Dokumen Administrasi Biro PAKLN"

    def __str__(self):
        return f"{self.pengajuan.kode} — {self.get_jenis_display()}"


def dokumen_pakln_pendukung_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/pakln/pendukung/{filename}"


class DokumenPaklnPendukung(models.Model):
    """Satu berkas dokumen pendukung Admin Biro PAKLN per pengajuan, dengan
    checklist jenis yang tercakup di dalamnya. Mengunggah/mengganti berkas
    dan mencentang/melepas centang salah satu jenis adalah dua proses yang
    berdiri sendiri-sendiri — tidak saling mensyaratkan, dan opsional
    (tidak menjadi syarat "selesaikan proses"), berbeda dengan
    `DokumenPakln` (ILN Sekjen) yang wajib."""

    pengajuan = models.OneToOneField(
        Pengajuan, on_delete=models.CASCADE, related_name="dokumen_pakln_pendukung"
    )
    file = models.FileField(upload_to=dokumen_pakln_pendukung_path, blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)

    nd_kabag = models.BooleanField("Nota Dinas Kepala Bagian", default=False)
    nd_kabiro = models.BooleanField("Nota Dinas Kepala Biro", default=False)

    class Meta:
        verbose_name = "Dokumen Pendukung Biro PAKLN"
        verbose_name_plural = "Dokumen Pendukung Biro PAKLN"

    KATEGORI_LABELS = {
        "nd_kabag": "Nota Dinas Kepala Bagian",
        "nd_kabiro": "Nota Dinas Kepala Biro",
    }

    def kategori_tercentang(self):
        return [label for field, label in self.KATEGORI_LABELS.items() if getattr(self, field)]

    def is_lengkap(self):
        return bool(self.file) and bool(self.kategori_tercentang())

    def __str__(self):
        return f"{self.pengajuan.kode} — Dokumen Pendukung Biro PAKLN"


def dokumen_generate_log_path(instance, filename):
    return f"generate_dokumen/{instance.jenis}/{filename}"


class DokumenGenerateLog(models.Model):
    """Riwayat dokumen (ND Kabag/ND Karo) yang berhasil digenerate Admin
    Biro PAKLN lewat halaman Generate Dokumen — satu baris per aksi
    "Unduh PDF" yang sukses, termasuk salinan berkasnya sendiri supaya
    bisa diunduh ulang dari halaman Histori Generate Dokumen."""

    class Jenis(models.TextChoices):
        ND_KABAG = "nd_kabag", "ND Kabag"
        ND_KARO = "nd_karo", "ND Karo"

    jenis = models.CharField(max_length=20, choices=Jenis.choices)
    jumlah_pengajuan = models.PositiveIntegerField(
        "Jumlah Pengajuan", default=1,
        help_text="Jumlah pengajuan yang diproses dalam satu batch generate ini.",
    )
    pengajuan = models.ManyToManyField(
        Pengajuan, blank=True, related_name="dokumen_generate_logs",
        verbose_name="Pengajuan Terkait",
    )
    file = models.FileField("Berkas PDF", upload_to=dokumen_generate_log_path)
    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Riwayat Generate Dokumen"
        verbose_name_plural = "Riwayat Generate Dokumen"

    def __str__(self):
        return f"{self.get_jenis_display()} — {self.created_at:%d %b %Y %H:%M}"


class PengaturanDokumen(models.Model):
    """Pengaturan default untuk dokumen ND Kabag & ND Karo (menu "Setting",
    khusus Admin Biro PAKLN) — satu baris saja (singleton, selalu pk=1).
    Kabag (Plt. Kepala Bagian KLN) & Karo (Kepala Biro PAKLN) adalah dua
    pejabat penandatangan yang berbeda, sehingga masing-masing punya
    pasangan field jabatan/nama sendiri — dipakai sebagai nilai awal form
    Generate ND Kabag / ND Karo saat dibuka."""

    jabatan_penandatangan_kabag = models.CharField(
        "Jabatan Pejabat Penandatangan (ND Kabag)", max_length=150, blank=True,
    )
    nama_pejabat_kabag = models.CharField("Nama Pejabat (ND Kabag)", max_length=150, blank=True)
    jabatan_penandatangan_karo = models.CharField(
        "Jabatan Pejabat Penandatangan (ND Karo)", max_length=150, blank=True,
    )
    nama_pejabat_karo = models.CharField("Nama Pejabat (ND Karo)", max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )

    class Meta:
        verbose_name = "Pengaturan Dokumen"
        verbose_name_plural = "Pengaturan Dokumen"

    def __str__(self):
        return "Pengaturan Dokumen"

    @classmethod
    def get_current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ---------------------------------------------------------------------------
# Manajemen Template — berkas contoh/standar (PDF/DOCX) yang disediakan
# Admin Biro PAKLN agar dokumen yang diunggah Pegawai/Admin Unor mengikuti
# format yang seragam.
# ---------------------------------------------------------------------------

def dokumen_template_path(instance, filename):
    return f"template_dokumen/{filename}"


class DokumenTemplate(models.Model):
    """Template dokumen (PDF/DOCX) yang dapat diunduh Pegawai dan/atau
    Admin Unor, dengan penargetan opsional berdasarkan peran, unit
    organisasi, dan kategori perjalanan."""

    nama = models.CharField("Nama Template", max_length=150)
    keterangan = models.CharField("Keterangan", max_length=255, blank=True)
    file = models.FileField(
        "Berkas",
        upload_to=dokumen_template_path,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "docx"])],
    )

    # --- Penargetan ---
    untuk_pegawai = models.BooleanField("Untuk Pegawai", default=True)
    untuk_admin_unor = models.BooleanField("Untuk Admin Unor", default=True)
    unit_organisasi = models.ManyToManyField(
        "paspor.UnitOrganisasi",
        blank=True,
        related_name="dokumen_template_list",
        verbose_name="Unit Organisasi Tertentu",
        help_text="Kosongkan agar berlaku untuk seluruh unit organisasi.",
    )
    kategori = models.ForeignKey(
        "paspor.KategoriPerjalanan",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="dokumen_template_list",
        verbose_name="Kategori Perjalanan Tertentu",
        help_text="Kosongkan agar berlaku untuk seluruh kategori perjalanan.",
    )

    aktif = models.BooleanField("Tampilkan", default=True)

    diunggah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nama"]
        verbose_name = "Template Dokumen"
        verbose_name_plural = "Template Dokumen"

    def __str__(self):
        return self.nama

    def relevan_untuk(self, user, kategori=None):
        """True jika template ini semestinya ditampilkan untuk `user`
        (Pegawai/Admin Unor), opsional difilter kategori perjalanan
        pengajuan yang sedang berjalan."""
        if not self.aktif:
            return False
        if user.role == "pegawai" and not self.untuk_pegawai:
            return False
        if user.role == "admin_unor" and not self.untuk_admin_unor:
            return False

        unit_ids = set(self.unit_organisasi.values_list("id", flat=True))
        if unit_ids and user.unit_organisasi_id not in unit_ids:
            return False

        if self.kategori and kategori and self.kategori != kategori:
            return False

        return True


# ---------------------------------------------------------------------------
# Riwayat Pemrosesan (wiki/instructions/RIWAYAT_PEMROSESAN_PENGAJUAN.MD)
# ---------------------------------------------------------------------------

class RiwayatPengajuan(models.Model):
    """Log append-only setiap perpindahan status Pengajuan beserta pesan
    pengembalian. Tidak pernah di-update/dihapus dari aplikasi — tulis
    lewat `pengajuan.riwayat.catat`, baca lewat `riwayat_untuk`."""

    class Aksi(models.TextChoices):
        DIKIRIM = "dikirim", "Diajukan ke Admin Unor"
        DIKIRIM_ULANG = "dikirim_ulang", "Perbaikan dikirim ke Admin Unor"
        DIKEMBALIKAN_UNOR = "dikembalikan_unor", "Dikembalikan Admin Unor ke Pegawai"
        DITERUSKAN_PAKLN = "diteruskan_pakln", "Diteruskan ke Biro PAKLN"
        DIKEMBALIKAN_PAKLN = "dikembalikan_pakln", "Dikembalikan Biro PAKLN ke Admin Unor"
        SELESAI = "selesai", "Selesai diproses"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="riwayat")
    aksi = models.CharField(max_length=30, choices=Aksi.choices)
    status_dari = models.CharField(max_length=20, choices=Pengajuan.Status.choices)
    status_ke = models.CharField(max_length=20, choices=Pengajuan.Status.choices)

    aktor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="riwayat_pengajuan",
    )
    # Snapshot saat kejadian — tetap benar walau user kemudian dihapus
    # atau perannya diganti. Dasar aturan visibilitas pesan.
    aktor_role = models.CharField(max_length=20)
    aktor_nama = models.CharField(max_length=150)

    catatan = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["pengajuan", "created_at"])]
        verbose_name = "Riwayat Pengajuan"
        verbose_name_plural = "Riwayat Pengajuan"

    def __str__(self):
        return f"{self.pengajuan.kode} — {self.get_aksi_display()}"
