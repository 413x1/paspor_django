from django.db import migrations


def isi_peranuser(apps, schema_editor):
    """Setiap user lama mendapat tepat satu PeranUser sesuai kolom `role`;
    Admin Unor membawa unit organisasi yang dikelola."""
    User = apps.get_model("accounts", "User")
    PeranUser = apps.get_model("accounts", "PeranUser")
    baris = [
        PeranUser(
            user_id=u.pk,
            role=u.role,
            unit_organisasi_id=u.unit_organisasi_id if u.role == "admin_unor" else None,
        )
        for u in User.objects.exclude(role="").only("pk", "role", "unit_organisasi_id")
        if not PeranUser.objects.filter(user_id=u.pk, role=u.role).exists()
    ]
    PeranUser.objects.bulk_create(baris)


def hapus_peranuser(apps, schema_editor):
    apps.get_model("accounts", "PeranUser").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_peranuser'),
    ]

    operations = [
        migrations.RunPython(isi_peranuser, hapus_peranuser),
    ]
