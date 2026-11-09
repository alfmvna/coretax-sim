"""Reset database simulator ke kondisi demo bersih.

PERINGATAN: menghapus seluruh data di data/coretax.db.
Jangan jalankan di server yang sudah dipakai tim.

    python3 reset_db.py            # reset + seed
    python3 reset_db.py --keep     # reset schema + user, tanpa seed demo
"""
import os
import sys

import models as M

DB = M.DB


def reset():
    for suffix in ("", "-wal", "-shm"):
        p = DB + suffix
        if os.path.exists(p):
            os.remove(p)
            print(f"hapus {p}")
    M.init_db()
    print("schema + user demo dibuat")


if __name__ == "__main__":
    if "--yes" not in sys.argv and "-y" not in sys.argv:
        print(f"AKAN MENGHAPUS {DB}")
        print("Jalankan ulang dengan --yes bila yakin.")
        sys.exit(1)
    reset()
    if "--keep" not in sys.argv:
        import seed  # noqa: F401  (side effect: mengisi data demo)
        print("seed demo selesai")
