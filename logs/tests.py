from unittest import mock

from django.db import transaction
from django.test import RequestFactory, TestCase, override_settings

from accounts.models import User

from .models import ActivityLog
from .utils import record_activity


class RecordActivityTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.user = User.objects.create_user(username="uji.log", password="x", role="pegawai")

    def _request(self, **extra):
        request = self.rf.post("/pegawai/contoh/", HTTP_USER_AGENT="UA-Uji/1.0", REMOTE_ADDR="10.0.0.5", **extra)
        request.user = self.user
        return request

    def test_mencatat_semua_kolom(self):
        log = record_activity(
            self._request(), ActivityLog.Aktivitas.KIRIM_PENGAJUAN, "Mengirim pengajuan X",
            target_type="pengajuan", target_id="PLN01-071026-001",
        )
        log.refresh_from_db()
        self.assertEqual(log.user, self.user)
        self.assertEqual((log.username, log.role), ("uji.log", "pegawai"))
        self.assertEqual(log.aktivitas, "pengajuan.kirim")
        self.assertEqual(log.status, ActivityLog.Status.BERHASIL)
        self.assertEqual(log.ip_address, "10.0.0.5")
        self.assertEqual(log.user_agent, "UA-Uji/1.0")
        self.assertEqual((log.request_method, log.request_path), ("POST", "/pegawai/contoh/"))
        self.assertIsNotNone(log.timestamp)

    def test_pengguna_anonim(self):
        from django.contrib.auth.models import AnonymousUser
        request = self._request()
        request.user = AnonymousUser()
        log = record_activity(request, ActivityLog.Aktivitas.LOGIN_GAGAL, "Login gagal",
                              status=ActivityLog.Status.GAGAL, username="orang.asing")
        self.assertIsNone(log.user)
        self.assertEqual((log.username, log.role, log.status), ("orang.asing", "", "failed"))

    def test_tanpa_request(self):
        log = record_activity(None, ActivityLog.Aktivitas.RESET_LOG, "Dari command", username="sistem")
        self.assertIsNone(log.ip_address)
        self.assertEqual((log.user_agent, log.request_path), ("", ""))

    def test_input_panjang_dipotong(self):
        log = record_activity(self._request(HTTP_X_X="1"), "x" * 80, "d" * 500, detail="e" * 5000)
        self.assertEqual(len(log.aktivitas), 50)
        self.assertEqual(len(log.deskripsi), 255)
        self.assertEqual(len(log.detail), 1000)

    def test_xff_diabaikan_kecuali_proxy_dipercaya(self):
        request = self._request(HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1")
        self.assertEqual(record_activity(request, "a").ip_address, "10.0.0.5")
        with override_settings(ACTIVITY_LOG_TRUST_PROXY=True):
            self.assertEqual(record_activity(request, "a").ip_address, "203.0.113.9")

    def test_kegagalan_tidak_melempar_error(self):
        with mock.patch.object(ActivityLog.objects, "create", side_effect=RuntimeError("db mati")):
            with self.assertLogs("logs.utils", level="ERROR"):
                self.assertIsNone(record_activity(self._request(), "a"))

    def test_kegagalan_tidak_merusak_transaksi_pemanggil(self):
        with transaction.atomic():
            with mock.patch.object(ActivityLog.objects, "create", side_effect=__import__("django").db.DatabaseError("x")):
                with self.assertLogs("logs.utils", level="ERROR"):
                    record_activity(self._request(), "a")
            # transaksi luar tetap sehat: query masih bisa dijalankan
            self.assertEqual(ActivityLog.objects.count(), 0)
