from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pengajuan", "0002_dokumentemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="pengajuan",
            name="catatan_unor",
            field=models.TextField(blank=True, verbose_name="Catatan Admin Unor"),
        ),
    ]
