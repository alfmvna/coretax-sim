"""Simulator Coretax DJP — server FastAPI.

Meniru alur portal Coretax: login WP -> topnav modul -> sidebar -> halaman.
Modul yang diimplementasikan penuh: SPT (Surat Pemberitahuan).
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import date, datetime, timedelta

from fastapi import FastAPI, Form, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import models as M
import security as S
import tax as T

ROOT = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")

M.init_db()


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Pasang header keamanan ke semua respons (termasuk error)."""
    resp = await call_next(request)
    for k, v in S.security_headers().items():
        resp.headers.setdefault(k, v)
    return resp

# Session disimpan di SQLite (bukan dict in-memory) supaya:
#  - tidak hilang saat container restart / redeploy
#  - konsisten antar worker (kritikal kalau multi-worker uvicorn/gunicorn)
def _session_row(request: Request):
    tok = request.cookies.get(S.SESSION_COOKIE)
    if not tok:
        return None
    c = M.conn()
    try:
        return S.get_session(c, tok)
    finally:
        c.close()


def current_npwp(request: Request) -> str | None:
    row = _session_row(request)
    return row["npwp"] if row else None


def current_wp(request: Request):
    """Row WP milik user yang sedang login."""
    npwp = current_npwp(request)
    if not npwp:
        return None
    c = M.conn()
    try:
        return c.execute("SELECT * FROM wp WHERE npwp=? AND aktif=1", (npwp,)).fetchone()
    finally:
        c.close()


def login_required(request: Request):
    return current_wp(request)


def actor(request: Request) -> str:
    """NPWP user aktif; fallback ke string kosong (tidak akan crash log)."""
    return current_npwp(request) or "anon"


def client_ip(request: Request) -> str:
    """IP klien. Hanya percaya X-Forwarded-For bila di-set reverse proxy (TRUST_PROXY)."""
    if os.environ.get("CORETAX_TRUST_PROXY", "0") == "1":
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def csrf_field(request: Request) -> str:
    """Hidden input token CSRF untuk disisipkan ke dalam <form>."""
    tok = csrf_token(request)
    if not tok:
        return ""
    return f'<input type="hidden" name="csrf_token" value="{esc(tok)}">'


def csrf_token(request: Request) -> str:
    """Token CSRF untuk session aktif (string kosong bila belum login)."""
    tok = request.cookies.get(S.SESSION_COOKIE)
    if not tok:
        return ""
    c = M.conn()
    try:
        return S.session_csrf(c, tok)
    finally:
        c.close()


def check_csrf(request: Request, form) -> bool:
    """Validasi token CSRF dari form. Wajib pada semua POST bertamu state."""
    tok = request.cookies.get(S.SESSION_COOKIE)
    submitted = form.get("csrf_token") or ""
    c = M.conn()
    try:
        return S.check_csrf(c, tok, submitted)
    finally:
        c.close()


def check_csrf_get(request: Request) -> bool:
    """Validasi token CSRF dari query string.

    Dipakai untuk link GET yang mengubah state (hapus lampiran, bayar billing).
    Token CSRF bersifat per-session dan hanya berguna bagi penyerang yang sudah
    punya cookie session, jadi menaruhnya di query string tidak menambah risiko.
    """
    tok = request.cookies.get(S.SESSION_COOKIE)
    submitted = request.query_params.get("csrf_token") or ""
    c = M.conn()
    try:
        return S.check_csrf(c, tok, submitted)
    finally:
        c.close()


def get_wp(request: Request = None) -> dict:
    """Data WP. Kalau request diberikan -> WP milik session itu (multi-user).
    Tanpa request -> fallback ke WP default (dipakai seed & konteks non-request)."""
    if request is not None:
        row = current_wp(request)
        if row:
            return dict(row)
    c = M.conn()
    r = c.execute("SELECT * FROM wp ORDER BY id LIMIT 1").fetchone()
    c.close()
    return dict(r) if r else M.DEFAULT_WP


def fmt(v):
    """Format angka gaya Indonesia: 1.234.567,00"""
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def esc(s) -> str:
    import html
    return html.escape("" if s is None else str(s))


def spt_row(spt_id: int, request: Request | None = None):
    """Ambil SPT. Kalau request diberikan, WAJIB milik user yang login (anti-IDOR).

    Operator (role OP) boleh melihat semua SPT; WP hanya SPT-nya sendiri.
    """
    c = M.conn()
    try:
        if request is not None:
            npwp = current_npwp(request)
            if not npwp:
                return None
            row = c.execute("SELECT * FROM wp WHERE npwp=?", (npwp,)).fetchone()
            if row is not None and row["role"] == "OP":
                return c.execute("SELECT * FROM spt WHERE id=?", (spt_id,)).fetchone()
            return c.execute("SELECT * FROM spt WHERE id=? AND npwp=?",
                             (spt_id, npwp)).fetchone()
        return c.execute("SELECT * FROM spt WHERE id=?", (spt_id,)).fetchone()
    finally:
        c.close()


# ================================================================== LOGIN
@app.get("/favicon.ico")
def favicon():
    return RedirectResponse("/static/favicon.svg", status_code=301)


@app.get("/healthz")
def healthz():
    """Healthcheck untuk Docker/Kubernetes. Tidak butuh auth."""
    try:
        c = M.conn()
        c.execute("SELECT 1").fetchone()
        c.close()
        return {"status": "ok"}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


@app.get("/", response_class=HTMLResponse)
def beranda(request: Request):
    if current_npwp(request):
        return RedirectResponse("/home")
    return login_page()


LOGIN_HTML = """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Masuk — Coretax DJP (Simulator)</title>
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/app.css"></head>
<body class="login-page">
<div class="login-wrap">
  <div class="login-card">
    <div class="brand-lg">
      <div class="logo-box">CORETAX</div>
      <div class="brand-sub">Sistem Inti Administrasi Perpajakan<br><span>SIMULATOR PEMBELAJARAN</span></div>
    </div>
    <h1>Selamat Datang!</h1>
    <p class="muted">Masuk untuk mengakses Layanan Coretax DJP (simulasi)</p>
    <form method="post" action="/login" class="stack">
      <label>NIK/NPWP/NITKU
        <input name="id" placeholder="2171121009959003" required autocomplete="username"></label>
      <label>Kata Sandi
        <input name="pwd" type="password" placeholder="Masukkan kata sandi Anda" required
               autocomplete="current-password"></label>
      <label class="check"><input type="checkbox" name="robot" checked> Saya bukan robot</label>
      <button class="btn-primary" type="submit">Masuk</button>
    </form>
    <div id="login-msg" class="login-msg" role="alert" aria-live="polite">{LOGIN_ERROR}</div>
    <div class="login-hint">
      <b>Akun demo:</b> NIK/NPWP <code>2171121009959003</code>, sandi <code>demo123</code>.<br>
      <small>Simulator untuk pembelajaran. Tidak terhubung ke DJP, tidak mengirim data apa pun ke server pajak.</small>
    </div>
  </div>
</div></body></html>"""


def login_page(error: str = "") -> HTMLResponse:
    """Halaman login dengan pesan error (tanpa membocorkan detail validasi)."""
    html = LOGIN_HTML.replace("{LOGIN_ERROR}", esc(error) if error else "")
    return HTMLResponse(html, headers=S.security_headers())


@app.post("/login")
async def do_login(request: Request, id: str = Form(...), pwd: str = Form(...)):
    """Login wajib pajak.

    Proteksi brute-force:
      - lockout per-NPWP setelah N gagal (default 5), durasi 15 menit
      - batas percobaan per-IP untuk mencegah satu IP menyapu banyak NPWP
      - verifikasi password PBKDF2 + salt, constant-time compare
    """
    npwp = id.strip()
    ip = client_ip(request)
    c = M.conn()
    try:
        blocked, pesan = S.login_blocked(c, npwp, ip)
        if blocked:
            M.log(npwp, "login_blocked", f"ip={ip}", db=c)
            c.commit()
            return login_page(pesan)

        row = c.execute("SELECT * FROM wp WHERE npwp=?", (npwp,)).fetchone()
        # Pesan error seragam: jangan bocorkan apakah NPWP terdaftar.
        pesan_gagal = "NIK/NPWP atau kata sandi salah."
        if row is None or not row["aktif"]:
            # Hash dummy: response time seragam dengan password salah ->
            # tidak bisa dipakai untuk memetakan NIK yang terdaftar.
            S.verify_dummy(pwd)
            S.register_failed(c, npwp, ip)
            M.log(npwp, "login_gagal", "npwp_tidak_ada", db=c)
            c.commit()
            return login_page(pesan_gagal)

        if not S.verify_password(pwd, row["password_hash"] or "", row["salt"] or ""):
            # Mode demo: password tetap wajib cocok bila hash tersedia.
            S.register_failed(c, npwp, ip)
            M.log(npwp, "login_gagal", "password_salah", db=c)
            c.commit()
            return login_page(pesan_gagal)

        S.register_success(c, npwp)
        tok = S.new_session(c, npwp, ip)
        M.log(npwp, "login", f"role={row['role']}", db=c)
        c.commit()
    finally:
        c.close()

    resp = RedirectResponse("/home", status_code=303)
    resp.set_cookie(
        S.SESSION_COOKIE, tok,
        httponly=True,
        samesite="lax",
        secure=S.COOKIE_SECURE,
        max_age=S.SESSION_TTL,
        path="/",
    )
    return resp


@app.get("/logout")
def logout(request: Request):
    tok = request.cookies.get(S.SESSION_COOKIE)
    if tok:
        c = M.conn()
        try:
            S.destroy_session(c, tok)
        finally:
            c.close()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(S.SESSION_COOKIE, path="/")
    return resp


