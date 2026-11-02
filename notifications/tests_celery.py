"""Celery (Fase 1): task pengiriman email, pemicu dari antrean, dan konfigurasi dasar."""

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from paspor_project import celery_app

from . import email_queue
from .models import EmailLog
from .tasks import kirim_antrean_email
from .tests_email import _antrean, _notif, _user

PATCH_KIRIM = "notifications.tasks.kirim_antrean_email.apply_async"
PATCH_KONEKSI = "notifications.tasks.kirim_antrean_email.app.connection_for_write"


@override_settings(MAIL_ALLOW_SEND=True, MAIL_USE_CELERY=True, MAIL_QUEUE=_antrean(), MAIL_DEV_REDIRECT_TO="")
class TaskKirimAntreanEmailTests(TestCase):
    def setUp(self):
        self.unor = _user("unor1", "admin_unor", "unor1@pu.go.id")

    def _antre(self, n=1):
        for i in range(n):
            email_queue.enqueue([_notif(self.unor, title=f"Judul {i}")])

    def test_mengirim_baris_pending(self):
        self._antre(3)
        hasil = kirim_antrean_email.apply().get()
        self.assertEqual(hasil["terkirim"], 3)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(EmailLog.objects.filter(status=EmailLog.Status.SENT).count(), 3)

    def test_beberapa_batch_dalam_satu_eksekusi(self):
        self._antre(5)
        with override_settings(MAIL_QUEUE=_antrean(BATCH_SIZE=2)):
            hasil = kirim_antrean_email.apply().get()
        self.assertEqual(hasil["terkirim"], 5)                       # 3 putaran (2+2+1), bukan menunggu Beat
        self.assertFalse(EmailLog.objects.filter(status=EmailLog.Status.PENDING).exists())

    def test_tidak_mengambil_baris_yang_masih_menunggu_backoff(self):
        self._antre(1)
        EmailLog.objects.update(next_attempt_at=timezone.now() + timedelta(minutes=10))
        hasil = kirim_antrean_email.apply().get()
        self.assertEqual(hasil["diambil"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_dua_kali_jalan_tidak_mengirim_ganda(self):
        self._antre(2)
        kirim_antrean_email.apply().get()
        kirim_antrean_email.apply().get()
        self.assertEqual(len(mail.outbox), 2)

    def test_saklar_mail_allow_send_tetap_dihormati(self):
        self._antre(1)
        with override_settings(MAIL_ALLOW_SEND=False):
            hasil = kirim_antrean_email.apply().get()
        self.assertEqual(hasil["diambil"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_dialihkan_ke_alamat_uji(self):
        self._antre(1)
        with override_settings(MAIL_DEV_REDIRECT_TO="uji@contoh.test"):
            kirim_antrean_email.apply().get()
        self.assertEqual(mail.outbox[0].to, ["uji@contoh.test"])

    @override_settings(MAIL_USE_CELERY=False)
    def test_dilewati_bila_saklar_celery_mati(self):
        self._antre(1)
        hasil = kirim_antrean_email.apply().get()
        self.assertIn("dilewati", hasil)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(MAIL_ALLOW_SEND=True, MAIL_QUEUE=_antrean(), MAIL_DEV_REDIRECT_TO="")
class PicuPengirimanTests(TestCase):
    def setUp(self):
        self.unor = _user("unor1", "admin_unor", "unor1@pu.go.id")

    @override_settings(MAIL_USE_CELERY=True)
    def test_task_dipicu_setelah_commit(self):
        with mock.patch(PATCH_KIRIM) as picu, mock.patch(PATCH_KONEKSI):
            with self.captureOnCommitCallbacks(execute=True):
                email_queue.enqueue([_notif(self.unor)])
                picu.assert_not_called()                            # belum commit: worker belum boleh jalan
        picu.assert_called_once()
        self.assertEqual((picu.call_args.kwargs["retry"], picu.call_args.kwargs["expires"]), (False, 120))

    @override_settings(MAIL_USE_CELERY=False)
    def test_tidak_memicu_bila_saklar_celery_mati(self):
        with mock.patch(PATCH_KIRIM) as picu:
            with self.captureOnCommitCallbacks(execute=True):
                email_queue.enqueue([_notif(self.unor)])
        picu.assert_not_called()

    @override_settings(MAIL_USE_CELERY=True)
    def test_tidak_memicu_untuk_email_yang_dilewati(self):
        tanpa_email = _user("tanpa", "admin_unor", "")
        with mock.patch(PATCH_KIRIM) as picu:
            with self.captureOnCommitCallbacks(execute=True):
                email_queue.enqueue([_notif(tanpa_email)])
        picu.assert_not_called()
        self.assertEqual(EmailLog.objects.get().status, EmailLog.Status.SKIPPED)

    @override_settings(MAIL_USE_CELERY=True)
    def test_redis_mati_gagal_cepat_dan_tidak_menggagalkan_alur(self):
        with mock.patch(PATCH_KIRIM, side_effect=ConnectionError("redis mati")), mock.patch(PATCH_KONEKSI):
            with self.assertLogs("notifications.email", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    self.assertEqual(email_queue.enqueue([_notif(self.unor)]), 1)
        self.assertEqual(EmailLog.objects.get().status, EmailLog.Status.PENDING)   # disapu Beat nanti

    @override_settings(MAIL_USE_CELERY=True)
    def test_kirim_ulang_memicu_task(self):
        email_queue.enqueue([_notif(self.unor)])
        log = EmailLog.objects.get()
        EmailLog.objects.filter(pk=log.pk).update(status=EmailLog.Status.FAILED)
        log.refresh_from_db()
        with mock.patch(PATCH_KIRIM) as picu, mock.patch(PATCH_KONEKSI):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(email_queue.kirim_ulang(log))
        picu.assert_called_once()


class KonfigurasiCeleryTests(TestCase):
    def test_aplikasi_celery_termuat_dari_django(self):
        self.assertEqual(celery_app.main, "paspor_project")
        self.assertEqual(celery_app.conf.timezone, "Asia/Jakarta")
        self.assertTrue(celery_app.conf.broker_url.startswith("redis://"))

    def test_task_email_terdaftar_dan_dirutekan_ke_antrean_email(self):
        celery_app.loader.import_default_modules()
        self.assertIn("notifications.kirim_antrean_email", celery_app.tasks)
        rute = celery_app.amqp.router.route({}, "notifications.kirim_antrean_email")
        self.assertEqual(rute["queue"].name, "email")

    def test_pengaturan_keamanan_task(self):
        c = celery_app.conf
        self.assertTrue(c.task_acks_late)
        self.assertEqual(c.worker_prefetch_multiplier, 1)
        self.assertLess(c.task_soft_time_limit, c.task_time_limit)
        self.assertLessEqual(c.broker_transport_options["socket_connect_timeout"], 5)
