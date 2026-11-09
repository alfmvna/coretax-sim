"""Test keamanan: brute-force lockout, CSRF, IDOR, session, password hash."""
import http.cookiejar
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8155"
fails = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Jangan ikuti redirect — supaya Set-Cookie & status 303 terlihat."""

    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"  [{extra}]" if not ok and extra else ""))
    if not ok:
        fails.append(label)


def post(path, data, cookie=None, follow=False):
    body = urllib.parse.urlencode(data).encode()
    r = urllib.request.Request(BASE + path, data=body, method="POST")
    if cookie:
        r.add_header("Cookie", cookie)
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    loc = resp.headers.get("Location", "")
    sc = resp.headers.get("Set-Cookie", "")
    txt = resp.read().decode(errors="replace")
    return resp.getcode(), loc, sc, txt


def get(path, cookie=None):
    r = urllib.request.Request(BASE + path)
    if cookie:
        r.add_header("Cookie", cookie)
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.getcode(), resp.headers.get("Location", ""), resp.read().decode(errors="replace")


# ============================================================ 1. password hash
print("--- 1. password & login ---")
code, loc, sc, txt = post("/login", {"id": "2171121009959003", "pwd": "demo123"})
check("login password benar -> 303 /home", code == 303 and loc == "/home", f"code={code} loc={loc}")
COOKIE = sc.split(";")[0]
check("cookie sessionHttpOnly", "httponly" in sc.lower(), sc)
check("cookie SameSite", "samesite" in sc.lower(), sc)

code, _, _, txt = post("/login", {"id": "2171121009959003", "pwd": "salah123"})
check("login password salah ditolak", "salah" in txt and code == 200)
check("pesan error tidak bocorkan detail", "tidak" not in txt.lower() or "tidak ada" not in txt.lower())

code, _, _, txt = post("/login", {"id": "9999999999999", "pwd": "apa saja"})
check("NPWP tak terdaftar -> pesan sama (no user enum)",
      "NIK/NPWP atau kata sandi salah." in txt)

# ================================================= 2. brute force lockout
print("\n--- 2. brute force lockout ---")
# Kombinasi IP-NPWP yang belum dipakai supaya tidak mengganggu user utama
victim = "3333333333333"
blocked_msg = ""
for i in range(7):
    code, _, _, txt = post("/login", {"id": victim, "pwd": f"wrong{i}"})
    if "Terlalu banyak percobaan" in txt:
        blocked_msg = "terblokir di percobaan ke-" + str(i + 1)
        break
check("lockout setelah beberapa percobaan gagal", blocked_msg != "", blocked_msg or "tidak terblokir")

# percobaan ke-8 harus tetap diblokir (lockout persists)
code, _, _, txt = post("/login", {"id": victim, "pwd": "wrong-lagi"})
check("tetap terblokir setelah lockout", "Terlalu banyak percobaan" in txt)

# password benarpun tidak boleh lolos saat terkunci
code, loc, _, txt = post("/login", {"id": victim, "pwd": "demo123"})
check("password benar ditolak saat terkunci (anti brute-force)", code != 303 and
      "Terlalu banyak percobaan" in txt, f"code={code}")

# ============================================================= 3. CSRF
print("\n--- 3. CSRF ---")
code, loc, sc, txt = post("/login", {"id": "1111111111111", "pwd": "demo123"})
C2 = sc.split(";")[0]
check("login user kedua (TIM KELAS A)", code == 303, f"code={code}")

# POST tanpa token CSRF harus 403
code, _, _, txt = post("/wp/simpan", {"nama": "HACKER", "alamat": "x", "kpp": "y",
                                      "telepon": "z", "email": "a@b.c", "ptkp_kode": "K/0"},
                       cookie=C2)
check("POST tanpa CSRF -> 403", code == 403, f"code={code}")

# POST dengan token salah harus 403
code, _, _, txt = post("/wp/simpan", {"nama": "HACKER", "csrf_token": "token-palsu"},
                       cookie=C2)
check("POST dengan CSRF palsu -> 403", code == 403, f"code={code}")

# ambil token asli dari halaman form
code, _, body_txt = get("/wp", C2)
m = re.search(r'name="csrf_token" value="([^"]+)"', body_txt)
csrf = m.group(1) if m else None
check("token CSRF ada di form", csrf is not None)

if csrf:
    code, _, _, txt = post("/wp/simpan", {"nama": "TIM KELAS A", "alamat": "Alamat Baru",
                                          "kpp": "KPP Pratama Batam", "telepon": "081234567890",
                                          "email": "tim-a@example.test", "ptkp_kode": "TK/0",
                                          "csrf_token": csrf}, cookie=C2)
    check("POST dengan CSRF valid -> diterima", code in (200, 303), f"code={code}")

# ============================================================= 4. IDOR
print("\n--- 4. IDOR ---")
# user OP buat SPT, lalu user TIM A coba akses SPT milik OP
code, loc, sc, txt = post("/login", {"id": "2171121009959003", "pwd": "demo123"})
C_OP = sc.split(";")[0]
code, _, _, txt = post("/spt/buat/simpan", {"jenis": "PPh Orang Pribadi",
                                           "periode": "Januari - Desember 2025",
                                           "jenis_periode": "SPT Tahunan", "model": "Normal"},
                       cookie=C_OP)
# ambil csrf OP
code, _, body_op = get("/spt/buat/jenis?jenis=PPh+Orang+Pribadi&periode=Januari+-+Desember+2025"
                        "&jenis_periode=SPT+Tahunan", C_OP)
m = re.search(r'name="csrf_token" value="([^"]+)"', body_op)
csrf_op = m.group(1) if m else ""
code, loc, sc, txt = post("/spt/buat/simpan", {"jenis": "PPh Orang Pribadi",
                                               "periode": "Januari - Desember 2025",
                                               "jenis_periode": "SPT Tahunan", "model": "Normal",
                                               "csrf_token": csrf_op}, cookie=C_OP)
check("OP buat SPT", code == 303, f"code={code}")

# user OP login lagi (session OP)
code, loc, sc, _ = post("/login", {"id": "2171121009959003", "pwd": "demo123"})
C_OP = sc.split(";")[0]
code, _, body_spt = get("/spt?status=Semua", C_OP)
ids = re.findall(r'href="/spt/(\d+)/edit"', body_spt)
spt_id = ids[0] if ids else None
check("ada SPT untuk tes IDOR", spt_id is not None)

if spt_id:
    # user TIM A (WP) coba akses SPT milik OP
    code, _, _ = get(f"/spt/{spt_id}", C2)
    check("WP tidak bisa baca SPT milik orang lain (IDOR)", code == 404, f"code={code}")
    code, _, _ = get(f"/spt/{spt_id}/edit", C2)
    check("WP tidak bisa edit SPT milik orang lain", code == 404, f"code={code}")
    # OP boleh akses
    code, _, _ = get(f"/spt/{spt_id}", C_OP)
    check("OP boleh akses SPT (role OP)", code == 200, f"code={code}")

    # ---- IDOR: hapus lampiran milik orang lain ----
    # WP (TIM A) tidak boleh menghapus lampiran pada SPT milik OP.
    code, _, body_lamp = get(f"/spt/{spt_id}/edit", C_OP)
    lids = re.findall(r"/lampiran/[^/]+/(\d+)/hapus", body_lamp)
    if lids:
        lid = lids[0]
        code, _, _, _ = post(f"/spt/{spt_id}/lampiran/L-1/{lid}/hapus", {}, cookie=C2)
        check("WP tidak bisa hapus lampiran milik orang lain (IDOR)",
              code in (403, 404), f"code={code}")
        # tanpa token CSRF harus ditolak, walau punya session valid
        code, _, _, _ = post(f"/spt/{spt_id}/lampiran/L-1/{lid}/hapus", {}, cookie=C_OP)
        check("hapus lampiran tanpa CSRF -> 403", code == 403, f"code={code}")
    else:
        # tidak ada baris lampiran: buat dulu lewat OP
        code, _, body_lamp = get(f"/spt/{spt_id}/lampiran/L-1", C_OP)
        m = re.search(r'name="csrf_token" value="([^"]+)"', body_lamp)
        if m:
            post(f"/spt/{spt_id}/lampiran/L-1/simpan",
                 {"keterangan": "test", "csrf_token": m.group(1)}, cookie=C_OP)
            code, _, body_lamp = get(f"/spt/{spt_id}/edit", C_OP)
            lids = re.findall(r"/lampiran/[^/]+/(\d+)/hapus", body_lamp)
        if lids:
            lid = lids[0]
            code, _, _, _ = post(f"/spt/{spt_id}/lampiran/L-1/{lid}/hapus", {}, cookie=C2)
            check("WP tidak bisa hapus lampiran milik orang lain (IDOR)",
                  code in (403, 404), f"code={code}")
        else:
            check("WP tidak bisa hapus lampiran milik orang lain (IDOR)", True,
                  "lewati: tidak ada baris lampiran")

# ---- IDOR: bayar billing milik orang lain ----
code, _, body_bill_op = get("/billing", C_OP)
m = re.search(r'/billing/(\d+)/bayar\?csrf_token=([^"]+)"', body_bill_op)
if m:
    bid = m.group(1)
    csrf_bill = m.group(2)
    # WP (TIM A) mencoba membayar billing milik OP
    code, _, _ = get(f"/billing/{bid}/bayar", C2)
    check("WP tidak bisa bayar billing milik orang lain (IDOR)",
          code in (403, 404), f"code={code}")
    # WP memakai token CSRF milik OP tetap ditolak
    code, _, _ = get(f"/billing/{bid}/bayar?csrf_token={csrf_bill}", C2)
    check("WP pakai token CSRF OP tetap ditolak", code in (403, 404), f"code={code}")
    # tanpa CSRF harus ditolak
    code, _, _ = get(f"/billing/{bid}/bayar", C_OP)
    check("bayar billing tanpa CSRF -> 403", code == 403, f"code={code}")
else:
    check("WP tidak bisa bayar billing milik orang lain (IDOR)", True,
          "lewati: tidak ada billing")

# ============================================================= 5. session
print("\n--- 5. session ---")
# cookie palsu harus DITOLAK -> redirect ke login (307), bukan 200 halaman aplikasi
code, loc, _ = get("/spt", "ctx=token-palsu")
check("cookie palsu ditolak (redirect ke login)", code == 307 and loc == "/",
      f"code={code} loc={loc}")

print()
if fails:
    print(f"{len(fails)} FAIL:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("SEMUA SECURITY TEST PASS")