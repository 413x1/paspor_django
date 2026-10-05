from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


class Pengajuan(models.Model):
    """
    Satu pengajuan perjalanan luar negeri — Non-Kedinasan atau PDLN
    (Perjalanan Dinas Luar Negeri), lihat
    wiki/instructions/BISNIS_PROSES_PDLN.MD.

    `status` adalah "sumber kebenaran" siklus proses. Urutan tahap
    bergantung tipe (`pengajuan.alur.ALUR`):

        Non-Dinas, T1, T3 : belum -> proses -> proses_pakln -> selesai
        T2P, T2L          : belum -> proses -> proses_bpsdm -> proses_pakln -> selesai

    `dibatalkan` adalah status final yang bisa dicapai dari status mana
    pun lewat permohonan pembatalan (`pengajuan.pembatalan`).
    """

    class Kanal(models.TextChoices):
        MOBILE = "mobile", "Mobile App"
        WEB = "web", "Web App"

    class Status(models.TextChoices):
        BELUM = "belum", "Belum Diajukan"
        PROSES = "proses", "Dalam Proses Unor"
        PROSES_BPSDM = "proses_bpsdm", "Dalam Proses BPSDM"
        PROSES_PAKLN = "proses_pakln", "Dalam Proses Biro PAKLN"
        SELESAI = "selesai", "Selesai"
        DIBATALKAN = "dibatalkan", "Dibatalkan"

    class JenisPerjalanan(models.TextChoices):
        NONDINAS = "nondinas", "Non-Kedinasan"
        PDLN = "pdln", "PDLN"

    class TipePdln(models.TextChoices):
        T1 = "T1", "PDLN Tipe 1"
        T2P = "T2P", "PDLN Tipe 2 — Pendidikan"
        T2L = "T2L", "PDLN Tipe 2 — Pelatihan"
        T3 = "T3", "PDLN Tipe 3 — Penugasan Khusus"

    kode = models.CharField("Kode Pengajuan", max_length=20, unique=True, blank=True)
    pegawai = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pengajuan_list"
    )
    jenis_perjalanan = models.CharField(
        "Jenis Perjalanan", max_length=20, choices=JenisPerjalanan.choices,
        default=JenisPerjalanan.NONDINAS,
    )
    tipe_pdln = models.CharField("Tipe PDLN", max_length=5, choices=TipePdln.choices, blank=True)
    # Snapshot unit organisasi pegawai saat pengajuan dikirim — dasar
    # cakupan Admin Unor & report, tidak bergeser bila pegawai mutasi.
    unit_organisasi = models.ForeignKey(
        "paspor.UnitOrganisasi", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="Unit Organisasi (saat diajukan)",
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
    preview_bpsdm_agree = models.BooleanField(default=False)
    preview_pakln_agree = models.BooleanField(default=False)

    # Catatan Admin Unor saat mengembalikan pengajuan ke pegawai (mis. ada
    # dokumen yang perlu diperbaiki) — dikosongkan lagi saat pegawai
    # mengirim ulang pengajuannya.
    catatan_unor = models.TextField("Catatan Admin Unor", blank=True)

    # Catatan Admin BPSDM saat mengembalikan pengajuan Tipe 2 ke Admin Unor
    # — penanda bahwa penerusan berikutnya ke BPSDM adalah penerusan ulang.
    catatan_bpsdm = models.TextField("Catatan Admin BPSDM", blank=True)

    # Catatan Admin Biro PAKLN saat mengembalikan pengajuan ke tahap
    # sebelumnya (Admin Unor, atau Admin BPSDM untuk Tipe 2).
    catatan_pakln = models.TextField("Catatan Admin PKLN", blank=True)

    # --- Tanggal penting untuk pelaporan / monitor progres ---
    tgl_pengajuan = models.DateField(null=True, blank=True)
    tgl_masuk_bpsdm = models.DateField(null=True, blank=True)
    tgl_masuk_pakln = models.DateField(null=True, blank=True)
    tgl_selesai = models.DateField(null=True, blank=True)
    tgl_dibatalkan = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["jenis_perjalanan", "tipe_pdln", "status"]),
            models.Index(fields=["unit_organisasi", "status"]),
            models.Index(fields=["status", "tgl_pengajuan"]),
            models.Index(fields=["pegawai", "status"]),
        ]
        verbose_name = "Pengajuan"
        verbose_name_plural = "Pengajuan"

    def save(self, *args, **kwargs):
        if not self.kode:
            self.kode = self._generate_kode()
        super().save(*args, **kwargs)

    def _generate_kode(self):
        """Non-Dinas: PSP-<tahun>-<urutan> (mis. PSP-2026-0142); PDLN:
        PDLN-<tahun>-<tipe>-<urutan> (mis. PDLN-2026-T2P-0001). Nomor urut
        dihitung per prefiks per tahun."""
        year = timezone.now().year
        if self.jenis_perjalanan == self.JenisPerjalanan.PDLN and self.tipe_pdln:
            prefix = f"PDLN-{year}-{self.tipe_pdln}-"
        else:
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

    # --- Turunan jenis/tipe & status ---------------------------------

    @property
    def is_pdln(self):
        return self.jenis_perjalanan == self.JenisPerjalanan.PDLN

    @property
    def is_tipe2(self):
        return self.tipe_pdln in (self.TipePdln.T2P, self.TipePdln.T2L)

    @property
    def kunci_alur(self):
        """Kunci `alur.ALUR` & `persyaratan.PERSYARATAN`: "nondinas" atau
        kode tipe PDLN."""
        return self.tipe_pdln if self.is_pdln and self.tipe_pdln else "nondinas"

    @property
    def jenis_label(self):
        """Label ringkas untuk tabel: "Non-Kedinasan" / "PDLN Tipe 1" …"""
        return self.get_tipe_pdln_display() if self.is_pdln and self.tipe_pdln else "Non-Kedinasan"

    @property
    def pernah_dikirim(self):
        return self.tgl_pengajuan is not None

    @property
    def perlu_visa(self):
        """True bila salah satu negara tujuan memerlukan visa — Rekomendasi
        Visa menjadi wajib (BISNIS_PROSES_PDLN.MD §6.4)."""
        return self.tujuan_negara.filter(perlu_visa=True).exists()

    @property
    def negara_perlu_visa(self):
        return ", ".join(
            self.tujuan_negara.filter(perlu_visa=True).values_list("nama_negara", flat=True)
        )

    @property
    def pembatalan_terbuka(self):
        """Permohonan pembatalan yang masih menunggu keputusan, atau None.
        Selama ada, aksi alur utama dibekukan."""
        if not self.pk:
            return None
        return self.permohonan_pembatalan.filter(
            status__in=PermohonanPembatalan.STATUS_TERBUKA
        ).first()

    @property
    def laporan(self):
        if not self.pk:
            return None
        try:
            return self.laporan_pdln
        except LaporanPdln.DoesNotExist:
            return None

    @property
    def detail(self):
        if not self.pk:
            return None
        try:
            return self.detail_pdln
        except DetailPdln.DoesNotExist:
            return None

    @property
    def tuntas(self):
        """Pengajuan telah mencapai tahap akhir (§2.1): dibatalkan,
        Non-Dinas selesai, atau PDLN selesai + laporan disetujui."""
        if self.status == self.Status.DIBATALKAN:
            return True
        if self.status != self.Status.SELESAI:
            return False
        if not self.is_pdln:
            return True
        laporan = self.laporan
        return bool(laporan and laporan.status == LaporanPdln.Status.DISETUJUI)

    @property
    def timeline(self):
        """Tahap-tahap Timeline Proses sesuai tipe (lihat `alur.timeline`)."""
        from .alur import timeline
        return timeline(self)

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
    """Dokumen yang diunggah pegawai. Jenis yang wajib per jenis/tipe
    perjalanan ditentukan registri `pengajuan.persyaratan`."""

    class Jenis(models.TextChoices):
        # Non-Kedinasan
        CUTI = "cuti", "1.a Formulir Persetujuan Cuti Pegawai"
        ILN = "iln", "1.b Formulir Izin Luar Negeri"
        NOTADINAS = "notadinas", "1.c Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor"
        PENDUKUNG = "pendukung", "1.d Dokumen Pendukung"
        # PDLN
        UNDANGAN = "undangan", "Undangan/Surat Permohonan dari Penyelenggara"
        KAK = "kak", "Kerangka Acuan Kerja (KAK)"
        RAB = "rab", "RAB Pembiayaan"
        ITINERARY = "itinerary", "Jadwal Kegiatan/Itinerary"
        LOA = "loa", "Letter of Acceptance (LoA)"
        LOG = "log", "Letter of Guarantee (LoG)"
        SURAT_PERNYATAAN = "surat_pernyataan", "Surat Pernyataan sesuai ketentuan Kemensetneg"
        DRH = "drh", "Daftar Riwayat Hidup (DRH)"
        IKATAN_DINAS = "ikatan_dinas", "Perjanjian Ikatan Dinas"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_pegawai")
    jenis = models.CharField(max_length=30, choices=Jenis.choices)
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
        # Non-Kedinasan
        DISPOSISI = "disposisi", "2.a Lembar Disposisi / Izin Prinsip"
        ILN_PIMPINAN = "iln_pimpinan", "2.b Formulir Izin Luar Negeri (TTD Pimpinan Unor)"
        ND_BIROPAKLN = "nd_biropakln", "2.c Nota Dinas Sekertaris Unor ke Biro PAKLN"
        # PDLN
        IZIN_PRINSIP = "izin_prinsip", "Izin Prinsip Menteri"
        SURAT_TUGAS = "surat_tugas", "Surat Tugas"
        ND_KABIRO_PAKLN = "nd_kabiro_pakln", "Nota Dinas Sekretaris Unor ke Kepala Biro PAKLN"
        ND_SEK_BPSDM = "nd_sek_bpsdm", "Nota Dinas Sekretaris Unor ke Sekretaris BPSDM"
        DRH_TTD = "drh_ttd", "DRH ttd Pimpinan Unor"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_unor")
    jenis = models.CharField(max_length=30, choices=Jenis.choices)
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
        # Non-Kedinasan
        ILN_SEKJEN = "iln_sekjen", "3.a Izin Luar Negeri (TTD Sekjen a.n. Menteri)"
        # PDLN
        SP_SETNEG = "sp_setneg", "SP Setneg"
        PASPOR_DINAS = "paspor_dinas", "Paspor Dinas"
        EXIT_PERMIT = "exit_permit", "Exit Permit"
        VISA = "visa", "Rekomendasi Visa"
        SK_TUBEL = "sk_tubel", "SK Tugas Belajar"
        ND_KARO_UNOR = "nd_karo_unor", "Nota Dinas Karo PAKLN ke Sekretaris Unor hal Penyampaian Dokumen PDLN"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_pakln")
    jenis = models.CharField(max_length=30, choices=Jenis.choices)
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


