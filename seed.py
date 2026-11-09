"""Seed data demo untuk simulator Coretax: faktur, bukti potong, WP, deposit.

Jalankan: python3 seed.py
"""
import json
import models as M
import tax as T

M.init_db()
c = M.conn()
npwp = M.DEFAULT_WP["npwp"]

# --- bersihkan data lama (idempoten)
for tbl in ("e_faktur", "bupot", "billing", "lampiran", "spt", "log"):
    c.execute(f"DELETE FROM {tbl}")

# ---------------------------------------------------------------- e-Faktur
faktur = [
    ("Maret 2026", "PT Sumber Makmur", "3333333333333", "9911", "Paket A", 10, 12_500_000),
    ("Maret 2026", "CV Bintang Sinar", "4444444444444", "9912", "Konsultasi", 3, 8_000_000),
    ("Maret 2026", "Warung Ibu Rina", "", "9913", "Makanan", 20, 750_000),
]
for masa, nama, npwp_beli, kode, nama_barang, jml, harga in faktur:
    total = jml * harga
    dpp = total / 1.11
    ppn = total - dpp
    c.execute("""INSERT INTO e_faktur (npwp_penjual,npwp_pembeli,nama_pembeli,masa_pajak,tahun_pajak,
                 tanggal,tipe,kode_barang,nama_barang,jumlah,harga_satuan,nilai,ppn,ppnbm,status)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (npwp, npwp_beli, nama, masa, "2026", "2026-03-10", "Barang/Jasa", kode, nama_barang,
               jml, harga, dpp, ppn, 0, "Terbit"))

# --------------------------------------------------------------- eBUPOT
# pegawai tetap: 3 orang, PTKP berbeda -> tarif TER berbeda
pegawai = [
    ("Budi Santoso", "1111111111111", "K/0", 12_000_000, 12),
    ("Siti Aminah", "2222222222222", "TK/2", 8_500_000, 12),
    ("Andi Wijaya", "5555555555555", "TK/0", 7_000_000, 12),
]
for nama, npwp_penerima, ptkp, bruto, _ in pegawai:
    h = T.hitung_pph21_bulanan(bruto, ptkp)
    c.execute("""INSERT INTO bupot (npwp_pemotong,npwp_penerima,nama_penerima,masa_pajak,tahun_pajak,
                 jenis,bruto,dpp,pajak,status) VALUES (?,?,?,?,?,?,?,?,?,?)""",
              (npwp, npwp_penerima, nama, "Maret 2026", "2026", "Bukti Potong Bulanan",
               bruto, h["dpp"], h["pajak"], "Terbit"))

# satu bukti potong tidak tetap (harian)
h = T.hitung_pph21_tidak_tetap(9_000_000, 3)
c.execute("""INSERT INTO bupot (npwp_pemotong,npwp_penerima,nama_penerima,masa_pajak,tahun_pajak,
             jenis,bruto,dpp,pajak,status) VALUES (?,?,?,?,?,?,?,?,?,?)""",
          (npwp, "6666666666666", "Rina Consultant", "Maret 2026", "2026",
           "Bukti Potong Tidak Tetap", 9_000_000, h["dpp"], h["pajak"], "Terbit"))

# -------------------------------------------------------------- deposit
c.execute("UPDATE deposit SET saldo=? WHERE npwp=?", (150_000_000, npwp))

# -------------------------------------------------- SPT demo (sudah terisi)
# SPT Tahunan PPh OP 2025: penghasilan neto 600 jt, kredit pajak 50 jt.
import tax as T

spt_data = {
    "tahun_pajak": "2025", "periode_akuntansi": "Januari - Desember 2025",
    "status_spt": "Normal", "jenis_pembukuan": "Pembukuan Stelsel Akrual",
    "sumber_penghasilan": "Pekerjaan",
    "npwp": npwp, "nama": M.DEFAULT_WP["nama"], "telepon": M.DEFAULT_WP["telepon"],
    "email": M.DEFAULT_WP["email"], "status_kewajiban": M.DEFAULT_WP["status"],
    "npwp_pasangan": "",
    "q_1a": "Ya", "q_1b1": "Tidak", "q_1b2": "Tidak", "q_1b3": "Tidak",
    "q_1b4": "", "q_1c": "Tidak", "q_1d": "Tidak",
    "q_2": "600000000", "q_3": "Tidak", "pengurang_neto": "0",
    "q_8": "Tidak", "pengurang_pph": "0",
    "q_10a": "Ya", "q_10b": "12000000", "q_10c": "0", "q_10d": "Tidak",
    "kredit_pajak": "50000000",
    "q_11b": "Tidak", "nilai_pengangsuran": "0",
    "q_13a": "Ya", "q_13b": "Tidak", "q_13c": "Tidak",
    "q_14a": "450000000", "q_14b": "Ya", "q_14c": "Tidak", "q_14d": "Ya",
    "q_14e": "Ya", "q_14f": "Tidak", "q_14g": "Tidak", "q_14h": "0",
    "jabatan_penandatangan": "Pemilik",
    "pernyataan": "Saya menyatakan bahwa SPT ini lengkap dan benar.",
}
ptkp = T.PTKP[M.DEFAULT_WP["ptkp_kode"]]
neto = 600_000_000
pkp = neto - ptkp
pph = T.hitung_pasal17(pkp)
# Kredit pajak = bukti potong dari lampiran L-1 bagian E (24jt + 26jt = 50jt)
bukti_potong = 50_000_000
kurang = pph - bukti_potong
hitung = {"neto": neto, "pengurang_neto": 0.0, "neto_setelah": neto, "ptkp": ptkp,
          "pkp": pkp, "pph_terutang": pph, "pengurang_pph": 0.0, "pph_setelah": pph,
          "kredit_pajak": bukti_potong, "kurang_bayar": kurang, "pengangsuran": 0.0,
          "masih_bayar": kurang, "status": "Kurang Bayar",
          "angsuran_pph25": T.angsuran_pph25(pph, 12)}

cur = c.execute("""INSERT INTO spt (npwp,jenis_pajak,jenis_spt,masa_pajak,tahun_pajak,periode,
                    status_spt,status_tabel,kanal,tgl_jatuh_tempo,tgl_dibuat,kurang_bayar,
                    lebih_bayar,tanda_tangan,data,hitung)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (npwp, "PPh Orang Pribadi", "SPT Tahunan PPh Wajib Pajak Orang Pribadi",
                  "Januari - Desember 2025", "2025", "Januari - Desember 2025", "Normal",
                  "Konsep SPT", "Web", "2026-04-30", M.now(), kurang, 0, 1,
                  json.dumps(spt_data), json.dumps(hitung)))
