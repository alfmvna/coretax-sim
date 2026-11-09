import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8155"
HERE = os.path.dirname(os.path.abspath(__file__))

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/google/chrome/chrome", args=["--no-sandbox"])
    pg = b.new_context(viewport={"width": 1440, "height": 1000}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.fill('input[name=id]', "2171121009959003")
    pg.fill('input[name=pwd]', "demo123")
    pg.click('button[type=submit]')
    pg.wait_for_load_state("networkidle")

    # dari /faktur, klik nav "SPT" -> harus ke /spt
    pg.goto(BASE + "/faktur", wait_until="networkidle")
    pg.click('.mainnav a:has-text("SPT")')
    pg.wait_for_load_state("networkidle")
    print("klik SPT dari /faktur ->", pg.url)
    print("  judul:", pg.title())

    pg.screenshot(path=os.path.join(HERE, "shot-nav-spt.png"), full_page=True)

    # dari /spt, klik nav "e-Faktur"
    pg.click('.mainnav a:has-text("e-Faktur")')
    pg.wait_for_load_state("networkidle")
    print("klik e-Faktur dari /spt ->", pg.url)

    # dari /spt, klik sidebar "Faktur Pajak"? (tidak ada) -> klik nav "Buku Besar"
    pg.click('.mainnav a:has-text("Buku Besar")')
    pg.wait_for_load_state("networkidle")
    print("klik Buku Besar ->", pg.url)

    # klik link di breadcrumb/tab
    pg.goto(BASE + "/spt", wait_until="networkidle")
    print("sidebar SPT aktif:", pg.eval_on_selector_all(
        '.side-link.active', "els=>els.map(e=>e.textContent.trim())"))
    print("nav aktif:", pg.eval_on_selector_all(
        '.nav-link.active', "els=>els.map(e=>e.textContent.trim())"))

    print("JS errors:", errs if errs else "none")
    b.close()
print("done")
