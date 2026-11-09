import os, sqlite3, re
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8155"
HERE = os.path.dirname(os.path.abspath(__file__))
db = sqlite3.connect(os.path.join(HERE, "data", "coretax.db"))
sid = db.execute("SELECT id FROM spt WHERE jenis_pajak='PPh Orang Pribadi' "
                 "AND json_extract(data,'$.q_2') IS NOT NULL "
                 "AND json_extract(data,'$.q_2') != '' ORDER BY id DESC LIMIT 1").fetchone()[0]
db.close()

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/google/chrome/chrome", args=["--no-sandbox"])
    pg = b.new_context(viewport={"width": 1440, "height": 1200}).new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))

    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.fill('input[name=id]', "2171121009959003")
    pg.fill('input[name=pwd]', "demo123")
    pg.click('button[type=submit]')
    pg.wait_for_load_state("networkidle")

    pg.goto(f"{BASE}/spt/{sid}/edit", wait_until="networkidle")
    pg.screenshot(path=os.path.join(HERE, "shot-edit.png"), full_page=True)

    def calc(label):
        el = pg.evaluate("""(lab)=>{
            let r=null;
            document.querySelectorAll('.rov.calc').forEach(e=>{
              const l=e.parentElement&&e.parentElement.querySelector('label');
              if(l&&l.textContent.trim()===lab) r=e.textContent.trim();});
            return r;}""", label)
        return el

    print("BEFORE q_2=600jt -> q_7 (PPh terutang):", calc("PPh terutang"))
    print("BEFORE q_11c:", calc("PPh yang masih harus dibayar (11a-11b)"))

    pg.fill('[name=q_2]', '800000000')
    pg.wait_for_timeout(400)
    print("AFTER  q_2=800jt -> q_7 (PPh terutang):", calc("PPh terutang"))
    print("AFTER  q_11c:", calc("PPh yang masih harus dibayar (11a-11b)"))

    # cek ringkasan (.sum-row) ikut berubah
    sums = pg.evaluate("""()=>[...document.querySelectorAll('.sum-row')].map(r=>
        (r.querySelector('span')||{}).textContent+' = '+(r.querySelector('b')||{}).textContent)""")
    for s in sums[:12]:
        print("SUM:", s)

    pg.screenshot(path=os.path.join(HERE, "shot-edit-live.png"), full_page=True)
    print("JS errors:", errs[:5] if errs else "none")
    b.close()
