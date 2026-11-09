import os
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8155"
import sqlite3
_db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coretax.db"))
_op = _db.execute("SELECT id FROM spt WHERE jenis_pajak='PPh Orang Pribadi' ORDER BY id DESC LIMIT 1").fetchone()[0]
_db.close()

shots = [
    ("login", "/", None),
    ("spt-dashboard", "/spt", None),
    ("spt-wizard", "/spt/buat", None),
    ("spt-detail", f"/spt/{_op}", None),
    ("spt-edit", f"/spt/{_op}/edit", None),
    ("spt-tt", f"/spt/{_op}/tt", None),
    ("billing", "/billing", None),
    ("buku-besar", "/buku-besar", None),
]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/google/chrome/chrome", args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.fill('input[name=id]', "2171121009959003")
    pg.fill('input[name=pwd]', "demo123")
    pg.click('button[type=submit]')
    pg.wait_for_load_state("networkidle")
    print("after login:", pg.url)

    for name, path, _ in shots:
        pg.goto(BASE + path, wait_until="networkidle")
        pg.screenshot(path=f"shot-{name}.png", full_page=True)
        print("shot", name, "->", pg.url)

    ctx.close()
    b.close()
print("done")