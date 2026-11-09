"""Cek presisi: berapa baris nyata (bukan keyword) yang dilihat WP vs OP."""
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8140"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


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

for label, path, rowre in [
    ("SPT    ", "/spt?status=Semua", r'href="/spt/(\d+)/edit"'),
    ("Faktur ", "/faktur", r"<td>(\d+)</td>"),
    ("Bupot  ", "/bupot", r"<td>([^<]*)</td><td>([^<]*)</td>"),
]:
    _, bo = get(path, OP)
    _, bw = get(path, WP)
    print(f"{label} OP: {re.findall(rowre, bo)[:6]}")
    print(f"{label} WP: {re.findall(rowre, bw)[:6]}")
    print()

# Cek billing
_, bo = get("/billing", OP)
print("billing OP keyword:", "Belum Dibayar" in bo, "Lunas" in bo)
_, bw = get("/billing", WP)
print("billing WP keyword:", "Belum Dibayar" in bw, "Lunas" in bw)
m = re.search(r"kode_billing|spt_id", bo)
print("billing OP isi:", re.findall(r"<td>(\d{10,})</td>", bo))
