import re, sys, urllib.parse, urllib.request, urllib.error
BASE = "http://127.0.0.1:8140"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
OP = urllib.request.build_opener(NoRedirect)

COOKIE = ""
def open_req(url, data=None, method=None, follow=True):
    r = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    if COOKIE: r.add_header("Cookie", COOKIE)
    op = urllib.request.urlopen if follow else OP.open
    try: resp = op(r)
    except urllib.error.HTTPError as e: resp = e
    return resp

r = open_req(BASE + "/login", urllib.parse.urlencode({"id":"2171121009959003","pwd":"demo"}).encode(), follow=False)
COOKIE = r.headers.get("Set-Cookie","").split(";")[0]

def g(p):
    resp = open_req(BASE+p)
    return resp.getcode(), resp.read().decode(errors="replace")

def p(path, data):
    resp = open_req(BASE+path, urllib.parse.urlencode(data).encode())
    return resp.getcode(), resp.read().decode(errors="replace")

print("=== /faktur")
c, b = g("/faktur"); print(c); print(b[:1200])
print("\n=== PPh21 buat")
c, b = p("/spt/buat/simpan", {"jenis":"PPh Pasal 21/26","periode":"Maret 2026","jenis_periode":"SPT Masa","model":"Normal"})
print(c); print(b[:900])
print("\n=== lampiran L-1/A/1")
c, b = g("/spt/1/lampiran/L-1/A/1"); print(c); print(b[:600])
print("\n=== lampiran L-1?sub1=A&sub2=1")
c, b = g("/spt/1/lampiran/L-1?sub1=A&sub2=1"); print(c); print(b[:600])