# ================================================================== SHELL
TOPNAV = ["Portal Saya", "e-Faktur", "eBUPOT", "SPT", "Pembayaran", "Buku Besar",
          "Layanan WP", "Manajemen Akses"]

SIDEBAR = {
    "SPT": [("Surat Pemberitahuan (SPT)", "/spt"),
            ("Coretax Form", "/spt/form"),
            ("Pencatatan", "/spt/pencatatan"),
            ("Dasbor Kompensasi", "/spt/kompensasi"),
            ("Pengungkapan Ketidakbenaran SPT", "/spt/pengungkapan")],
}

DEFAULT_SIDEBAR = {
    "Portal Saya": [("Portal Saya", "/home"), ("Perubahan Data", "/wp"),
                    ("Perubahan Status", "/wp"), ("eBupot", "/ebupot"),
                    ("Layanan Wajib Pajak", "/layanan"), ("Layanan Administrasi", "/layanan"),
                    ("Layanan Permintaan Informasi Perpajakan", "/layanan"),
                    ("Layanan Pengaduan, Saran, dan Apresiasi", "/layanan"),
                    ("Layanan Edukasi Perpajakan", "/layanan")],
    "e-Faktur": [("Faktur Pajak", "/faktur"), ("Pajak Masukan", "/faktur/masuk"),
                 ("Daftar Retur Pajak Masukan", "/faktur/masuk"),
                 ("Dokumen Lain", "/faktur/dokumen"), ("Pengganti", "/faktur"),
                 ("Pembatalan", "/faktur"), ("Retur", "/faktur/masuk")],
    "eBUPOT": [("Bukti Potong", "/bupot"), ("Bukti Potong A1", "/bupot"),
               ("Bukti Potong A2", "/bupot"), ("Dokumen Lain", "/bupot"),
               ("Pelaporan", "/spt")],
    "Pembayaran": [("Kode Billing", "/billing"), ("Riwayat Pembayaran", "/billing"),
                    ("Formulir Restitusi Pajak", "/billing"), ("Pemindahbukuan", "/billing")],
    "Buku Besar": [("Buku Besar Saya", "/buku-besar")],
    "Layanan WP": [("Permohonan Informasi Perpajakan", "/layanan"),
                   ("Permohonan Pengembalian Pajak", "/layanan"),
                   ("Permohonan Pengunduran-tax", "/layanan"),
                   ("Permohonanunication", "/layanan"),
                   ("Materi Edukasi Umum", "/layanan"), ("Permohonan Edukasi", "/layanan"),
                   ("Jadwal Kegiatan Edukasi", "/layanan")],
    "Manajemen Akses": [("Manajemen Akses", "/akses")],
}

# Nav atas harus menuju path modul yang absolut — URL relatif "?modul=X" membuat
# link tidak berpindah modul saat diklik dari halaman lain (mis. /faktur).
MODUL_URL = {
    "Portal Saya": "/home", "e-Faktur": "/faktur", "eBUPOT": "/bupot", "SPT": "/spt",
    "Pembayaran": "/billing", "Buku Besar": "/buku-besar", "Layanan WP": "/layanan",
    "Manajemen Akses": "/akses",
}



def redirect_modul(request: Request) -> RedirectResponse | None:
    """Jika URL membawa ?modul=X (mis. link lama dari halaman lain), arahkan ke path modul."""
    m = request.query_params.get("modul")
    if m and m in MODUL_URL:
        return RedirectResponse(MODUL_URL[m], status_code=303)
    return None


def shell(request: Request, modul: str, aktif: str, konten: str, sub: str = "") -> HTMLResponse:
    wp = get_wp(request)
    nav = "".join(
        f'<li class="nav-item{" active" if m == modul else ""}">'
        f'<a href="{MODUL_URL.get(m, "/home")}" class="nav-link{" active" if m == modul else ""}">{m}</a></li>'
        for m in TOPNAV)
    side = SIDEBAR.get(modul, DEFAULT_SIDEBAR.get(modul, []))
    side_html = "".join(
        f'<li><a href="{h}" class="side-link{" active" if aktif == t else ""}">{esc(t)}</a></li>'
        for t, h in side)
    crumb = f'<div class="crumb">Beranda <span>›</span> {esc(sub or modul)}</div>' if (sub or modul) else ""
    html = f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(modul)} — Coretax DJP (Simulator)</title>
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/app.css"></head>
<body data-ptkp="{esc(wp.get("ptkp_kode") or "K/0")}">
<header class="topbar">
  <div class="topbar-in">
    <a class="logo" href="/home">CORETAX<span>sim</span></a>
    <input class="search" placeholder="Cari layanan..." disabled>
    <div class="spacer"></div>
    <span class="chip">Simulasi</span>
    <span class="chip">{esc(wp["kpp"])}</span>
    <a class="user" href="/logout">{esc(wp["npwp"])}<br><b>{esc(wp["nama"])}</b></a>
  </div>
  <nav class="mainnav"><ul>{nav}</ul></nav>
</header>
<div class="shell">
  <aside class="sidebar">
    <div class="side-title">{esc(modul)}</div>
    <ul>{side_html}</ul>
  </aside>
  <main class="main">
    {crumb}
    <div class="who"><span>{esc(wp["npwp"])}</span><span>{esc(wp["nama"])}</span></div>
    {konten}
  </main>
</div>
<footer class="foot">
  <div>Hubungi Kami · Kring Pajak: (021) 1500200</div>
  <div>Simulator Coretax untuk pembelajaran mahasiswa — bukan aplikasi DJP resmi.</div>
</footer>
<script src="/static/live.js"></script>
</body></html>"""
    return HTMLResponse(html)


# ================================================================== HOME
@app.get("/home", response_class=HTMLResponse)
def home(request: Request, modul: str = Query("Portal Saya")):
    if not current_npwp(request):
        return RedirectResponse("/")
    # "?modul=X" dari URL lama/ bookmark -> arahkan ke path modul yang benar
    if modul != "Portal Saya" and modul in MODUL_URL:
        return RedirectResponse(MODUL_URL[modul], status_code=303)
    if modul == "SPT":
        return RedirectResponse("/spt")
    if modul == "e-Faktur":
        return RedirectResponse("/faktur")
    if modul == "eBUPOT":
        return RedirectResponse("/bupot")
    if modul == "Pembayaran":
        return RedirectResponse("/billing")
    if modul == "Buku Besar":
        return RedirectResponse("/buku-besar")
    if modul == "Layanan WP":
        return RedirectResponse("/layanan")
    if modul == "Manajemen Akses":
        return RedirectResponse("/akses")
    wp = get_wp(request)
    c = M.conn()
    n_spt = c.execute("SELECT COUNT(*) n FROM spt").fetchone()["n"]
    n_faktur = c.execute("SELECT COUNT(*) n FROM e_faktur").fetchone()["n"]
    n_bupot = c.execute("SELECT COUNT(*) n FROM bupot").fetchone()["n"]
    saldo = c.execute("SELECT saldo FROM deposit WHERE npwp=?", (wp["npwp"],)).fetchone()["saldo"]
    c.close()
    konten = f"""
    <div class="hero">
      <h1>Selamat datang, <b>{esc(wp['nama'])}</b>.</h1>
      <p class="muted">Coretax DJP siap melayani kebutuhan perpajakan Anda (simulasi).</p>
    </div>
    <div class="grid4">
      <div class="stat"><div class="stat-n">{n_spt}</div><div class="stat-l">SPT dibuat</div>
        <a href="/spt">Kelola SPT</a></div>
      <div class="stat"><div class="stat-n">{n_faktur}</div><div class="stat-l">Faktur Pajak</div>
        <a href="/faktur">Buka e-Faktur</a></div>
      <div class="stat"><div class="stat-n">{n_bupot}</div><div class="stat-l">Bukti Potong</div>
        <a href="/bupot">Buka eBUPOT</a></div>
      <div class="stat"><div class="stat-n">Rp {fmt(saldo)}</div><div class="stat-l">Saldo Deposit</div>
        <a href="/billing">Kelola Pembayaran</a></div>
    </div>
    <div class="card">
      <h2>Modul yang tersedia pada simulator ini</h2>
      <ul class="modul-list">
        <li><b>SPT (Surat Pemberitahuan)</b> — lengkap: wizard pembuatan konsep, form per jenis SPT,
            lampiran, penghitungan, pembayaran, tanda tangan, dan pelaporan.</li>
        <li><b>e-Faktur</b> — daftar faktur pajak keluaran dan masukan (data pendukung SPT PPN).</li>
        <li><b>eBUPOT</b> — bukti potong (data pendukung SPT PPh 21/26 dan Unifikasi).</li>
        <li><b>Pembayaran</b> — kode billing, riwayat setoran, saldo deposit.</li>
        <li><b>Buku Besar</b> — rekapitulasi omzet dan pajak.</li>
      </ul>
      <p class="muted small">Modul lain (Portal Saya, Layanan WP, Manajemen Akses) masih kerangka
      halaman — cukup untuk navigasi tim, isi detailnya menyusul.</p>
    </div>
    """
    return shell(request, "Portal Saya", "Portal Saya", konten)


# ================================================================== SPT
STATUS_FILTER = ["Semua", "Konsep SPT", "SPT Menunggu Pembayaran", "SPT Dilaporkan",
                  "SPT Ditolak", "SPT Dibatalkan"]


@app.get("/spt", response_class=HTMLResponse)
def spt_dashboard(request: Request, status: str = Query("Konsep SPT"),
                  jenis: str = Query(""), Searching: str = Query("")):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    c = M.conn()
    sql = "SELECT * FROM spt WHERE 1=1"
    args = []
    if status and status != "Semua":
        sql += " AND status_tabel=?"
        args.append(status)
    if jenis:
        sql += " AND jenis_pajak=?"
        args.append(jenis)
    sql += " ORDER BY id DESC"
    rows = c.execute(sql, args).fetchall()
    c.close()

    def opt(label, val):
        return f'<option value="{esc(val)}">{esc(label)}</option>'

    baris = ""
    for r in rows:
        kb = r["kurang_bayar"]
        badge = ('<span class="badge b-kurang">Kurang Bayar</span>' if kb > 0 else
                 ('<span class="badge b-lebih">Lebih Bayar</span>' if r["lebih_bayar"] > 0 else
                  '<span class="badge b-nihil">Nihil</span>'))
        baris += f"""<tr>
        <td>{esc(r["jenis_pajak"])}</td>
        <td>{esc(r["jenis_spt"])}</td>
        <td>{esc(r["masa_pajak"])}</td>
        <td>{esc(r["tahun_pajak"])}</td>
        <td>{esc(r["status_spt"])}</td>
        <td class="num">{fmt(r["kurang_bayar"] or 0)}</td>
        <td>{badge}</td>
        <td>{esc(r["status_tabel"])}</td>
        <td>{esc(r["tgl_dibuat"] or "")}</td>
        <td><a class="btn-mini" href="/spt/{r['id']}">Lihat</a>
            <a class="btn-mini ghost" href="/spt/{r['id']}/edit">Ubah</a></td></tr>"""
    if not baris:
        baris = '<tr><td colspan="10" class="empty">Tidak ada data yang ditemukan.</td></tr>'

    filter_status = "".join(opt(s, s) for s in STATUS_FILTER)
    filter_jenis = '<option value="">Semua Jenis Pajak</option>' + "".join(
        opt(j["kode"], j["kode"]) for j in M.JENIS_PAJAK)
    isi = f"""
    <div class="page-head">
      <div><h1>Surat Pemberitahuan (SPT)</h1>
      <p class="muted">Sampaikan SPT Anda</p></div>
      <a class="btn-primary" href="/spt/buat">Buat Konsep SPT</a>
    </div>
    <div class="card">
      <form class="filters" method="get">
        <label>Jenis Pajak <select name="jenis">{filter_jenis}</select></label>
        <label>Status SPT <select name="status">{filter_status}</select></label>
        <button class="btn" type="submit">Terapkan</button>
        <a class="btn ghost" href="/spt?status=Semua">Reset</a>
      </form>
      <table class="tbl">
        <thead><tr>
          <th>Jenis Pajak</th><th>Jenis Surat Pemberitahuan Pajak</th><th>Masa Pajak</th>
          <th>Tahun</th><th>Status SPT</th><th>Kurang Bayar</th><th>Posisi</th>
          <th>Status</th><th>Tanggal Dibuat</th><th>Aksi</th>
        </tr></thead>
        <tbody>{baris}</tbody>
      </table>
    </div>
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Surat Pemberitahuan (SPT)")


