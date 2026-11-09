# API Reference — Simulator Coretax DJP

Aplikasi ini **server-rendered**: sebagian besar endpoint mengembalikan HTML,
bukan JSON. Halaman dimuat lewat form `POST` biasa, bukan fetch/XHR — sama
seperti portal Coretax asli, dan disengaja agar perennial diDepan syllabus.

---

## Konvensi

| Aspek | Nilai |
|---|---|
| Base URL | `http://<host>:8140` |
| Auth | Cookie session `ctx` (HttpOnly, SameSite=Lax) |
| Format | HTML (`text/html`) kecuali `/healthz` (JSON) |
| Encoding | UTF-8 |
| CSRF | Field `csrf_token` wajib di semua POST (kecuali `/login`) |
| Content-Type | `application/x-www-form-urlencoded` |

Semua respons membawa header keamanan (lihat `docs/KEAMANAN.md` §6).

---

## Health

### `GET /healthz`

Healthcheck untuk Docker/Kubernetes. Tidak butuh auth.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok"}
```

Return `503` dengan `{"status":"error","detail":"..."}` kalau DB tidak terjangkau.

---

## Autentikasi

### `GET /`

Halaman login. Kalau sudah login → `307` ke `/home`.

```html
<form method="post" action="/login" class="stack">
  <input name="id" placeholder="2171121009959003" required>
  <input name="pwd" type="password" required>
  <input type="checkbox" name="robot" checked>
  <button class="btn-primary" type="submit">Masuk</button>
</form>
```

### `POST /login`

| Field | Tipe | Keterangan |
|---|---|---|
| `id` | string | NIK/NPWP/NITKU wajib pajak |
| `pwd` | string | Kata sandi |
| `robot` | checkbox | Honeypot ringan (diabaikan server) |

**Sukses** → `303` ke `/home`, dengan `Set-Cookie: ctx=...; HttpOnly; SameSite=Lax; Path=/`.

**Gagal** → `200` dengan halaman login + pesan di `#login-msg`. Pesan selalu
seragam ("NIK/NPWP atau kata sandi salah.") supaya tidak bisa dipakai memetakan
NIK terdaftar.

**Terkunci** → `200` dengan pesan "Terlalu banyak percobaan. Coba lagi dalam
N menit." (lockout per-NPWP, `CORETAX_MAX_ATTEMPT` × `CORETAX_LOCKOUT_SEC`).

```bash
curl -i -X POST -d 'id=2171121009959003&pwd=demo123' http://localhost:8140/login
```

### `GET /logout`

Menghapus session, `303` ke `/`, hapus cookie.

---

## Navigasi

| Method | Path | Keterangan |
|---|---|---|
| `GET` | `/home` | Dashboard. Query `?modul=X` di-redirect ke path modul yang benar (kompatibilitas URL lama) |
| `GET` | `/faktur` | Daftar e-Faktur |
| `GET` | `/bupot` | Daftar bukti potong |
| `GET` | `/spt` | Daftar SPT. Query: `status`, `jenis`, `Searching` |
| `GET` | `/billing` | Kode billing + saldo deposit |
| `GET` | `/buku-besar` | Rekap omzet & pajak |
| `GET` | `/wp` | Ubah data WP (termasuk status PTKP) |
| `GET` | `/layanan` | Kerangka halaman layanan |
| `GET` | `/akses` | Kerangka manajemen akses |

Semua butuh session. Tanpa cookie valid → `307` ke `/`.

---

## SPT

### `GET /spt/buat` — Langkah 1

Pilih jenis pajak. Kartu-kartu berasal dari `models.JENIS_PAJAK`.

### `GET /spt/buat/periode?jenis=...` — Langkah 2

Pilih periode pelaporan + jenis periode (Tahunan / Masa).

### `GET /spt/buat/jenis?jenis=...&periode=...&jenis_periode=...` — Langkah 3

Pilih model SPT (`Normal` / `Pembetulan`).

### `POST /spt/buat/simpan`

| Field | Tipe | Contoh |
|---|---|---|
| `jenis` | string | `PPh Orang Pribadi` |
| `periode` | string | `Januari - Desember 2025` |
| `jenis_periode` | string | `SPT Tahunan` / `SPT Masa` |
| `model` | string | `Normal` / `Pembetulan` |
| `csrf_token` | string | Wajib |

→ `303` ke `/spt/{id}/edit`.

### `GET /spt/{id}` — Ringkasan hasil penghitungan

Menampilkan hasil hitung (neto, PKP, PPh terutang, kredit, kurang/lebih bayar,
angsuran PPh 25) + ringkasan per bagian.

### `GET /spt/{id}/edit` — Formulir induk

12 bagian (SPT Tahunan OP), atau 3–5 bagian (SPT Masa). Field bertipe `calc`
bersifat read-only dan nilainya dihitung server.

### `POST /spt/{id}/simpan`

Menyimpan draft. Body = seluruh field form + `csrf_token`.

Perhitungan dihitung ulang server, dan `spt.hitung` + `kurang_bayar` di-update.

