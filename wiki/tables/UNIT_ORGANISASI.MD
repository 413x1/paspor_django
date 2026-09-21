# Tabel `org_units` — Unit Organisasi

Referensi unit organisasi eselon I Kementerian Pekerjaan Umum. Dipakai
sebagai cakupan kerja **Admin Unor** dan data kepegawaian **Pegawai**.

## Skema

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | BigAutoField (PK) | Primary key |
| `code` | CharField(2), unik | Kode unit organisasi (`"00"`–`"10"`) |
| `alias` | CharField(20) | Singkatan (mis. `DJSDA`) |
| `name` | CharField(150) | Nama lengkap unit organisasi |

Model: `paspor.models.UnitOrganisasi` (`db_table = "org_units"`, urut `code`).
Direferensikan oleh `accounts.User.unit_organisasi` dan
`accounts.PegawaiProfile.unit_organisasi` (ForeignKey, `on_delete=PROTECT`).

## Data awal (seed)

| code | alias | name |
|------|-------|------|
| 00 | MENTERI | Menteri Pekerjaan Umum |
| 01 | SETJEN | Sekretariat Jenderal |
| 02 | ITJEN | Inspektorat Jenderal |
| 03 | DJSDA | Direktorat Jenderal Sumber Daya Air |
| 04 | DJPS | Direktorat Jenderal Prasarana Strategis |
| 05 | DJCK | Direktorat Jenderal Cipta Karya |
| 06 | DJBM | Direktorat Jenderal Bina Marga |
| 07 | DJPI | Direktorat Jenderal Pembiayaan Infrastruktur |
| 08 | DJBK | Direktorat Jenderal Bina Konstruksi |
| 09 | BPIW | Badan Pengembangan Infrastruktur Wilayah |
| 10 | BPSDM | Badan Pengembangan Sumber Daya Manusia |

Data ini disisipkan oleh:

- **Migrasi** `accounts/migrations/0003_unit_organisasi_table.py` (RunPython
  `seed_units`) — otomatis saat `python manage.py migrate`. Migrasi ini yang
  membuat tabel `org_units`; kepemilikan model kemudian dipindahkan ke app
  `paspor` (state-only) oleh `paspor/0001_initial` + `accounts/0005`.
- **Command** `python manage.py seed_demo_data` (idempoten, `update_or_create`).

## Catatan

- Menghapus baris yang masih dirujuk user/pegawai ditolak (`PROTECT`).
- Pada pendaftaran user (Manajemen User oleh Admin Biro PAKLN), field
  **Unit Organisasi** adalah dropdown dari tabel ini untuk kedua peran.
