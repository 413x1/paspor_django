"""
Sinkronisasi data kepegawaian dari e-HRM ke PASPOR (AB-02, AB-18).
Klien API ada di `paspor/integrasi/ehrm.py`.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from paspor.integrasi.ehrm import DataPegawai
from paspor.models import UnitOrganisasi

from .models import PegawaiProfile, PeranUser, User
from .validators import normalisasi_no_hp

logger = logging.getLogger(__name__)


def _unit(kode):
    if not kode:
        return None
    unit = UnitOrganisasi.objects.filter(code=kode).first()
    if unit is None:
        logger.warning("Kode unit organisasi e-HRM %r tidak dikenal; unit lama dipertahankan.", kode)
    return unit


def _no_hp(data):
    try:
        return normalisasi_no_hp(data.no_hp)
    except ValidationError:
        logger.warning("Nomor HP e-HRM untuk NIP %s tidak valid; diabaikan.", data.nip)
        return ""


def sinkron_profil(user, data: DataPegawai) -> list[str]:
    """Perbarui PegawaiProfile + User dari data e-HRM. Kembalikan daftar field
    yang berubah (untuk log). Email/no_hp dilewati bila `*_dikunci`; nilai
    e-HRM yang kosong/tidak valid tidak menimpa nilai lama."""
    berubah = []
    unit = _unit(data.kode_unit_organisasi)

    with transaction.atomic():
        profile = PegawaiProfile.objects.filter(user=user).first()
        if profile is None:
            profile = PegawaiProfile(user=user, nip=data.nip)
            berubah.append("profil")
        nilai_profil = {
            "nip": data.nip,
            "nama": data.nama,
            "jabatan": data.jabatan,
            "pangkat_golongan": data.pangkat_golongan,
            "unit_kerja": data.unit_kerja,
        }
        for field, nilai in nilai_profil.items():
            if nilai and getattr(profile, field) != nilai:
                setattr(profile, field, nilai)
                berubah.append(field)
        if unit and profile.unit_organisasi_id != unit.pk:
            profile.unit_organisasi = unit
            berubah.append("unit_organisasi")
        profile.save()

        depan, _, belakang = data.nama.partition(" ")
        if data.nama and (user.first_name, user.last_name) != (depan[:150], belakang[:150]):
            user.first_name, user.last_name = depan[:150], belakang[:150]
        if data.unit_kerja:
            user.unit_kerja = data.unit_kerja
        if unit:
            user.unit_organisasi = unit
        if data.email and not user.email_dikunci and user.email != data.email:
            if User.objects.filter(email__iexact=data.email).exclude(pk=user.pk).exists():
                logger.warning("Email e-HRM %s sudah dipakai akun lain; diabaikan.", data.email)
            else:
                user.email = data.email
                berubah.append("email")
        no_hp = _no_hp(data)
        if no_hp and not user.no_hp_dikunci and user.no_hp != no_hp:
            user.no_hp = no_hp
            berubah.append("no_hp")
        user.ehrm_sinkron_at = timezone.now()
        user.save()

        # AB-08: setiap pegawai e-HRM memiliki role Pegawai.
        peran, dibuat = PeranUser.objects.get_or_create(user=user, role=User.Role.PEGAWAI)
        if not dibuat and not peran.is_active:
            peran.is_active = True
            peran.save(update_fields=["is_active"])
        user.reset_cache_peran()
    return berubah


def _username_tersedia(dasar):
    username, n = dasar, 0
    while User.objects.filter(username__iexact=username).exists():
        n += 1
        username = f"{dasar}-{n}"
    return username


def buat_user_dari_ehrm(data: DataPegawai, *, sso_sub=None) -> User:
    """User(sumber_akun=SSO, username=NIP, password unusable) + PegawaiProfile
    + PeranUser(pegawai). `sso_sub` kosong = pra-daftar (ditautkan saat login
    SSO pertama berdasarkan NIP)."""
    with transaction.atomic():
        user = User(
            username=_username_tersedia(data.nip),
            role=User.Role.PEGAWAI,
            sso_sub=sso_sub or None,
            sumber_akun=User.SumberAkun.SSO,
        )
        user.set_unusable_password()
        user.save()
        sinkron_profil(user, data)
    return user
