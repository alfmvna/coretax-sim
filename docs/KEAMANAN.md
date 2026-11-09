# Keamanan — Simulator Coretax DJP

Dokumen ini menjelaskan apa yang sudah diamankan, bagaimana cara kerjanya, dan
apa yang **belum** diamankan.

> **Konteks:** aplikasi ini adalah simulator untuk pembelajaran mahasiswa.
> Data yang masuk adalah fiktif. Tapi aplikasi ini tetap diaudit dan di-hardening
> supaya kelas bisa dipakai dengan aman dan tidak menjadi celah yang bisa
> dieksploitasi untuk hal lain.

---

## Ringkasan status

| Area | Status | Implementasi |
|---|---|---|
| Hashing password | ✅ | PBKDF2-HMAC-SHA256, 200.000 iterasi, salt per-user |
| Verifikasi password | ✅ | `hmac.compare_digest` (constant-time) |
| Anti brute-force | ✅ | Lockout per-NPWP + batas per-IP |
| User enumeration | ✅ | Pesan error seragam |
| Session | ✅ | Persisten di SQLite, HttpOnly, SameSite, TTL |
| CSRF | ✅ | Token per-session, dicek di semua POST |
| IDOR | ✅ | `spt_row()` filter kepemilikan, role-based access |
| Security headers | ✅ | CSP ketat + 6 header lain |
| SQL injection | ✅ | Semua query ter-parameterisasi |
| XSS | ✅ | `html.escape` di semua output |
| Path traversal | ✅ | Tidak ada input path ke filesystem |
| Container hardening | ✅ | Non-root, no-new-privileges, resource limits |
| TLS | ⚠️ | Perlu reverse proxy (Caddy/nginx) |
| Rate limit di proxy | ⚠️ | Opsional, rekomendasi untuk internet publik |
| 2FA / MFA | ❌ | Tidak ada |
| Audit log UI | ❌ | Ada di DB (`tabel log`), belum ada halaman viewers |
| Content-Security-Policy nonce | ❌ | Tidak perlu — app tidak pakai inline script |

---

## 1. Password

### Hashing

```python
# security.py
def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
    return dk.hex(), salt.hex()
```

**Kenapa PBKDF2 dan bukan bcrypt/argon2?**
Keduanya butuh native binary (compile saat build). Kalau image dibangun di satu
CPU dan dijalankan di arsitektur lain (mis. ARM di Raspberry Pi), build bisa
gagal. PBKDF2 pure stdlib → image selalu portable.

200.000 iterasi ≈ 100 ms per verifikasi di CPU modern. Cukup mahal untuk
brute-force offline, cukup cepat untuk login normal.

### Verifikasi

```python
dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
return hmac.compare_digest(dk, expected)
```

`hmac.compare_digest`constant-time — mencegah timing attack yang menebak hash
karakter demi karakter.

### Ganti password

```bash
docker compose exec app python -c "
import models as M, security as S
c = M.conn()
h, s = S.hash_password('password-baru')
c.execute('UPDATE wp SET password_hash=?, salt=? WHERE npwp=?', (h, s, '1111111111111'))
c.commit(); print('ok')"
```

---

## 2. Anti brute-force

Dua lapis, keduanya di `security.py`:

### Lapis 1 — lockout per-NPWP

| Setting | Default | Env |
|---|---|---|
| Maks percobaan gagal | 5 | `CORETAX_MAX_ATTEMPT` |
| Durasi lockout | 900 detik (15 mnt) | `CORETAX_LOCKOUT_SEC` |

Setelah 5× gagal, NPWP itu terkunci 15 menit — **termasuk saat passwordnya
benar**. Ini penting: kalau tidak, penyerang bisa menunggu dan mencoba lagi.

### Lapis 2 — batas per-IP

| Setting | Default | Env |
|---|---|---|
| Maks percobaan per-IP | 20 | `CORETAX_IP_ATTEMPT_MAX` |
| Window | 300 detik | `CORETAX_IP_WINDOW` |

Mencegah satu IP menyapu banyak NPWP berbeda (mis. daftar NIK dari leak).
Penting kalau aplikasinya bisa diakses publik.

> `client_ip()` hanya mempercayai `X-Forwarded-For` kalau `CORETAX_TRUST_PROXY=1`.
> Tanpa itu, header itu bisa dipalsukan oleh klien sendiri untuk melewati batas per-IP.

