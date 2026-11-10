# Pemetaan UI & alur Coretax asli (10 Nov 2026)

Diambil langsung dari DOM portal `coretaxdjp.pajak.go.id` lewat Chrome DevTools
Protocol (bukan dari screenshot). Hanya baca: tidak ada konsep SPT yang dibuat
atau dikirim. Data akun disamarkan.

## Tampilan umum
- Angular + PrimeNG, font Plus Jakarta Sans, latar `#F5F4EF`, teks `#131B44`,
  primary `#2196F3`, radius kartu 16px / input 8px.
- Header dua bar: atas 64px (logo, pencarian 448×40 `Ctrl K`, tema, notifikasi,
  bahasa, profil); bawah 50px (Portal Saya, e-Faktur, eBUPOT, SPT, Pembayaran,
  Buku Besar, Layanan WP, Manajemen Akses).
- Pola URL: `/<portal>/id-ID/<halaman>`; portal SPT = `returnsheets-portal`.

## Menu SPT
Surat Pemberitahuan (SPT) · Coretax Form · Pencatatan · Dasbor Kompensasi ·
Pengungkapan Ketidakbenaran SPT.

## Daftar SPT
- Judul "SPT Belum Disampaikan", tombol *Buat Konsep SPT*.
- Tab: Konsep SPT · SPT Menunggu Pembayaran · SPT Dilaporkan · SPT Ditolak ·
  SPT Dibatalkan.
- Tabel 11 kolom: Jenis Pajak, Jenis SPT, Masa Pajak, NOP, Nama Objek Pajak,
  Model SPT, Jatuh Tempo, Tanggal Dibuat, Status SPT, Kanal, Submission
  Progress; baris filter; pagination 10/halaman.

## Wizard Buat Konsep SPT (3 langkah)
1. **Pilih Jenis Pajak** — kartu: PPh Final Pengungkapan Harta Bersih, PPh Orang
   Pribadi, PPh Pasal 21/26, PPh Unifikasi. *Lanjut* nonaktif sampai dipilih.
2. **Pilih periode** — radio *Jenis Periode SPT* (SPT Tahunan | SPT Bagian Tahun
   Pajak) dan dropdown *Periode dan Tahun Pajak*.
3. **Pilih Jenis SPT** — ringkasan langkah 1–2 + dropdown *Model SPT*. Bila
   Normal periode itu sudah dilaporkan, hanya *Pembetulan* yang muncul.

## Konsep dan penghapusan
Buku Manual Coretax 2024 (*Pelaporan SPT Tahunan PPh OP*, hal. 15): konsep SPT
masih dapat dihapus bila ada kesalahan. Setelah dilaporkan (ada BPE) SPT tidak
bisa dihapus, hanya dibetulkan.

## Belum dipetakan dari portal asli
Isi form setelah konsep dibuat (induk, lampiran, ringkasan, pernyataan, bayar,
submit), kode verifikasi pada Pembetulan, dan kolom/filter daftar SPT di sim
yang belum sama dengan 11 kolom di atas. Implementasi sim untuk bagian ini
mengikuti Buku Manual DJP dan `models.py`.
