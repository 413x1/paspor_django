import re

from django import forms
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from paspor.models import UnitOrganisasi

from .models import PegawaiProfile, PeranUser, User
from .validators import normalisasi_no_hp

PESAN_EMAIL_DIPAKAI = "Email sudah digunakan akun lain."


def _input(**attrs):
    return forms.TextInput(attrs={"class": "input", **attrs})


def _email_unik(email, kecuali=None):
    """Email unik tanpa membedakan huruf besar/kecil, bila diisi (AB-20)."""
    email = (email or "").strip()
    if email:
        qs = User.objects.filter(email__iexact=email)
        if kecuali is not None:
            qs = qs.exclude(pk=kecuali.pk)
        if qs.exists():
            raise forms.ValidationError(PESAN_EMAIL_DIPAKAI)
    return email


def _no_hp_wajib(nilai):
    nomor = normalisasi_no_hp(nilai)
    if not nomor:
        raise forms.ValidationError("Nomor HP wajib diisi.")
    return nomor


class KontakForm(forms.Form):
    """Email & nomor HP — hanya diproses untuk Admin Biro PAKLN: di Profil
    miliknya sendiri, dan (lewat EditUserForm) milik user lain (AB-16, AB-17)."""

    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "input"}))
    no_hp = forms.CharField(
        max_length=25, label="Nomor HP (WhatsApp)",
        widget=_input(placeholder="cth. 0812-3456-7890", inputmode="tel"),
    )

    def __init__(self, *args, instance, **kwargs):
        self.instance = instance
        kwargs.setdefault("initial", {"email": instance.email, "no_hp": instance.no_hp})
        super().__init__(*args, **kwargs)

    def clean_email(self):
        return _email_unik(self.cleaned_data["email"], kecuali=self.instance)

    def clean_no_hp(self):
        return _no_hp_wajib(self.cleaned_data["no_hp"])

    def perubahan(self):
        """{field: (lama, baru)} untuk field yang berubah."""
        user = self.instance
        return {
            f: (getattr(user, f), self.cleaned_data[f])
            for f in ("email", "no_hp")
            if getattr(user, f) != self.cleaned_data[f]
        }

    def save(self, *, kunci=False):
        """Simpan kontak. `kunci=True`: field yang berubah dikunci agar tidak
        ditimpa sinkronisasi e-HRM (AB-18). Mengembalikan `perubahan()`."""
        user = self.instance
        berubah = self.perubahan()
        for field, (_, baru) in berubah.items():
            setattr(user, field, baru)
            if kunci:
                setattr(user, f"{field}_dikunci", True)
        if berubah:
            user.save()
        return berubah