# ---------------------------------------------------- wizard buat konsep SPT
@app.get("/spt/buat", response_class=HTMLResponse)
def spt_buat(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    kartu = "".join(
        f'<a class="pick-card" href="/spt/buat?jenis={esc(j["kode"])}">'
        f'<b>{esc(j["kode"])}</b><span>{esc(j["spt"])}</span>'
        + (f'<span class="pick-note">{esc(j["catatan"])}</span>' if j.get("catatan") else "")
        + '</a>'
        for j in M.JENIS_PAJAK)
    isi = f"""
    <div class="page-head"><div><h1>Buat Konsep SPT</h1>
      <p class="muted">Langkah 1 — Pilih Jenis Pajak</p></div></div>
    <div class="steps">
      <div class="step active"><b>1</b> Pilih Jenis Pajak</div>
      <div class="step"><b>2</b> Pilih periode pelaporan SPT</div>
      <div class="step"><b>3</b> Pilih Jenis SPT</div>
    </div>
    <div class="card">
      <h2>Langkah 1. Pilih jenis SPT yang akan dilaporkan</h2>
      <div class="pick-grid">{kartu}</div>
    </div>
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Create Returnsheets")


@app.get("/spt/buat/periode", response_class=HTMLResponse)
def spt_buat_periode(request: Request, jenis: str = Query(...)):
    if not current_npwp(request):
        return RedirectResponse("/")
    j = next((x for x in M.JENIS_PAJAK if x["kode"] == jenis), None)
    if not j:
        return RedirectResponse("/spt/buat")
    tahun = ["2025", "2024", "2023"]
    if jenis in ("PPh Orang Pribadi", "PPh Final Pengungkapan Harta Bersih"):
        periode = "".join(f'<option value="Januari - Desember {t}">Januari - Desember {t}</option>' for t in tahun)
        jenis_periode = '<option>SPT Tahunan</option>'
    else:
        bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
                 "September", "Oktober", "November", "Desember"]
        periode = "".join(f'<option value="{b} {t}">{b} {t}</option>' for b in bulan for t in ["2025"])
        jenis_periode = '<option>SPT Masa</option>'
    isi = f"""
    <div class="page-head"><div><h1>Buat Konsep SPT</h1>
      <p class="muted">Langkah 2 — Pilih periode pelaporan SPT</p></div></div>
    <div class="steps">
      <div class="step done"><b>1</b> Pilih Jenis Pajak</div>
      <div class="step active"><b>2</b> Pilih periode pelaporan SPT</div>
      <div class="step"><b>3</b> Pilih Jenis SPT</div>
    </div>
    <div class="card">
      <h2>Langkah 2. Pilih periode pelaporan SPT</h2>
      <dl class="kv">
        <dt>Jenis Surat Pemberitahuan Pajak</dt><dd>{esc(j["spt"])}</dd>
        <dt>Jenis Periode SPT</dt><dd>{jenis_periode}</dd>
      </dl>
      <form method="get" action="/spt/buat/jenis" class="stack">
        <input type="hidden" name="jenis" value="{esc(jenis)}">
        <label>Periode dan Tahun Pajak <select name="periode" required>{periode}</select></label>
        <label>Jenis Periode SPT <select name="jenis_periode">{jenis_periode}</select></label>
        <div class="row-btns">
          <a class="btn ghost" href="/spt/buat">Kembali</a>
          <button class="btn-primary" type="submit">Lanjut</button>
        </div>
      </form>
    </div>
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Create Returnsheets")


@app.get("/spt/buat/jenis", response_class=HTMLResponse)
def spt_buat_jenis(request: Request, jenis: str = Query(...), periode: str = Query(...),
                   jenis_periode: str = Query(...)):
    if not current_npwp(request):
        return RedirectResponse("/")
    j = next((x for x in M.JENIS_PAJAK if x["kode"] == jenis), None)
    if not j:
        return RedirectResponse("/spt/buat")
    model_ops = {
        "PPh Orang Pribadi": ["Normal", "Pembetulan"],
        "PPh Final Pengungkapan Harta Bersih": ["Normal"],
        "PPh Pasal 21/26": ["Normal", "Pembetulan"],
        "PPh Unifikasi": ["Normal", "Pembetulan"],
        "PPN": ["Normal", "Pembetulan"],
    }.get(jenis, ["Normal"])
    isi = f"""
    <div class="page-head"><div><h1>Buat Konsep SPT</h1>
      <p class="muted">Langkah 3 — Pilih Jenis SPT</p></div></div>
    <div class="steps">
      <div class="step done"><b>1</b> Pilih Jenis Pajak</div>
      <div class="step done"><b>2</b> Pilih periode pelaporan SPT</div>
      <div class="step active"><b>3</b> Pilih Jenis SPT</div>
    </div>
    <div class="card">
      <h2>Langkah 3. Pilih jenis SPT</h2>
      <form method="post" action="/spt/buat/simpan" class="stack">
        {csrf_field(request)}
        <input type="hidden" name="jenis" value="{esc(jenis)}">
        <input type="hidden" name="periode" value="{esc(periode)}">
        <input type="hidden" name="jenis_periode" value="{esc(jenis_periode)}">
        <dl class="kv">
          <dt>Jenis Surat Pemberitahuan Pajak</dt><dd>{esc(j["spt"])}</dd>
          <dt>Jenis Periode SPT</dt><dd>{esc(jenis_periode)}</dd>
          <dt>Periode dan Tahun Pajak</dt><dd>{esc(periode)}</dd>
        </dl>
        <label>Model SPT (Status SPT)
          <select name="model">{''.join(f'<option>{m}</option>' for m in model_ops)}</select></label>
        <div class="row-btns">
          <a class="btn ghost" href="/spt/buat/periode?jenis={esc(jenis)}">Kembali</a>
          <button class="btn-primary" type="submit">Simpan</button>
        </div>
      </form>
    </div>
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Create Returnsheets")


@app.post("/spt/buat/simpan")
async def spt_buat_simpan(request: Request, jenis: str = Form(...), periode: str = Form(...),
                          jenis_periode: str = Form(...), model: str = Form(...)):
    if not current_npwp(request):
        return RedirectResponse("/")
    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)

    npwp = current_npwp(request)
    j = next((x for x in M.JENIS_PAJAK if x["kode"] == jenis), None)
    tahun = periode.split()[-1]
    masa = periode if jenis_periode == "SPT Tahunan" else periode
    # jatuh tempo
    if jenis_periode == "SPT Tahunan":
        jtt = f"{int(tahun)+1}-04-30"
    else:
        bln = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
               "September", "Oktober", "November", "Desember"].index(periode.split()[0]) + 1
        y = int(tahun) + (1 if bln == 12 else 0)
        m = 1 if bln == 12 else bln + 1
        jtt = f"{y}-{m:02d}-10"

    c = M.conn()
    data = {}
    bagian, _ = M.form_for(jenis)
    for b in bagian:
        for f in b["field"]:
            data[f[0]] = ""
    # prepopulate header
    data.update({"tahun_pajak": tahun, "status_spt": model, "periode_akuntansi": masa,
                 "npwp": npwp, "nama": get_wp(request)["nama"], "telepon": get_wp(request)["telepon"],
                 "email": get_wp(request)["email"], "status_kewajiban": get_wp(request)["status"],
                 "npwp_pasangan": "", "masa_pajak": masa, "jenis_pajak": jenis,
                 "jenis_spt": j["spt"] if j else jenis, "model": model})
    cur = c.execute("""INSERT INTO spt (npwp,jenis_pajak,jenis_spt,masa_pajak,tahun_pajak,periode,
                        status_spt,status_tabel,kanal,tgl_jatuh_tempo,tgl_dibuat,data)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (npwp, jenis, j["spt"] if j else jenis, masa, tahun, masa, model,
                      "Konsep SPT", "Web", jtt, M.now(), json.dumps(data)))
    c.commit()
    c.close()
    M.log(npwp, "buat_konsep_spt", f"{jenis} | {masa} | {model}")
    return RedirectResponse(f"/spt/{cur.lastrowid}/edit", status_code=303)


