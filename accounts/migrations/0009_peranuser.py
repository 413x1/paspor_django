import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_user_kontak_sso'),
        ('paspor', '0009_label_platform_bpsdm'),
    ]

    operations = [
        migrations.CreateModel(
            name='PeranUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('pegawai', 'Pegawai'), ('admin_unor', 'Admin Unor'), ('admin_bpsdm', 'Admin BPSDM'), ('admin_pakln', 'Admin Biro PAKLN'), ('admin_bko', 'Admin BKO')], max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('diberikan_oleh', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('unit_organisasi', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='paspor.unitorganisasi', verbose_name='Unit Organisasi')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='peran_list', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Peran User',
                'verbose_name_plural': 'Peran User',
                'unique_together': {('user', 'role')},
            },
        ),
    ]
