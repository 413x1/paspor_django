saat pemrosesan administrasi oleh admin pakln, akan ditambahkan fitur generate dokumen Nota Dinas (ND), dimana output generate ini berupa file pdf.
case:
ketika proses administrasi telah di proses oleh admin unor ke admin pakln, admin pakln diharapkan bisa melakukan generate dokumen nd dengan ketentuan admin pakln bisa mengenerate ND untuk per pegawai ataupun lebih dari 1 pegawai yang berasal dari 1 unit organisasi yang sama, tujuan negara yang sama dan Maksud tujuan perjalanan yang sama
template dokumen ND terdapat di static/templateND/ file dalam bentuk docx ataupun PDF.

berdasarkan template yang disediakan ada nilai nilai yang berasal dari database:
1. Plt. Kepala Bagian Kerja Sama Luar Negeri
itu harus data dinamis dari database yang bisa di atur oleh adminpakln dengan nilai default Plt. Kepala Bagian Kerja Sama Luar Negeri
2. [nama] => nama pegawai yang akan digeneratekan dokumen ND, jika pegawai hanya satu orang maka nama satu orang tersebut, jika lebih dari satu orang maka nama dari orang pertama ditambah dkk.
3. [negara tujuan] => negara tujuan pengajuan administrasi
4. [Nama Pejabat] => value yang dapat di atur dan berhubungan dengan jabatan Plt. Kepala Bagian
Kerja Sama Luar Negeri
5. Kotak paraf "Ketua Tim AKI" dimana dokumen ND ukuran A5 di generate 2 lembar 1 dengan paraf satu tanpa paraf
6. [keperluan] => merupakan Maksud Perjalanan dari pegawai yang di pilih
7. [tanggal bulan tahun] => tanggal bulan tahun dokumen di generate, tanggal di kosongkan diganti dengan spasi kosong nanti di tulis tangan
8. [nama unor] => nama unit organisasi pegawai yang di pilih
9. [sumber biaya] => sumber biaya yang di input oleh pegawai yang di pilih
10. Data Pegawai => data pegawai di masukan kedalam tabel dengan format data seperti pada template
11. Reiza Setiawan => nama pegawai dengan jabatan Kepala Biro Perencanaan Anggaran dan Kerja Sama Luar Negeri
12. Kotak paraf seperti kasus kotak paraf sebelumnya dengan dua kotak antara Katim Aki dan Plt. Kabag KLN dimana dua data tersebut harus bisa dinamis dan diatur oleh admin pakln dengan nilai default.

Pegawai dipilih dengan menggunakan checklist lalu ada button generate ND, ND yang telah di generate untuk pegawai akan tersimpan dalam riwayat generate ND dan jika pegawai yang telah memiliki hasil generate ND maka akan muncul notif konfirmasi jika dipilih kembali untuk di generate ND