# ------------------------------------------------------------- detail SPT

def bukti_potong_total(spt_id: int) -> float:
    """Total PPh yang dipotong pihak lain, dari lampiran L-1 bagian E (bukti potong)."""
    c = M.conn()
    total = 0.0
    for r in c.execute("SELECT data FROM lampiran WHERE spt_id=? AND kode LIKE 'L-1|E%'",
                       (spt_id,)):
        try:
            d = json.loads(r["data"] or "{}")
        except json.JSONDecodeError:
            continue
        total += T.num(d.get("withholding_tax"))
    c.close()
    return total


# --------- peta field bertipe "calc" -> key di dict hasil hitung (agar form menampilkan angkanya)
CALC_KEYS = {
    # SPT Tahunan PPh OP
    "q_4": "neto_setelah", "q_5": "ptkp", "q_6": "pkp", "q_7": "pph_terutang",
    "q_9": "pph_setelah", "kredit_pajak": "kredit_pajak", "q_11a": "kurang_bayar",
    "q_11c": "masih_bayar", "angsuran_pph25": "angsuran_pph25",
    # SPT Masa PPN
    "ppn_keluar": "ppn_keluar", "ppn_masuk": "ppn_masuk", "ppn_terutang": "ppn_terutang",
    "jumlah_kurang_bayar": "kurang_bayar",
}


def hitung_spt(spt, data: dict, request: Request | None = None) -> dict:
    """Hitung angka-angka SPT berdasarkan data form. Mengembalikan dict + pesan error."""
    jenis = spt["jenis_pajak"]
    spt_id = spt["id"]
    wp = get_wp(request)
    out = {}
    if jenis == "PPh Orang Pribadi":
        neto = T.num(data.get("q_2"))
        pengurang = T.num(data.get("pengurang_neto"))
        neto_setelah = max(0.0, neto - pengurang)
        ptkp = T.PTKP.get(wp["ptkp_kode"], 54_000_000)
        pkp = max(0.0, neto_setelah - ptkp)
        pph_terutang = T.hitung_pasal17(pkp)
        pengurang_pph = T.num(data.get("pengurang_pph"))
        pph_setelah = max(0.0, pph_terutang - pengurang_pph)
        # Kredit pajak = bukti potong (lampiran L-1 bagian E, auto-posting seperti
        # Coretax) + angsuran PPh 25 + STP. Field kredit_pajak di form bersifat readonly.
        kredit = (bukti_potong_total(spt_id)
                  + T.num(data.get("q_10b")) + T.num(data.get("q_10c"))
                  + T.num(data.get("kredit_luar_negeri")))
        kurang = pph_setelah - kredit
        pengangsuran = T.num(data.get("nilai_pengangsuran"))
        masih_bayar = max(0.0, kurang - pengangsuran)
        out.update({
            "neto": neto, "pengurang_neto": pengurang, "neto_setelah": neto_setelah,
            "ptkp": ptkp, "pkp": pkp, "pph_terutang": pph_terutang,
            "pengurang_pph": pengurang_pph, "pph_setelah": pph_setelah,
            "kredit_pajak": kredit, "kurang_bayar": kurang, "pengangsuran": pengangsuran,
            "masih_bayar": masih_bayar,
            "status": "Kurang Bayar" if masih_bayar > 0 else ("Lebih Bayar" if kurang < 0 else "Nihil"),
            "angsuran_pph25": T.angsuran_pph25(pph_setelah, 12),
        })
    elif jenis == "PPh Pasal 21/26":
        total = T.num(data.get("total_pajak"))
        out.update({"total_bruto": T.num(data.get("total_bruto")),
                    "total_dpp": T.num(data.get("total_dpp")),
                    "total_pajak": total,
                    "pajak_ditanggung": T.num(data.get("pajak_ditanggung")),
                    "kurang_bayar": total,
                    "status": "Kurang Bayar" if total > 0 else "Nihil"})
    elif jenis == "PPh Unifikasi":
        total = T.num(data.get("total_pajak"))
        out.update({"total_bruto": T.num(data.get("total_bruto")),
                    "total_dpp": T.num(data.get("total_dpp")),
                    "total_pajak": total, "kurang_bayar": total,
                    "status": "Kurang Bayar" if total > 0 else "Nihil"})
    elif jenis == "PPN":
        dpp_k = T.num(data.get("dpp_keluar"))
        dpp_m = T.num(data.get("dpp_masuk"))
        h = T.hitung_ppn(dpp_k, dpp_m, ppnbm=T.num(data.get("ppnbm")))
        h["kurang_bayar"] = h["ppn_terutang"]
        h["status"] = "Kurang Bayar" if h["ppn_terutang"] > 0 else "Nihil"
        out.update(h)
    else:
        out.update({"kurang_bayar": 0, "status": "Nihil"})
    return out


