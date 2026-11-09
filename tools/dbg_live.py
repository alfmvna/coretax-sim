import os, sqlite3
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8155"
HERE = os.path.dirname(os.path.abspath(__file__))
db = sqlite3.connect(os.path.join(HERE, "data", "coretax.db"))
db.row_factory = sqlite3.Row
sid = db.execute("SELECT id FROM spt WHERE jenis_pajak='PPh Orang Pribadi' ORDER BY id DESC LIMIT 1").fetchone()["id"]
db.close()

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/google/chrome/chrome", args=["--no-sandbox"])
    pg = b.new_context(viewport={"width": 1440, "height": 1200}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("CONSOLE " + m.type + ": " + m.text) if m.type == "error" else None)

    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.fill('input[name=id]', "2171121009959003")
    pg.fill('input[name=pwd]', "demo123")
    pg.click('button[type=submit]')
    pg.wait_for_load_state("networkidle")
    pg.goto(f"{BASE}/spt/{sid}/edit", wait_until="networkidle")

    print("body data-ptkp:", pg.evaluate("document.body.dataset.ptkp"))
    print("q_2 value:", pg.evaluate("(document.querySelector('[name=q_2]')||{}).value"))
    print("kredit_dipotong:", pg.evaluate("(document.querySelector('[name=kredit_dipotong]')||{}).value"))
    print("calc count:", pg.evaluate("document.querySelectorAll('.rov.calc').length"))
    print("sum count:", pg.evaluate("document.querySelectorAll('.sum-row').length"))
    print("q_7 text:", pg.evaluate("""()=>{let r=null;document.querySelectorAll('.rov.calc').forEach(e=>{
        const l=e.parentElement&&e.parentElement.querySelector('label');
        if(l&&l.textContent.trim()==='PPh terutang') r=e.textContent.trim();});return r;}"""))
    print("errors:", errs[:6])
    b.close()
