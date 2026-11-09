#!/bin/sh
# Entrypoint Simulator Coretax DJP.
#
# Tanggung jawab:
#  1. Pastikan volume data ada & writable
#  2. Inisialisasi skema DB + user demo (idempoten)
#  3. Bersihkan session kadaluarsa
#  4. Jalankan aplikasi
set -eu

DATA_DIR="${CORETAX_DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"

if [ ! -w "$DATA_DIR" ]; then
  echo "FATAL: $DATA_DIR tidak writable oleh user container ($(id -u):$(id -g))" >&2
  exit 1
fi

echo "[entrypoint] inisialisasi database di $DATA_DIR ..."
python - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
import models as M
import security as S

M.init_db()
c = M.conn()
n = S.purge_expired(c)
users = c.execute("SELECT COUNT(*) n FROM wp").fetchone()["n"]
print(f"[entrypoint] schema siap | user: {users} | session kadaluarsa dibersihkan: {n}")
c.close()
PY

# Seed data demo hanya kalau DB masih kosong (opsional, dimatikan di produksi)
if [ "${CORETAX_SEED_DEMO:-0}" = "1" ]; then
  echo "[entrypoint] mengisi data demo ..."
  python seed.py || echo "[entrypoint] seed demo gagal (diabaikan)"
fi

echo "[entrypoint] menjalankan: $*"
exec "$@"
