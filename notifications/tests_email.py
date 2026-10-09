"""Tes Email Notification System (antrean database, worker, monitoring, form email)."""

import json
import smtplib
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import EditUserForm, TambahUserForm
from accounts.models import User
from logs.models import ActivityLog
from paspor.models import UnitOrganisasi

from . import email_queue
from .models import EmailLog, Notification

Event = Notification.Event


def _antrean(**perubahan):
    """MAIL_QUEUE dengan beberapa nilai ditimpa (untuk override_settings)."""
    return {**settings.MAIL_QUEUE, "SEND_PACING": 0, **perubahan}


def _notif(user, event=Event.SUBMIT_UNOR, title="Pengajuan Baru - X", body="Isi pesan", pengajuan=None):
    return Notification(
        recipient=user, pengajuan=pengajuan, event=event, level=Notification.Level.INFO,
        title=title, body=body, redirect_url="/admin-biropakln/",
    )


def _user(username, role, email="", **kw):
    return User.objects.create_user(username=username, password="x", role=role, email=email, **kw)


@override_settings(MAIL_ALLOW_SEND=True, MAIL_QUEUE=_antrean(), SITE_BASE_URL="http://situs.test")
class AntreTests(TestCase):
    def setUp(self):
        self.unor = _user("unor1", "admin_unor", "unor1@pu.go.id")

    def test_penerima_beremail_menjadi_pending(self):
        self.assertEqual(email_queue.enqueue([_notif(self.unor)]), 1)
        log = EmailLog.objects.get()
        self.assertEqual((log.status, log.to_email, log.event), ("pending", "unor1@pu.go.id", Event.SUBMIT_UNOR))
        self.assertEqual(log.subject, "[PASPOR] Pengajuan Baru - X")
        self.assertEqual(log.max_attempts, settings.MAIL_QUEUE["MAX_ATTEMPTS"])
        self.assertIn("http://situs.test/admin-biropakln/", log.body_html)
        self.assertIn("http://situs.test/admin-biropakln/", log.body_text)

    def test_penerima_tanpa_email_dilewati_dengan_jejak(self):
        tanpa = _user("unor2", "admin_unor", "")
        email_queue.enqueue([_notif(tanpa)])
        log = EmailLog.objects.get()
        self.assertEqual((log.status, log.status_note), ("skipped", "Penerima belum memiliki email"))

    @override_settings(MAIL_ALLOW_SEND=False)
    def test_saklar_pengaman_mencatat_tetapi_tidak_mengirim(self):
        email_queue.enqueue([_notif(self.unor)])
        log = EmailLog.objects.get()
        self.assertEqual(log.status, "skipped")
        self.assertIn("MAIL_ALLOW_SEND=false", log.status_note)
        self.assertEqual(email_queue.proses_antrean()["diambil"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_event_dan_peran_di_luar_daftar_putih_tidak_diantre(self):
        email_queue.enqueue([_notif(self.unor, event=Event.LAPORAN_DIUNGGAH)])   # event tidak terdaftar
        pegawai = _user("peg1", "pegawai", "peg1@pu.go.id")
        email_queue.enqueue([_notif(pegawai, event=Event.SUBMIT_UNOR)])           # peran tidak sesuai event
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_kegagalan_enqueue_tidak_melempar_error(self):
        with mock.patch.object(email_queue, "_baris_email", side_effect=RuntimeError("rusak")):
            with self.assertLogs("notifications.email", level="ERROR"):
                self.assertEqual(email_queue.enqueue([_notif(self.unor)]), 0)

    def test_konten_pengguna_di_escape_pada_html(self):
        email_queue.enqueue([_notif(self.unor, body='<script>alert(1)</script> "x"')])
        log = EmailLog.objects.get()
        self.assertNotIn("<script>", log.body_html)
        self.assertIn("&lt;script&gt;", log.body_html)
        self.assertIn("<script>alert(1)</script>", log.body_text)  # teks polos tidak di-escape

    def test_hook_di_create_membuat_notifikasi_dan_email(self):
        from . import services
        services._create(
            [self.unor], pengajuan=None, event=Event.SUBMIT_UNOR, level=Notification.Level.INFO,
            title="Judul", body="Isi", redirect_url="/admin-biropakln/",
        )
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(EmailLog.objects.count(), 1)

    def test_kegagalan_email_tidak_menggagalkan_notifikasi_in_app(self):
        from . import services
        with mock.patch.object(email_queue, "_baris_email", side_effect=RuntimeError("rusak")):
            with self.assertLogs("notifications.email", level="ERROR"):
                services._create(
                    [self.unor], pengajuan=None, event=Event.SUBMIT_UNOR, level=Notification.Level.INFO,
                    title="Judul", body="Isi", redirect_url="/x/",
                )
        self.assertEqual(Notification.objects.count(), 1)


@override_settings(MAIL_ALLOW_SEND=True, MAIL_QUEUE=_antrean(RETRY_DELAY=30, MAX_ATTEMPTS=3, LOCK_TTL=60))
class WorkerTests(TestCase):
    def setUp(self):
        self.unor = _user("unor1", "admin_unor", "unor1@pu.go.id")

    def _antre(self, n=1):
        for i in range(n):
            email_queue.enqueue([_notif(self.unor, title=f"Judul {i}")])
        EmailLog.objects.update(max_attempts=3)

    def test_mengirim_dan_menandai_terkirim(self):
        self._antre()
        self.assertEqual(email_queue.proses_antrean(), {"diambil": 1, "terkirim": 1, "ditunda": 0, "gagal": 0})
        log = EmailLog.objects.get()
        self.assertEqual((log.status, log.attempts), ("sent", 1))
        self.assertIsNotNone(log.sent_at)
        self.assertIsNone(log.locked_at)
        pesan = mail.outbox[0]
        self.assertEqual((pesan.to, pesan.subject), (["unor1@pu.go.id"], "[PASPOR] Judul 0"))
        self.assertEqual(pesan.alternatives[0][1], "text/html")  # versi HTML dan teks polos

    def test_batas_batch(self):
        self._antre(5)
        self.assertEqual(email_queue.proses_antrean(batch_size=2)["diambil"], 2)
        self.assertEqual(EmailLog.objects.filter(status="pending").count(), 3)

    def test_gagal_sementara_kembali_pending_dengan_jeda(self):
        self._antre()
        with mock.patch.object(email_queue, "_kirim", side_effect=smtplib.SMTPException("timeout")):
            hasil = email_queue.proses_antrean()
        self.assertEqual((hasil["ditunda"], hasil["gagal"]), (1, 0))
        log = EmailLog.objects.get()
        self.assertEqual((log.status, log.attempts), ("pending", 1))
        self.assertIn("SMTPException: timeout", log.last_error)
        self.assertGreater(log.next_attempt_at, timezone.now() + timedelta(seconds=20))
        self.assertEqual(email_queue.proses_antrean()["diambil"], 0)  # belum waktunya dicoba lagi

    def test_gagal_permanen_setelah_max_attempts(self):
        self._antre()
        with mock.patch.object(email_queue, "_kirim", side_effect=smtplib.SMTPException("x")):
            for _ in range(3):
                EmailLog.objects.update(next_attempt_at=timezone.now())
                email_queue.proses_antrean()
        log = EmailLog.objects.get()
        self.assertEqual((log.status, log.attempts), ("failed", 3))
        EmailLog.objects.update(next_attempt_at=timezone.now())
        self.assertEqual(email_queue.proses_antrean()["diambil"], 0)  # failed tidak diambil lagi

    def test_klaim_tidak_mengambil_baris_yang_sudah_terkunci(self):
        self._antre(3)
        pertama = email_queue._klaim(10, "worker-A")
        kedua = email_queue._klaim(10, "worker-B")
        self.assertEqual((len(pertama), len(kedua)), (3, 0))
        self.assertTrue(all(b.locked_by == "worker-A" for b in EmailLog.objects.all()))

    def test_kunci_kedaluwarsa_diambil_ulang(self):
        self._antre()
        email_queue._klaim(10, "worker-mati")
        EmailLog.objects.update(locked_at=timezone.now() - timedelta(seconds=120))  # > LOCK_TTL 60 dtk
        hasil = email_queue.proses_antrean(worker_id="worker-baru")
        self.assertEqual(hasil["terkirim"], 1)
        self.assertEqual(EmailLog.objects.get().attempts, 2)

    def test_kunci_kedaluwarsa_dengan_percobaan_habis_menjadi_failed(self):
        self._antre()
        email_queue._klaim(10, "worker-mati")
        EmailLog.objects.update(
            attempts=3, locked_at=timezone.now() - timedelta(seconds=120),
        )
        self.assertEqual(email_queue.proses_antrean()["diambil"], 0)
        self.assertEqual(EmailLog.objects.get().status, "failed")

    @override_settings(MAIL_DEV_REDIRECT_TO="uji@contoh.test")
    def test_mode_uji_mengalihkan_semua_email(self):
        self._antre()
        email_queue.proses_antrean()
        pesan = mail.outbox[0]
        self.assertEqual(pesan.to, ["uji@contoh.test"])
        self.assertIn("[untuk: unor1@pu.go.id]", pesan.subject)

    def test_kirim_ulang_failed_dan_penolakan_status_lain(self):
        self._antre(2)
        sent, failed = EmailLog.objects.order_by("pk")
        EmailLog.objects.filter(pk=sent.pk).update(status="sent")
        EmailLog.objects.filter(pk=failed.pk).update(status="failed", attempts=3, last_error="x")
        self.assertFalse(email_queue.kirim_ulang(EmailLog.objects.get(pk=sent.pk)))
        self.assertTrue(email_queue.kirim_ulang(EmailLog.objects.get(pk=failed.pk)))
        log = EmailLog.objects.get(pk=failed.pk)
        self.assertEqual((log.status, log.attempts, log.last_error), ("pending", 0, ""))

    def test_skipped_tanpa_email_baru_bisa_dikirim_ulang_setelah_email_diisi(self):
        tanpa = _user("unor2", "admin_unor", "")
        email_queue.enqueue([_notif(tanpa)])
        log = EmailLog.objects.get()
        self.assertFalse(email_queue.bisa_kirim_ulang(log))
        tanpa.email = "baru@pu.go.id"
        tanpa.save()
        log = EmailLog.objects.select_related("recipient").get(pk=log.pk)
        self.assertTrue(email_queue.kirim_ulang(log))
        self.assertEqual(EmailLog.objects.get().to_email, "baru@pu.go.id")


class CommandTests(TestCase):
    def setUp(self):
        _user("unor1", "admin_unor", "unor1@pu.go.id")

    def _jalan(self, *args, **kw):
        out = StringIO()
        call_command("kirim_email_antrean", *args, stdout=out, stderr=StringIO(), **kw)
        return out.getvalue()

    @override_settings(MAIL_ALLOW_SEND=True, MAIL_QUEUE=_antrean(ENABLE_WORKER=False))
    def test_loop_ditolak_bila_worker_dinonaktifkan_tetapi_once_boleh(self):
        with self.assertRaises(CommandError):
            self._jalan()
        self._jalan(once=True)  # tidak melempar error

    @override_settings(MAIL_ALLOW_SEND=True, MAIL_QUEUE=_antrean(ENABLE_WORKER=False))
    def test_once_memproses_antrean(self):
        email_queue.enqueue([_notif(User.objects.get(username="unor1"))])
        self.assertIn("terkirim 1", self._jalan(once=True))
        self.assertEqual(EmailLog.objects.get().status, "sent")

    @override_settings(MAIL_ALLOW_SEND=True)
    def test_bersihkan_email_log(self):
        user = User.objects.get(username="unor1")
        email_queue.enqueue([_notif(user)] * 3)
        lama = list(EmailLog.objects.order_by("pk")[:2])
        EmailLog.objects.filter(pk=lama[0].pk).update(status="sent", created_at=timezone.now() - timedelta(days=100))
        EmailLog.objects.filter(pk=lama[1].pk).update(status="failed", created_at=timezone.now() - timedelta(days=100))
        out = StringIO()
        call_command("bersihkan_email_log", hari=90, stdout=out)
        self.assertEqual(EmailLog.objects.count(), 2)            # hanya yang terkirim & lama dihapus
        self.assertTrue(EmailLog.objects.filter(status="failed").exists())
        with self.assertRaises(CommandError):
            call_command("bersihkan_email_log", hari=0, stdout=out)


@override_settings(MAIL_ALLOW_SEND=True)
class MonitoringTests(TestCase):
    def setUp(self):
        self.pakln = _user("adm.pakln", "admin_pakln", "pakln@pu.go.id")
        self.pegawai = _user("peg", "pegawai", "peg@pu.go.id")
        self.client.force_login(self.pakln)
        ActivityLog.objects.all().delete()  # force_login memicu signal login

    def _buat(self, n=1, **kw):
        return [EmailLog.objects.create(
            recipient=self.pegawai, to_email="peg@pu.go.id", to_name="Peg", subject=f"Subjek {i}",
            event=Event.REJECT_UNOR, **kw) for i in range(n)]

    def test_hanya_admin_pakln(self):
        for nama in ("pakln:monitor_email", "pakln:monitor_email_data"):
            self.client.logout()
            self.assertEqual(self.client.get(reverse(nama)).status_code, 302)
            self.client.force_login(self.pegawai)
            self.assertEqual(self.client.get(reverse(nama)).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("pakln:monitor_email_kirim_ulang", args=[1])).status_code, 403,
        )

    def test_halaman_dan_menu(self):
        r = self.client.get(reverse("pakln:monitor_email"))
        self.assertContains(r, 'id="emailTable"')
        self.assertContains(self.client.get(reverse("pakln:dashboard")), "Monitor Email")
        self.client.force_login(self.pegawai)
        self.assertNotContains(self.client.get(reverse("pegawai:beranda")), "Monitor Email")

    def test_data_paginasi_filter_dan_ringkasan(self):
        self._buat(3, status="failed")
        self._buat(2, status="sent")
        d = self.client.get(reverse("pakln:monitor_email_data"), {"draw": 4, "length": 2}).json()
        self.assertEqual((d["draw"], d["recordsTotal"], d["recordsFiltered"], len(d["data"])), (4, 5, 5, 2))
        self.assertEqual(len(d["data"][0]), 8)
        self.assertEqual((d["ringkasan"]["failed"], d["ringkasan"]["sent"], d["ringkasan"]["pending"]), (3, 2, 0))
        f = self.client.get(reverse("pakln:monitor_email_data"), {"status": "failed"}).json()
        self.assertEqual((f["recordsFiltered"], f["recordsTotal"]), (3, 5))
        c = self.client.get(reverse("pakln:monitor_email_data"), {"search[value]": "Subjek 1"}).json()
        self.assertEqual(c["recordsFiltered"], 2)
        self.assertEqual(
            self.client.get(reverse("pakln:monitor_email_data"), {"length": 5000, "order[0][column]": "9;DROP"}).status_code, 200,
        )

    def test_filter_tanggal(self):
        lama, baru = self._buat(2)
        EmailLog.objects.filter(pk=lama.pk).update(created_at=timezone.now() - timedelta(days=10))
        hari_ini = timezone.localdate().isoformat()
        url = reverse("pakln:monitor_email_data")
        self.assertEqual(self.client.get(url, {"tgl_dari": hari_ini}).json()["recordsFiltered"], 1)
        self.assertEqual(self.client.get(url, {"tgl_sampai": hari_ini}).json()["recordsFiltered"], 2)

    def test_isi_sel_di_escape(self):
        EmailLog.objects.create(
            to_email="a@b.test", to_name="<b>x</b>", subject="<script>alert(1)</script>",
            last_error="<img src=x>", status="failed", event="<i>",
        )
        isi = json.dumps(self.client.get(reverse("pakln:monitor_email_data")).json()["data"])
        for bahaya in ("<script>", "<img", "<b>", "<i>"):
            self.assertNotIn(bahaya, isi)

    def test_kirim_ulang_berhasil_dan_tercatat_di_log_sistem(self):
        (log,) = self._buat(status="failed", attempts=5, last_error="x")
        r = self.client.post(reverse("pakln:monitor_email_kirim_ulang", args=[log.pk]))
        self.assertEqual(r.status_code, 200)
        log.refresh_from_db()
        self.assertEqual((log.status, log.attempts), ("pending", 0))
        catatan = ActivityLog.objects.get(aktivitas="email.kirim_ulang")
        self.assertEqual((catatan.status, catatan.username, catatan.target_id), ("success", "adm.pakln", str(log.pk)))

    def test_kirim_ulang_ditolak_untuk_status_lain_dan_get(self):
        (sent,) = self._buat(status="sent")
        r = self.client.post(reverse("pakln:monitor_email_kirim_ulang", args=[sent.pk]))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ActivityLog.objects.get(aktivitas="email.kirim_ulang").status, "failed")
        self.assertEqual(self.client.get(reverse("pakln:monitor_email_kirim_ulang", args=[sent.pk])).status_code, 405)

    def test_tombol_kirim_ulang_hanya_untuk_yang_bisa(self):
        self._buat(status="failed")
        self._buat(status="sent")
        isi = " ".join(r[7] for r in self.client.get(reverse("pakln:monitor_email_data")).json()["data"])
        self.assertEqual(isi.count("data-kirim-ulang"), 1)