### Yang **tidak** dilakukan (sengaja)

- **Tidak ada CAPTCHA.** CAPTCHAs lebih banyak()`, tapi untuk kelas yang terkontrol
  ribet. Rate limit sudah menutup jalur brute-force. Kalau aplikasi dipublikasikan
  luas, tambahkan CAPTCHA di halaman login.
- **Tidak ada delay eksponensial.** Lockout 15 menit sudah cukup efektif dan
  tidak memperlambat user yang salah ketik 1-2 kali.
- **Password tidak pernah di-log.** Tabel `log` hanya mencatat aksi, bukan kredensial.

### User enumeration

Pesan error untuk NPWP tidak terdaftar **sama persis** dengan password salah:

> "NIK/NPWP atau kata sandi salah."

Tidak ada endpoint "cek apakah NIK terdaftar". Response time juga dibuat
seragam: saat NPWP tidak ditemukan, kode tetap menjalankan PBKDF2 terhadap
hash dummy (lihat §7) sehingga waktunya sama dengan kasus password salah.

---

## 3. Session

```python
SESSION_COOKIE = "ctx"
# cookie: HttpOnly; SameSite=Lax; Secure (kalau HTTPS); Max-Age=TTL
```

| Aspek | Keputusan | Alasan |
|---|---|---|
| Penyimpanan | Tabel `session` di SQLite | Bertahan restart; konsisten antar worker |
| Token | `secrets.token_urlsafe(32)` (256-bit) | CSPRNG, tidak bisa ditebak |
| TTL | 12 jam default | Menutup sesi di kelas; logout tombol ada |
| Cookie `HttpOnly` | Ya | JavaScript tidak bisa baca token → lessen XSS |
| Cookie `SameSite` | `Lax` | Mencegah cookie dikirim pada POST lintas situs (lapisan CSRF tambahan) |
| Cookie `Secure` | Hanya kalau `CORETAX_COOKIE_SECURE=1` | Tidak bisa aktif di HTTP-only LAN |

Sesi yang kedaluwarsa dihapus otomatis saat diakses (`get_session`) dan saat start
container (`purge_expired`).

---

## 4. CSRF

Token acak per-session (32 karakter), disimpan di tabel `session`.

```html
<form method="post" action="/spt/{id}/simpan">
  <input type="hidden" name="csrf_token" value="...">
```

Semua POST kecuali `/login` memvalidasi token:

```python
form = await request.form()
if not check_csrf(request, form):
    return HTMLResponse("403 ...", status_code=403)
```

`hmac.compare_digest` dipakai untuk perbandingan.

CSRF token dibuat **per-session**, bukan per-request — jadi satu `GET` halaman
form sudah cukup untuk mendapatkan token yang berlaku lama.

---

## 5. IDOR / otorisasi

Sebelum hardening, `spt_row(spt_id)` hanya `SELECT * FROM spt WHERE id=?` —
**siapa pun yang login bisa membuka SPT siapa pun** dengan menebak ID.

Sekarang:

```python
def spt_row(spt_id, request=None):
    npwp = current_npwp(request)
    role = ...  # dari tabel wp
    if role == "OP":
        return SELECT ... WHERE id=?          # operator: semua SPT
    return SELECT ... WHERE id=? AND npwp=?   # WP: hanya miliknya
```

Role:
- `WP` — wajib pajak. Hanya melihat SPT sendiri.
- `OP` — operator. Melihat semua SPT (berguna untuk instructor yang mau
  mereview hasil latihan mahasiswa).

Semua 8 call site `spt_row()` sudah dipasses `request`.

---

## 6. Security headers

Middleware global (`app.py`) — dipasang ke semua respons, termasuk halaman error.

```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self';
  frame-ancestors 'none'; base-uri 'self'; object-src 'none'