→ `303` ke `/spt/{id}`.

### Lampiran

| Method | Path | Keterangan |
|---|---|---|
| `GET` | `/spt/{id}/lampiran/{kode}` | Form tambah data (lampiran kolom) |
| `GET` | `/spt/{id}/lampiran/{kode}/{sub1}/{sub2}` | Form tambah data (lampiran per-bagian) |
| `POST` | `/spt/{id}/lampiran/{kode}/simpan` | Simpan baris lampiran |
| `POST` | `/spt/{id}/lampiran/{kode}/{sub1}/{sub2}/simpan` | Simpan baris lampiran (per-bagian) |
| `GET` | `/spt/{id}/lampiran/{kode}/{lid}/hapus` | Hapus baris |

Penting: **Lampiran 1 (L-1) Bagian E = Daftar Bukti Pemotongan** — isinya
otomatis menjadi kredit pajak di Bagian D. Menambah/menghapus baris L-1/E
memaksa server menghitung ulang SPT.

### `GET /spt/{id}/tt` — Tanda tangan & pelaporan

Form penencoreaan (Signer Provider, Signer ID, Passphrase, Jabatan) +
ringkasan posisi pajak + pilihan metode pelunasan.

### `POST /spt/{id}/tt/simpan`

Simpan tanda tangan (`tanda_tangan = 1`).

### `POST /spt/{id}/submit`

| Field | Tipe | Keterangan |
|---|---|---|
| `metode` | string | `billing` (default) atau `deposit` |
| `csrf_token` | string | Wajib |

Perilaku:

| Posisi pajak | Hasil |
|---|---|
| Nihil | Langsung `SPT DilCocorkan`, `tgl_disampaikan` diisi |
| Kurang Bayar + `deposit` + saldo cukup | Saldo dipotong, `SPT Dilaporkan` |
| Kurang Bayar + `deposit` + saldo kurang | `SPT Menunggu Pembayaran` |
| Kurang Bayar + `billing` | Kode billing dibuat, `SPT Menunggu Pembayaran` |

→ `303` ke `/spt/{id}`.

---

## Modul lain

### `GET /faktur` · `POST /faktur/tambah`

Buat faktur pajak. Field: `masa_pajak`, `nama_pembeli`, `npwp_pembeli`,
`kode_barang`, `nama_barang`, `jumlah`, `harga_satuan`, `nilai` (total termasuk PPN).
DPP dan PPN dihitung otomatis (dibagi 1,11).

### `GET /bupot`

Daftar bukti potong (read-only di simulator; sumber data untuk SPT PPh 21/26).

### `GET /billing` · `GET /billing/{id}/bayar`

Daftar kode billing. Endpoint `bayar` memotong saldo deposit, menandai billing
`Lunas`, dan mengubah SPT jadi `SPT Dilaporkan`.

### `GET /buku-besar`

Rekapitulasi: total faktur, total PPN keluar, total bukti potong, total PPh
dipotong.

### `POST /wp/simpan`

Ubah profil WP: `nama`, `alamat`, `kpp`, `telepon`, `email`, `ptkp_kode`.
Perubahan `ptkp_kode` langsung memengaruhi perhitungan PPh.

---

## Static files

| Path | Keterangan |
|---|---|
| `/static/app.css` | Stylesheet |
| `/static/live.js` | Live calculation di browser |
| `/static/favicon.svg` | Favicon |
| `/favicon.ico` | Redirect ke SVG (301) |

---

## Format angka

Semua input dan output angka memakai format Indonesia:

- Input diterima: `1234567`, `1.234.567`, `1234,56`, `1.234.567,89`
- Output: `1.234.567,00`

Parser ada di `tax.num()`.

---

## Perilaku otorisasi

| Role | Akses |
|---|---|
| `WP` (wajib pajak) | Hanya SPT, lampiran, faktur, billing miliknya sendiri |
| `OP` (operator) | Semua SPT (untuk instructor mereview latihan mahasiswa) |

Akses SPT milik orang lain oleh `WP` mengembalikan **404** (bukan 403) supaya
tidak mengonfirmasi keberadaan ID tersebut.

---

## Audit trail

Setiap aksi penting dicatat di tabel `log`:

| Aksi | Kapan |
|---|---|
| `login` / `login_gagal` / `login_blocked` | Setiap percobaan login |
| `buat_konsep_spt` | Konsep SPT dibuat |
| `simpan_draft_spt` | Draft disimpan |
| `tambah_lampiran` | Baris lampiran ditambahkan |
| `tt_spt` | Dokumen ditandatangani |
| `submit_spt` | SPT dikirim |
| `bayar_billing` | Kode billing dibayar |
| `buat_faktur` | Faktur pajak diterbitkan |

Kolom: `waktu`, `actor` (NPWP), `aksi`, `detail`.

Belum ada endpoint untuk membacanya — query langsung:

```bash
docker compose exec app python -c "
import models as M
c = M.conn()
for r in c.execute('SELECT * FROM log ORDER BY id DESC LIMIT 20'):
    print(dict(r))"
```
