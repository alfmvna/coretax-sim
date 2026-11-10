"""Verifikasi manual: IDOR + CSRF pada route GET yang mengubah state.

Skenario:
 1. OP buat SPT, isi, submit via billing -> ada billing 'Belum Dibayar'
 2. OP coba bayar TANPA token CSRF -> harus 403
 3. WP (TIM A) coba bayar billing milik OP -> harus 403/404
 4. OP bayar DENGAN token CSRF -> harus 303 (diterima)
 5. WP coba hapus lampiran milik OP -> harus 403/404
"""
import re
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
    code, loc, sc, _ = post("/login", {"id": npwp, "pwd": "demo123"})
    return sc.split(";")[0] if sc else None


def csrf_from(body):
    m = re.search(r'name="csrf_token" value="([^"]+)"', body)
    return m.group(1) if m else None


OP = login("2171121009959003")
WP = login("1111111111111")
check("login OP & WP", OP and WP)

# --- 1. OP buat SPT ---
body = get("/spt/buat/jenis?jenis=PPh+Orang+Pribadi&periode=Januari+-+Desember+2025"
           "&jenis_periode=SPT+Tahunan", OP)[1]
tok = csrf_from(body)
code, loc, _, _ = post("/spt/buat/simpan", {"jenis": "PPh Orang Pribadi",
                                           "periode": "Januari - Desember 2025",
                                           "jenis_periode": "SPT Tahunan",
                                           "model": "Pembetulan" if "<option>Pembetulan</option>" in body else "Normal",
                                           "csrf_token": tok}, OP)
check("OP buat SPT", code == 303, f"code={code}")

body = get("/spt?status=Semua", OP)[1]
ids = re.findall(r'href="/spt/(\d+)/edit"', body)
spt_id = ids[0] if ids else None
check("SPT ada", spt_id is not None)
if not spt_id:
    print("gagal: tidak ada SPT")
    raise SystemExit(1)

# --- 2. isi form supaya PPh terutang > 0, lalu tanda tangan + submit via billing ---
# SPT kosong => kurang_bayar 0 => tidak ada kode billing yang dibuat.
form_body = get(f"/spt/{spt_id}/edit", OP)[1]
tok = csrf_from(form_body)
fields = dict(re.findall(r'name="([^"]+)"[^>]*value="([^"]*)"', form_body))
fields = {k: v for k, v in fields.items() if k != "csrf_token"}
# Penghasilan neto (q_2) 600 juta => PPh terutang > 0 => ada kode billing.
# Field penghasilan pada form SPT OP bernama q_2 (jumlah penghasilan neto).
fields["q_2"] = "600000000"
fields["csrf_token"] = tok
code, _, _, _ = post(f"/spt/{spt_id}/simpan", fields, OP)
check("simpan draft SPT", code in (200, 303), f"code={code}")

body = get(f"/spt/{spt_id}/tt", OP)[1]
tok = csrf_from(body)
code, _, _, _ = post(f"/spt/{spt_id}/tt/simpan", {"csrf_token": tok}, OP)
check("tanda tangan", code in (200, 303), f"code={code}")

code, _, _, _ = post(f"/spt/{spt_id}/submit", {"metode": "billing", "csrf_token": tok}, OP)
check("submit via billing", code in (200, 303), f"code={code}")

# --- 3. billing milik OP harus muncul ---
body = get("/billing", OP)[1]
m = re.search(r'/billing/(\d+)/bayar', body)
check("billing unpaid milik OP terdaftar", m is not None)
if not m:
    print("gagal: tidak ada billing untuk dibayar")
    raise SystemExit(1)
bid = m.group(1)

# token CSRF dari link bayar
csrf_link = re.search(r'csrf_token=([^"&]+)', body)
csrf_link = csrf_link.group(1) if csrf_link else ""

# --- 4. OP bayar TANPA CSRF -> 403 ---
code, _ = get(f"/billing/{bid}/bayar", OP)
check("bayar tanpa CSRF -> 403", code == 403, f"code={code}")

# --- 5. WP bayar billing milik OP -> 403/404 ---
code, _ = get(f"/billing/{bid}/bayar", WP)
check("WP bayar billing milik OP ditolak (IDOR)", code in (403, 404), f"code={code}")

# --- 6. WP dengan CSRF OP juga tetap ditolak (token bukanMiliknya) ---
code, _ = get(f"/billing/{bid}/bayar?csrf_token={csrf_link}", WP)
check("WP pakai token CSRF OP tetap ditolak", code in (403, 404), f"code={code}")

# --- 7. OP bayar DENGAN CSRF -> diterima ---
code, _ = get(f"/billing/{bid}/bayar?csrf_token={csrf_link}", OP)
check("OP bayar dengan CSRF -> diterima", code in (200, 303), f"code={code}")

# --- 8. IDOR hapus lampiran ---
# Link hapus memuat kode lampiran ber-sub-bagian (mis. L-1|E|1) yang mengandung
# karakter '|', jadi regex harus toleran terhadap karakter non-slash.
# Baris lampiran hanya ada di SPT yang memang punya data (mis. dari seed).
# Cari SPT pertama yang halaman editnya punya link hapus.
# kode lampiran memuat '|' (mis. L-1|A|1) -> ambil segmen sebelum /<id>/hapus
lids = []
for cand in re.findall(r'href="/spt/(\d+)/edit"', get("/spt?status=Semua", OP)[1]):
    cand_body = get(f"/spt/{cand}/edit", OP)[1]
    found = re.findall(r"/lampiran/([^/]+)/([^/]+)/([^/]+)/(\d+)/hapus", cand_body)
    if found:
        spt_id = cand
        body = cand_body
        lids = found
        break
check("ada baris lampiran untuk tes", bool(lids))
if lids:
    _k, _b, _s, lid = lids[0]
    base = f"/spt/{spt_id}/lampiran/{_k}/{_b}/{_s}/{lid}/hapus"
    code, _ = get(base, WP)
    check("WP hapus lampiran milik OP ditolak (IDOR)", code in (403, 404), f"code={code}")
    code, _ = get(base, OP)
    check("OP hapus lampiran tanpa CSRF -> 403", code == 403, f"code={code}")
    # dengan CSRF harus diterima
    csrf_h = re.search(re.escape(base) + r"\?csrf_token=([^\"]+)", body)
    if csrf_h:
        code, _ = get(f"{base}?csrf_token={csrf_h.group(1)}", OP)
        check("OP hapus lampiran dengan CSRF -> diterima", code in (200, 303), f"code={code}")
    else:
        check("OP hapus lampiran dengan CSRF -> diterima", False, "link csrf tidak ditemukan")

print()
if fails:
    print(f"{len(fails)} FAIL")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("SEMUA PASS")