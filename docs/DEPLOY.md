# Panduan Deployment — Simulator Coretax DJP

## Ringkas

```bash
git clone <repo> coretax-sim && cd coretax-sim
cp .env.example .env          # edit bila perlu
docker compose up -d --build
docker compose exec app python reset_db.py --yes   # reset + seed demo (opsional)
```

Aplikasi jalan di `http://<ip-server>:8140`.

---

## 1. Prasyarat

- Docker Engine 24+ dan Docker Compose v2
- Port 8140 bebas
- Untuk akses dari internet: domain + reverse proxy dengan TLS

Cek:
```bash
docker --version && docker compose version
```

---

## 2. Deploy di server sendiri (VPS / LAN)

### 2.1 Setup

```bash
cd ~/projects/coretax-sim     # atau clone
cp .env.example .env
```

`.env` yang perlu diubah untuk produksi:

```ini
CORETAX_BIND=127.0.0.1        # WAJIB 127.0.0.1 kalau pakai reverse proxy
CORETAX_MODE=strict           # tanpa data demo
CORETAX_SEED_DEMO=0
CORETAX_COOKIE_SECURE=1       # karena HTTPS
CORETAX_TRUST_PROXY=1         # hanya kalau reverse proxy set X-Forwarded-For
```

### 2.2 Jalankan

```bash
docker compose up -d --build
docker compose logs -f app
```

Cek sehat:
```bash
curl http://127.0.0.1:8140/healthz
# {"status":"ok"}
```

### 2.3 Data demo (opsional, untuk kelas)

```bash
docker compose exec app python reset_db.py --yes
```

Atau set `CORETAX_SEED_DEMO=1` di `.env` supaya container mengisinya otomatis saat start.

### 2.4 User

Akun demo dibuat otomatis oleh `init_db()`:

| NIK/NPWP | Nama | Role | Status PTKP |
|---|---|---|---|
| `2171121009959003` | ALLIF MAULANA | OP | K/0 |
| `1111111111111` | TIM KELAS A | WP | TK/0 |
| `2222222222222` | TIM KELAS B | WP | K/0 |
| `3333333333333` | TIM KELAS C | WP | K/1 |

Password awal semua: `demo123`

> **Wajib ganti password sebelum dipakai di luar kelas.**
> ```bash
> docker compose exec app python -c "
> import models as M, security as S
> c = M.conn()
> h, s = S.hash_password('password-baru-anda')
> c.execute('UPDATE wp SET password_hash=?, salt=? WHERE npwp=?', (h, s, '1111111111111'))
> c.commit(); print('ok')"
> ```

### 2.5 Restart / update

```bash
docker compose restart app     # restart
docker compose up -d --build   # rebuild setelah update kode
```

> Setelah mengubah `.env`, wajib `docker compose up -d --force-recreate`
> — `restart` saja tidak membaca ulang `env_file`.

---

## 3. Reverse proxy + TLS (wajib kalau internet publik)

Contoh dengan Caddy (`/etc/caddy/Caddyfile`):

```caddy
coretax.example.id {
    reverse_proxy 127.0.0.1:8140 {
        header_up X-Forwarded-For {remote_host}
        header_up X-Real-IP {remote_host}
    }
}
```

Lalu di `.env`: `CORETAX_BIND=127.0.0.1`, `CORETAX_COOKIE_SECURE=1`, `CORETAX_TRUST_PROXY=1`.

Caddy otomatis dapat sertifikat Let's Encrypt. Alternatif: nginx + certbot.

**Penting:** `CORETAX_TRUST_PROXY=1` hanya aman kalau aplikasi **tidak** bisa dijangkau langsung dari luar (bind ke 127.0.0.1). Kalau aplikasi terekspos langsung, siapa pun bisa memalsukan `X-Forwarded-For` dan melewati batas percobaan per-IP.

### Rate limit tambahan di proxy

Caddy:
```caddy
coretax.example.id {
    reverse_proxy 127.0.0.1:8140
    # blokir IP yang terlalu agresif
}
```

nginx (di blok `server`):
```nginx
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;

location /login {
    limit_req zone=login burst=5 nodelay;
    proxy_pass http://127.0.0.1:8140;
}
```

Lapisan rate limit di aplikasi (SQLite) tetap menyala sebagai lapis kedua.

---

## 4. Backup & restore

Database = 1 file di volume Docker.

```bash
# Backup
docker compose exec app python -c "
import sqlite3
src = sqlite3.connect('/app/data/coretax.db')
dst = sqlite3.connect('/app/data/backup.db')
src.backup(dst)          # backup API: aman walau ada yang sedang menulis
dst.close(); src.close()
print('backup ok')"
docker compose cp app:/app/data/backup.db ./coretax-backup-$(date +%F).db

# Restore
docker compose cp ./coretax-backup-2026-11-09.db app:/app/data/coretax.db
docker compose restart app
```

Jadwal harian (crontab user):
```cron
15 2 * * * cd ~/projects/coretax-sim && docker compose exec -T app python -c "import sqlite3; s=sqlite3.connect('/app/data/coretax.db'); d=sqlite3.connect('/app/data/bk.db'); s.backup(d)" && docker compose exec -T app rm -f /app/data/bk.db
```

Jangan `cp` file `.db` langsung saat container berjalan — bisa dapat file yang belum konsisten. Paket `sqlite3.backup()` di atas aman.

---

## 5. Update aplikasi

```bash
cd ~/projects/coretax-sim
git pull
docker compose up -d --build
docker compose exec app python -c "import models as M; M.init_db(); print('migrasi ringan ok')"
```

`init_db()` idempoten: aman dijalankan setiap start, hanya menambah kolom yang belum ada.

---

## 6. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| Container restart loop | Lihat `docker compose logs app`. Commonly: `CORETAX_DATA_DIR` tidak writable. |
| `database is locked` | WAL aktif; kalau masih muncul, kurangi `deploy.resources.limits` atau cek disk penuh. |
| Login selalu "Terlalu banyak percobaan" | NPWP terkunci 15 menit. `docker compose exec app python -c "import models as M; c=M.conn(); c.execute('DELETE FROM percobaan_login'); c.commit()"`. |
| Semua user logout setelah restart | Normal kalau `session` table dihapus. Sebaliknya, kalau session **tidak** bertahan, cek volume ter-mount benar. |
| Halaman kosong / CSS hilang | Volume `static/` tidak ikut. Cek `docker compose exec app ls -la /app/static`. |
| Cookie tidak dikirim di HTTPS | `CORETAX_COOKIE_SECURE=1` + aplikasi diakses via HTTP (mixed) — samakan. |
| 403 "Token CSRF tidak valid" | Session kadaluarsa. Muat ulang halaman login. |

---

## 7. Deployment ke PaaS (Railway / Render / Fly.io)

**Peringatan:** filesystem PaaS bersifat *ephemeral*. SQLite di dalam container **hilang tiap redeploy**.

Solusinya:
1. Pakai Postgres bawaan providers, **atau**
2. Mount persistent volume (Fly.io saja yang mendukung), **atau**
3. Export/import DB manual tiap deploy (tidak praktis untuk kelas).

Kalau memilih PaaS, perlu migrasi `models.py` dari SQLite ke SQLAlchemy/Postgres — ini pekerjaan tersendiri, bukan sekadar ganti URL. Untuk skenario "copy-paste dan jalan", **VPS + Docker Compose tetap yang paling sederhana**.
