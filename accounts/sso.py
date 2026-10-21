"""
Login SSO — alur inti yang TIDAK bergantung pada protokol
(IMPROVEMENT_PLAN_19102026.MD §4 & §9.1). Adaptor protokol (OIDC/SAML/CAS,
menunggu Q1) cukup memvalidasi respons penyedia lalu memanggil
`masuk_dari_sso(request, sub=..., nip=..., klaim=...)`.
"""

import logging

from django.contrib.auth import login
from django.contrib.auth.backends import BaseBackend
from django.db import transaction

from logs.models import ActivityLog
from logs.utils import record_activity
from paspor.integrasi import ehrm

from .ehrm_sync import buat_user_dari_ehrm, sinkron_profil
from .models import User

logger = logging.getLogger(__name__)

BACKEND = "accounts.sso.SsoBackend"


class SsoGagal(Exception):
    """Login SSO ditolak. Pesannya aman untuk ditampilkan ke pengguna."""


class SsoBackend(BaseBackend):
    """Backend minimal agar sesi user yang masuk lewat SSO dikenali.
    `authenticate` selalu None: identitas sudah divalidasi adaptor protokol."""

    def authenticate(self, request, **kwargs):
        return None

    def get_user(self, user_id):
        return User.objects.filter(pk=user_id, is_active=True).first()


def _cari_atau_buat(sub, nip):
    """Langkah 1–3: cari user by `sso_sub`, tautkan user lama by NIP, atau buat
    user baru dari e-HRM. Mengembalikan `(user, baru)`."""
    user = User.objects.filter(sso_sub=sub).first()
    if user:
        return user, False

    if nip:
        user = User.objects.filter(profile__nip=nip).first()
        if user:
            if user.sso_sub and user.sso_sub != sub:
                raise SsoGagal("Akun dengan NIP ini sudah tertaut ke identitas SSO lain. Hubungi Admin Biro PAKLN.")
            # Tautkan akun lama; password lama (bila ada) tetap berlaku.
            user.sso_sub = sub
            user.sumber_akun = User.SumberAkun.SSO
            user.save(update_fields=["sso_sub", "sumber_akun"])
            return user, False

    if not nip:
        raise SsoGagal("Identitas SSO tidak memuat NIP. Hubungi Admin Biro PAKLN.")
    try:
        data = ehrm.ambil_pegawai(nip)
    except ehrm.EhrmTidakTersedia as exc:
        raise SsoGagal("Data kepegawaian tidak dapat diambil, coba lagi nanti.") from exc
    if data is None:
        raise SsoGagal("NIP Anda tidak ditemukan di e-HRM. Hubungi Admin Biro PAKLN.")
    return buat_user_dari_ehrm(data, sso_sub=sub), True


def masuk_dari_sso(request, *, sub: str, nip: str, klaim: dict) -> User:
    """
    1. User by sso_sub → ada: lanjut ke 4.
    2. User by profile__nip=nip → ada: tautkan (sso_sub=sub, sumber_akun=SSO).
    3. Tidak ada: data = ehrm.ambil_pegawai(nip); None/EhrmTidakTersedia → SsoGagal;
       user = buat_user_dari_ehrm(data, sso_sub=sub).
    4. user.is_active False → SsoGagal("Akun dinonaktifkan").
    5. Sinkron e-HRM (user lama: tangkap EhrmTidakTersedia → log, lanjut).
    6. login(request, user, backend=SsoBackend); log auth.login_sso.
    """
    sub = (sub or "").strip()
    nip = (nip or "").strip()
    if not sub:
        raise SsoGagal("Respons SSO tidak valid.")

    with transaction.atomic():
        user, baru = _cari_atau_buat(sub, nip)

    if not user.is_active:
        record_activity(
            request, ActivityLog.Aktivitas.LOGIN_GAGAL, "Login SSO ditolak: akun nonaktif",
            status=ActivityLog.Status.GAGAL, username=user.username,
        )
        raise SsoGagal("Akun Anda dinonaktifkan. Hubungi Admin Biro PAKLN.")

    if not baru:
        nip_sinkron = nip or getattr(getattr(user, "profile", None), "nip", "")
        try:
            data = ehrm.ambil_pegawai(nip_sinkron) if nip_sinkron else None
        except ehrm.EhrmTidakTersedia:
            data = None
            record_activity(
                request, ActivityLog.Aktivitas.SINKRON_EHRM_GAGAL,
                "Sinkronisasi e-HRM saat login SSO gagal; memakai data terakhir",
                status=ActivityLog.Status.GAGAL, user=user, target_type="user", target_id=user.pk,
            )
        if data is not None:
            sinkron_profil(user, data)

    login(request, user, backend=BACKEND)
    record_activity(request, ActivityLog.Aktivitas.LOGIN_SSO, "Login lewat SSO", user=user)
    return user
