"""Uji end-to-end alur SPT lewat HTTP (bukan TestClient, supaya server nyata yang dites).

Jalankan: python3 e2e_test.py
"""
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8140"

# E2E butuh DB bersih supaya hasil deterministik: billing/SPT dari run
# sebelumnya bisa sudah "Lunas" / sudah submit, sehingga beberapa assertion
# gagal bukan karena bug aplikasi.
import os
import sqlite3
import subprocess
import sys

_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coretax.db")
if os.path.exists(_DB):
    subprocess.run([sys.executable, "reset_db.py", "--yes"],
                   cwd=os.path.dirname(os.path.abspath(__file__)),
                   capture_output=True, check=False)
COOKIE = ""
fails = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def req(path, data=None, method=None):
    """Kembalikan (code, body). Non-2xx tidak exception; redirect tidak diikutkan."""
    url = BASE + path
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method or ("POST" if data else "GET"))
    if COOKIE:
        r.add_header("Cookie", COOKIE)
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.getcode(), resp.read().decode(errors="replace")


def req_redirect(path):
    """Kembalikan (code, Location) tanpa mengikuti redirect."""
    r = urllib.request.Request(BASE + path)
    if COOKIE:
        r.add_header("Cookie", COOKIE)
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.getcode(), resp.headers.get("Location", "")