class TambahUserForm(forms.Form):
    """Pembuatan AKUN LOKAL oleh Admin Biro PAKLN (AB-05, Q6): Admin Biro
    PAKLN dan akun admin darurat (Admin Unor/BPSDM/BKO) yang login dengan
    username & password. Pegawai tidak dibuat manual — gunakan pra-daftar via
    NIP (data e-HRM) atau login SSO. Akun admin darurat tidak memiliki role
    Pegawai."""

    ROLE_CHOICES = [
        (User.Role.ADMIN_UNOR, "Admin Unor"),
        (User.Role.ADMIN_BPSDM, "Admin BPSDM"),
        (User.Role.ADMIN_BKO, "Admin BKO"),
        (User.Role.ADMIN_PAKLN, "Admin Biro PAKLN"),
    ]

    # --- Akun ---
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={"id": "id_role"}),
        label="Peran",
    )
    username = forms.CharField(max_length=150, widget=_input(placeholder="cth. budi.santoso"))
    nama = forms.CharField(
        max_length=150, label="Nama Lengkap", widget=_input(placeholder="cth. Budi Santoso, S.T."),
    )
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "input"}))
    no_hp = forms.CharField(
        max_length=25, label="Nomor HP (WhatsApp)",
        widget=_input(placeholder="cth. 0812-3456-7890", inputmode="tel"),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Minimal 8 karakter"}),
    )
    password_konfirmasi = forms.CharField(
        label="Konfirmasi Password",
        widget=forms.PasswordInput(attrs={"class": "input"}),
    )
    # Wajib untuk Admin Unor: menentukan cakupan pengajuan yang boleh diproses.
    unit_organisasi = forms.ModelChoiceField(
        queryset=UnitOrganisasi.objects.all(),
        required=False,
        label="Unit Organisasi",
        empty_label="— Pilih unit organisasi —",
    )
    unit_kerja = forms.CharField(
        max_length=150, label="Unit Kerja",
        widget=_input(placeholder="cth. Direktorat Bina Teknik Sumber Daya Air"),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Username sudah digunakan.")
        return username

    def clean_email(self):
        return _email_unik(self.cleaned_data["email"])

    def clean_no_hp(self):
        return _no_hp_wajib(self.cleaned_data["no_hp"])

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
        if cleaned.get("role") == User.Role.ADMIN_UNOR and not cleaned.get("unit_organisasi"):
            self.add_error("unit_organisasi", "Wajib diisi untuk Admin Unor.")
        return cleaned

    @transaction.atomic
    def save(self, diberikan_oleh=None):
        data = self.cleaned_data
        nama = data["nama"].strip()
        depan, _, belakang = nama.partition(" ")
        role = data["role"]
        unit = data.get("unit_organisasi")

        user = User(
            username=data["username"],
            role=role,
            first_name=depan[:150],
            last_name=belakang[:150],
            email=data["email"],
            no_hp=data["no_hp"],
            sumber_akun=User.SumberAkun.LOKAL,
            unit_kerja=data["unit_kerja"].strip(),
            unit_organisasi=unit,
        )
        user.set_password(data["password"])
        user.save()  # signal kompatibilitas membuat PeranUser; lengkapi di bawah
        PeranUser.objects.update_or_create(
            user=user, role=role,
            defaults={
                "unit_organisasi": unit if role == User.Role.ADMIN_UNOR else None,
                "diberikan_oleh": diberikan_oleh,
                "is_active": True,
            },
        )
        return user


class EditUserForm(forms.Form):
    """Penyuntingan user oleh Admin Biro PAKLN. Role diatur terpisah lewat
    `KelolaPeranForm`. Email & nomor HP yang diubah pada akun yang datanya
    bersumber dari e-HRM dikunci (AB-18). Data kepegawaian akun e-HRM tampil
    baca-saja (diperbarui lewat sinkronisasi)."""

    username = forms.CharField(max_length=150, widget=_input())
    nama = forms.CharField(max_length=150, label="Nama Lengkap", widget=_input())
    is_active = forms.BooleanField(required=False, label="Akun aktif")
    unit_organisasi = forms.ModelChoiceField(
        queryset=UnitOrganisasi.objects.all(),
        required=False,
        label="Unit Organisasi",
        empty_label="— Pilih unit organisasi —",
    )
    unit_kerja = forms.CharField(max_length=150, required=False, label="Unit Kerja", widget=_input())

    # --- Kontak (AB-17) ---
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "input"}))
    no_hp = forms.CharField(
        max_length=25, label="Nomor HP (WhatsApp)",
        widget=_input(placeholder="cth. 0812-3456-7890", inputmode="tel"),
    )
    buka_kunci_email = forms.BooleanField(required=False, label="Buka kunci email")
    buka_kunci_no_hp = forms.BooleanField(required=False, label="Buka kunci nomor HP")

    # --- Data kepegawaian (user yang memiliki PegawaiProfile) ---
    nip = forms.CharField(max_length=20, required=False, label="NIP", widget=_input())
    jabatan = forms.CharField(max_length=150, required=False, widget=_input())
    pangkat_golongan = forms.CharField(max_length=100, required=False, label="Pangkat/Golongan", widget=_input())
    sisa_cuti_tahun_berjalan = forms.IntegerField(
        required=False, min_value=0, label="Sisa Cuti Tahun Berjalan (hari)",
        widget=forms.NumberInput(attrs={"class": "input"}),
    )

    # --- Password ---
    password_baru = forms.CharField(
        required=False, label="Password Baru",
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Kosongkan jika tidak diubah"}),
    )
    password_baru_konfirmasi = forms.CharField(
        required=False, label="Konfirmasi Password Baru",
        widget=forms.PasswordInput(attrs={"class": "input"}),
    )
    hapus_password = forms.BooleanField(
        required=False, label="Hapus password (akun hanya bisa masuk lewat SSO)",
    )

    PEGAWAI_FIELDS = ["nip", "jabatan", "pangkat_golongan"]
    EHRM_FIELDS = ["nama", "nip", "jabatan", "pangkat_golongan", "unit_kerja", "unit_organisasi"]

    def __init__(self, *args, instance, **kwargs):
        self.instance = instance
        self.punya_profil = PegawaiProfile.objects.filter(user=instance).exists()
        super().__init__(*args, **kwargs)
        # Data kepegawaian akun e-HRM dikelola lewat sinkronisasi, bukan manual.
        self.data_ehrm_baca_saja = self.punya_profil and instance.tersinkron_ehrm()
        if self.data_ehrm_baca_saja:
            for name in self.EHRM_FIELDS:
                self.fields[name].disabled = True
                self.fields[name].required = False
        if not instance.email_dikunci:
            del self.fields["buka_kunci_email"]
        if not instance.no_hp_dikunci:
            del self.fields["buka_kunci_no_hp"]
        if not instance.punya_sso():
            del self.fields["hapus_password"]

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Username sudah digunakan.")
        return username

    def clean_email(self):
        return _email_unik(self.cleaned_data["email"], kecuali=self.instance)

    def clean_no_hp(self):
        return _no_hp_wajib(self.cleaned_data["no_hp"])

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
            if cleaned.get("hapus_password"):
                self.add_error("hapus_password", "Pilih salah satu: password baru atau hapus password.")
            if password:
                try:
                    validate_password(password, user=self.instance)
                except forms.ValidationError as exc:
                    self.add_error("password_baru", exc)
            if password != konfirmasi:
                self.add_error("password_baru_konfirmasi", "Konfirmasi password tidak cocok.")

        if self.punya_profil and not self.data_ehrm_baca_saja:
            for field in self.PEGAWAI_FIELDS:
                if not (cleaned.get(field) or "").strip():
                    self.add_error(field, "Wajib diisi untuk user dengan data kepegawaian.")
        return cleaned

    @transaction.atomic
    def save(self):
        """Simpan perubahan. Mengembalikan `(perubahan_kontak, kunci_dibuka)`:
        {field: (lama, baru)} dan daftar field kontak yang dibuka kuncinya."""
        data = self.cleaned_data
        user = self.instance
        kunci = user.tersinkron_ehrm()

        perubahan_kontak = {
            f: (getattr(user, f), data[f]) for f in ("email", "no_hp") if getattr(user, f) != data[f]
        }
        for field, (_, baru) in perubahan_kontak.items():
            setattr(user, field, baru)
            if kunci:
                setattr(user, f"{field}_dikunci", True)
        kunci_dibuka = []
        for field in ("email", "no_hp"):
            if data.get(f"buka_kunci_{field}") and field not in perubahan_kontak:
                setattr(user, f"{field}_dikunci", False)
                kunci_dibuka.append(field)

        user.username = data["username"]
        user.is_active = data["is_active"]
        if not self.data_ehrm_baca_saja:
            nama = data["nama"].strip()
            depan, _, belakang = nama.partition(" ")
            user.first_name = depan[:150]
            user.last_name = belakang[:150]
            user.unit_kerja = (data.get("unit_kerja") or "").strip()
            user.unit_organisasi = data.get("unit_organisasi")
        if data.get("password_baru"):
            user.set_password(data["password_baru"])
        elif data.get("hapus_password"):
            user.set_unusable_password()
        user.save()

        if self.punya_profil and not self.data_ehrm_baca_saja:
            PegawaiProfile.objects.filter(user=user).update(
                nip=data["nip"].strip(),
                nama=data["nama"].strip(),
                jabatan=data["jabatan"].strip(),
                pangkat_golongan=data["pangkat_golongan"].strip(),
                unit_kerja=user.unit_kerja,
                unit_organisasi=user.unit_organisasi,
                sisa_cuti_tahun_berjalan=data.get("sisa_cuti_tahun_berjalan") or 0,
            )
        elif self.punya_profil and data.get("sisa_cuti_tahun_berjalan") is not None:
            # Sisa cuti tetap dikelola PASPOR, juga untuk akun e-HRM.
            PegawaiProfile.objects.filter(user=user).update(
                sisa_cuti_tahun_berjalan=data["sisa_cuti_tahun_berjalan"],
            )
        return perubahan_kontak, kunci_dibuka