@app.get("/spt/{spt_id}", response_class=HTMLResponse)
def spt_detail(request: Request, spt_id: int):
    if not current_npwp(request):
        return RedirectResponse("/")
    s = spt_row(spt_id, request)
    if not s:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    data = json.loads(s["data"] or "{}")
    hit = hitung_spt(s, data, request)
    bagian, lampiran = M.form_for(s["jenis_pajak"])

    def f_html(f):
        kode, label, jenis_f, extra = f
        val = esc(data.get(kode, ""))
        if jenis_f == "readonly":
            return f'<div class="ro"><label>{esc(label)}</label><div class="rov">{esc(data.get(kode) or "-")}</div></div>'
        if jenis_f == "yn":
            y = 'checked' if data.get(kode) == "Ya" else ""
            n = 'checked' if data.get(kode) == "Tidak" else ""
            return (f'<div class="yn"><label>{esc(label)}</label>'
                    f'<label class="radio"><input type="radio" name="{kode}" value="Ya" {y}> Ya</label>'
                    f'<label class="radio"><input type="radio" name="{kode}" value="Tidak" {n}> Tidak</label></div>')
        if jenis_f == "select":
            opts = "".join(f'<option value="{esc(o)}"{" selected" if data.get(kode)==o else ""}>{esc(o)}</option>'
                           for o in (extra or []))
            return f'<label>{esc(label)}<select name="{kode}">{opts}</select></label>'
        if jenis_f == "number":
            return (f'<label>{esc(label)}<input type="text" inputmode="decimal" name="{kode}" '
                    f'value="{val}" placeholder="0,00"></label>')
        if jenis_f == "textarea":
            return f'<label>{esc(label)}<textarea name="{kode}" rows="2">{val}</textarea></label>'
        if jenis_f == "file":
            return f'<label>{esc(label)}<input type="file" name="{kode}"></label>'
        if jenis_f == "calc":
            key = CALC_KEYS.get(kode)
            v = hit.get(key) if key else None
            shown = fmt(v) if v is not None else val
            return f'<div class="ro"><label>{esc(label)}</label><div class="rov calc">{esc(shown)}</div></div>'
        return f'<label>{esc(label)}<input type="text" name="{kode}" value="{val}"></label>'

    # Bukti potong dari lampiran otomatis menjadi kredit pajak (seperti auto-posting Coretax)
    hidden_kredit = (f'<input type="hidden" name="kredit_dipotong" '
                     f'value="{bukti_potong_total(spt_id):.0f}">')

    isi_bagian = ""
    for b in bagian:
        isi_bagian += f'<section class="card"><h3>{esc(b["judul"])}</h3><div class="form-grid">'
        for f in b["field"]:
            isi_bagian += f_html(f)
        isi_bagian += "</div></section>"

    # ringkasan hitungan
    def bar(label, val, cls=""):
        return f'<div class="sum-row"><span>{esc(label)}</span><b class="{cls}">{fmt(val)}</b></div>'

    if s["jenis_pajak"] == "PPh Orang Pribadi":
        ringkasan = (
            bar("Penghasilan neto setahun", hit["neto"]) +
            bar("Pengurang penghasilan neto", hit["pengurang_neto"]) +
            bar("Penghasilan neto setelah pengurang", hit["neto_setelah"]) +
            bar("Penghasilan tidak kena pajak (PTKP)", hit["ptkp"]) +
            bar("Penghasilan kena pajak", hit["pkp"]) +
            bar("PPh terutang", hit["pph_terutang"]) +
            bar("Pengurang PPh terutang", hit["pengurang_pph"]) +
            bar("PPh terutang setelah pengurang", hit["pph_setelah"]) +
            bar("Kredit pajak", hit["kredit_pajak"]) +
            bar("PPh kurang/lebih bayar", hit["kurang_bayar"], "big") +
            bar("PPh yang masih harus dibayar", hit["masih_bayar"], "big") +
            bar("Angsuran PPh Pasal 25 tahun berikutnya", hit["angsuran_pph25"]))
    elif s["jenis_pajak"] == "PPN":
        ringkasan = (bar("PPN keluaran", hit["ppn_keluar"]) +
                     bar("PPN masukan", hit["ppn_masuk"]) +
                     bar("PPnBM", hit["ppnbm"]) +
                     bar("PPN terutang", hit["ppn_terutang"], "big") +
                     bar("PPN kurang bayar", hit["kurang_bayar"], "big"))
    else:
        ringkasan = (bar("Total penghasilan bruto", hit.get("total_bruto", 0)) +
                     bar("Total DPP", hit.get("total_dpp", 0)) +
                     bar("Total pajak", hit.get("total_pajak", 0), "big") +
                     bar("Pajak yang harus dibayar", hit.get("kurang_bayar", 0), "big"))

    isi = f"""
    <div class="page-head">
      <div><h1>{esc(s["jenis_spt"])}</h1>
        <p class="muted">Masa Pajak {esc(s["masa_pajak"])} · Tahun Pajak {esc(s["tahun_pajak"])} ·
        Status SPT: {esc(s["status_spt"])}</p></div>
      <div class="row-btns">
        <a class="btn ghost" href="/spt">Kembali ke daftar</a>
        <a class="btn" href="/spt/{spt_id}/edit">Ubah / isi form</a>
      </div>
    </div>
    <div class="card">
      <h3>Hasil Penghitungan</h3>
      {hidden_kredit}
      <div class="sum">{ringkasan}</div>
      <div class="status-line">Status: <b>{esc(hit.get("status","Nihil"))}</b>
        · Posisi: <b>{esc(s["status_tabel"])}</b>
        · Jatuh tempo: <b>{esc(s["tgl_jatuh_tempo"] or "-")}</b></div>
    </div>
    {isi_bagian}
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Surat Pemberitahuan (SPT)")


@app.get("/spt/{spt_id}/edit", response_class=HTMLResponse)
def spt_edit(request: Request, spt_id: int):
    if not current_npwp(request):
        return RedirectResponse("/")
    s = spt_row(spt_id, request)
    if not s:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    data = json.loads(s["data"] or "{}")
    hit = hitung_spt(s, data, request)
    bagian, lampiran = M.form_for(s["jenis_pajak"])

    def f_html(f):
        kode, label, jenis_f, extra = f
        val = esc(data.get(kode, ""))
        if jenis_f == "readonly":
            return f'<div class="ro"><label>{esc(label)}</label><div class="rov">{esc(data.get(kode) or "-")}</div></div>'
        if jenis_f == "yn":
            y = 'checked' if data.get(kode) == "Ya" else ""
            n = 'checked' if data.get(kode) == "Tidak" else ""
            return (f'<div class="yn"><label>{esc(label)}</label>'
                    f'<label class="radio"><input type="radio" name="{kode}" value="Ya" {y}> Ya</label>'
                    f'<label class="radio"><input type="radio" name="{kode}" value="Tidak" {n}> Tidak</label></div>')
        if jenis_f == "select":
            opts = "".join(f'<option value="{esc(o)}"{" selected" if data.get(kode)==o else ""}>{esc(o)}</option>'
                           for o in (extra or []))
            return f'<label>{esc(label)}<select name="{kode}">{opts}</select></label>'
        if jenis_f == "number":
            return f'<label>{esc(label)}<input type="text" inputmode="decimal" name="{kode}" value="{val}" placeholder="0,00"></label>'
        if jenis_f == "textarea":
            return f'<label>{esc(label)}<textarea name="{kode}" rows="2">{val}</textarea></label>'
        if jenis_f == "file":
            return f'<label>{esc(label)}<input type="file" name="{kode}"></label>'
        if jenis_f == "calc":
            key = CALC_KEYS.get(kode)
            v = hit.get(key) if key else None
            shown = fmt(v) if v is not None else val
            return f'<div class="ro"><label>{esc(label)}</label><div class="rov calc">{esc(shown)}</div></div>'
        return f'<label>{esc(label)}<input type="text" name="{kode}" value="{val}"></label>'

    # Bukti potong dari lampiran otomatis menjadi kredit pajak (seperti auto-posting Coretax)
    hidden_kredit = (f'<input type="hidden" name="kredit_dipotong" '
                     f'value="{bukti_potong_total(spt_id):.0f}">')

    isi_bagian = ""
    for b in bagian:
        isi_bagian += f'<section class="card"><h3>{esc(b["judul"])}</h3><div class="form-grid">'
        for f in b["field"]:
            isi_bagian += f_html(f)
        isi_bagian += "</div></section>"

    # lampiran
    c = M.conn()
    isi_lamp = ""
    for lp in lampiran:
        if "kolom" in lp:
            rows = c.execute("SELECT * FROM lampiran WHERE spt_id=? AND kode=?", (spt_id, lp["kode"])).fetchall()
            th = "".join(f"<th>{esc(k[1])}</th>" for k in lp["kolom"])
            tb = ""
            for r in rows:
                d = json.loads(r["data"] or "{}")
                tds = "".join(f'<td>{esc(d.get(k[0],""))}</td>' for k in lp["kolom"])
                tb += f"<tr>{tds}<td><a class='btn-mini ghost' href='/spt/{spt_id}/lampiran/{lp['kode']}/{r['id']}/hapus?csrf_token={esc(csrf_token(request))}'>Hapus</a></td></tr>"
            if not tb:
                tb = f'<tr><td colspan="{len(lp["kolom"])+1}" class="empty">Belum ada data.</td></tr>'
            isi_lamp += (f'<section class="card"><h3>{esc(lp["judul"])}</h3>'
                         f'<p class="muted small">{esc(lp["keterangan"])}</p>'
                         f'<table class="tbl"><thead><tr>{th}<th>Aksi</th></tr></thead><tbody>{tb}</tbody></table>'
                         f'<a class="btn-mini" href="/spt/{spt_id}/lampiran/{lp["kode"]}">+ Tambah Data</a></section>')
        else:
            for bg in lp["bagian"]:
                for sb in bg["sub"]:
                    rows = c.execute("SELECT * FROM lampiran WHERE spt_id=? AND kode=? AND sub=?",
                                     (spt_id, f'{lp["kode"]}|{bg["kode"]}|{sb["kode"]}', sb["kode"])).fetchall()
                    tb = ""
                    subkey = f'{lp["kode"]}|{bg["kode"]}|{sb["kode"]}'
                    for r in rows:
                        d = json.loads(r["data"] or "{}")
                        tds = "".join(f'<td>{esc(d.get(k[0],""))}</td>' for k in sb["field"])
                        # subkey = "KODE|BAGIAN|SUB"; path param FastAPI tidak bisa
                        # menerima '|' dalam satu segmen -> pecah jadi 3 segmen.
                        _k, _b, _s = subkey.split("|", 2)
                        hapus = (f'<a class="btn-mini ghost" href="/spt/{spt_id}/lampiran/'
                                 f'{esc(_k)}/{esc(_b)}/{esc(_s)}/{r["id"]}/hapus?csrf_token='
                                 f'{esc(csrf_token(request))}">Hapus</a>')
                        tb += f"<tr>{tds}<td>{hapus}</td></tr>"
                    if not tb:
                        tb = f'<tr><td colspan="{len(sb["field"])+1}" class="empty">Belum ada data.</td></tr>'
                    th = "".join(f"<th>{esc(k[1])}</th>" for k in sb["field"]) + "<th>Aksi</th>"
                    desc = ""
                    if sb.get("desc"):
                        desc = ('<label>Deskripsi <select name="description">'
                                + "".join(f'<option>{esc(d)}</option>' for d in sb["desc"]) + "</select></label>")
                    isi_lamp += (f'<section class="card"><h3>{esc(lp["judul"])} — {esc(sb["judul"])}</h3>'
                                 f'<table class="tbl"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>'
                                 f'<a class="btn-mini" href="/spt/{spt_id}/lampiran/{lp["kode"]}/{bg["kode"]}/{sb["kode"]}">+ Tambah Data</a>'
                                 f'{desc}</section>')
    c.close()

    isi = f"""
    <div class="page-head">
      <div><h1>{esc(s["jenis_spt"])}</h1>
        <p class="muted">Isi formulir induk dan lampiran, lalu simpan sebagai draft</p></div>
      <div class="row-btns">
        <a class="btn ghost" href="/spt/{spt_id}">Batal</a>
        <a class="btn" href="/spt/{spt_id}/tt">Tanda tangan &amp; Bayar</a>
      </div>
    </div>
    <form method="post" action="/spt/{spt_id}/simpan">
        {csrf_field(request)}
      {hidden_kredit}
      {isi_bagian}
      <div class="row-btns end">
        <button class="btn-primary" type="submit">Simpan Draft</button>
      </div>
    </form>
    <h2 class="sec-title">Lampiran SPT</h2>
    {isi_lamp}
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Surat Pemberitahuan (SPT)")


@app.post("/spt/{spt_id}/simpan")
async def spt_simpan(request: Request, spt_id: int):
    if not current_npwp(request):
        return RedirectResponse("/")
    s = spt_row(spt_id, request)
    if not s:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    form = await request.form()

    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)
    data = json.loads(s["data"] or "{}")
    bagian, _ = M.form_for(s["jenis_pajak"])
    allowed = {f[0] for b in bagian for f in b["field"]}
    for k in allowed:
        v = form.get(k)
        if v is not None:
            data[k] = str(v)
    hit = hitung_spt(s, data, request)
    c = M.conn()
    c.execute("UPDATE spt SET data=?, hitung=?, kurang_bayar=?, lebih_bayar=? WHERE id=?",
              (json.dumps(data), json.dumps(hit),
               max(0.0, hit.get("kurang_bayar", 0) if hit.get("kurang_bayar", 0) > 0 else 0),
               max(0.0, -hit.get("kurang_bayar", 0)) if hit.get("kurang_bayar", 0) < 0 else 0,
               spt_id))
    c.commit()
    c.close()
    M.log(actor(request), "simpan_draft_spt", f"spt_id={spt_id}")
    return RedirectResponse(f"/spt/{spt_id}", status_code=303)


