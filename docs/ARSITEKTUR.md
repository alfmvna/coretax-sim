# Arsitektur Simulator Coretax DJP

## Gambaran umum

```
Browser (mahasiswa)
   │  HTTP/HTTPS
   ▼
Reverse proxy (Caddy / nginx)          ← opsional: TLS, rate limit tambahan
   │
   ▼
┌─────────────────────────────────────────┐
│ Container "coretax-sim"                │
│                                         │
│  uvicorn (1 worker default)             │
│    └── FastAPI app                      │
│         ├── app.py    — shell, wizard, form, lampiran, bayar, submit
│         ├── models.py — definisi form SPT (12 bagian + 11 lampiran), skema DB
│         ├── security.py— hash password, session, rate limit, CSRF, headers
│         ├── tax.py     — engine perhitungan pajak (fungsi murni)
│         └── static/    — app.css, live.js (live calc), favicon
│                                         │
│  Volume: /app/data/coretax.db          ← SQLite (WAL mode)
└─────────────────────────────────────────┘
```

## Kenapa stack ini

| Keputusan | Alasan |
|---|---|
| **FastAPI + Jinja2** (server-rendered) | Bentuk kerja aplikasi adalah form panjang (12 bagian + 11 lampiran). Server-rendered cocok; tidak perlu SPA. Coretax asli juga server-rendered (PrimeNG + Angular) — jadi behavior-nya lebih mirip, bukan kurang. |
| **SQLite + WAL** | Nol konfigurasi: 1 file, tanpa container DB, tanpa password DB. Cukup untuk puluhan user kelas. WAL mode mencegah "database is locked" saat beberapa user menulis bersamaan. |
| **PBKDF2-HMAC-SHA256 via `hashlib`** | Pure stdlib. Sengaja tanpa `passlib`/`bcrypt` agar tidak ada native binary yang harus di-compile saat build di server lain. |
| **Session di SQLite** | Bertahan restart/redeploy, dan konsisten antar worker. Dict in-memory hilang tiap restart. |
| **1 file JS, tanpa build step** | `static/live.js` (live calc) — tanpa npm, tanpa webpack, tanpa node_modules. |

## Layer & alur data

```
Request
  │
  ├─ middleware: security_headers()      → CSP, X-Frame-Options, dll
  │
  ├─ auth: current_npwp(request)         → session cookie → tabel session
  │      └─ current_wp(request)          → row wp milik session
  │
  ├─ authz: spt_row(id, request)         → IDOR guard
  │      └─ role OP: semua SPT; role WP: hanya SPT-nya
  │
  ├─ CSRF: check_csrf(request, form)     → wajib di semua POST
  │
  ├─ handler
  │    ├─ baca form → data dict
  │    ├─ hitung_spt(spt, data, request) → hitung_spt via tax.py
  │    ├─ tulis ke SQLite
  │    └─ render HTML (shell)
  │
  └─ Response + security headers
```

## Model data

```
wp (1) ──< spt (N) ──< lampiran (N)
 │            │
 │            └──< billing (N)
 │
 ├── deposit (1:1 per npwp)
 ├── session (1:N per user)
 └── percobaan_login (audit brute-force)
```

- `wp.npwp` = identitas login (NIK/NPWP/NITKU)
- `wp.role` = `OP` (operator, boleh lihat semua SPT) atau `WP` (wajib pajak, hanya SPT-nya)
- `spt.data` = JSON berisi seluruh isian form (12 bagian)
- `spt.hitung` = JSON berisi hasil perhitungan (k-cache, di-refresh tiap simpan)
- `lampiran.data` = JSON per baris lampiran

**Shortcut yang disengaja:** `spt.data` dan `lampiran.data` disimpan sebagai JSON blob, bukan tabel relasional per kolom. Cukup untuk simulasi; analytics lintas SPT akan lebih sulit. Kalau nanti butuh statistik, migrasi ke kolom terpisah.

## Komponen

| File | Tanggung jawab |
|---|---|
| `app.py` | Shell (topnav + sidebar), wizard SPT 3 langkah, form per jenis SPT, lampiran, tanda tangan, bayar, submit, modul e-Faktur/eBUPOT/Pembayaran/Buku Besar |
| `models.py` | Definisi field form SPT (dari Buku Manual DJP), skema DB, migrasi ringan, user demo |
| `security.py` | `hash_password`/`verify_password`, session, `login_blocked`/`register_failed`, CSRF, `security_headers` |
| `tax.py` | Engine perhitungan murni: PPh 21 TER, Pasal 17, PPN, PPh final, PPh 25, PTKP |
| `seed.py` | Data demo: faktur, bukti potong, deposit, SPT contoh |
| `reset_db.py` | Reset DB ke kondisi bersih (idempoten) |
| `static/live.js` | Live calculation di browser (cermin `tax.py`) |

## Referensi spesifikasi

Struktur form SPT diambil dari sumber resmi, bukan dikarang:

- *Buku Manual Coretax — Pelaporan SPT Tahunan PPh Orang Pribadi* (DJP, 2024)
  → 12 bagian induk (Header, A–K) + 11 lampiran (L-1 … L-5)
- *Buku Manual Coretax — Pelaporan SPT Masa PPh Pasal 21/26* (DJP)
- *Buku Manual Coretax — SPT Masa PPN* (DJP, 2025)
  → 5 bagian induk + 6 lampiran (A-1 … C)
- Wizard "Buat Konsep SPT" portal Coretax (akun OP) — struktur 3 langkah & 4 jenis pajak

Tarif yang dipakai (lihat `tax.py` untuk referensi per fungsi):

| Pajak | Dasar hukum |
|---|---|
| PPh Pasal 21 (TER) | PP 58/2023, PMK 168/2023 |
| PPh Pasal 17 (UU HPP) | UU 7/2021 Pasal 17 |
| PTKP | PMK 101/PMK.010/2016 |
| PPN | PMK 131/2024 (11% umum, 12% subject PPnBM) |
| PPh final | UU HPP (0,5% UMKM / 1% omzet bruto) |

## Batasan yang diketahui

- Modul e-Faktur / eBUPOT / Pembayaran masih daftar + tombol dasar, belum alur multi-langkah seperti portal asli.
- PPN **belum** menarik otomatis dari faktur — DPP diisi manual di form.
- Lampiran PPh Final (Pengungkapan Harta Bersih) baru kerangka.
- Skema memakai `CREATE TABLE IF NOT EXISTS` + migrasi kolom manual — belum ada Alembic.
- Multi-user: setiap WP punya SPT-nya sendiri, tapi belum ada fitur "lihat semua SPT" untuk instructor.
