from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0007_event_kegiatan'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='untuk_peran',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
