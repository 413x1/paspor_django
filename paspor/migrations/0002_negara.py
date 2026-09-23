# Generated manually (mengikuti pola accounts/0003_unit_organisasi_table.py)

from django.db import migrations, models

# Data awal tabel Negara — daftar negara dunia (nama umum berbahasa
# Indonesia, kode ISO 3166-1 alpha-2) sebagai sumber pilihan pada field
# "Tujuan Negara" di Formulir Pengajuan. Admin Biro PAKLN dapat menambah,
# menyunting, menonaktifkan, atau menghapus data ini lewat menu
# Manajemen Negara.
NEGARA = [
    ("Afganistan", "AF"), ("Afrika Selatan", "ZA"), ("Albania", "AL"), ("Aljazair", "DZ"),
    ("Amerika Serikat", "US"), ("Andorra", "AD"), ("Angola", "AO"), ("Antigua dan Barbuda", "AG"),
    ("Arab Saudi", "SA"), ("Argentina", "AR"), ("Armenia", "AM"), ("Australia", "AU"),
    ("Austria", "AT"), ("Azerbaijan", "AZ"), ("Bahama", "BS"), ("Bahrain", "BH"),
    ("Bangladesh", "BD"), ("Barbados", "BB"), ("Belanda", "NL"), ("Belarus", "BY"),
    ("Belgia", "BE"), ("Belize", "BZ"), ("Benin", "BJ"), ("Bhutan", "BT"),
    ("Bolivia", "BO"), ("Bosnia dan Herzegovina", "BA"), ("Botswana", "BW"), ("Brasil", "BR"),
    ("Brunei Darussalam", "BN"), ("Bulgaria", "BG"), ("Burkina Faso", "BF"), ("Burundi", "BI"),
    ("Cabo Verde", "CV"), ("Chad", "TD"), ("Chili", "CL"), ("Denmark", "DK"),
    ("Djibouti", "DJ"), ("Dominika", "DM"), ("Ekuador", "EC"), ("El Salvador", "SV"),
    ("Eritrea", "ER"), ("Estonia", "EE"), ("Eswatini", "SZ"), ("Ethiopia", "ET"),
    ("Fiji", "FJ"), ("Filipina", "PH"), ("Finlandia", "FI"), ("Gabon", "GA"),
    ("Gambia", "GM"), ("Georgia", "GE"), ("Ghana", "GH"), ("Grenada", "GD"),
    ("Guatemala", "GT"), ("Guinea", "GN"), ("Guinea-Bissau", "GW"), ("Guinea Khatulistiwa", "GQ"),
    ("Guyana", "GY"), ("Haiti", "HT"), ("Honduras", "HN"), ("Hongaria", "HU"),
    ("India", "IN"), ("Indonesia", "ID"), ("Inggris", "GB"), ("Irak", "IQ"),
    ("Iran", "IR"), ("Irlandia", "IE"), ("Islandia", "IS"), ("Israel", "IL"),
    ("Italia", "IT"), ("Jamaika", "JM"), ("Jepang", "JP"), ("Jerman", "DE"),
    ("Kamboja", "KH"), ("Kamerun", "CM"), ("Kanada", "CA"), ("Kazakhstan", "KZ"),
    ("Kenya", "KE"), ("Kepulauan Marshall", "MH"), ("Kepulauan Solomon", "SB"), ("Kirgistan", "KG"),
    ("Kiribati", "KI"), ("Kolombia", "CO"), ("Komoro", "KM"), ("Kongo", "CG"),
    ("Kongo (Republik Demokratik)", "CD"), ("Korea Selatan", "KR"), ("Korea Utara", "KP"), ("Kosta Rika", "CR"),
    ("Kroasia", "HR"), ("Kuba", "CU"), ("Kuwait", "KW"), ("Laos", "LA"),
    ("Latvia", "LV"), ("Lebanon", "LB"), ("Lesotho", "LS"), ("Liberia", "LR"),
    ("Libya", "LY"), ("Liechtenstein", "LI"), ("Lituania", "LT"), ("Luksemburg", "LU"),
    ("Madagaskar", "MG"), ("Makedonia Utara", "MK"), ("Malawi", "MW"), ("Malaysia", "MY"),
    ("Maladewa", "MV"), ("Mali", "ML"), ("Malta", "MT"), ("Maroko", "MA"),
    ("Mauritania", "MR"), ("Mauritius", "MU"), ("Meksiko", "MX"), ("Mesir", "EG"),
    ("Mikronesia", "FM"), ("Moldova", "MD"), ("Monako", "MC"), ("Mongolia", "MN"),
    ("Montenegro", "ME"), ("Mozambik", "MZ"), ("Myanmar", "MM"), ("Namibia", "NA"),
    ("Nauru", "NR"), ("Nepal", "NP"), ("Niger", "NE"), ("Nigeria", "NG"),
    ("Nikaragua", "NI"), ("Norwegia", "NO"), ("Oman", "OM"), ("Pakistan", "PK"),
    ("Palau", "PW"), ("Palestina", "PS"), ("Panama", "PA"), ("Pantai Gading", "CI"),
    ("Papua Nugini", "PG"), ("Paraguay", "PY"), ("Peru", "PE"), ("Polandia", "PL"),
    ("Portugal", "PT"), ("Prancis", "FR"), ("Qatar", "QA"), ("Republik Afrika Tengah", "CF"),
    ("Republik Ceko", "CZ"), ("Republik Dominika", "DO"), ("Rumania", "RO"), ("Rusia", "RU"),
    ("Rwanda", "RW"), ("Saint Kitts dan Nevis", "KN"), ("Saint Lucia", "LC"), ("Saint Vincent dan Grenadines", "VC"),
    ("Samoa", "WS"), ("San Marino", "SM"), ("Sao Tome dan Principe", "ST"), ("Selandia Baru", "NZ"),
    ("Senegal", "SN"), ("Serbia", "RS"), ("Seychelles", "SC"), ("Sierra Leone", "SL"),
    ("Singapura", "SG"), ("Siprus", "CY"), ("Slovakia", "SK"), ("Slovenia", "SI"),
    ("Somalia", "SO"), ("Spanyol", "ES"), ("Sri Lanka", "LK"), ("Sudan", "SD"),
    ("Sudan Selatan", "SS"), ("Suriah", "SY"), ("Suriname", "SR"), ("Swedia", "SE"),
    ("Swiss", "CH"), ("Tajikistan", "TJ"), ("Tanzania", "TZ"), ("Thailand", "TH"),
    ("Timor Leste", "TL"), ("Togo", "TG"), ("Tonga", "TO"), ("Trinidad dan Tobago", "TT"),
    ("Tunisia", "TN"), ("Turki", "TR"), ("Turkmenistan", "TM"), ("Tuvalu", "TV"),
    ("Uganda", "UG"), ("Ukraina", "UA"), ("Uni Emirat Arab", "AE"), ("Uruguay", "UY"),
    ("Uzbekistan", "UZ"), ("Vanuatu", "VU"), ("Vatikan", "VA"), ("Venezuela", "VE"),
    ("Vietnam", "VN"), ("Yaman", "YE"), ("Yordania", "JO"), ("Yunani", "GR"),
    ("Zambia", "ZM"), ("Zimbabwe", "ZW"),
]


def seed_negara(apps, schema_editor):
    Negara = apps.get_model("paspor", "Negara")
    for nama, kode in NEGARA:
        Negara.objects.update_or_create(nama_negara=nama, defaults={"kode_negara": kode})


def unseed_negara(apps, schema_editor):
    apps.get_model("paspor", "Negara").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("paspor", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Negara",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nama_negara", models.CharField(max_length=100, unique=True, verbose_name="Nama Negara")),
                ("kode_negara", models.CharField(
                    blank=True, max_length=5,
                    help_text="Opsional, mis. kode ISO 3166-1 alpha-2 (ID, SA, SG, dst.)",
                    verbose_name="Kode Negara",
                )),
                ("is_active", models.BooleanField(default=True, verbose_name="Aktif")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Negara",
                "verbose_name_plural": "Negara",
                "ordering": ["nama_negara"],
            },
        ),
        migrations.RunPython(seed_negara, unseed_negara),
    ]