class KelolaPeranForm(forms.Form):
    """Bagian "Peran" di Edit User (AB-09). Role Pegawai tidak dicentang
    manual: otomatis dimiliki user yang memiliki PegawaiProfile. Mencabut
    role = `PeranUser.is_active=False` (baris tetap ada untuk jejak audit)."""

    PERAN_ADMIN = [
        (User.Role.ADMIN_UNOR, "Admin Unor"),
        (User.Role.ADMIN_BPSDM, "Admin BPSDM"),
        (User.Role.ADMIN_BKO, "Admin BKO"),
        (User.Role.ADMIN_PAKLN, "Admin Biro PAKLN"),
    ]

    admin_unor = forms.BooleanField(required=False, label="Admin Unor")
    unit_admin_unor = forms.ModelChoiceField(
        queryset=UnitOrganisasi.objects.all(),
        required=False,
        label="Unit organisasi yang dikelola",
        empty_label="— Pilih unit organisasi —",
    )
    admin_bpsdm = forms.BooleanField(required=False, label="Admin BPSDM")
    admin_bko = forms.BooleanField(required=False, label="Admin BKO")
    admin_pakln = forms.BooleanField(required=False, label="Admin Biro PAKLN")

    def __init__(self, *args, instance, oleh=None, **kwargs):
        self.instance = instance
        self.oleh = oleh
        self.punya_profil = PegawaiProfile.objects.filter(user=instance).exists()
        aktif = {p.role: p for p in instance.peran_list.filter(is_active=True)}
        self.peran_aktif = aktif
        if not args or args[0] is None:
            unor = aktif.get(User.Role.ADMIN_UNOR)
            initial = {role: role in aktif for role, _ in self.PERAN_ADMIN}
            initial["unit_admin_unor"] = (
                (unor.unit_organisasi_id or instance.unit_organisasi_id) if unor else None
            )
            kwargs.setdefault("initial", initial)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("admin_unor") and not cleaned.get("unit_admin_unor"):
            self.add_error("unit_admin_unor", "Admin Unor wajib memiliki unit organisasi.")
        if not self.punya_profil and not any(cleaned.get(role) for role, _ in self.PERAN_ADMIN):
            raise forms.ValidationError("User minimal harus memiliki satu peran.")
        if (
            self.oleh is not None and self.oleh.pk == self.instance.pk
            and User.Role.ADMIN_PAKLN in self.peran_aktif and not cleaned.get("admin_pakln")
        ):
            self.add_error("admin_pakln", "Anda tidak dapat mencabut peran Admin Biro PAKLN milik sendiri.")
        return cleaned

    @transaction.atomic
    def save(self):
        """Terapkan perubahan role. Mengembalikan `(diberikan, dicabut)` —
        daftar label role (untuk pesan & log)."""
        user = self.instance
        data = self.cleaned_data
        diinginkan = {role for role, _ in self.PERAN_ADMIN if data.get(role)}
        if self.punya_profil:
            diinginkan.add(User.Role.PEGAWAI)

        diberikan, dicabut = [], []
        for role in [r for r, _ in User.Role.choices]:
            peran = PeranUser.objects.filter(user=user, role=role).first()
            unit = data.get("unit_admin_unor") if role == User.Role.ADMIN_UNOR else None
            if role in diinginkan:
                if peran is None:
                    PeranUser.objects.create(user=user, role=role, unit_organisasi=unit, diberikan_oleh=self.oleh)
                    diberikan.append(User.Role(role).label)
                elif not peran.is_active or peran.unit_organisasi_id != getattr(unit, "pk", None):
                    if not peran.is_active:
                        diberikan.append(User.Role(role).label)
                    elif role == User.Role.ADMIN_UNOR:
                        diberikan.append(f"{User.Role(role).label} ({unit.alias})")
                    peran.is_active = True
                    peran.unit_organisasi = unit
                    peran.diberikan_oleh = self.oleh
                    peran.save(update_fields=["is_active", "unit_organisasi", "diberikan_oleh"])
            elif peran is not None and peran.is_active:
                peran.is_active = False
                peran.save(update_fields=["is_active"])
                dicabut.append(User.Role(role).label)

        user.reset_cache_peran()
        # Peran default (User.role) harus tetap peran yang dimiliki.
        sisa = user.daftar_peran()
        role_db = User.objects.filter(pk=user.pk).values_list("role", flat=True).first()
        if sisa and role_db not in sisa:
            User.objects.filter(pk=user.pk).update(role=sisa[0])
        return diberikan, dicabut


