from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_alter_user_role_admin_bko'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='no_hp',
            field=models.CharField(blank=True, db_index=True, max_length=20, verbose_name='Nomor HP (WhatsApp)'),
        ),
        migrations.AddField(
            model_name='user',
            name='sso_sub',
            field=models.CharField(blank=True, editable=False, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='user',
            name='sumber_akun',
            field=models.CharField(choices=[('sso', 'SSO'), ('lokal', 'Lokal')], default='lokal', max_length=10),
        ),
        migrations.AddField(
            model_name='user',
            name='email_dikunci',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='no_hp_dikunci',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='ehrm_sinkron_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