def get(path):
    """GET dengan follow redirect (agar body halaman tujuan terbaca)."""
    url = BASE + path
    r = urllib.request.Request(url)
    if COOKIE:
        r.add_header("Cookie", COOKIE)
    try:
        resp = urllib.request.urlopen(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.getcode(), resp.read().decode(errors="replace")


# Halaman yang memuat form POST untuk path tertentu -> sumber token CSRF.
# Pola: path POST dipetakan ke path halaman GET tempat form itu berada.
CSRF_SOURCE = {
    "/spt/buat/simpan": "/spt/buat/jenis?jenis=PPh+Orang+Pribadi"
                        "&periode=Januari+-+Desember+2025&jenis_periode=SPT+Tahunan",
}
# Aturan generik: /spt/{id}/X -> /spt/{id}/Y
CSRF_RULES = [
    (re.compile(r"^/spt/\d+/simpan$"), "/spt/{id}/edit"),
    (re.compile(r"^/spt/\d+/lampiran/[^/]+/[^/]+/[^/]+/simpan$"), "/spt/{id}/edit"),
    (re.compile(r"^/spt/\d+/lampiran/[^/]+/simpan$"), "/spt/{id}/edit"),
    (re.compile(r"^/spt/\d+/tt/simpan$"), "/spt/{id}/tt"),
    (re.compile(r"^/spt/\d+/submit$"), "/spt/{id}/tt"),
    (re.compile(r"^/faktur/tambah$"), "/faktur/tambah"),
    (re.compile(r"^/wp/simpan$"), "/wp"),
]


def csrf_for(path):
    """Ambil token CSRF dari halaman yang memuat form untuk path tsb."""
    src = CSRF_SOURCE.get(path)
    if src is None:
        for pat, tmpl in CSRF_RULES:
            m = pat.match(path)
            if m:
                sid = path.split("/")[2]
                src = tmpl.replace("{id}", sid)
                break
    if not src:
        return ""
    code, body = get(src)
    m = re.search(r'name="csrf_token" value="([^"]+)"', body)
    return m.group(1) if m else ""


def post(path, data):
    """POST dengan follow redirect. Token CSRF ditambahkan otomatis bila perlu."""
    url = BASE + path
    data = dict(data)
    if "csrf_token" not in data:
        tok = csrf_for(path)
        if tok:
            data["csrf_token"] = tok
    body = urllib.parse.urlencode(data, doseq=True).encode()
    r = urllib.request.Request(url, data=body, method="POST")
    if COOKIE:
        r.add_header("Cookie", COOKIE)
    try:
        resp = urllib.request.urlopen(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.getcode(), resp.read().decode(errors="replace")


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- 1. login
code, body = get("/")
check("login page tampil", code == 200 and "Selamat Datang" in body)

r = urllib.request.Request(BASE + "/login", data=urllib.parse.urlencode(
    {"id": "2171121009959003", "pwd": "demo123"}).encode(), method="POST")
try:
    resp = OPENER.open(r)
except urllib.error.HTTPError as e:
    resp = e
COOKIE = resp.headers.get("Set-Cookie", "").split(";")[0]
check("login dapat cookie", "ctx=" in COOKIE, COOKIE)

code, body = get("/home")
check("home tampil", code == 200 and "selamat datang" in body.lower() and "Coretax" in body)

# ------------------------------------------------------- 2. dashboard SPT
code, body = get("/spt")
check("dashboard SPT", code == 200 and "Buat Konsep SPT" in body)
check("sidebar SPT ada", "Dasbor Kompensasi" in body and "Coretax Form" in body)
check("topnav 8 modul", all(m in body for m in
      ["Portal Saya", "e-Faktur", "eBUPOT", "SPT", "Pembayaran", "Buku Besar", "Layanan WP",
       "Manajemen Akses"]))

# ------------------------------------------------------- 3. wizard 3 langkah
code, body = get("/spt/buat")
check("wizard langkah 1", code == 200 and "PPh Orang Pribadi" in body and
      "PPh Pasal 21/26" in body and "PPh Unifikasi" in body and
      "PPh Final Pengungkapan Harta Bersih" in body)

code, body = get("/spt/buat/periode?jenis=PPh%20Orang%20Pribadi")
check("wizard langkah 2 (periode)", code == 200 and "Januari - Desember 2025" in body)

code, body = get("/spt/buat/jenis?jenis=PPh%20Orang%20Pribadi&periode=Januari%20-%20Desember%202025&jenis_periode=SPT%20Tahunan")
check("wizard langkah 3 (model)", code == 200 and "Normal" in body and "Pembetulan" in body)

# buat konsep -> redirect ke /spt/{id}/edit
code, body = post("/spt/buat/simpan", {
    "jenis": "PPh Orang Pribadi", "periode": "Januari - Desember 2025",
    "jenis_periode": "SPT Tahunan", "model": "Normal"})
check("konsep SPT dibuat", code == 200 and "Isi formulir induk" in body)

code, body = get("/spt?status=Semua")
m = re.search(r'href="/spt/(\d+)/edit"', body)
spt_id = m.group(1) if m else None
check("SPT muncul di daftar", spt_id is not None)

# ------------------------------------------------- 4. form induk 12 bagian
code, body = get(f"/spt/{spt_id}/edit")
for judul in ["Header (Tajuk)", "A. Identity of Taxpayers", "B. Summary of Income",
              "C. Income Tax Payable Calculation", "D. Income Tax Credit",
              "E. Underpayment/Overpayment", "F. Amendment Tax Return", "G. Refund",
              "H. Income Tax Installment", "I. Statement of Other Transactions",
              "J. Additional Attachments", "K. Statement"]:
    check(f"bagian: {judul[:34]}", judul in body)
for lamp in ["Lampiran 1", "Lampiran 2", "Lampiran 3A-1", "Lampiran 3A-2", "Lampiran 3A-3",
             "Lampiran 3A-4", "Lampiran 3B", "Lampiran 3C", "Lampiran 3D", "Lampiran 4", "Lampiran 5"]:
    check(f"lampiran: {lamp}", lamp in body)

# --------------------------- 5a. lampiran bukti potong (sumber kredit pajak)
# Credit pajak comes from lampiran L-1 bagian E (auto-posting seperti Coretax asli),
# jadi lampiran harus diisi sebelum draft disimpan.
code, body = get(f"/spt/{spt_id}/lampiran/L-1/E/1")
check("form lampiran bukti potong", code == 200 and "Withholding" in body)
for i, (bp, pajak) in enumerate([("1111111111111", 24_000_000),
                                  ("2222222222222", 26_000_000)], 1):
    code, body = post(f"/spt/{spt_id}/lampiran/L-1/E/1/simpan", {
        "no_bupot": f"BPA1-2025-{i:03d}", "npwp": bp, "name": f"Pembayar {i}",
        "gross_income": 100_000_000, "withholding_tax": pajak})
check("bukti potong tersimpan", code == 200)

# ------------------------------------------------------- 6. lampiran isi
code, body = get(f"/spt/{spt_id}/lampiran/L-1/A/1")
check("form lampiran kas & setara kas", code == 200 and "Cash and Cash Equivalents" in body
      and "Account Number" in body)
code, body = post(f"/spt/{spt_id}/lampiran/L-1/A/1/simpan", {
    "description": "Tabungan (Bank/Lembaga Keuangan)",
    "code": "CASH01", "account_number": "1234567890", "on_behalf_of": "ALLIF MAULANA",
    "bank_name": "Bank Contoh", "country": "Indonesia", "year_acquisition": "2020",
    "balance": "15000000", "remark": ""})
check("lampiran tersimpan", code == 200 and "CASH01" in body)

code, body = get(f"/spt/{spt_id}/lampiran/A-2")
check("lampiran A-2 bukan milik SPT OP (harus 404)", code == 404)

# ------------------------------------------------------------ 5. isi + hitung
form = {
    "tahun_pajak": "2025", "periode_akuntansi": "Januari - Desember 2025",
    "status_spt": "Normal", "jenis_pembukuan": "Pembukuan Stelsel Akrual",
    "sumber_penghasilan": "Pekerjaan",
    "npwp": "2171121009959003", "nama": "ALLIF MAULANA", "telepon": "081234567890",
    "email": "allif@example.test", "status_kewajiban": "Wajib Pajak Orang Pribadi",
    "npwp_pasangan": "",
    "q_1a": "Ya", "q_1b1": "Tidak", "q_1c": "Tidak", "q_1d": "Tidak",
    "q_2": "600000000", "q_3": "Tidak", "pengurang_neto": "0",
    "q_8": "Tidak", "pengurang_pph": "0",
    "q_10a": "Ya", "q_10b": "0", "q_10c": "0", "q_10d": "Tidak",
    "q_11b": "Tidak", "nilai_pengangsuran": "0",
    "q_13a": "Ya", "q_13b": "Tidak", "q_13c": "Tidak",
    "q_14a": "500000000", "q_14b": "Tidak", "q_14c": "Tidak", "q_14d": "Tidak",
    "q_14e": "Tidak", "q_14f": "Tidak", "q_14g": "Tidak", "q_14h": "0",
    "jabatan_penandatangan": "Pemilik", "pernyataan": "Pernyataan benar dan jelas",
}
code, body = post(f"/spt/{spt_id}/simpan", form)
check("simpan draft", code == 200 and "Hasil Penghitungan" in body)
# 600jt neto, PTKP K/0=58.5jt -> PKP 541.5jt -> PPh = 3jt + 28.5jt + 72.875jt = 104.375jt
check("PKP 541.500.000 tampil", "541.500.000" in body, body[:200])
check("PPh terutang 106.450.000 tampil", "106.450.000" in body)
check("kredit pajak 50.000.000 tampil", "50.000.000" in body)
check("kurang bayar 56.450.000 tampil", "56.450.000" in body)
check("status Kurang Bayar", "Kurang Bayar" in body)



# ---------------------------------------------------- 7. tanda tangan
code, body = get(f"/spt/{spt_id}/tt")
check("halaman tanda tangan", code == 200 and "Signer Provider" in body and
      "Pay and Submit" in body)
code, body = post(f"/spt/{spt_id}/tt/simpan", {
    "provider": "KO DJP (Kode Otorisasi DJP)", "signer_id": "2171121009959003",
    "passphrase": "demo", "jabatan": "Pemilik"})
check("tanda tangan tersimpan", code == 200 and "Sudah" in body)

# ------------------------------------------------- 8. submit via billing
code, body = post(f"/spt/{spt_id}/submit", {"metode": "billing"})
check("submit buat kode billing", code == 200 and "Menunggu Pembayaran" in body)
code, body = get("/spt?status=Semua")
check("status SPT Menunggu Pembayaran", "SPT Menunggu Pembayaran" in body)

# ------------------------------------------------- 9. bayar kode billing
# Catatan: DB harus dalam kondisi bersih. Billing dari run sebelumnya bisa sudah
# berstatus "Lunas", sehingga pengecekan "belum Lunas" di bawah jadi salah.
code, body = get("/billing")
check("halaman billing", code == 200 and "Kode Billing" in body)
m = re.search(r'href="/billing/(\d+)/bayar"', body)
bid = m.group(1) if m else None
check("tombol bayar ada", bid is not None)
code, body = get(f"/billing/{bid}/bayar")
check("billing lunas", code == 200 and "Lunas" in body)
code, body = get("/spt?status=Semua")
check("SPT jadi Dilaporkan", "SPT Dilaporkan" in body)

# ------------------------------------------- 10. SPT PPh 21/26 (masa)
code, body = post("/spt/buat/simpan", {
    "jenis": "PPh Pasal 21/26", "periode": "Maret 2026",
    "jenis_periode": "SPT Masa", "model": "Normal"})
check("konsep SPT PPh 21 dibuat", code == 200 and "Rincian Pemotongan" in body)
m = re.search(r'href="/spt/(\d+)/edit"', get("/spt?status=Semua")[1])
id21 = m.group(1)
code, body = post(f"/spt/{id21}/simpan", {
    "npwp_pemotong": "2171121009959003", "nama_pemotong": "ALLIF MAULANA",
    "jabatan_penandatangan": "Pemilik", "jumlah_bupot": "4", "total_bruto": "36500000",
    "total_dpp": "36500000", "total_pajak": "847500", "pajak_ditanggung": "0",
    "masa_pajak": "Maret 2026", "tahun_pajak": "2026", "status_spt": "Normal",
    "keterangan": ""})
check("SPT PPh 21 terisi", code == 200 and "847.500" in body)
check("status PPh 21 Kurang Bayar", "Kurang Bayar" in body)

# ------------------------------------------- 11. SPT PPN
code, body = post("/spt/buat/simpan", {
    "jenis": "PPN", "periode": "Maret 2026", "jenis_periode": "SPT Masa", "model": "Normal"})
m = re.search(r'href="/spt/(\d+)/edit"', get("/spt?status=Semua")[1])
idppn = m.group(1)
code, body = post(f"/spt/{idppn}/simpan", {
    "nilai_penyerahan": "200000000", "jumlah_faktur_keluar": "3", "jumlah_faktur_masuk": "0",
    "dpp_keluar": "180180180", "dpp_masuk": "0", "ppnbm": "0", "ppn_dipungut": "0",
    "jabatan_penandatangan": "Pemilik", "masa_pajak": "Maret 2026", "tahun_pajas": "2026",
    "status_spt": "Normal"})
check("SPT PPN terisi", code == 200 and "PPN Terutang" in body)
code, body = get(f"/spt/{idppn}/lampiran/A-2")
check("form lampiran PPN A-2 di SPT PPN", code == 200 and "Nomor Faktur Pajak" in body)

# ------------------------------------------------ 12. modul lain
for path, expect in [("/faktur", "Faktur Pajak"), ("/bupot", "Bukti Potong"),
                     ("/buku-besar", "Buku Besar"), ("/wp", "Data Wajib Pajak"),
                     ("/layanan", "Layanan Wajib Pajak"), ("/akses", "Manajemen Akses")]:
    code, body = get(path)
    check(f"modul {path}", code == 200 and expect in body)

# ------------------------------------- 12b. navigasi: nav atas harus berpindah modul
code, body = get("/faktur")
check("nav atas tanpa ?modul=", "?modul=" not in body)
for tujuan in ("/home", "/faktur", "/bupot", "/spt", "/billing", "/buku-besar",
               "/layanan", "/akses"):
    check(f"nav menuju {tujuan}", f'href="{tujuan}"' in body)
# URL lama "?modul=X" dari halaman lain harus redirect ke path modul
for modul, tujuan in [("SPT", "/spt"), ("e-Faktur", "/faktur"), ("eBUPOT", "/bupot"),
                      ("Pembayaran", "/billing"), ("Buku Besar", "/buku-besar"),
                      ("Portal Saya", "/home"), ("Layanan WP", "/layanan"),
                      ("Manajemen Akses", "/akses")]:
    code, loc = req_redirect(f"/faktur?modul={urllib.parse.quote(modul)}")
    check(f"link lama /faktur?modul={modul}", code == 303 and loc == tujuan,
          f"code={code} loc={loc}")

# -------------------------------------------------------- 13. audit trail
code, body = get("/spt?status=Semua")
n_spt = len(re.findall(r'href="/spt/\d+/edit"', body))
check("3 SPT tercatat", n_spt >= 3, f"n={n_spt}")

print()
if fails:
    print(f"{len(fails)} FAIL:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("SEMUA E2E PASS")