demo_spt_id = cur.lastrowid

# lampiran L-1 bagian A: kas & setara kas
c.execute("INSERT INTO lampiran (spt_id,kode,sub,no,data) VALUES (?,?,?,?,?)",
          (demo_spt_id, "L-1|A|1", "1", 1, json.dumps({
              "description": "Tabungan (Bank/Lembaga Keuangan)", "code": "CASH01",
              "account_number": "1234567890", "on_behalf_of": "ALLIF MAULANA",
              "bank_name": "Bank Contoh", "country": "Indonesia",
              "year_acquisition": "2020", "balance": "150000000", "remark": ""})))
# lampiran L-1 bagian E: bukti potong dari kantor
for i, (npwp_p, nama, bruto, pajak) in enumerate([
        ("1111111111111", "PT Contoh-indicator", 480_000_000, 24_000_000),
        ("2222222222222", "CV Rekan Kerja", 120_000_000, 26_000_000)], 1):
    c.execute("INSERT INTO lampiran (spt_id,kode,sub,no,data) VALUES (?,?,?,?,?)",
              (demo_spt_id, "L-1|E|1", "1", i, json.dumps({
                  "no_bupot": f"BPA1-2025-{i:03d}", "npwp": npwp_p, "name": nama,
                  "gross_income": bruto, "withholding_tax": pajak})))

# SPT Masa PPh 21/26 demo
bupot_total = 847_500
c.execute("""INSERT INTO spt (npwp,jenis_pajak,jenis_spt,masa_pajak,tahun_pajak,periode,
             status_spt,status_tabel,kanal,tgl_jatuh_tempo,tgl_dibuat,kurang_bayar,
             lebih_bayar,tanda_tangan,data,hitung)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (npwp, "PPh Pasal 21/26", "SPT Masa PPh Pasal 21/26", "Maret 2026", "2026",
           "Maret 2026", "Normal", "Konsep SPT", "Web", "2026-04-10", M.now(),
           bupot_total, 0, 0, json.dumps({
               "npwp_pemotong": npwp, "nama_pemotong": M.DEFAULT_WP["nama"],
               "jabatan_penandatangan": "Pemilik", "jumlah_bupot": "4",
               "total_bruto": "36500000", "total_dpp": "36500000",
               "total_pajak": str(bupot_total), "pajak_ditanggung": "0",
               "masa_pajak": "Maret 2026", "tahun_pajak": "2026", "status_spt": "Normal",
               "keterangan": "Bukti potong 4 pegawai"}),
           json.dumps({"total_bruto": 36500000.0, "total_dpp": 36500000.0,
                       "total_pajak": bupot_total, "pajak_ditanggung": 0.0,
                       "kurang_bayar": bupot_total, "status": "Kurang Bayar"})))

c.commit()
c.close()

# ------------------------------------------------------------ ringkasan
c = M.conn()
print("faktur:", c.execute("SELECT COUNT(*) n FROM e_faktur").fetchone()["n"])
print("bupot:", c.execute("SELECT COUNT(*) n FROM bupot").fetchone()["n"])
print("total PPN keluar: Rp", round(c.execute("SELECT SUM(ppn) v FROM e_faktur").fetchone()["v"]))
print("total PPh dipotong: Rp", round(c.execute("SELECT SUM(pajak) v FROM bupot").fetchone()["v"]))
for r in c.execute("SELECT nama_penerima,bruto,pajak FROM bupot"):
    print(f"  - {r['nama_penerima']}: bruto {r['bruto']:,.0f} pajak {r['pajak']:,.0f}")
c.close()