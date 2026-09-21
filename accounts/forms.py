from django import forms
from django.contrib.auth.password_validation import validate_password

from paspor.models import UnitOrganisasi

from .models import PegawaiProfile, User


class TambahUserForm(forms.Form):
    """Form pembuatan user baru oleh Admin Biro PAKLN.

    Mendukung dua peran: Pegawai (butuh data kepegawaian pada
    PegawaiProfile) dan Admin Unor (cukup akun login).
    """

    ROLE_CHOICES = [
        (User.Role.PEGAWAI, "Pegawai"),
        (User.Role.ADMIN_UNOR, "Admin Unor"),
    ]

    # --- Akun ---
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={"id": "id_role"}),
        label="Peran",
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "cth. budi.santoso"}),
    )
    nama = forms.CharField(
        max_length=150,
        label="Nama Lengkap",
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "cth. Budi Santoso, S.T."}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Minimal 8 karakter"}),
    )
    password_konfirmasi = forms.CharField(
        label="Konfirmasi Password",
        widget=forms.PasswordInput(attrs={"class": "input"}),
    )
    # Unit Organisasi wajib untuk kedua peran: Pegawai (disimpan pada
    # PegawaiProfile) maupun Admin Unor (menentukan cakupan pengajuan yang
    # boleh diproses). Referensi ke tabel org_units.
    unit_organisasi = forms.ModelChoiceField(
        queryset=UnitOrganisasi.objects.all(),
        label="Unit Organisasi",
        empty_label="— Pilih unit organisasi —",
    )

    # Unit Kerja wajib untuk kedua peran (teks bebas).
    unit_kerja = forms.CharField(
        max_length=150, label="Unit Kerja",
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "cth. Direktorat Bina Teknik Sumber Daya Air"}),
    )

    # --- Data kepegawaian (khusus role Pegawai) ---
    nip = forms.CharField(
        max_length=20, required=False, label="NIP",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    jabatan = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    pangkat_golongan = forms.CharField(
        max_length=100, required=False, label="Pangkat/Golongan",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    sisa_cuti_tahun_berjalan = forms.IntegerField(
        required=False, min_value=0, initial=12, label="Sisa Cuti Tahun Berjalan (hari)",
        widget=forms.NumberInput(attrs={"class": "input"}),
    )

    PEGAWAI_FIELDS = ["nip", "jabatan", "pangkat_golongan"]

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Username sudah digunakan.")
        return username

    def clean_nip(self):
        nip = (self.cleaned_data.get("nip") or "").strip()
        if nip and PegawaiProfile.objects.filter(nip=nip).exists():
            raise forms.ValidationError("NIP sudah terdaftar.")
        return nip

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        konfirmasi = cleaned.get("password_konfirmasi")
        if password:
            try:
                validate_password(password)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
            if konfirmasi and password != konfirmasi:
                self.add_error("password_konfirmasi", "Konfirmasi password tidak cocok.")

        if cleaned.get("role") == User.Role.PEGAWAI:
            for field in self.PEGAWAI_FIELDS:
                if not (cleaned.get(field) or "").strip():
                    self.add_error(field, "Wajib diisi untuk role Pegawai.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        nama = data["nama"].strip()
        depan, _, belakang = nama.partition(" ")

        unit_organisasi = data["unit_organisasi"]
        unit_kerja = data["unit_kerja"].strip()
        user = User(
            username=data["username"],
            role=data["role"],
            first_name=depan[:150],
            last_name=belakang[:150],
            unit_kerja=unit_kerja,
            unit_organisasi=unit_organisasi,
        )
        user.set_password(data["password"])
        user.save()

        if user.role == User.Role.PEGAWAI:
            PegawaiProfile.objects.create(
                user=user,
                nip=data["nip"].strip(),
                nama=nama,
                jabatan=data["jabatan"].strip(),
                pangkat_golongan=data["pangkat_golongan"].strip(),
                unit_kerja=unit_kerja,
                unit_organisasi=unit_organisasi,
                sisa_cuti_tahun_berjalan=data.get("sisa_cuti_tahun_berjalan") or 12,
            )
        return user


class EditUserForm(forms.Form):
    """Form penyuntingan user (Pegawai / Admin Unor) oleh Admin Biro PAKLN.

    Peran tidak dapat diubah lewat form ini — ganti peran berarti membuat
    ulang/menghapus PegawaiProfile, di luar cakupan edit sederhana.
    Password hanya diganti jika diisi."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    nama = forms.CharField(
        max_length=150,
        label="Nama Lengkap",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    is_active = forms.BooleanField(required=False, label="Akun aktif")
    unit_organisasi = forms.ModelChoiceField(
        queryset=UnitOrganisasi.objects.all(),
        label="Unit Organisasi",
        empty_label="— Pilih unit organisasi —",
    )
    unit_kerja = forms.CharField(
        max_length=150, label="Unit Kerja",
        widget=forms.TextInput(attrs={"class": "input"}),
    )

    # --- Data kepegawaian (khusus role Pegawai) ---
    nip = forms.CharField(
        max_length=20, required=False, label="NIP",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    jabatan = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    pangkat_golongan = forms.CharField(
        max_length=100, required=False, label="Pangkat/Golongan",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    sisa_cuti_tahun_berjalan = forms.IntegerField(
        required=False, min_value=0, label="Sisa Cuti Tahun Berjalan (hari)",
        widget=forms.NumberInput(attrs={"class": "input"}),
    )

    # --- Password (opsional) ---
    password_baru = forms.CharField(
        required=False, label="Password Baru",
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Kosongkan jika tidak diubah"}),
    )
    password_baru_konfirmasi = forms.CharField(
        required=False, label="Konfirmasi Password Baru",
        widget=forms.PasswordInput(attrs={"class": "input"}),
    )

    PEGAWAI_FIELDS = ["nip", "jabatan", "pangkat_golongan"]

    def __init__(self, *args, instance, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Username sudah digunakan.")
        return username

    def clean_nip(self):
        nip = (self.cleaned_data.get("nip") or "").strip()
        if nip and PegawaiProfile.objects.filter(nip=nip).exclude(user=self.instance).exists():
            raise forms.ValidationError("NIP sudah terdaftar.")
        return nip

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password_baru")
        konfirmasi = cleaned.get("password_baru_konfirmasi")
        if password or konfirmasi:
            if password:
                try:
                    validate_password(password, user=self.instance)
                except forms.ValidationError as exc:
                    self.add_error("password_baru", exc)
            if password != konfirmasi:
                self.add_error("password_baru_konfirmasi", "Konfirmasi password tidak cocok.")

        if self.instance.role == User.Role.PEGAWAI:
            for field in self.PEGAWAI_FIELDS:
                if not (cleaned.get(field) or "").strip():
                    self.add_error(field, "Wajib diisi untuk role Pegawai.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        nama = data["nama"].strip()
        depan, _, belakang = nama.partition(" ")
        unit_organisasi = data["unit_organisasi"]
        unit_kerja = data["unit_kerja"].strip()

        user = self.instance
        user.username = data["username"]
        user.first_name = depan[:150]
        user.last_name = belakang[:150]
        user.is_active = data["is_active"]
        user.unit_kerja = unit_kerja
        user.unit_organisasi = unit_organisasi
        if data.get("password_baru"):
            user.set_password(data["password_baru"])
        user.save()

        if user.role == User.Role.PEGAWAI:
            PegawaiProfile.objects.update_or_create(
                user=user,
                defaults={
                    "nip": data["nip"].strip(),
                    "nama": nama,
                    "jabatan": data["jabatan"].strip(),
                    "pangkat_golongan": data["pangkat_golongan"].strip(),
                    "unit_kerja": unit_kerja,
                    "unit_organisasi": unit_organisasi,
                    "sisa_cuti_tahun_berjalan": data.get("sisa_cuti_tahun_berjalan") or 0,
                },
            )
        return user