# -------------------------------------------------- lampiran (tambah data)
@app.get("/spt/{spt_id}/lampiran/{kode}/{sub1}/{sub2}", response_class=HTMLResponse)
def lampiran_tambah_sub(request: Request, spt_id: int, kode: str, sub1: str, sub2: str):
    return lampiran_tambah(request, spt_id, kode, sub1, sub2)


@app.get("/spt/{spt_id}/lampiran/{kode}", response_class=HTMLResponse)
def lampiran_tambah(request: Request, spt_id: int, kode: str,
                    sub1: str = Query(""), sub2: str = Query("")):
    if not current_npwp(request):
        return RedirectResponse("/")
    s = spt_row(spt_id, request)
    if not s:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    bagian, lampiran = M.form_for(s["jenis_pajak"])
    target = None
    for lp in lampiran:
        if lp["kode"] != kode:
            continue
        if "kolom" in lp:
            target = {"judul": lp["judul"], "field": lp["kolom"], "desc": None}
        else:
            for bg in lp["bagian"]:
                for sb in bg["sub"]:
                    if bg["kode"] == sub1 and sb["kode"] == sub2:
                        target = {"judul": f'{lp["judul"]} — {sb["judul"]}', "field": sb["field"],
                                  "desc": sb.get("desc")}
    if not target:
        return HTMLResponse("<h1>Lampiran tidak ditemukan</h1>", status_code=404)
    inputs = ""
    for k, label, jenis_f in target["field"]:
        if jenis_f == "number":
            inputs += f'<label>{esc(label)}<input type="text" inputmode="decimal" name="{esc(k)}" placeholder="0,00"></label>'
        elif jenis_f == "date":
            inputs += f'<label>{esc(label)}<input type="date" name="{esc(k)}"></label>'
        elif jenis_f == "textarea":
            inputs += f'<label>{esc(label)}<textarea name="{esc(k)}" rows="2"></textarea></label>'
        else:
            inputs += f'<label>{esc(label)}<input type="text" name="{esc(k)}"></label>'
    if target["desc"]:
        inputs = ('<label>Deskripsi <select name="description">'
                  + "".join(f'<option>{esc(d)}</option>' for d in target["desc"]) + "</select></label>") + inputs
    isi = f"""
    <div class="page-head"><div><h1>Tambah Data Lampiran</h1>
      <p class="muted">{esc(target["judul"])}</p></div></div>
    <form method="post" action="/spt/{spt_id}/lampiran/{kode}/simpan" class="card stack">
        {csrf_field(request)}
      <input type="hidden" name="sub1" value="{esc(sub1)}">
      <input type="hidden" name="sub2" value="{esc(sub2)}">
      {inputs}
      <div class="row-btns">
        <a class="btn ghost" href="/spt/{spt_id}/edit">Batal</a>
        <button class="btn-primary" type="submit">Simpan</button>
      </div>
    </form>
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Surat Pemberitahuan (SPT)")


@app.post("/spt/{spt_id}/lampiran/{kode}/{sub1}/{sub2}/simpan")
async def lampiran_simpan_sub(request: Request, spt_id: int, kode: str, sub1: str, sub2: str):
    return await _lampiran_simpan(request, spt_id, kode, sub1, sub2)


@app.post("/spt/{spt_id}/lampiran/{kode}/simpan")
async def lampiran_simpan(request: Request, spt_id: int, kode: str):
    form = await request.form()

    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)
    return await _lampiran_simpan(request, spt_id, kode,
                                  str(form.get("sub1") or ""), str(form.get("sub2") or ""))


async def _lampiran_simpan(request: Request, spt_id: int, kode: str, sub1: str, sub2: str):
    if not current_npwp(request):
        return RedirectResponse("/")
    form = await request.form()

    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)
    data = {}
    for k in form.keys():
        if k in ("sub1", "sub2"):
            continue
        data[k] = str(form.get(k))
    subkey = f"{kode}|{sub1}|{sub2}" if sub1 else kode
    c = M.conn()
    n = c.execute("SELECT COUNT(*) n FROM lampiran WHERE spt_id=? AND kode=? AND sub=?",
                  (spt_id, subkey, sub2)).fetchone()["n"]
    c.execute("INSERT INTO lampiran (spt_id,kode,sub,no,data) VALUES (?,?,?,?,?)",
              (spt_id, subkey, sub2, n + 1, json.dumps(data)))
    c.commit()
    c.close()
    # Bukti potong memengaruhi kredit pajak -> refresh hitungan SPT
    s = spt_row(spt_id, request)
    data_spt = json.loads(s["data"] or "{}")
    hit = hitung_spt(s, data_spt, request)
    kurang = hit.get("kurang_bayar", 0)
    c = M.conn()
    c.execute("UPDATE spt SET hitung=?, kurang_bayar=?, lebih_bayar=? WHERE id=?",
              (json.dumps(hit), max(0.0, kurang),
               max(0.0, -kurang) if kurang < 0 else 0, spt_id))
    c.commit()
    c.close()
    M.log(actor(request), "tambah_lampiran", f"spt_id={spt_id} {kode}")
    return RedirectResponse(f"/spt/{spt_id}/edit", status_code=303)


@app.get("/spt/{spt_id}/lampiran/{kode}/{sub1}/{sub2}/{lid}/hapus")
def lampiran_hapus_sub(request: Request, spt_id: int, kode: str, sub1: str, sub2: str, lid: int):
    return lampiran_hapus(request, spt_id, kode, lid)


@app.get("/spt/{spt_id}/lampiran/{kode}/{lid}/hapus")
def lampiran_hapus(request: Request, spt_id: int, kode: str, lid: int):
    if not current_npwp(request):
        return RedirectResponse("/")
    # Kepemilikan dicek lewat SPT induknya; tanpa ini WP bisa hapus lampiran
    # SPT orang lain hanya dengan menebak id (IDOR).
    s = spt_row(spt_id, request)
    if not s:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    if not check_csrf_get(request):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid.</p>", status_code=403)
    c = M.conn()
    c.execute("DELETE FROM lampiran WHERE id=? AND spt_id=?", (lid, spt_id))
    c.commit()
    c.close()
    M.log(actor(request), "hapus_lampiran", f"spt_id={spt_id} {kode}")
    return RedirectResponse(f"/spt/{spt_id}/edit", status_code=303)


# ------------------------------------------------ tanda tangan + bayar/kirim
@app.get("/spt/{spt_id}/tt", response_class=HTMLResponse)
def spt_tt(request: Request, spt_id: int):
    if not current_npwp(request):
        return RedirectResponse("/")
    s = spt_row(spt_id, request)
    if not s:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    data = json.loads(s["data"] or "{}")
    hit = hitung_spt(s, data, request)
    npwp = current_npwp(request)
    c = M.conn()
    saldo = c.execute("SELECT saldo FROM deposit WHERE npwp=?", (npwp,)).fetchone()["saldo"]
    c.close()
    kurang = max(0.0, hit.get("kurang_bayar", 0))
    isi = f"""
    <div class="page-head"><div><h1>Tanda tangan Dokumen &amp; Penyampaian</h1>
      <p class="muted">{esc(s["jenis_spt"])} · {esc(s["masa_pajak"])}</p></div></div>
    <div class="card">
      <h3>Penencoreaan SPT</h3>
      <form method="post" action="/spt/{spt_id}/tt/simpan" class="stack">
        {csrf_field(request)}
        <label>Signer Provider (Penyelenggara Sertifikasi Elektronik)
          <select name="provider">
            <option>KO DJP (Kode Otorisasi DJP)</option>
            <option>Sertifikat Elektronik Terenkripsi</option>
            <option>Sertifikat Elektronik Tersertifikasi</option>
          </select></label>
        <label>Signer ID (Penandatangan ID)
          <input type="text" name="signer_id" value="{esc(npwp)}"></label>
        <label>Passphrase <input type="password" name="passphrase" placeholder="passphrase demo"></label>
        <label>Jabatan penandatangan <input type="text" name="jabatan" value="Pemilik"></label>
        <button class="btn-primary" type="submit">Tanda tangan &amp; Simpan</button>
      </form>
    </div>
    <div class="card">
      <h3>Penyampaian SPT</h3>
      <div class="sum">
        <div class="sum-row"><span>Posisi pajak</span><b>{esc(hit.get("status","Nihil"))}</b></div>
        <div class="sum-row"><span>Total yang harus dibayar</span><b class="big">{fmt(kurang)}</b></div>
        <div class="sum-row"><span>Saldo deposit</span><b>{fmt(saldo)}</b></div>
        <div class="sum-row"><span>Kode billing</span><b>{esc(s["kode_billing"] or "-")}</b></div>
        <div class="sum-row"><span>Tanda tangan</span><b>{'Sudah' if s["tanda_tangan"] else 'Belum'}</b></div>
      </div>
      <form method="post" action="/spt/{spt_id}/submit" class="row-btns">
        {csrf_field(request)}
        <button class="btn-primary" type="submit">Pay and Submit (Bayar dan Kirim)</button>
      </form>
      <p class="muted small">Jika status Nihil, SPT terkirim otomatis. Jika Kurang Bayar,
      pilih metode pelunasan di bawah lalu kirim.</p>
      <form method="post" action="/spt/{spt_id}/submit" class="stack">
        {csrf_field(request)}
        <label>Metode pembayaran
          <select name="metode">
            <option value="deposit">Deposit Balance Transfer (Saldo Deposit)</option>
            <option value="billing">Create Billing Code (Buat Kode Billing)</option>
          </select></label>
        <button class="btn" type="submit">Bayar dan Kirim</button>
      </form>
    </div>
    """
    return shell(request, "SPT", "Surat Pemberitahuan (SPT)", isi, "Surat Pemberitahuan (SPT)")


@app.post("/spt/{spt_id}/tt/simpan")
async def spt_tt_simpan(request: Request, spt_id: int):
    if not current_npwp(request):
        return RedirectResponse("/")
    form = await request.form()

    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)
    s = spt_row(spt_id, request)
    data = json.loads(s["data"] or "{}")
    bagian, _ = M.form_for(s["jenis_pajak"])
    allowed = {f[0] for b in bagian for f in b["field"]}
    for k in ("jabatan_penandatangan",):
        if k in allowed and form.get(k):
            data[k] = str(form.get(k))
    c = M.conn()
    c.execute("UPDATE spt SET data=?, tanda_tangan=1 WHERE id=?",
              (json.dumps(data), spt_id))
    c.commit()
    c.close()
    M.log(actor(request), "tt_spt", f"spt_id={spt_id} provider={form.get('provider')}")
    return RedirectResponse(f"/spt/{spt_id}/tt", status_code=303)


@app.post("/spt/{spt_id}/submit")
async def spt_submit(request: Request, spt_id: int, metode: str = Form("billing")):
    if not current_npwp(request):
        return RedirectResponse("/")
    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)

    npwp = current_npwp(request)
    s = spt_row(spt_id, request)
    if not s:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    data = json.loads(s["data"] or "{}")
    hit = hitung_spt(s, data, request)
    kurang = max(0.0, hit.get("kurang_bayar", 0))
    c = M.conn()
    if kurang <= 0:
        # nihil -> langsung terkirim
        c.execute("UPDATE spt SET status_tabel='SPT Dilaporkan', tgl_disampaikan=? WHERE id=?",
                  (M.now(), spt_id))
        pesan = f"spt_id={spt_id} nihil (langsung terkirim)"
    elif metode == "deposit":
        row = c.execute("SELECT saldo FROM deposit WHERE npwp=?", (npwp,)).fetchone()
        if row and row["saldo"] >= kurang:
            c.execute("UPDATE deposit SET saldo=saldo-? WHERE npwp=?", (kurang, npwp))
            c.execute("UPDATE spt SET status_tabel='SPT Dilaporkan', tgl_disampaikan=?, "
                      "kurang_bayar=0, deposit=? WHERE id=?", (M.now(), kurang, spt_id))
            pesan = f"spt_id={spt_id} bayar via deposit"
        else:
            c.execute("UPDATE spt SET status_tabel='SPT Menunggu Pembayaran' WHERE id=?", (spt_id,))
            pesan = f"spt_id={spt_id} deposit tidak cukup -> menunggu pembayaran"
    else:
        kode = f"{datetime.now().strftime('%Y%m%d')}{spt_id:05d}{secrets.randbelow(999):03d}"
        c.execute("UPDATE spt SET status_tabel='SPT Menunggu Pembayaran', kode_billing=? WHERE id=?",
                  (kode, spt_id))
        c.execute("INSERT INTO billing (kode,spt_id,npwp,nama_pajak,jumlah,tgl_issued,tgl_jatuh_tempo,status)"
                  " VALUES (?,?,?,?,?,?,?,?)",
                  (kode, spt_id, npwp, s["jenis_spt"], kurang, M.now(), s["tgl_jatuh_tempo"], "Belum Dibayar"))
        pesan = f"spt_id={spt_id} buat kode billing {kode}"
    M.log(npwp, "submit_spt", pesan, db=c)
    c.commit()
    c.close()
    return RedirectResponse(f"/spt/{spt_id}", status_code=303)


# ============================================================ MODUL LAINNYA
@app.get("/faktur", response_class=HTMLResponse)
def faktur(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    c = M.conn()
    rows = c.execute("SELECT * FROM e_faktur ORDER BY id DESC").fetchall()
    c.close()
    tb = "".join(f"<tr><td>{esc(r['id'])}</td><td>{esc(r['masa_pajak'])}</td>"
                 f"<td>{esc(r['nama_pembeli'])}</td><td>{esc(r['nilai'])}</td>"
                 f"<td>{esc(r['ppn'])}</td><td>{esc(r['status'])}</td></tr>" for r in rows)
    isi = f"""
    <div class="page-head"><div><h1>Faktur Pajak (e-Faktur)</h1>
      <p class="muted">Data ini menjadi sumber PPN Keluaran pada SPT Masa PPN</p></div>
      <a class="btn-primary" href="/faktur/tambah">Buat Faktur Pajak</a></div>
    <div class="card"><table class="tbl">
      <thead><tr><th>Nomor</th><th>Masa Pajak</th><th>Pembeli</th><th>Nilai (DPP)</th><th>PPN</th><th>Status</th></tr></thead>
      <tbody>{tb or '<tr><td colspan="6" class="empty">Belum ada faktur.</td></tr>'}</tbody></table></div>
    """
    return shell(request, "e-Faktur", "Faktur Pajak", isi, "Faktur Pajak")


@app.post("/faktur/tambah")
async def faktur_tambah(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    form = await request.form()

    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)
    c = M.conn()
    nama = str(form.get("nama_pembeli") or "")
    nilai = T.num(form.get("nilai"))
    masa = str(form.get("masa_pajak") or "")
    dpp = nilai / 1.11
    ppn = nilai - dpp
    kode = f"INV-{datetime.now().strftime('%Y%m%d')}-{secrets.randbelow(900)+100}"
    c.execute("""INSERT INTO e_faktur (npwp_penjual,npwp_pembeli,nama_pembeli,masa_pajak,tahun_pajak,
                 tanggal,tipe,kode_barang,nama_barang,jumlah,harga_satuan,nilai,ppn,ppnbm,status)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (get_wp(request)["npwp"], str(form.get("npwp_pembeli") or ""), nama, masa,
               masa.split()[-1] if masa else "", M.now()[:10], "Barang/Jasa",
               str(form.get("kode_barang") or ""), str(form.get("nama_barang") or ""),
               T.num(form.get("jumlah")), T.num(form.get("harga_satuan")), dpp, ppn, 0, "Terbit"))
    c.commit()
    c.close()
    M.log(actor(request), "buat_faktur", nama)
    return RedirectResponse("/faktur", status_code=303)


