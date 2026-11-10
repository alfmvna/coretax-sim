"""Uji navigasi: semua link nav atas harus berpindah modul dengan benar."""
import urllib.parse
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8155"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None

OPENER = urllib.request.build_opener(NoRedirect)
fails = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else f"  [{extra}]"))
    if not ok:
        fails.append(label)


def req(path, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(BASE + path, data=body,
                               method="POST" if data else "GET")
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.status, resp.headers.get("Location", ""), resp.headers.get("Set-Cookie", "")


def get(path, cookie):
    r = urllib.request.Request(BASE + path)
    r.add_header("Cookie", cookie)
    try:
        resp = OPENER.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.status, resp.headers.get("Location", ""), resp.read().decode("utf-8", "ignore")


# login
code, _, sc = req("/login", {"id": "2171121009959003", "pwd": "demo123"})
cookie = sc.split(";")[0]
check("login", "ctx=" in cookie, cookie)

# --- 1. link lama ?modul=X dari halaman modul lain harus redirect ke path modul
for modul, tujuan in [("SPT", "/spt"), ("e-Faktur", "/faktur"), ("eBUPOT", "/bupot"),
                      ("Pembayaran", "/billing"), ("Buku Besar", "/buku-besar"),
                      ("Portal Saya", "/home"), ("Layanan WP", "/layanan"),
                      ("Manajemen Akses", "/akses")]:
    code, loc, _ = get(f"/faktur?modul={urllib.parse.quote(modul)}", cookie)
    check(f"link lama /faktur?modul={modul} -> {tujuan}", code == 303 and loc == tujuan,
          f"code={code} loc={loc}")

# --- 2. nav atas di HTML harus absolut, tidak '?modul='
code, _, body = get("/spt", cookie)
check("nav atas tanpa ?modul=", "?modul=" not in body)
check("nav atas ada href=/spt", 'href="/spt"' in body)

# --- 3. semua modul reachable dan berisi nav
for modul, tujuan in [("SPT", "/spt"), ("e-Faktur", "/faktur"), ("eBUPOT", "/bupot"),
                      ("Pembayaran", "/billing"), ("Buku Besar", "/buku-besar"),
                      ("Layanan WP", "/layanan"), ("Manajemen Akses", "/akses")]:
    code, _, body = get(tujuan, cookie)
    ok = code == 200 and "CORETAX" in body
    check(f"{tujuan} terbuka", ok, f"code={code}")
    # link nav modul ini harus ada di nav atas
    check(f"  nav menuju {tujuan}", f'href="{tujuan}"' in body)

# --- 4. klik nav dari /faktur harus benar-benar pindah (simulasi klik)
code, _, body = get("/faktur", cookie)
import re
links = re.findall(r'<a href="([^"]+)" class="nav-link', body)
expected = ["/home", "/faktur", "/bupot", "/spt", "/billing", "/buku-besar",
            "/layanan", "/akses"]
check("nav link semua absolut & lengkap",
      links == expected, f"dapat {links}")

print()
if fails:
    print(f"{len(fails)} FAIL:")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("SEMUA NAV PASS")