class FormEmailTests(TestCase):
    def _data_tambah(self, **kw):
        unit = UnitOrganisasi.objects.first()
        return {
            "role": "admin_unor", "username": "baru.user", "nama": "Baru User", "password": "Rahasia-12345",
            "password_konfirmasi": "Rahasia-12345", "unit_organisasi": unit.pk, "unit_kerja": "Biro", **kw,
        }

    def test_email_opsional_dan_dinormalisasi(self):
        form = TambahUserForm(self._data_tambah())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().email, "")
        form = TambahUserForm(self._data_tambah(username="user.dua", email="  Budi.S@PU.go.id "))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().email, "budi.s@pu.go.id")

    def test_format_email_tidak_valid_ditolak(self):
        form = TambahUserForm(self._data_tambah(email="bukan-email"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_edit_user_menyimpan_email(self):
        user = _user("edit.me", "admin_unor", "", unit_organisasi=UnitOrganisasi.objects.first())
        form = EditUserForm(
            {"username": "edit.me", "nama": "Edit Me", "email": "Edit.Me@pu.go.id", "is_active": "on",
             "unit_organisasi": UnitOrganisasi.objects.first().pk, "unit_kerja": "Biro"},
            instance=user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertEqual(user.email, "edit.me@pu.go.id")

    def test_halaman_user_menampilkan_field_dan_penanda_email_belum_diisi(self):
        pakln = _user("adm.pakln", "admin_pakln", "p@pu.go.id")
        _user("tanpa.email", "admin_unor", "", unit_organisasi=UnitOrganisasi.objects.first())
        self.client.force_login(pakln)
        self.assertContains(self.client.get(reverse("pakln:kelola_user")), 'name="email"')
        data = self.client.get(reverse("pakln:users_data"), {"length": 50}).json()["data"]
        self.assertIn("email belum diisi", json.dumps(data))
