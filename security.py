"""Modul keamanan untuk Simulator Coretax.

Menyediakan:
  - Hash password PBKDF2-HMAC-SHA256 (stdlib, tanpa dependency native)
  - Session persisten di SQLite (bertahan restart & multi-worker)
  - Rate limit + lockout akun anti brute-force
  - Token CSRF per-session
  - Security headers

Prinsip: tidak menambah dependency. Semua pakai stdlib + SQLite yang sudah ada.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time

# ----------------------------------------------------------------- konfigurasi
# Di-override lewat environment variable (lihat .env.example).
MODE = os.environ.get("CORETAX_MODE", "demo").lower()  # demo | strict
PBKDF2_ITER = int(os.environ.get("CORETAX_PBKDF2_ITER", "200000"))
SESSION_TTL = int(os.environ.get("CORETAX_SESSION_TTL", str(60 * 60 * 12)))
MAX_ATTEMPT = int(os.environ.get("CORETAX_MAX_ATTEMPT", "5"))
LOCKOUT_SEC = int(os.environ.get("CORETAX_LOCKOUT_SEC", "900"))
IP_ATTEMPT_MAX = int(os.environ.get("CORETAX_IP_ATTEMPT_MAX", "20"))
IP_WINDOW = int(os.environ.get("CORETAX_IP_WINDOW", "300"))
CSRF_TTL = int(os.environ.get("CORETAX_CSRF_TTL", str(60 * 60 * 8)))
COOKIE_SECURE = os.environ.get("CORETAX_COOKIE_SECURE", "0") == "1"


# --------------------------------------------------------------- password hash
def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Kembalikan (hex_hash, hex_salt). PBKDF2-HMAC-SHA256, pure stdlib.

    pbkdf2_hmac dipilih (bukan passlib/bcrypt) supaya tidak ada native binary
    yang harus di-compile saat build Docker di server lain.
    """
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
    return dk.hex(), salt.hex()


# Hash "palsu" dengan biaya sama untuk user yang tidak ada, supaya response time
# login seragam (user enumeration lewat timing).
_DUMMY_HASH, _DUMMY_SALT = hash_password("dummy-password-for-timing-equalisation")


def verify_dummy(password: str) -> None:
    """Jalankan PBKDF2 secepat biaya asli, lalu buang hasilnya.

    Dipanggil saat NPWP tidak terdaftar supaya waktu respons tidak membocarkan
    apakah sebuah NIK terdaftar.
    """
    hashlib.pbkdf2_hmac("sha256", password.encode(),
                        bytes.fromhex(_DUMMY_SALT), PBKDF2_ITER)


def verify_password(password: str, hex_hash: str, hex_salt: str) -> bool:
    """Constant-time verify. Selalu salty-hash lalu bandingkan dengan hmac.compare_digest."""
    try:
        salt = bytes.fromhex(hex_salt)
        expected = bytes.fromhex(hex_hash)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
    return hmac.compare_digest(dk, expected)


# ------------------------------------------------------------------- session
SESSION_COOKIE = "ctx"


def new_session(db: sqlite3.Connection, npwp: str, ip: str = "") -> str:
    """Buat token session baru, simpan ke DB. Return token."""
    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO session (token,npwp,ip,dibuat,kadaluarsa,csrf) VALUES (?,?,?,?,?,?)",
        (token, npwp, ip, now_ts(), now_ts() + SESSION_TTL, secrets.token_urlsafe(24)),
    )
    db.commit()
    return token


def now_ts() -> float:
    return time.time()


def get_session(db: sqlite3.Connection, token: str):
    """Return row session aktif (belum kadaluarsa) atau None."""
    if not token:
        return None
    row = db.execute("SELECT * FROM session WHERE token=?", (token,)).fetchone()
    if row is None:
        return None
    if row["kadaluarsa"] < now_ts():
        db.execute("DELETE FROM session WHERE token=?", (token,))
        db.commit()
        return None
    return row


def destroy_session(db: sqlite3.Connection, token: str) -> None:
    db.execute("DELETE FROM session WHERE token=?", (token,))
    db.commit()


