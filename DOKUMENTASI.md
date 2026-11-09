# Dokumentasi Lengkap — Simulator Coretax DJP

Dokumen ini merangkum **seluruh pekerjaan** pada Simulator Coretax DJP: apa yang
dibangun, dari mana spesifikasi diambil, apa yang sudah diuji, dan apa yang masih
bisa dikritisi.

Dokumen lain:
- [`docs/ARSITEKTUR.md`](docs/ARSITEKTUR.md) — struktur, layer, model data
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — deploy Docker, TLS, backup, troubleshooting
- [`docs/KEAMANAN.md`](docs/KEAMANAN.md) — threat model, kontrol, known gaps
- [`docs/API.md`](docs/API.md) — referensi endpoint

---

## Daftar Isi

1. [Tujuan](#1-tujuan)
2. [Tahapan kerja](#2-tahapan-kerja)
3. [Sumber spesifikasi](#3-sumber-spesifikasi)
4. [Fitur yang diimplementasikan](#4-fitur-yang-diimplementasikan)
5. [Engine perhitungan](#5-engine-perhitungan)
6. [Keamanan](#6-keamanan)
7. [Pengujian](#7-pengujian)
8. [Deployment](#8-deployment)
9. [Riwayat keputusan](#9-riwayat-keputusan)
10. [Batasan & pekerjaan lanjutan](#10-batasan--pekerjaan-lanjutan)
11. [Riwayat perubahan](#11-riwayat-perubahan)

---

## 1. Tujuan

Simulasi **Coretax DJP** (Direktorat Jenderal Pajak) untuk latihan mahasiswa
mata kuliah perpajakan.

Tiga syarat yang ditetapkan pemilik:

1. **Mirip Coretax** — struktur menu, alur pengisian, dan nama field mengikuti
   aplikasi asli.
2. **Spesifikasi dari sumber resmi** — bukan formulir karangan. Semua dari
   live Coretax dan *Buku Manual Coretax* DJP.
3. **Bisa dipakai tim** — multi-user, data demo, packaging yang bisa di-copy
   ke server lain.

Sifat penting: **bukan aplikasi DJP resmi**. Tidak terhubung ke server pajak,
tidak mengirim data apa pun, tidak punya efek hukum.

---

## 2. Tahapan kerja

| Tahap | Isi | Output |
|---|---|---|
| **1. Mapping** | Crawl read-only menu & wizard Coretax live (akun OP) via CDP. Download 3 Buku Manual DJP. Ekstrak teks PDF (`pdftotext -layout`). | `coretax-peta-fitur.md`, `coretax-map.json`, PDF manual |
| **2. Spesifikasi** | Mapping form SPT per jenis pajak: bagian induk, lampiran, field, opsi. Verifikasi tarif dari sumber resmi. | `models.py` (633 baris definisi form) |
| **3. Engine** | Fungsi perhitungan murni + test. | `tax.py` (261 baris), `test_tax.py` |
| **4. Aplikasi** | Shell portal, wizard, form, lampiran, pembayaran, arsip. | `app.py` (1612 baris) |
| **5. Test** | E2E HTTP, navigasi, browser nyata. | `e2e_test.py`, `nav_test.py`, `nav_browser_test.py` |
| **6. Hardening** | Audit kode → 6 temuan kritis → fix + regression test. | `security.py`, `security_test.py` |
| **7. Packaging** | Docker non-root, compose, entrypoint, env. | `Dockerfile`, `docker-compose.yml`, `entrypoint.sh` |
| **8. Dokumentasi** | Arsitektur, deploy, keamanan, API. | `docs/` |

### 1. Mapping — apa yang benar-benar dicek

Live Coretax diakses **read-only** dengan akun OP milik pemilik:

- **Wizard "Buat Konsep SPT"** — 3 langkah: pilih jenis pajak → pilih periode
  pelaporan → pilih model SPT.
- **4 jenis pajak** yang tampil untuk akun OP:
  1. PPh Final Pengungkapan Harta Bersih
  2. PPh Orang Pribadi
  3. PPh Pasal 21/26
  4. PPh Unifikasi
- **Tidak ada submit.** Tidak ada data pribadi yang diekstrak.
- Menu lain (24 halaman di Portal Saya) dipetakan sebagai referensi struktur.

Tiga manual resmi diunduh & diekstrak:

| File | Isi | Ukuran |
|---|---|---|
| `Buku Manual SPT Masa PPN.pdf` | SPT Masa PPN | 7.9 MB |
| `Buku Manual Coretax 2024 - 15 Pelaporan SPT Tahunan PPh OP.pdf` | SPT Tahunan OP | 6.3 MB |
| `Buku Manual SPT Masa PPh 21/26.pdf` | SPT Masa PPh 21/26 | — |

Teks PDF diekstrak dengan `pdftotext -layout` ke `.txt`, lalu dipetakan per
rentang baris.

### 2. Struktur SPT yang terpetakan

**SPT Tahunan PPh Orang Pribadi** — 12 bagian induk + 11 lampiran:

| Bagian | Judul |
|---|---|
| — | Header (Tajuk) |
| A | Identity of Taxpayers |
| B | Summary of Income |
| C | Income Tax Payable Calculation |
| D | Income Tax Credit |
| E | Underpayment/Overpayment Income Tax |
| F | Amendment Tax Return |
| G | Refund |
| H | Income Tax Installment |
| I | Statement of Other Transactions |
| J | Additional Attachments |
| K | Statement |

Lampiran: L-1 (Harta & Kewajiban), L-2 (Penghasilan Final & Luar Negeri),
L-3A-1 … L-3A-4, L-3B, L-3C, L-3D, L-4, L-5.

**SPT Masa PPN** — 5 bagian induk + 6 lampiran (A-1, A-2, B-1, B-2, B-3, C).

**SPT Masa PPh 21/26** — Identitas, Rincian Pemotongan, Penyampaian.

---

## 3. Sumber spesifikasi

Semua angka dan struktur form berasal dari sini — tidak ada yang dikarang:

**Manual DJP**
- *Buku Manual Coretax — Pelaporan SPT Tahunan PPh Orang Pribadi*
- *Buku Manual Coretax — Pelaporan SPT Masa PPh Pasal 21/26*
- *Buku Manual Coretax — SPT Masa PPN*

**Portal Coretax live** (akun OP) — struktur wizard & jenis pajak.

**Dasar hukum tarif**

| Pajak | Dasar hukum |
|---|---|
| PPh Pasal 21 (TER bulanan & harian) | PP 58/2023, PMK 168/2023 |
| PPh Pasal 17 (masa terakhir, non-pegawai tetap) | UU 7/2021 Pasal 17 |
| PTKP | PMK 101/PMK.010/2016 |
| PPN | PMK 131/2024 — 11% umum, 12% subject PPnBM |
| PPh final | UU HPP — 0,5% UMKM, 1% omzet bruto |
| PPh Pasal 25 | Pajak setahun ÷ jumlah bulan angsuran |

**Verifikasi silang** — tarif PPh 21 & PTKP juga dicek dengan kalkulator
pajak pihak ketiga (`kalkulatorpajak.id`) sebagai pembanding, bukan sebagai
sumber utama.

### Contoh verifikasi yang mempengaruhi implementasi

Dari manual, Bagian D (Income Tax Credit):

| Field | Perilaku di Coretax asli | Implementasi di sini |
|---|---|---|
| 10a | Mengaktifkan **Lampiran 1 (L-1) Bagian E** | Kredit diambil dari total "Jumlah Pajak di potong" di L-1/E |
| 10b | Prepopulated dari Pembayaran PPh Pasal 25 | Field angsuran PPh 25 |
| 10c | STP PPh Pasal 25 (hanya pokok pajak) | Field STP |
| 10d | Pengembalian/pengurangan kredit PPh luar negeri | Field kredit luar negeri |

Kredit = bukti potong + angsuran 25 + STP + kredit luar negeri. Field bersifat
read-only di form, dihitung ulang server tiap draft disimpan atau lampiran
ditambah — meniru auto-posting Coretax asli.

---

## 4. Fitur yang diimplementasikan

### Modul SPT (lengkap)

Alur persis seperti portal Coretax:

```
Buat Konsep SPT
  └─ wizard 3 langkah
       └─ isi formulir induk (12 bagian) + lampiran (11)
            └─ hitung otomatis (server + live di browser)
                 └─ simpan draft
                      └─ tanda tangan
                           └─ Pay and Submit (deposit | kode billing)
                                └─ SPT Dilaporkan (arsip)
```

**Jenis SPT tersedia**

| Jenis | Formulir induk | Lampiran | Status |
|---|---|---|---|
| PPh Orang Pribadi | 12 bagian | 11 | ✅ Lengkap |
| PPh Pasal 21/26 | 3 bagian | — | ✅ Lengkap |
| PPh Unifikasi | 4 bagian | — | ✅ Lengkap |
| PPN | 5 bagian | 6 | ✅ Lengkap |
| PPh Final Pengungkapan Harta Bersih | — | — | ⚠️ Kerangka |

> Catatan: portal Coretax asli **tidak** menampilkan PPN untuk akun OP (butuh
> status PKP). SPN PPN tetap disediakan di sini supaya tim bisa latihan SPT
> Masa PPN.

**Status SPT** (mengikuti portal): Konsep SPT → SPT Menunggu Pembayaran →
SPT Dilaporkan. Plus Ditolak & Dibatalkan sebagai tempat status sisa.

### Modul pendukung

| Modul | Isi | Status |
|---|---|---|
| e-Faktur | Daftar faktur pajak keluaran, form buat faktur (DPP & PPN auto) | Daftar + form |
| eBUPOT | Daftar bukti potong (sumber SPT PPh 21/26) | Read-only |
| Pembayaran | Kode billing, riwayat setoran, saldo deposit, tombol bayar | Daftar + aksi |
| Buku Besar | Rekap faktur, PPN keluar, bukti potong, PPh dipotong | Rekap |
| Portal Saya / Layanan WP / Manajemen Akses | Halaman kerangka + navigasi | Kerangka |

### Antarmuka

Shell meniru portal Coretax:

- **Topnav** 8 modul: Portal Saya, e-Faktur, eBUPOT, SPT, Pembayaran, Buku Besar,
  Layanan WP, Manajemen Akses
- **Sidebar** per modul
- **Breadcrumb**, kartu statistik, badge status, tabel dengan filter
- **Live calculation**: ubah angka → hitungan berubah seketika di browser

---

## 5. Engine perhitungan

`tax.py` — fungsi murni, tanpa I/O, mudah diuji terpisah.

```python
hitung_pph21_bulanan(bruto, ptkp_kode)      # TER bulanan (PP 58/2023)
hitung_pph21_harian(bruto)                  # TER harian
hitung_pph21_tidak_tetap(bruto, hari_kerja) # parameterized rate
hitung_pasal17(pkp)                         # tarif progresif UU HPP
hitung_ppn(dpp_keluar, dpp_masuk, ppnbm)    # PMK 131/2024
hitung_pph_final(omzet, status)             # 0,5% / 1%
angsuran_pph25(pajak_setahun, bulan)        # Pasal 25
num(s)                                      # parser angka Indonesia
```

Parser `num()` menerima: `1234567`, `1.234.567`, `1234,56`, `1.234.567,89`.

### Live calculation di browser

`static/live.js` adalah **cermin** `tax.py` — tarif TER A/B/C dan PTKP ditulis
ulang dalam JS. Sumber kebenaran tetap `tax.py`; JS hanya untuk tampilan
interaktif. When JS dan server berbeda, angka server yang tersimpan.

> **Shortcut yang disengaja:** tarif diduplikasi (Python + JS) alih-alih
> memanggil API hitung saat setiap ketikan. Alasannya: respons <50 ms tanpa
> network round-trip. Kalau tarif berubah, **kedua file harus diupdate**.

---

## 6. Keamanan

Detail lengkap di [`docs/KEAMANAN.md`](docs/KEAMANAN.md).

### Audit awal — 6 temuan kritis

Audit kode manual menemukan:

| # | Temuan | Dampak | Status |
|---|---|---|---|
| 1 | `spt_row(id)` = `SELECT WHERE id=?` | **IDOR** — user mana pun bisa buka SPT siapa pun | ✅ Diperbaiki |
| 2 | `do_login` mengabaikan `pwd` | Password **tidak pernah divalidasi** | ✅ Diperbaiki |
| 3 | Tidak ada rate limit | Brute force tanpa hambatan | ✅ Diperbaiki |
| 4 | Tidak ada CSRF | Cross-site request forgery | ✅ Diperbaiki |
| 5 | Tidak ada security headers | Tanpa CSP, bisa di-frame, XSS lebih luas | ✅ Diperbaiki |
| 6 | `SESSION = {}` in-memory | Hilang tiap restart; rusak di multi-worker | ✅ Diperbaiki |

Tambahan: `get_wp()` = `LIMIT 1` → semua user tertaut ke 1 WP. Diperbaiki jadi
multi-user berbasis session.

### Kontrol yang terpasang

| Kontrol | Implementasi |
|---|---|
| Hashing password | PBKDF2-HMAC-SHA256, 200k iterasi, salt per-user |
| Verifikasi | `hmac.compare_digest` (constant-time) |
| Anti brute-force | Lockout per-NPWP (5× gagal → 15 mnt, **termasuk saat password benar**) + batas 20/5 mnt per-IP |
| User enumeration | Pesan seragam + response time disamakan (hash dummy) |
| Session | SQLite, token 256-bit, HttpOnly, SameSite=Lax, TTL 12 jam |
| CSRF | Token per-session, dicek di 8 handler POST |
| IDOR | Filter kepemilikan; role `OP` (operator) vs `WP` (wajib pajak) |
| Headers | CSP `script-src 'self'` + 6 header lain, via middleware |
| SQLi | Semua query ter-parameterisasi |
| XSS | `html.escape` di semua output |
| Container | Non-root uid 10001, `no-new-privileges`, limit CPU/mem, log rotation |

**Kenapa PBKDF2 dan bukan bcrypt/argon2?** Keduanya butuh native binary yang
harus di-compile saat build. Kalau image dibangun di satu CPU dan dijalankan di
arsitektur lain, build bisa gagal. PBKDF2 pure stdlib → image selalu portable.

**Kenapa CSP bisa ketat?** Karena aplikasi tidak memakai inline script maupun
inline style. Data dinamis (mis. PTKP WP) dikirim lewat atribut
`data-ptkp` pada `<body>`, bukan inline `<script>`.

### Audit Strix (AI multi-agent pentest)

Scan black-box terhadap instance container, mode quick, budget $0.60.
Run: `host-docker-internal-8156_cc73`.

| Kategori | Jumlah |
|---|---|
| Ruled out (terbukti aman) | 30+ jalur |
| Vulnerability terkonfirmasi | **1** (`vuln-0001`, CWE-639, Medium) |
| Requires further review | 2 (dicek manual → aman) |

**Temuan utama — `vuln-0001`: list view bocor metadata WP lain.**

`/spt`, `/faktur`, `/bupot`, `/billing`, `/buku-besar`, `/home` mengembalikan
seluruh baris ke session WP mana pun tanpa filter owner. Detail route sudah
owner-filtered, jadi yang bocor adalah metadata (jenis pajak, masa, status,
nilai kurang bayar, ID) + nama counterpart faktur/bupot + agregat keuangan
global — bukan isi formulir.

Strix membuktikan dua arah: record yang dibuat WP langsung muncul di daftar OP,
dan sebaliknya. Keduanya hanya mungkin tanpa predikat owner.

Perbaikan: helper `owner_scope(request, kolom)` → WP dibatasi ke barisnya
sendiri, role `OP` tetap melihat semua. Diterapkan pada 6 query.

**Temuan lain yang sudah ditutup (audit manual, sebelum Strix selesai):**

| Route | Masalah | Perbaikan |
|---|---|---|
| `GET /billing/{id}/bayar` | Tanpa filter `npwp` → WP bisa bayar billing orang lain | Filter `npwp` |
| `GET /spt/{id}/lampiran/{kode}/{lid}/hapus` | Tanpa cek kepemilikan SPT | Cek via `spt_row()` → 404 |
| Kedua route di atas | State change via GET tanpa CSRF | Token CSRF di query string |
| `lampiran_tambah()` | Tidak cek `spt_row()` → HTTP 500 (bukan 404) | Return 404 |
| Lampiran SPT OP | Tidak punya tombol Hapus sama sekali | Kolom Aksi + link Hapus |

Rincian lengkap di [`docs/KEAMANAN.md`](docs/KEAMANAN.md) §5b.

### Multi-user & role

| Role | Akses |
|---|---|
| `WP` — wajib pajak | Hanya SPT, lampiran, faktur, billing miliknya |
| `OP` — operator | Semua SPT (untuk instructor mereview latihan mahasiswa) |

Akses SPT milik orang lain oleh `WP` mengembalikan **404** (bukan 403) supaya
tidak mengonfirmasi keberadaan ID tersebut.

---

## 7. Pengujian

Empat suite, semua dijalankan terhadap server yang benar-benar berjalan.

| Suite | Cakupan | Hasil |
|---|---|---|
| `test_tax.py` | 50 kasus engine pajak (Tarif, PTKP, TER, PPN, final, angsuran, parser angka) | **SEMUA PASS** |
| `e2e_test.py` | 43 pemeriksaan alur HTTP (login → wizard → form → lampiran → draft → TT → billing → bayar → submit), + 17 cek navigasi | **SEMUA E2E PASS** |
| `nav_test.py` | Navigasi antar modul, kompatibilitas URL lama `?modul=` | **SEMUA NAV PASS** |
| `security_test.py` | 26 pemeriksaan keamanan (brute force, CSRF, IDOR, session, enumeration) | **SEMUA SECURITY TEST PASS** |
| `tools/verify_idor.py` | 15 skenario IDOR + CSRF pada write path (billing, lampiran) | **SEMUA PASS** |
| `tools/verify_list_scope.py` | 14 pemeriksaan isolasi list view WP vs OP | **SEMUA PASS** |

### Yang terbukti berjalan

- **Lockout menahan password benar** saat NPWP terkunci — ini yang membuat
  lockout benar-benar berguna, bukan sekadar penundaan.
- **CSRF ditolak** tanpa token, dengan token palsu, dan token milik session lain.
- **IDOR tertutup**: user `TIM KELAS A` (role WP) tidak bisa baca maupun edit
  SPT milik operator.
- **Cookie palsu ditolak** → redirect ke login.
- **Live calc sinkron server**: neto 600 jt → PPh terutang 106.450.000 dan
  kurang bayar 56.450.000, identik di kedua sisi.

### Verifikasi di container

```bash
docker run -d --name coretax-sim-test -p 8156:8140 \
  -e CORETAX_MODE=demo -e CORETAX_SEED_DEMO=1 coretax-sim:latest
```

| Cek | Hasil |
|---|---|
| User container | `uid=10001(app)` — non-root ✅ |
| `/healthz` | `{"status":"ok"}` ✅ |
| Security headers | CSP + X-Frame-Options + nosniff + no-store ✅ |
| Login benar | `303 → /home` ✅ |
| Brute force | terkunci setelah 5 percobaan ✅ |
| Password benar saat terkunci | ditolak, "Coba lagi dalam 15 menit" ✅ |

---

## 8. Deployment

Detail lengkap di [`docs/DEPLOY.md`](docs/DEPLOY.md).

```bash
cp .env.example .env      # edit
docker compose up -d --build
```

Struktur paket:

```
coretax-sim/
├── Dockerfile              multi-stage, non-root, healthcheck
├── docker-compose.yml      volume DB, limit resource, no-new-privileges
├── entrypoint.sh           init DB idempoten + purge session
├── requirements.txt        versi exact
├── .env.example            konfigurasi (12 variabel keamanan)
├── .gitignore .dockerignore
├── app.py models.py security.py tax.py seed.py reset_db.py
├── static/                 app.css, live.js, favicon.svg
├── docs/                   ARSITEKTUR, DEPLOY, KEAMANAN, API
├── data/coretax.db         SQLite (volume, di-backup)
└── test_*.py e2e_test.py nav_test.py security_test.py
```

### Konfigurasi keamanan (`.env`)

| Variabel | Default | Arti |
|---|---|---|
| `CORETAX_MODE` | `demo` | `demo` (data demo) / `strict` |
| `CORETAX_PBKDF2_ITER` | `200000` | Iterasi hashing |
| `CORETAX_SESSION_TTL` | `43200` | Masa session (detik) |
| `CORETAX_MAX_ATTEMPT` | `5` | Gagal sebelum lockout |
| `CORETAX_LOCKOUT_SEC` | `900` | Durasi lockout |
| `CORETAX_IP_ATTEMPT_MAX` | `20` | Batas percobaan per-IP |
| `CORETAX_IP_WINDOW` | `300` | Window batas IP |
| `CORETAX_CSRF_TTL` | `28800` | Masa token CSRF |
| `CORETAX_COOKIE_SECURE` | `0` | Set 1 saat HTTPS |
| `CORETAX_TRUST_PROXY` | `0` | Set 1 **hanya** di belakang reverse proxy |

### Backup

```bash
docker compose exec app python -c "
import sqlite3
src = sqlite3.connect('/app/data/coretax.db')
dst = sqlite3.connect('/app/data/backup.db')
src.backup(dst)"
```

Pakai `sqlite3.backup()`, bukan `cp` — aman walau ada yang sedang menulis.

### Antes sebelum dipakai di luar kelas

- [ ] Ganti password semua akun demo
- [ ] `CORETAX_MODE=strict`, `CORETAX_SEED_DEMO=0`
- [ ] `CORETAX_BIND=127.0.0.1` + reverse proxy TLS
- [ ] `CORETAX_COOKIE_SECURE=1`, `CORETAX_TRUST_PROXY=1`
- [ ] Rate limit di proxy
- [ ] Jadwalkan backup
- [ ] Ganti NIK contoh `2171121009959003` dengan NIK fiktif

---

## 9. Riwayat keputusan

| Keputusan | Alternatif yang ditolak | Alasan |
|---|---|---|
| FastAPI + Jinja2 | React / Next.js | Bentuk kerja = form panjang. Server-rendered; rewrite 1600 baris tidak sepadan. Coretax asli juga server-rendered. |
| SQLite + WAL | PostgreSQL | 1 file, tanpa konfigurasi. Cukup untuk puluhan user kelas. |
| PBKDF2 stdlib | bcrypt / argon2 / passlib | Tanpa native binary → image portable. |
| Session di SQLite | Redis / dict in-memory | In-memory hilang tiap restart. Redis = komponen tambahan untuk kebutuhan yang belum ada. |
| CSRF per-session | Per-request token | Satu GET sudah cukup dapat token; form SPT panjang tidak perlu fetch ulang. |
| Tanpa CAPTCHA | CAPTCHA + rate limit | Rate limit cukup untuk kelas; CAPTCHA menyulitkan akses. |
| Tanpa pagination | Pagination | Skala kelas; ditambahkan kalau data membesar. |
| Tanpa Alembic | Alembic | `CREATE TABLE IF NOT EXISTS` + migrasi kolom manual cukup untuk tahap ini. |

### Bug yang ditemukan & diperbaiki

| Bug | Gejala | Akar masalah |
|---|---|---|
| Nav tidak berpindah modul | Klik "SPT" dari `/faktur` tidak berubah | `href="?modul=X"` URL relatif |
| Kredit pajak selalu 0 | Field read-only tidak pernah terisi | Kredit harus dari L-1/E, bukan field manual |
| `database is locked` | Error saat menambah lampiran | `M.log()` buka koneksi terpisah sebelum commit |
| Live calc tidak sinkron | Angka browser ≠ server | Hidden field tidak pernah disisipkan ke HTML |
| PTKP selalu fallback | Nilai PTKP WP tidak terpakai | Ambil dari `<select>` yang hanya ada di halaman `/wp` |
| Container gagal start | `status=216/GROUP` | `User=` tidak boleh diisi di systemd **user** unit |
| `/healthz` 404 | Endpoint taksts | Server belum restart setelah patch |

---

## 10. Batasan & pekerjaan lanjutan

**Yang belum selesai**

1. **Re-scan Strix setelah perbaikan `vuln-0001` belum dijalankan.** Scan
   pertama sudah selesai dan temuannya sudah ditutup (terverifikasi 14 cek
   `verify_list_scope.py`), tapi belum dikonfirmasi ulang oleh scanner.
2. **PPN belum menarik otomatis dari faktur.** Manual DJP menyebut data faktur
   auto-posting ke SPT PPN; di sini DPP diisi manual.
3. **e-Faktur / eBUPOT / Pembayaran** masih daftar + tombol — belum alur
   multi-langkah seperti portal asli.
4. **Lampiran PPh Final** baru kerangka.
5. **Belum ada pagination** di daftar SPT/faktur/bupot.
6. **Belum ada halaman viewer audit log** (data ada di tabel `log`).
7. **Belum ada 2FA.**
8. **Migrasi skema masih manual** — belum ada Alembic.

**Risiko yang harus diketahui**

- **Tarif diduplikasi di Python + JS.** Kalau tarif berubah, dua file harus
  diupdate. Kalau tidak, tampilan live_calc bisa berbeda dari angka tersimpan.
- **`CORETAX_TRUST_PROXY=1`** hanya aman kalau aplikasi tidak bisa dijangkau
  langsung dari luar (bind ke `127.0.0.1`). Kalau terekspos, `X-Forwarded-For`
  bisa dipalsukan klien dan batas per-IP dilewati.
- **Akun demo pakai NIK `2171121009959003`** yang milik asli — harus diganti.
- **Struktur SPT bisa berubah** kalau DJP memperbarui manual. Pemetaan di
  `models.py` perlu ditinjau ulang tiap tahun pajak baru.

---

## 11. Riwayat perubahan

| Tanggal | Perubahan |
|---|---|
| 2026-11-09 | Mapping live Coretax + 3 Buku Manual DJP |
| 2026-11-09 | Spesifikasi form SPT: 12 bagian + 11 lampiran (OP), 5 + 6 (PPN) |
| 2026-11-09 | Engine `tax.py` + 50 unit test |
| 2026-11-09 | Aplikasi FastAPI: shell, wizard, form, lampiran, bayar, arsip |
| 2026-11-09 | E2E 43 + nav 8 + browser test |
| 2026-11-09 | Perbaikan nav modul (URL relatif → absolut) |
| 2026-11-09 | Hardening: 6 temuan kritis → password hash, session DB, rate limit, CSRF, headers, IDOR guard |
| 2026-11-09 | Multi-user + role WP/OP, 4 akun demo |
| 2026-11-09 | Packaging Docker (non-root), compose, entrypoint, `.env.example` |
| 2026-11-09 | Dokumentasi: ARSITEKTUR, DEPLOY, KEAMANAN, API, dokumen ini |
| 2026-11-09 | Build + run container terverifikasi (uid 10001, headers, lockout) |
| 2026-11-09 | Audit Strix: 1 temuan Medium (list view bocor metadata, CWE-639) → ditutup |
| 2026-11-09 | Audit manual: 5 IDOR/CSRF tambahan ditutup (billing, hapus lampiran, CSRF GET) |