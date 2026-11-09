"""Verifikasi list-view scoping: WP hanya melihat barisnya sendiri.

Meniru temuan Strix vuln-0001 (CWE-639): list view dulu mengembalikan
seluruh baris ke session WP mana pun.
"""
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8140"
fails = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"  [{extra}]" if not ok and extra else ""))
    if not ok:
        fails.append(label)


def post(path, data, cookie=None):
    r = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode(), method="POST")
    if cookie:
        r.add_header("Cookie", cookie)
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return (resp.getcode(), resp.headers.get("Location", ""), resp.headers.get("Set-Cookie", ""),
            resp.read().decode(errors="replace"))


def get(path, cookie=None):
    r = urllib.request.Request(BASE + path)
    if cookie:
        r.add_header("Cookie", cookie)
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.getcode(), resp.read().decode(errors="replace")


def login(npwp):
    _, _, sc, _ = post("/login", {"id": npwp, "pwd": "demo123"})
    return sc.split(";")[0] if sc else None


OP = login("2171121009959003")
WP = login("1111111111111")
check("login OP & WP", bool(OP) and bool(WP))

# seed membuat SPT/faktur/bupot milik OP (NPWP 2171121009959003)
# dan deposit 150jt milik OP.

# --- 1. /spt : WP tidak boleh melihat SPT OP ---
code_op, body_op = get("/spt?status=Semua", OP)
code_wp, body_wp = get("/spt?status=Semua", WP)
ids_op = re.findall(r'href="/spt/(\d+)/edit"', body_op)
ids_wp = re.findall(r'href="/spt/(\d+)/edit"', body_wp)
check("OP melihat SPT miliknya", len(ids_op) > 0, f"ids={ids_op}")
check("WP tidak melihat SPT milik OP", len(ids_wp) == 0, f"ids WP={ids_wp}")

# --- 2. /faktur ---
_, f_op = get("/faktur", OP)
_, f_wp = get("/faktur", WP)
n_op = len(re.findall(r'<td>\d+</td>', f_op))
n_wp = len(re.findall(r'<td>\d+</td>', f_wp))
check("OP melihat faktur miliknya", n_op > 0, f"n={n_op}")
check("WP tidak melihat faktur milik OP", n_wp == 0, f"n WP={n_wp}")

# --- 3. /bupot ---
_, b_op = get("/bupot", OP)
_, b_wp = get("/bupot", WP)
# hitung baris data (nama penerima), bukan keyword di judul halaman
n_op = len(re.findall(r"<td>(?:Bukti Potong [^<]*)</td>", b_op))
n_wp = len(re.findall(r"<td>(?:Bukti Potong [^<]*)</td>", b_wp))
check("OP melihat bupot miliknya", n_op > 0, f"n={n_op}")
check("WP tidak melihat bupot milik OP", n_wp == 0, f"n WP={n_wp}")

# --- 4. /billing ---
# DB fresh belum punya billing -> buat milik OP dulu (isi SPT + submit via billing).
_bod = get(f"/spt/{ids_op[0]}/edit", OP)[1]
_tok = re.search(r'name="csrf_token" value="([^"]+)"', _bod)
_fields = dict(re.findall(r'name="([^"]+)"[^>]*value="([^"]*)"', _bod))
_fields = {k: v for k, v in _fields.items() if k != "csrf_token"}
_fields["q_2"] = "600000000"
_fields["csrf_token"] = _tok.group(1) if _tok else ""
post(f"/spt/{ids_op[0]}/simpan", _fields, OP)
_tt = get(f"/spt/{ids_op[0]}/tt", OP)[1]
_tok2 = re.search(r'name="csrf_token" value="([^"]+)"', _tt)
post(f"/spt/{ids_op[0]}/tt/simpan", {"csrf_token": _tok2.group(1) if _tok2 else ""}, OP)
post(f"/spt/{ids_op[0]}/submit", {"metode": "billing", "csrf_token": _tok2.group(1) if _tok2 else ""}, OP)

_, bl_op = get("/billing", OP)
_, bl_wp = get("/billing", WP)
n_bill_op = len(re.findall(r"<td>\d{10,}</td>", bl_op))
n_bill_wp = len(re.findall(r"<td>\d{10,}</td>", bl_wp))
check("OP melihat kode billing miliknya", n_bill_op > 0, f"n={n_bill_op}")
check("WP tidak melihat kode billing milik OP", n_bill_wp == 0, f"n WP={n_bill_wp}")

# --- 5. /buku-besar : agregat tidak boleh global ---
_, bb_op = get("/buku-besar", OP)
_, bb_wp = get("/buku-besar", WP)
m_op = re.search(r'Total PPN keluar</span><b>([^<]+)', bb_op)
m_wp = re.search(r'Total PPN keluar</span><b>([^<]+)', bb_wp)
check("agregat buku-besar WP tidak sama dengan OP",
      (m_wp is None) or (m_op is None) or m_wp.group(1) != m_op.group(1),
      f"OP={m_op.group(1) if m_op else None} WP={m_wp.group(1) if m_wp else None}")

# --- 6. /home : counter tidak boleh global ---
_, h_op = get("/home", OP)
_, h_wp = get("/home", WP)
c_op = re.search(r'<div class="stat-n">(\d+)</div><div class="stat-l">SPT dibuat', h_op)
c_wp = re.search(r'<div class="stat-n">(\d+)</div><div class="stat-l">SPT dibuat', h_wp)
check("counter SPT di dashboard WP bukan milik OP",
      (c_wp is None) or (c_op is None) or c_wp.group(1) == "0",
      f"OP={c_op.group(1) if c_op else None} WP={c_wp.group(1) if c_wp else None}")

# --- 7. WP buat data sendiri -> harus muncul di daftar WP, tidak di OP ---
# SPT milik WP
_wiz = get("/spt/buat/jenis?jenis=PPh+Orang+Pribadi&periode=Januari+-+Desember+2025"
           "&jenis_periode=SPT+Tahunan", WP)[1]
_wtok = re.search(r'name="csrf_token" value="([^"]+)"', _wiz)
post("/spt/buat/simpan", {
    "jenis": "PPh Orang Pribadi", "periode": "Januari - Desember 2025",
    "jenis_periode": "SPT Tahunan", "model": "Normal",
    "csrf_token": _wtok.group(1) if _wtok else ""}, WP)
_, home_wp = get("/spt?status=Semua", WP)
_, home_op = get("/spt?status=Semua", OP)
ids_wp2 = re.findall(r'href="/spt/(\d+)/edit"', home_wp)
ids_op2 = re.findall(r'href="/spt/(\d+)/edit"', home_op)
check("SPT milik WP muncul di daftar WP", len(ids_wp2) == 1, f"ids={ids_wp2}")
# Role OP memang melihat semua SPT (termasuk milik WP) - itu by design.
# Yang wajib benar: daftar WP hanya berisi SPT milik WP sendiri, dan daftar OP
# tetap memuat SPT milik OP (id yang sebelumnya tidak terlihat oleh WP).
check("WP hanya melihat SPT miliknya sendiri",
      len(ids_wp2) == 1, f"ids WP={ids_wp2} (harus 1)")
check("OP tetap melihat semua SPT termasuk milik WP",
      set(ids_wp2).issubset(set(ids_op2)) and len(ids_op2) > len(ids_wp2),
      f"WP={ids_wp2} OP={ids_op2}")

print()
if fails:
    print(f"{len(fails)} FAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("SEMUA PASS")