def purge_expired(db: sqlite3.Connection) -> int:
    cur = db.execute("DELETE FROM session WHERE kadaluarsa < ?", (now_ts(),))
    db.commit()
    return cur.rowcount


def session_csrf(db: sqlite3.Connection, token: str) -> str:
    """Ambil token CSRF session; buat baru kalau belum ada / kadaluarsa."""
    row = get_session(db, token)
    if row is None:
        return ""
    csrf = row["csrf"] or ""
    if not csrf or (row["dibuat"] + CSRF_TTL) < now_ts():
        csrf = secrets.token_urlsafe(24)
        db.execute("UPDATE session SET csrf=? WHERE token=?", (csrf, token))
        db.commit()
    return csrf


def check_csrf(db: sqlite3.Connection, token: str, submitted: str) -> bool:
    """Bandingkan token CSRF submit dengan session (constant-time)."""
    if not token or not submitted:
        return False
    row = get_session(db, token)
    if row is None:
        return False
    csrf = row["csrf"] or ""
    if not csrf:
        return False
    return hmac.compare_digest(csrf, submitted)


# -------------------------------------------------------- rate limit / lockout
def login_blocked(db: sqlite3.Connection, npwp: str, ip: str) -> tuple[bool, str]:
    """Cek apakah login dicoba dari NPWP/ip ini sedang diblokir.

    Return (blocked, pesan).
    """
    now = now_ts()
    row = db.execute(
        "SELECT gagal, terblokir_sampai FROM percobaan_login WHERE npwp=?",
        (npwp,),
    ).fetchone()
    if row and row["terblokir_sampai"] and row["terblokir_sampai"] > now:
        sisa = int(row["terblokir_sampai"] - now)
        return True, f"Terlalu banyak percobaan. Coba lagi dalam {sisa // 60 + 1} menit."

    # batas per-IP (mencegah satu IP menyapu banyak NPWP)
    ip_n = db.execute(
        "SELECT COUNT(*) n FROM percobaan_login WHERE ip=? AND waktu > ?",
        (ip, now - IP_WINDOW),
    ).fetchone()["n"]
    if ip_n >= IP_ATTEMPT_MAX:
        return True, "Terlalu banyak percobaan dari alamat ini. Coba beberapa menit lagi."
    return False, ""


def register_failed(db: sqlite3.Connection, npwp: str, ip: str) -> int:
    """Catat percobaan gagal; kembalikan jumlah kegagalan berturut-turut."""
    now = now_ts()
    db.execute(
        "INSERT INTO percobaan_login (npwp,ip,waktu,gagal,terblokir_sampai) VALUES (?,?,?,1,0)",
        (npwp, ip, now),
    )
    row = db.execute(
        "SELECT COUNT(*) n FROM percobaan_login WHERE npwp=? AND waktu > ? AND terblokir_sampai=0",
        (npwp, now - LOCKOUT_SEC),
    ).fetchone()
    gagal = row["n"]
    if gagal >= MAX_ATTEMPT:
        db.execute(
            "UPDATE percobaan_login SET terblokir_sampai=? WHERE npwp=? AND terblokir_sampai=0",
            (now + LOCKOUT_SEC, npwp),
        )
        db.execute("DELETE FROM percobaan_login WHERE npwp=? AND terblokir_sampai < ?",
                   (npwp, now))
    db.commit()
    return gagal


def register_success(db: sqlite3.Connection, npwp: str, ip: str = "") -> None:
    # reset juga counter per-IP supaya login sah mengisi ulang jatah
    db.execute("DELETE FROM percobaan_login WHERE npwp=? OR ip=?", (npwp, ip))
    db.commit()


# ------------------------------------------------------------ security headers
def security_headers(content_type: str = "text/html; charset=utf-8") -> dict:
    """Header keamanan standar. CSP ketat — aplikasi tidak memakai inline script/style."""
    h = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "object-src 'none'"
        ),
        # HSTS hanya bermakna di HTTPS; biarkan reverse proxy yang pasang.
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    }
    if content_type.startswith("text/html"):
        h["Cache-Control"] = "no-store"
    return h