def dokumen_bpsdm_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/bpsdm/{instance.jenis}/{filename}"


class DokumenBpsdm(models.Model):
    """Dokumen administrasi Admin BPSDM (khusus PDLN Tipe 2)."""

    class Jenis(models.TextChoices):
        IZIN_PRINSIP = "izin_prinsip", "Izin Prinsip Menteri"
        IKATAN_DINAS_TTD = "ikatan_dinas_ttd", "Perjanjian Ikatan Dinas ttd full / SK Tugas Belajar"
        ND_KABIRO_PAKLN = "nd_kabiro_pakln", "Nota Dinas Sekretaris BPSDM ke Kepala Biro PAKLN"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="dokumen_bpsdm")
    jenis = models.CharField(max_length=30, choices=Jenis.choices)
    file = models.FileField(upload_to=dokumen_bpsdm_path)
    tanggal_surat = models.DateField("Tanggal Surat", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("pengajuan", "jenis")
        verbose_name = "Dokumen Administrasi BPSDM"
        verbose_name_plural = "Dokumen Administrasi BPSDM"

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
    untuk_admin_bpsdm = models.BooleanField("Untuk Admin BPSDM", default=False)
    jenis_perjalanan = models.CharField(
        "Jenis Perjalanan Tertentu", max_length=20, blank=True,
        choices=Pengajuan.JenisPerjalanan.choices,
        help_text="Kosongkan agar berlaku untuk Non-Kedinasan maupun PDLN.",
    )
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

    def relevan_untuk(self, user, kategori=None, jenis_perjalanan=None):
        """True jika template ini semestinya ditampilkan untuk `user`
        (Pegawai/Admin Unor/Admin BPSDM), opsional difilter kategori dan
        jenis perjalanan pengajuan yang sedang berjalan."""
        if not self.aktif:
            return False
        if user.role == "pegawai" and not self.untuk_pegawai:
            return False
        if user.role == "admin_unor" and not self.untuk_admin_unor:
            return False
        if user.role == "admin_bpsdm" and not self.untuk_admin_bpsdm:
            return False
        if self.jenis_perjalanan and jenis_perjalanan and self.jenis_perjalanan != jenis_perjalanan:
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
        DITERUSKAN_ULANG = "diteruskan_ulang", "Perbaikan diteruskan ke Biro PAKLN"
        SELESAI = "selesai", "Selesai diproses"
        # Tahap BPSDM (PDLN Tipe 2)
        DITERUSKAN_BPSDM = "diteruskan_bpsdm", "Diteruskan ke Admin BPSDM"
        DITERUSKAN_ULANG_BPSDM = "diteruskan_ulang_bpsdm", "Perbaikan diteruskan ke Admin BPSDM"
        DIKEMBALIKAN_BPSDM = "dikembalikan_bpsdm", "Dikembalikan BPSDM ke Admin Unor"
        # Pelaporan PDLN
        LAPORAN_DIUNGGAH = "laporan_diunggah", "Laporan PDLN diunggah"
        LAPORAN_DIKEMBALIKAN = "laporan_dikembalikan", "Laporan PDLN dikembalikan"
        LAPORAN_DISETUJUI = "laporan_disetujui", "Laporan PDLN disetujui"
        # Pembatalan (mekanisme interim)
        PEMBATALAN_DIAJUKAN = "pembatalan_diajukan", "Permohonan pembatalan diajukan"
        PEMBATALAN_DITARIK = "pembatalan_ditarik", "Permohonan pembatalan ditarik"
        PEMBATALAN_DISETUJUI_UNOR = "pembatalan_disetujui_unor", "Pembatalan disetujui Admin Unor"
        PEMBATALAN_DITOLAK_UNOR = "pembatalan_ditolak_unor", "Pembatalan ditolak Admin Unor"
        PEMBATALAN_DITOLAK_PAKLN = "pembatalan_ditolak_pakln", "Pembatalan ditolak Biro PAKLN"
        DIBATALKAN = "dibatalkan", "Perjalanan dibatalkan"

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


# ---------------------------------------------------------------------------
# PDLN (wiki/instructions/BISNIS_PROSES_PDLN.MD §8.3)
# ---------------------------------------------------------------------------

class DetailPdln(models.Model):
    """Field khusus PDLN (1:1 dengan Pengajuan). Field yang dipakai
    bergantung tipe — lihat BISNIS_PROSES_PDLN.MD §5."""

    pengajuan = models.OneToOneField(Pengajuan, on_delete=models.CASCADE, related_name="detail_pdln")
    penyelenggara = models.CharField("Penyelenggara", max_length=200, blank=True)
    perguruan_tinggi = models.CharField("Perguruan Tinggi", max_length=200, blank=True)
    kota_tujuan = models.CharField("Kota Tujuan", max_length=150, blank=True)
    tgl_mulai_kegiatan = models.DateField("Tanggal Mulai Kegiatan", null=True, blank=True)
    tgl_selesai_kegiatan = models.DateField("Tanggal Selesai Kegiatan", null=True, blank=True)
    # Pencalonan beasiswa dari Aplikasi PINTAR (T2P/T2L) — id + snapshot
    # nama agar tetap terbaca bila data PINTAR berubah/tidak tersedia.
    beasiswa_pintar_id = models.CharField("ID Pencalonan PINTAR", max_length=50, blank=True)
    beasiswa_nama = models.CharField("Nama Beasiswa", max_length=255, blank=True)
    pernyataan_benar = models.BooleanField("Pernyataan kebenaran data", default=False)

    class Meta:
        verbose_name = "Detail PDLN"
        verbose_name_plural = "Detail PDLN"

    def __str__(self):
        return f"{self.pengajuan.kode} — Detail PDLN"


def laporan_pdln_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/laporan/{filename}"


class LaporanPdln(models.Model):
    """Laporan perjalanan dinas — wajib disetujui Admin Biro PAKLN agar
    pengajuan PDLN dianggap tuntas (BISNIS_PROSES_PDLN.MD §4.4)."""

    class Status(models.TextChoices):
        MENUNGGU = "menunggu", "Menunggu Verifikasi"
        DIKEMBALIKAN = "dikembalikan", "Dikembalikan"
        DISETUJUI = "disetujui", "Disetujui"

    pengajuan = models.OneToOneField(Pengajuan, on_delete=models.CASCADE, related_name="laporan_pdln")
    file = models.FileField("Berkas Laporan", upload_to=laporan_pdln_path)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MENUNGGU, db_index=True)
    # Catatan pengembalian terakhir — penanda unggah ulang wajib catatan balasan.
    catatan_pakln = models.TextField("Catatan Admin PAKLN", blank=True)
    diunggah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    diverifikasi_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    tgl_disetujui = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Laporan PDLN"
        verbose_name_plural = "Laporan PDLN"

    def __str__(self):
        return f"{self.pengajuan.kode} — Laporan ({self.get_status_display()})"


