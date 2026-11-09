import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8140"


class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OP = urllib.request.build_opener(NR)


def post(p, d, c=None):
    r = urllib.request.Request(BASE + p, data=urllib.parse.urlencode(d).encode(), method="POST")
    if c:
        r.add_header("Cookie", c)
    try:
        x = OP.open(r)
    except urllib.error.HTTPError as e:
        x = e
    return x.getcode(), x.headers.get("Set-Cookie", "")


def get(p, c=None):
    r = urllib.request.Request(BASE + p)
    if c:
        r.add_header("Cookie", c)
    try:
        x = OP.open(r)
    except urllib.error.HTTPError as e:
        x = e
    return x.getcode(), x.read().decode(errors="replace")


code, sc = post("/login", {"id": "2171121009959003", "pwd": "demo123"})
C = sc.split(";")[0]
code, body = get("/spt/1/edit", C)
print("status", code)
i = body.find("Lampiran SPT")
print(body[i:i + 2200])
