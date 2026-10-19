from django.core.management.base import BaseCommand

from accounts.ehrm_sync import sinkron_profil
from accounts.models import User
from logs.models import ActivityLog
from logs.utils import record_activity
from paspor.integrasi import ehrm


class Command(BaseCommand):
    help = (
        "Sinkronisasi data kepegawaian (termasuk email & nomor HP yang tidak dikunci) "
        "dari e-HRM untuk semua user yang memiliki PegawaiProfile. Dapat dijadwalkan lewat cron."
    )

    def add_arguments(self, parser):
        parser.add_argument("--nip", help="Hanya sinkron pegawai dengan NIP ini.")
        parser.add_argument("--dry-run", action="store_true", help="Ambil data e-HRM tanpa menyimpan perubahan.")

    def handle(self, *args, **options):
        users = User.objects.filter(profile__isnull=False).select_related("profile").order_by("username")
        if options["nip"]:
            users = users.filter(profile__nip=options["nip"])

        jumlah = {"sinkron": 0, "tidak_ditemukan": 0, "gagal": 0}
        for user in users:
            nip = user.profile.nip
            try:
                data = ehrm.ambil_pegawai(nip)
            except ehrm.EhrmTidakTersedia as exc:
                jumlah["gagal"] += 1
                self.stderr.write(f"{nip}: e-HRM tidak tersedia ({exc})")
                if not options["dry_run"]:
                    record_activity(
                        None, ActivityLog.Aktivitas.SINKRON_EHRM_GAGAL, f"Sinkron e-HRM {user.username} gagal",
                        status=ActivityLog.Status.GAGAL, user=user, target_type="user", target_id=user.pk,
                    )
                continue
            if data is None:
                jumlah["tidak_ditemukan"] += 1
                self.stdout.write(f"{nip}: tidak ditemukan di e-HRM")
                continue
            if options["dry_run"]:
                self.stdout.write(f"{nip}: {data.nama} — {data.jabatan} (dry-run, tidak disimpan)")
                continue
            berubah = sinkron_profil(user, data)
            jumlah["sinkron"] += 1
            if berubah:
                self.stdout.write(f"{nip}: diperbarui ({', '.join(berubah)})")

        self.stdout.write(self.style.SUCCESS(
            f"Selesai. Disinkronkan: {jumlah['sinkron']}, tidak ditemukan: {jumlah['tidak_ditemukan']}, "
            f"gagal: {jumlah['gagal']}."
        ))