class PermohonanPembatalan(models.Model):
    """Permohonan pembatalan perjalanan (mekanisme interim,
    BISNIS_PROSES_PDLN.MD §4.5). Maksimal satu yang terbuka per pengajuan —
    ditegakkan di `pengajuan.pembatalan`, karena MySQL tidak mendukung
    conditional unique constraint."""

    class Status(models.TextChoices):
        MENUNGGU_UNOR = "menunggu_unor", "Menunggu Admin Unor"
        MENUNGGU_PAKLN = "menunggu_pakln", "Menunggu Biro PAKLN"
        DISETUJUI = "disetujui", "Disetujui"
        DITOLAK = "ditolak", "Ditolak"
        DITARIK = "ditarik", "Ditarik"

    STATUS_TERBUKA = (Status.MENUNGGU_UNOR, Status.MENUNGGU_PAKLN)

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="permohonan_pembatalan")
    diajukan_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    diajukan_role = models.CharField(max_length=20)
    alasan = models.TextField("Alasan Pembatalan")
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    status_pengajuan_saat_diajukan = models.CharField(max_length=20, choices=Pengajuan.Status.choices)

    unor_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    unor_waktu = models.DateTimeField(null=True, blank=True)
    unor_catatan = models.TextField(blank=True)
    pakln_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    pakln_waktu = models.DateTimeField(null=True, blank=True)
    pakln_catatan = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["pengajuan", "status"])]
        verbose_name = "Permohonan Pembatalan"
        verbose_name_plural = "Permohonan Pembatalan"

    def __str__(self):
        return f"{self.pengajuan.kode} — Pembatalan ({self.get_status_display()})"

    @property
    def terbuka(self):
        return self.status in self.STATUS_TERBUKA
