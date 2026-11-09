# Simulator Coretax DJP

Aplikasi web simulasi **Coretax DJP** (Direktorat Jenderal Pajak) untuk
pembelajaran mahasiswa perpajakan. Struktur menu, alur pengisian, dan nama field
**mengikuti aplikasi Coretax DJP asli** serta *Buku Manual Coretax* yang
dipublikasikan DJP.

> **Bukan aplikasi DJP resmi.** Tidak terhubung ke server pajak, tidak mengirim
> data apa pun, dan tidak punya efek hukum. Semua perhitungan memakai tarif
> publik yang berlaku (lihat `tax.py` untuk sumber dan tanggalnya).

📖 **[Dokumentasi lengkap → `DOKUMENTASI.md`](DOKUMENTASI.md)**

Dokumentasi lain:
- [`docs/ARSITEKTUR.md`](docs/ARSITEKTUR.md) — struktur, layer, model data
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — deploy Docker, TLS, backup, troubleshooting
- [`docs/KEAMANAN.md`](docs/KEAMANAN.md) — threat model, kontrol, known gaps
- [`docs/API.md`](docs/API.md) — referensi endpoint

---

## Menjalankan

### Docker (disarankan)

```bash
cp .env.example .env      # edit sesuai kebutuhan
docker compose up -d --build
```

Buka `http://<ip-server>:8140`.

### Manual

```bash
cd ~/projects/coretax-sim
pip install -r requirements.txt
python3 -m uvicorn app:app --host 0.0.0.0 --port 8140
```

### Akun demo

| NIK/NPWP | Nama | Role | Status PTKP |
|---|---|---|---|
| `2171121009959003` | ALLIF MAULANA | OP (operator) | K/0 |
| `1111111111111` | TIM KELAS A | WP | TK/0 |
| `2222222222222` | TIM KELAS B | WP | K/0 |
| `3333333333333` | TIM KELAS C | WP | K/1 |

Password awal semua: **`demo123`**

> Ganti password sebelum dipakai di luar kelas. Lihat
> [`docs/DEPLOY.md`](docs/DEPLOY.md) §2.4.

### Data demo

```bash
python3 seed.py              # isi faktur, bukti potong, deposit, SPT contoh
python3 reset_db.py --yes    # reset total + seed ulang
```

---

## Yang sudah ada

### Modul SPT (lengkap)

Alur persis seperti portal Coretax: **Buat Konsep SPT** → wizard 3 langkah
(1 pilih jenis pajak → 2 pilih periode pelaporan → 3 pilih model SPT) → isi
formulir induk + lampiran → hitung otomatis → simpan draft → tanda tangan →
*Pay and Submit* (deposit atau kode billing).

| Jenis SPT | Formulir induk | Lampiran |
|---|---|---|
| SPT Tahunan PPh Orang Pribadi | 12 bagian (Header, A–K) | 11 lampiran (L-1 … L-5) |
| SPT Masa PPh Pasal 21/26 | Identitas, Rincian Pemotongan, Penyampaian | — |
| SPT Masa PPh Unifikasi | Identitas, Ringkasan, Pembukuan, Penyampaian | — |
| SPT Masa PPN | Penyerahan, Perhitungan, Pemungutan, Kelengkapan, Penyampaian | 6 lampiran (A-1 … C) |
| SPT Tahunan PPh Final Pengungkapan Harta Bersih | kerangka | — |

Status SPT mengikuti portal: Konsep → SPT Menunggu Pembayaran → SPT Dilaporkan
(plus Ditolak & Dibatalkan).

### Modul pendukung

- **e-Faktur** — daftar faktur pajak keluaran (sumber PPN pada SPT Masa PPN)
- **eBUPOT** — daftar bukti potong (sumber SPT Masa PPh 21/26 dan Unifikasi)
- **Pembayaran** — kode billing, riwayat setoran, saldo deposit
- **Buku Besar** — rekapitulasi omzet dan pajak
- **Portal Saya / Layanan WP / Manajemen Akses** — kerangka halaman + navigasi

### Perhitungan pajak

Semua perhitungan ada di `tax.py` (fungsi murni, tanpa I/O) dan diuji di
`test_tax.py`.

| Pajak | Dasar | Tarif |
|---|---|---|
| PPh Pasal 21 | TER bulanan/harian (PP 58/2023, PMK 168/2023); Pasal 17 UU HPP | 5–35% progresif; TER 0–34% |
| PTKP | PMK 101/PMK.010/2016 | TK/0 54 jt … K/I/0 112,5 jt/tahun |
| PPh Orang Pribadi | Pasal 17 atas PKP tahunan | 5–35% |
| PPN | PMK 131/2024 | 11% (umum) / 12% (subject PPnBM) |
| PPh Final | UU HPP | 0,5% (UMKM) / 1% omzet bruto |
| PPh Pasal 25 | pajak setahun ÷ jumlah bulan angsuran | — |

