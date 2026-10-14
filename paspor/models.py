from django.conf import settings
from django.db import models


class UnitOrganisasi(models.Model):
    """Unit organisasi eselon I Kementerian Pekerjaan Umum (tabel
    `org_units`). Dipakai sebagai referensi untuk cakupan kerja Admin Unor
    dan data kepegawaian pegawai."""

    code = models.CharField("Kode", max_length=2, unique=True)
    alias = models.CharField("Alias", max_length=20)
    name = models.CharField("Nama", max_length=150)

    class Meta:
        db_table = "org_units"
        ordering = ["code"]
        verbose_name = "Unit Organisasi"
        verbose_name_plural = "Unit Organisasi"

    def __str__(self):
        return f"{self.alias} — {self.name}"


class Negara(models.Model):
    """Data referensi negara tujuan perjalanan luar negeri. Dikelola oleh
    Admin Biro PAKLN (menu Manajemen Negara) dan dipakai sebagai sumber
    pilihan pada field "Tujuan Negara" di Formulir Pengajuan."""

    nama_negara = models.CharField("Nama Negara", max_length=100, unique=True)
    kode_negara = models.CharField(
        "Kode Negara", max_length=5, blank=True,
        help_text="Opsional, mis. kode ISO 3166-1 alpha-2 (ID, SA, SG, dst.)",
    )
    is_active = models.BooleanField("Aktif", default=True)
    # Penentu wajib/opsionalnya Rekomendasi Visa pada PDLN
    # (wiki/instructions/BISNIS_PROSES_PDLN.MD §6.4).
    perlu_visa = models.BooleanField(
        "Memerlukan Visa", default=False,
        help_text="Centang bila perjalanan dinas ke negara ini memerlukan visa — "
                  "Rekomendasi Visa menjadi dokumen wajib pada PDLN.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nama_negara"]
        verbose_name = "Negara"
        verbose_name_plural = "Negara"

    def __str__(self):
        return self.nama_negara