@app.get("/faktur/tambah", response_class=HTMLResponse)
def faktur_tambah_form(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    isi = """<div class="page-head"><div><h1>Buat Faktur Pajak</h1></div></div>
    <form method="post" action="/faktur/tambah" class="card stack">
        {csrf_field(request)}
      <label>Masa Pajak <input type="text" name="masa_pajak" placeholder="Maret 2026"></label>
      <label>Nama Pembeli <input type="text" name="nama_pembeli" required></label>
      <label>NPWP Pembeli <input type="text" name="npwp_pembeli"></label>
      <label>Kode Barang/Jasa <input type="text" name="kode_barang"></label>
      <label>Nama Barang/Jasa <input type="text" name="nama_barang"></label>
      <label>Jumlah <input type="text" inputmode="decimal" name="jumlah" value="1"></label>
      <label>Harga Satuan <input type="text" inputmode="decimal" name="harga_satuan"></label>
      <label>Total Harga (termasuk PPN) <input type="text" inputmode="decimal" name="nilai" required></label>
      <div class="row-btns"><a class="btn ghost" href="/faktur">Batal</a>
        <button class="btn-primary" type="submit">Terbitkan</button></div>
    </form>"""
    return shell(request, "e-Faktur", "Faktur Pajak", isi, "Faktur Pajak")


@app.get("/bupot", response_class=HTMLResponse)
def bupot(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    c = M.conn()
    rows = c.execute("SELECT * FROM bupot ORDER BY id DESC").fetchall()
    c.close()
    tb = "".join(f"<tr><td>{esc(r['jenis'])}</td><td>{esc(r['nama_penerima'])}</td>"
                 f"<td>{esc(r['masa_pajak'])}</td><td>{esc(r['bruto'])}</td>"
                 f"<td>{esc(r['dpp'])}</td><td>{esc(r['pajak'])}</td>"
                 f"<td>{esc(r['status'])}</td></tr>" for r in rows)
    isi = f"""
    <div class="page-head"><div><h1>Bukti Potong / Bukti Pemungut (eBUPOT)</h1>
      <p class="muted">Data ini menjadi sumber pengisian SPT Masa PPh 21/26 dan Unifikasi</p></div></div>
    <div class="card"><table class="tbl">
      <thead><tr><th>Jenis</th><th>Penerima</th><th>Masa Pajak</th><th>Bruto</th><th>DPP</th>
      <th>Pajak</th><th>Status</th></tr></thead>
      <tbody>{tb or '<tr><td colspan="7" class="empty">Belum ada bukti potong.</td></tr>'}</tbody></table></div>
    """
    return shell(request, "eBUPOT", "Bukti Potong", isi, "Bukti Potong")


@app.get("/billing", response_class=HTMLResponse)
def billing(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    npwp = current_npwp(request)
    c = M.conn()
    rows = c.execute("SELECT * FROM billing ORDER BY id DESC").fetchall()
    saldo = c.execute("SELECT saldo FROM deposit WHERE npwp=?", (npwp,)).fetchone()["saldo"]
    c.close()
    tb = "".join(f"<tr><td>{esc(r['kode'])}</td><td>{esc(r['nama_pajak'])}</td>"
                 f"<td>{fmt(r['jumlah'])}</td><td>{esc(r['tgl_jatuh_tempo'])}</td>"
                 f"<td>{esc(r['status'])}</td>"
                 f"{'<td><a class=\"btn-mini\" href=\"/billing/'+str(r['id'])+'/bayar?csrf_token='+esc(csrf_token(request))+'\">Bayar</a></td>' if r['status']=='Belum Dibayar' else '<td>-</td>'}"
                 f"</tr>" for r in rows)
    isi = f"""
    <div class="page-head"><div><h1>Pembayaran</h1>
      <p class="muted">Kode billing, riwayat setoran, dan saldo deposit</p></div></div>
    <div class="grid3">
      <div class="stat"><div class="stat-n">Rp {fmt(saldo)}</div><div class="stat-l">Saldo Deposit</div></div>
      <div class="stat"><div class="stat-n">{sum(1 for r in rows if r['status']=='Belum Dibayar')}</div>
        <div class="stat-l">Kode billing aktif</div></div>
      <div class="stat"><div class="stat-n">{len(rows)}</div><div class="stat-l">Total billing</div></div>
    </div>
    <div class="card"><table class="tbl">
      <thead><tr><th>Kode Billing</th><th>Nama Pajak</th><th>Jumlah</th><th>Jatuh Tempo</th>
      <th>Status</th><th>Aksi</th></tr></thead>
      <tbody>{tb or '<tr><td colspan="6" class="empty">Belum ada kode billing.</td></tr>'}</tbody></table></div>
    """
    return shell(request, "Pembayaran", "Kode Billing", isi, "Pembayaran")


@app.get("/billing/{bid}/bayar")
def billing_bayar(request: Request, bid: int):
    if not current_npwp(request):
        return RedirectResponse("/")
    npwp = current_npwp(request)
    c = M.conn()
    # Filter npwp: WP hanya boleh membayar billing miliknya sendiri (anti-IDOR).
    # Operator (OP) boleh membayar semua.
    w = c.execute("SELECT role FROM wp WHERE npwp=?", (npwp,)).fetchone()
    if w is not None and w["role"] == "OP":
        b = c.execute("SELECT * FROM billing WHERE id=?", (bid,)).fetchone()
    else:
        b = c.execute("SELECT * FROM billing WHERE id=? AND npwp=?", (bid, npwp)).fetchone()
    if not b:
        c.close()
        return HTMLResponse("<h1>404</h1>", status_code=404)
    if not check_csrf_get(request):
        c.close()
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid.</p>", status_code=403)
    d = c.execute("SELECT saldo FROM deposit WHERE npwp=?", (npwp,)).fetchone()
    if d and d["saldo"] >= b["jumlah"]:
        c.execute("UPDATE deposit SET saldo=saldo-? WHERE npwp=?", (b["jumlah"], npwp))
        c.execute("UPDATE billing SET status='Lunas' WHERE id=?", (bid,))
        c.execute("UPDATE spt SET status_tabel='SPT Dilaporkan', tgl_disampaikan=? WHERE id=?",
                  (M.now(), b["spt_id"]))
        M.log(npwp, "bayar_billing", f"{b['kode']} Rp {b['jumlah']}")
    else:
        c.execute("UPDATE billing SET status='Gagal: saldo tidak cukup' WHERE id=?", (bid,))
    c.commit()
    c.close()
    return RedirectResponse("/billing", status_code=303)


@app.get("/buku-besar", response_class=HTMLResponse)
def buku_besar(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    c = M.conn()
    faktur = c.execute("SELECT COUNT(*) n, COALESCE(SUM(nilai),0) v, COALESCE(SUM(ppn),0) p FROM e_faktur").fetchone()
    bupot = c.execute("SELECT COUNT(*) n, COALESCE(SUM(bruto),0) v, COALESCE(SUM(pajak),0) p FROM bupot").fetchone()
    spt = c.execute("SELECT COUNT(*) n FROM spt").fetchone()
    c.close()
    isi = f"""
    <div class="page-head"><div><h1>Buku Besar Saya</h1>
      <p class="muted">Rekapitulasi omzet dan pajak</p></div></div>
    <div class="grid3">
      <div class="stat"><div class="stat-n">{faktur['n']}</div><div class="stat-l">Faktur Pajak</div>
        <div class="muted small">Total nilai Rp {fmt(faktur['v'])}</div></div>
      <div class="stat"><div class="stat-n">{bupot['n']}</div><div class="stat-l">Bukti Potong</div>
        <div class="muted small">Total bruto Rp {fmt(bupot['v'])}</div></div>
      <div class="stat"><div class="stat-n">{spt['n']}</div><div class="stat-l">SPT</div>
        <div class="muted small">Seluruh jenis</div></div>
    </div>
    <div class="card"><h3>PPN dari Faktur Pajak</h3>
      <div class="sum"><div class="sum-row"><span>Total PPN keluar</span><b>{fmt(faktur['p'])}</b></div></div>
      <h3>PPh dari Bukti Potong</h3>
      <div class="sum"><div class="sum-row"><span>Total PPh dipotong</span><b>{fmt(bupot['p'])}</b></div></div>
    </div>
    """
    return shell(request, "Buku Besar", "Buku Besar Saya", isi, "Buku Besar")


@app.get("/wp", response_class=HTMLResponse)
def wp_page(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    wp = get_wp(request)
    isi = f"""
    <div class="page-head"><div><h1>Data Wajib Pajak</h1>
      <p class="muted">Perubahan data (simulasi)</p></div></div>
    <form method="post" action="/wp/simpan" class="card stack">
        {csrf_field(request)}
      <label>NPWP <input type="text" name="npwp" value="{esc(wp['npwp'])}" readonly></label>
      <label>Nama <input type="text" name="nama" value="{esc(wp['nama'])}"></label>
      <label>Alamat <input type="text" name="alamat" value="{esc(wp['alamat'])}"></label>
      <label>KPP <input type="text" name="kpp" value="{esc(wp['kpp'])}"></label>
      <label>Telepon <input type="text" name="telepon" value="{esc(wp['telepon'])}"></label>
      <label>Email <input type="text" name="email" value="{esc(wp['email'])}"></label>
      <label>Status PTKP <select name="ptkp_kode">
        {''.join(f'<option value="{k}"{" selected" if k==wp["ptkp_kode"] else ""}>{k} (Rp {fmt(v)})</option>' for k,v in T.PTKP.items())}
      </select></label>
      <div class="row-btns"><button class="btn-primary" type="submit">Simpan</button></div>
    </form>
    """
    return shell(request, "Portal Saya", "Perubahan Data", isi, "Perubahan Data")


@app.post("/wp/simpan")
async def wp_simpan(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    form = await request.form()

    form = await request.form()
    if not check_csrf(request, form):
        return HTMLResponse("<h1>403</h1><p>Token CSRF tidak valid atau kedaluwarsa. "
                            "Muat ulang halaman lalu coba lagi.</p>", status_code=403)
    c = M.conn()
    c.execute("UPDATE wp SET nama=?, alamat=?, kpp=?, telepon=?, email=?, ptkp_kode=? WHERE npwp=?",
              (str(form.get("nama")), str(form.get("alamat")), str(form.get("kpp")),
               str(form.get("telepon")), str(form.get("email")), str(form.get("ptkp_kode")),
               get_wp(request)["npwp"]))
    c.commit()
    c.close()
    return RedirectResponse("/wp", status_code=303)


@app.get("/layanan", response_class=HTMLResponse)
def layanan(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    isi = """
    <div class="page-head"><div><h1>Layanan Wajib Pajak</h1></div></div>
    <div class="card"><p class="muted">Modul layanan (permohonan informasi, pengembalian pajak,
    edukasi) masih kerangka halaman pada simulator ini.</p></div>"""
    return shell(request, "Layanan WP", "Layanan Wajib Pajak", isi, "Layanan Wajib Pajak")


@app.get("/akses", response_class=HTMLResponse)
def akses(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    r = redirect_modul(request)
    if r:
        return r
    isi = """
    <div class="page-head"><div><h1>Manajemen Akses</h1></div></div>
    <div class="card"><p class="muted">Pengelolaan role drafter/signer masih kerangka halaman.</p></div>"""
    return shell(request, "Manajemen Akses", "Manajemen Akses", isi, "Manajemen Akses")


@app.get("/spt/pencatatan", response_class=HTMLResponse)
def pencatatan(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    isi = """
    <div class="page-head"><div><h1>Pencatatan</h1>
      <p class="muted">Pencatatan transaksi untuk PPh Final (Pengungkapan Harta Bersih)</p></div></div>
    <div class="card"><p class="muted">Modul pencatatan masih kerangka halaman pada simulator ini.</p></div>"""
    return shell(request, "SPT", "Pencatatan", isi, "Pencatatan")


@app.get("/spt/kompensasi", response_class=HTMLResponse)
def kompensasi(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    isi = """
    <div class="page-head"><div><h1>Dasbor Kompensasi</h1></div></div>
    <div class="card"><p class="muted">Modul dasbor kompensasi masih kerangka halaman.</p></div>"""
    return shell(request, "SPT", "Dasbor Kompensasi", isi, "Dasbor Kompensasi")


@app.get("/spt/pengungkapan", response_class=HTMLResponse)
def pengungkapan(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    isi = """
    <div class="page-head"><div><h1>Pengungkapan Ketidakbenaran SPT</h1></div></div>
    <div class="card"><p class="muted">Modul pengungkapan masih kerangka halaman.</p></div>"""
    return shell(request, "SPT", "Pengungkapan Ketidakbenaran SPT", isi, "Pengungkapan")


@app.get("/spt/form", response_class=HTMLResponse)
def coretax_form(request: Request):
    if not current_npwp(request):
        return RedirectResponse("/")
    isi = """
    <div class="page-head"><div><h1>Coretax Form</h1></div></div>
    <div class="card"><p class="muted">Pemeriksaan formulir SPT masih kerangka halaman.</p></div>"""
    return shell(request, "SPT", "Coretax Form", isi, "Coretax Form")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8140)