Strict-Transport-Security: max-age=31536000; includeSubDomains
Cache-Control: no-store          (halaman HTML)
```

### Catatan CSP

Aplikasi **tidak** memakai inline `<script>` atau `style="..."` — semua CSS di
`static/app.css`, JS di `static/live.js`. Ini disengaja supaya CSP bisa
`script-src 'self'` tanpa `unsafe-inline`.

Data dinamis yang biasanya butuh inline script (mis. PTKP WP) dikirim lewat
atribut `data-ptkp` pada `<body>`:

```html
<body data-ptkp="K/0">
```

lalu dibaca di JS: `document.body.dataset.ptkp`.

---

## 7. Timing attack pada user enumeration

Kode login:

```python
row = c.execute("SELECT * FROM wp WHERE npwp=?", (npwp,)).fetchone()
if row is None or not row["aktif"]:
    S.register_failed(c, npwp, ip)
    return login_page(pesan_gagal)     # <- TIDAK hashing

if not S.verify_password(pwd, row["password_hash"], row["salt"]):
    ...
```

Jika NPWP tidak terdaftar, response time jauh lebih singkat (tidak ada PBKDF2
200k iterasi). Attacker bisa memetakan NIK mana yang terdaftar.

`verify_password` dijalankan terhadap dummy hash ketika user tidak ditemukan:

```python
if row is None:
    # hash dummy supaya timing seragam
    S.verify_password(pwd, DUMMY_HASH, DUMMY_SALT)
    S.register_failed(c, npwp, ip)
    return login_page(pesan_gagal)
```

---

## 8. SQL Injection

Semua query memakai parameter binding:

```python
c.execute("SELECT * FROM spt WHERE id=? AND npwp=?", (spt_id, npwp))
```

Tidak ada string interpolation ke SQL. Satu-satunya `execute(f"...")` ada di
`models.py` untuk `ALTER TABLE` — nama kolomnya dari **tuple literal** di dalam
kode, bukan dari input user.

---

## 9. XSS

Semua output dinamis melalui `esc()`:

```python
def esc(s) -> str:
    return html.escape("" if s is None else str(s))
```

Dicek pada halaman yang berisi data dari user (nama WP, isi form, nama
pembeli faktur, keterangan lampiran).

---

## 10. Hardening container

| Measure | Detail |
|---|---|
| Non-root | User `app` uid/gid 10001, shell `nologin` |
| Multi-stage build | Runtime image tidak punya compiler/pip cache |
| `no-new-privileges` | `security_opt` di compose |
| Resource limits | 1 CPU, 512 MB |
| Dependency pinned | `requirements.txt` dengan versi exact |
| Data di volume | DB di luar image, `VOLUME /app/data` |
| Log rotation | json-file, 10 MB × 3 file |
| `.dockerignore` | Test, screenshot, `.env`, DB tidak masuk image |
| Healthcheck | `GET /healthz` → 200 |

Image final berjalan sebagai user non-root dengan working directory yang hanya
dimiliki user tersebut.

---

## 11. Daftar periksa sebelum dipakai di luar kelas

- [ ] Ganti password semua akun demo
- [ ] `CORETAX_MODE=strict`, `CORETAX_SEED_DEMO=0`
- [ ] Ganti `CORETAX_BIND` ke `127.0.0.1` + pasang reverse proxy TLS
- [ ] `CORETAX_COOKIE_SECURE=1`
- [ ] `CORETAX_TRUST_PROXY=1` (hanya kalau lewat proxy)
- [ ] Tambah rate limit di proxy
- [ ] Jadwalkan backup harian
- [ ] Pastikan `data/` tidak masuk git (sudah ada di `.gitignore`)
- [ ] Ganti NIK contoh `2171121009959003` dengan NIK fiktif kalau masih dipakai

---

## 12. Known gaps (sengaja, terdokumentasi)

1. **Tidak ada 2FA.** Untuk aplikasi kelas, risikonya rendah.
2. **Tabel `log` belum punya halaman viewer.** Data audit ada, tapi belum bisa
   dibaca lewat UI.
3. **CSP belum pakai nonce.** Tidak perlu selama tidak ada inline script.
4. **Session tidak bisa dicabut dari sisi server** selain logout per-token.
   Untuk memblokir user sepenuhnya, set `wp.aktif = 0`.
5. **Belum ada Content-Security-Policy `report-uri`.** Violation CSP tidak
   dilaporkan ke mana pun. Tambahkan kalau perlu monitoring.
6. **Belum ada pagination** pada daftar SPT/faktur/bupot. Untuk skala kelas
   cukup; kalau data tumbuh besar, tambahkan LIMIT/OFFSET.