class SumberPembiayaan(models.Model):
    """Data referensi sumber pembiayaan perjalanan luar negeri. Dikelola
    oleh Admin Biro PAKLN (menu Manajemen Sumber Pembiayaan) dan dipakai
    sebagai sumber pilihan pada field "Sumber Pembiayaan" di Formulir
    Pengajuan. `tipe_perjalanan` membedakan untuk alur Non-Kedinasan yang
    sudah berjalan dan alur PDLN (Perjalanan Dinas Luar Negeri) yang akan
    menyusul."""

    class TipePerjalanan(models.TextChoices):
        PDLN = "PDLN", "PDLN (Perjalanan Dinas Luar Negeri)"
        NON_DINAS = "Non-Dinas", "Non-Dinas"

    tipe_perjalanan = models.CharField(
        "Tipe Perjalanan", max_length=20, choices=TipePerjalanan.choices,
        default=TipePerjalanan.NON_DINAS,
    )
    nama = models.CharField("Nama", max_length=100)
    # Daftar kode tipe PDLN yang boleh memakai sumber ini (mis. ["T2P"]);
    # kosong = berlaku untuk semua tipe PDLN. Diabaikan untuk Non-Dinas.
    tipe_pdln = models.JSONField("Berlaku untuk Tipe PDLN", default=list, blank=True)
    keterangan = models.TextField("Keterangan", blank=True)
    is_active = models.BooleanField("Aktif", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tipe_perjalanan", "nama"]
        verbose_name = "Sumber Pembiayaan"
        verbose_name_plural = "Sumber Pembiayaan"

    def __str__(self):
        return self.nama


class KategoriPerjalanan(models.Model):
    """Data referensi kategori perjalanan luar negeri. Dikelola oleh Admin
    Biro PAKLN (menu Manajemen Kategori Perjalanan) dan dipakai sebagai
    sumber pilihan pada field "Kategori Perjalanan" di Formulir Pengajuan
    (dikelompokkan pada dropdown berdasarkan `jenis_perjalanan`)."""

    class JenisPerjalanan(models.TextChoices):
        PDLN = "PDLN", "PDLN (Perjalanan Dinas Luar Negeri)"
        NON_DINAS = "Non-Dinas", "Perjalanan Non Dinas Luar Negeri"

    jenis_perjalanan = models.CharField(
        "Jenis Perjalanan", max_length=20, choices=JenisPerjalanan.choices,
        default=JenisPerjalanan.NON_DINAS,
    )
    nama_kategori = models.CharField("Nama Kategori", max_length=100)
    # Daftar kode tipe PDLN yang memakai kategori ini (mis. ["T1", "T3"]);
    # kosong = berlaku untuk semua tipe PDLN. Diabaikan untuk Non-Dinas.
    tipe_pdln = models.JSONField("Berlaku untuk Tipe PDLN", default=list, blank=True)
    is_active = models.BooleanField("Aktif", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["jenis_perjalanan", "nama_kategori"]
        verbose_name = "Kategori Perjalanan"
        verbose_name_plural = "Kategori Perjalanan"

    def __str__(self):
        return self.nama_kategori


class HariLibur(models.Model):
    """Tanggal merah (libur nasional / cuti bersama) yang dikecualikan dari
    perhitungan Jumlah Hari Kerja pada Formulir Pengajuan. Dikelola Admin
    Biro PAKLN (menu Setting Kalender). Sabtu & Minggu TIDAK perlu diinput
    di sini — sudah otomatis dianggap bukan hari kerja (lihat
    `paspor.kalender`)."""

    class Jenis(models.TextChoices):
        LIBUR_NASIONAL = "libur_nasional", "Libur Nasional"
        CUTI_BERSAMA = "cuti_bersama", "Cuti Bersama"

    tanggal = models.DateField("Tanggal", unique=True)
    keterangan = models.CharField("Keterangan", max_length=150)
    jenis = models.CharField(
        "Jenis", max_length=20, choices=Jenis.choices, default=Jenis.LIBUR_NASIONAL,
    )
    is_active = models.BooleanField("Aktif", default=True)

    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tanggal"]
        verbose_name = "Hari Libur"
        verbose_name_plural = "Hari Libur"

    def __str__(self):
        return f"{self.tanggal:%d-%m-%Y} — {self.keterangan}"


def berlaku_untuk_tipe(obj, tipe):
    """True bila master Kategori/Sumber berlaku untuk kode tipe PDLN
    `tipe` (daftar kosong = semua tipe)."""
    return not obj.tipe_pdln or tipe in obj.tipe_pdln


# ---------------------------------------------------------------------------
# Kegiatan PDLN (wiki/instructions/EVENT_IMPLEMENTATION_PLAN.MD)
# ---------------------------------------------------------------------------

# Tipe PDLN yang boleh dibuat Admin BPSDM (aturan B10a).
TIPE_KEGIATAN_BPSDM = ("T2P", "T2L")


def kategori_pendidikan(kategori):
    """Kategori pendidikan = kategori yang tegas berlaku untuk T2P."""
    return "T2P" in (kategori.tipe_pdln or [])


def kategori_untuk_bpsdm(kategori):
    """Kategori yang boleh dipakai Admin BPSDM: tegas berlaku T2P/T2L saja."""
    tipe = kategori.tipe_pdln or []
    return bool(tipe) and all(t in TIPE_KEGIATAN_BPSDM for t in tipe)


class KegiatanQuerySet(models.QuerySet):
    def dapat_dipilih(self, tipe=None, kategori=None):
        """Kegiatan yang boleh dipilih pegawai (B2, B14, §7.5): disetujui,
        aktif, belum lewat, punya kategori & skema; opsional disaring tipe
        PDLN dan/atau kategori. Penyaringan tipe dilakukan di Python karena
        `tipe_pdln` berupa JSON list."""
        from django.utils import timezone

        qs = (
            self.filter(status=Kegiatan.Status.DISETUJUI, is_active=True, tgl_selesai__gte=timezone.localdate())
            .filter(kategori__isnull=False, skema_pendanaan__isnull=False)
            .distinct()
        )
        if kategori is not None:
            qs = qs.filter(kategori=kategori)
        if tipe:
            ids = [k.pk for k in qs.prefetch_related("kategori") if k.berlaku_untuk_tipe(tipe)]
            qs = self.model.objects.filter(pk__in=ids)
        return qs


class Kegiatan(models.Model):
    """Kegiatan di luar negeri yang menjadi tujuan PDLN — dikelola Admin
    Biro PAKLN, dapat diusulkan Pegawai (semua kategori) atau Admin BPSDM
    (pendidikan & pelatihan) dan baru dapat dipilih setelah disetujui."""

    class Status(models.TextChoices):
        MENUNGGU = "menunggu", "Menunggu Persetujuan"
        DISETUJUI = "disetujui", "Disetujui"
        DITOLAK = "ditolak", "Ditolak"

    class SumberData(models.TextChoices):
        MANUAL = "manual", "Dibuat Admin Biro PAKLN"
        USULAN_PEGAWAI = "usulan_pegawai", "Usulan Pegawai"
        USULAN_BPSDM = "usulan_bpsdm", "Usulan Admin BPSDM"
        PINTAR = "pintar", "Aplikasi PINTAR"

    nama = models.CharField("Nama Kegiatan", max_length=255)
    deskripsi = models.TextField("Deskripsi", blank=True)
    negara = models.ManyToManyField(Negara, related_name="kegiatan_list", verbose_name="Negara")
    kota = models.CharField("Kota", max_length=255)
    penyelenggara = models.CharField("Penyelenggara", max_length=200)
    tgl_mulai = models.DateField("Tanggal Mulai Kegiatan")
    tgl_selesai = models.DateField("Tanggal Selesai Kegiatan")
    tahun_pelaksanaan = models.PositiveSmallIntegerField("Tahun Pelaksanaan")
    kategori = models.ManyToManyField(KategoriPerjalanan, related_name="kegiatan_list", verbose_name="Kategori")
    skema_pendanaan = models.ManyToManyField(
        SumberPembiayaan, related_name="kegiatan_list", verbose_name="Skema Pendanaan",
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DISETUJUI)
    is_active = models.BooleanField("Aktif", default=True)
    sumber_data = models.CharField(max_length=20, choices=SumberData.choices, default=SumberData.MANUAL)
    # ID kegiatan/beasiswa di Aplikasi PINTAR — kunci sinkron (§7.5). NULL
    # (bukan string kosong) agar unique tetap berlaku hanya untuk yang terisi.
    kode_pintar = models.CharField("Kode PINTAR", max_length=50, null=True, blank=True, unique=True)

    diusulkan_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="kegiatan_diusulkan",
    )
    diputus_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    tgl_diputus = models.DateTimeField(null=True, blank=True)
    catatan_keputusan = models.TextField("Catatan Keputusan", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = KegiatanQuerySet.as_manager()

    class Meta:
        ordering = ["-tgl_mulai", "nama"]
        indexes = [
            models.Index(fields=["status", "is_active"]),
            models.Index(fields=["tahun_pelaksanaan"]),
        ]
        verbose_name = "Kegiatan"
        verbose_name_plural = "Kegiatan"

    def __str__(self):
        return f"{self.nama} ({self.tahun_pelaksanaan})"

    @property
    def is_pendidikan(self):
        return any(kategori_pendidikan(k) for k in self.kategori.all())

    @property
    def label_penyelenggara(self):
        return "Universitas" if self.is_pendidikan else "Penyelenggara"

    def berlaku_untuk_tipe(self, tipe):
        return any(berlaku_untuk_tipe(k, tipe) for k in self.kategori.all())

    @property
    def negara_display(self):
        return ", ".join(n.nama_negara for n in self.negara.all())

    @property
    def dapat_dipilih(self):
        from django.utils import timezone

        return (
            self.status == self.Status.DISETUJUI and self.is_active
            and self.tgl_selesai >= timezone.localdate()
            and self.kategori.exists() and self.skema_pendanaan.exists()
        )

    @property
    def label_opsi(self):
        """Teks opsi pada field Kegiatan di Formulir PDLN."""
        return f"{self.nama} — {self.penyelenggara}, {self.kota} ({self.tgl_mulai:%d %b %Y} – {self.tgl_selesai:%d %b %Y})"


def dasar_kegiatan_path(instance, filename):
    return f"kegiatan/{instance.kegiatan_id}/dasar/{filename}"


class DasarKegiatan(models.Model):
    """Bukti/rujukan resmi keberadaan kegiatan (aturan B15) — minimal satu
    per kegiatan."""

    class Jenis(models.TextChoices):
        SURAT = "surat", "Surat"
        TAUTAN = "tautan", "Tautan"
        PINTAR = "pintar", "Aplikasi PINTAR"
        LAINNYA = "lainnya", "Lainnya"

    # Field yang wajib terisi per jenis.
    FIELD_WAJIB = {
        Jenis.SURAT: ("nomor_surat", "Nomor surat wajib diisi."),
        Jenis.TAUTAN: ("tautan", "Tautan wajib diisi."),
        Jenis.PINTAR: ("kode_pintar", "Kode PINTAR wajib diisi."),
        Jenis.LAINNYA: ("keterangan", "Keterangan wajib diisi."),
    }

    kegiatan = models.ForeignKey(Kegiatan, on_delete=models.CASCADE, related_name="dasar_list")
    jenis = models.CharField(max_length=10, choices=Jenis.choices)
    nomor_surat = models.CharField("Nomor Surat", max_length=100, blank=True)
    tgl_surat = models.DateField("Tanggal Surat", null=True, blank=True)
    tautan = models.URLField("Tautan", max_length=500, blank=True)
    kode_pintar = models.CharField("Kode PINTAR", max_length=50, blank=True)
    berkas = models.FileField("Berkas", upload_to=dasar_kegiatan_path, blank=True)
    keterangan = models.CharField("Keterangan", max_length=255, blank=True)
    ditambahkan_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Dasar Kegiatan"
        verbose_name_plural = "Dasar Kegiatan"

    def __str__(self):
        return f"{self.get_jenis_display()}: {self.ringkas}"

    @property
    def ringkas(self):
        if self.jenis == self.Jenis.SURAT:
            return self.nomor_surat + (f" ({self.tgl_surat:%d %b %Y})" if self.tgl_surat else "")
        if self.jenis == self.Jenis.TAUTAN:
            return self.tautan
        if self.jenis == self.Jenis.PINTAR:
            return self.kode_pintar
        return self.keterangan

    def clean(self):
        from django.core.exceptions import ValidationError

        wajib = self.FIELD_WAJIB.get(self.jenis)
        if wajib and not (getattr(self, wajib[0]) or "").strip():
            raise ValidationError({wajib[0]: wajib[1]})