# ---------------------------------------------------------------------------
# Profil — akun mandiri (AB-03, AB-07, AB-16, AB-20, AB-21)
# ---------------------------------------------------------------------------

class UbahUsernameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username"]
        widgets = {"username": forms.TextInput(attrs={"class": "input", "autocomplete": "username"})}

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Username sudah digunakan.")
        # Jangan mengambil format NIP (18 digit) milik orang lain.
        if re.fullmatch(r"\d{18}", username):
            nip_sendiri = PegawaiProfile.objects.filter(user=self.instance).values_list("nip", flat=True).first()
            if username != nip_sendiri:
                raise forms.ValidationError("Username berupa 18 digit angka hanya boleh NIP Anda sendiri.")
        return username


class _PasswordInputMixin:
    def _gaya_input(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")


class AturPasswordForm(_PasswordInputMixin, SetPasswordForm):
    """Atur password pertama kali (akun SSO tanpa password) — tanpa password
    lama, karena pengguna sudah terautentikasi lewat SSO (AB-21)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gaya_input()


class GantiPasswordForm(_PasswordInputMixin, PasswordChangeForm):
    """Ganti password yang sudah ada — wajib password lama (AB-21)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gaya_input()


class HapusPasswordForm(forms.Form):
    """Hapus password (kembali ke SSO saja) — khusus akun yang tertaut SSO
    agar akun lokal tidak terkunci (AB-07)."""

    password_lama = forms.CharField(
        label="Password saat ini",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "current-password"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password_lama(self):
        password = self.cleaned_data["password_lama"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Password saat ini salah.")
        return password

    def save(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        return self.user


class PraDaftarForm(forms.Form):
    """Pra-daftar pegawai via NIP (data ditarik dari e-HRM) — berguna untuk
    memberi role admin sebelum orangnya login SSO pertama kali."""

    nip = forms.CharField(max_length=20, label="NIP", widget=_input(placeholder="18 digit NIP", inputmode="numeric"))

    def clean_nip(self):
        nip = self.cleaned_data["nip"].strip()
        if not nip.isdigit():
            raise forms.ValidationError("NIP hanya berisi angka.")
        if PegawaiProfile.objects.filter(nip=nip).exists():
            raise forms.ValidationError("NIP sudah terdaftar di PASPOR.")
        return nip