Live calculation di browser (`static/live.js`) adalah cermin `tax.py`.

### Kredit pajak (Bagian D) — mengikuti Buku Manual DJP

Sesuai *Buku Manual Coretax — Pelaporan SPT Tahunan PPh Orang Pribadi*:

| Field | Sumber |
|---|---|
| 10a | Mengaktifkan Lampiran 1 (L-1) **Bagian E** = Daftar Bukti Pemotongan |
| 10b | Prepopulated dari Pembayaran PPh Pasal 25 |
| 10c | STP PPh Pasal 25 (hanya pokok pajak) |
| 10d | Pengembalian/pengurangan kredit PPh luar negeri |

Total kredit = bukti potong (L-1/E) + angsuran 25 + STP + kredit luar negeri.
Kredit bersifat **read-only di form** dan dihitung ulang server tiap kali draft
disimpan atau lampiran ditambah — meniru auto-posting Coretax asli.

---

## Keamanan

Sudah diperkeras dan diuji — rincian di [`docs/KEAMANAN.md`](docs/KEAMANAN.md).

| Kontrol | Implementasi |
|---|---|
| Password | PBKDF2-HMAC-SHA256 200k iterasi, salt per-user, constant-time compare |
| Anti brute-force | Lockout per-NPWP (5× gagal → 15 mnt) + batas per-IP |
| User enumeration | Pesan seragam + response time disamakan |
| Session | SQLite, token 256-bit, HttpOnly, SameSite, TTL 12 jam |
| CSRF | Token per-session, dicek di semua POST |
| IDOR (detail) | Filter kepemilikan; role OP vs WP |
| IDOR (list view) | `owner_scope()` filter owner pada 6 query list |
| Headers | CSP `script-src 'self'` + 6 header lain |
| SQLi / XSS | Query ter-parameterisasi; output di-escape |
| Container | Non-root uid 10001, `no-new-privileges`, limit resource |

> Deploy di internet publik? **Pasang reverse proxy TLS** (Caddy/nginx) dan set
> `CORETAX_COOKIE_SECURE=1`. Lihat [`docs/DEPLOY.md`](docs/DEPLOY.md) §3.

---

## Pengujian

```bash
python3 test_tax.py         # 50 kasus engine perhitungan
python3 e2e_test.py         # alur HTTP end-to-end (butuh server jalan)
python3 nav_test.py         # navigasi antar modul
python3 security_test.py    # keamanan: brute force, CSRF, IDOR, session
python3 tools/verify_idor.py      # IDOR + CSRF pada write path
python3 tools/verify_list_scope.py # isolasi list view WP vs OP
```

---

## Struktur berkas

```
app.py        FastAPI: shell, wizard SPT, form, lampiran, bayar, submit
models.py     Definisi form SPT (12 bagian + 11 lampiran), skema DB
security.py   Hash password, session, rate limit, CSRF, security headers
tax.py        Engine perhitungan pajak (fungsi murni)
seed.py       Data demo
reset_db.py   Reset DB ke kondisi bersih
entrypoint.sh Init DB + purge session saat container start
static/       app.css, live.js, favicon.svg
docs/         ARSITEKTUR, DEPLOY, KEAMANAN, API
data/         SQLite (volume Docker, di-backup)
```

---

## Batasan yang diketahui

- **SPT belum membaca data faktur/bupot secara otomatis.** Manual DJP menyebut
  data faktur otomatis posting ke SPT PPN; di sini DPP masih diisi manual.
- **Lampiran disimpan sebagai JSON per baris**, bukan tabel relasional per kolom.
  Cukup untuk simulasi, tapi analytics lintas SPT lebih sulit.
- **e-Faktur / eBUPOT / Pembayaran** masih daftar + tombol dasar, belum alur
  multi-langkah seperti portal asli.
- **Tarif diduplikasi di `tax.py` dan `static/live.js`** — kalau tarif berubah,
  dua file harus diupdate.
- **Akun demo memakai NIK `2171121009959003`** milik asli. Ganti di
  `models.py` → `DEMO_USERS` sebelum dipakai di luar kelas.
- **Audit Strix sudah dijalankan** (mode quick, black-box). 1 temuan Medium
  (list view bocor metadata WP lain) sudah ditutup. Re-scan untuk verifikasi
  belum dijalankan.
