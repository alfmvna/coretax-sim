"""Self-check engine pajak. Jalankan: python3 test_tax.py"""
import tax as T

fails = []


def eq(name, got, want, tol=1.0):
    if isinstance(want, str) or isinstance(got, str):
        ok = got == want
    else:
        ok = abs(got - want) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got} want={want}")
    if not ok:
        fails.append(name)


# --- num parsing
eq("num ribuan titik", T.num("1.234.567"), 1234567)
eq("num ribuan koma", T.num("1,234,567"), 1234567)
eq("num desimal koma", T.num("1.234.567,89"), 1234567.89)
eq("num desimal titik", T.num("1234.56"), 1234.56)
eq("num float", T.num(1234.5), 1234.5)
eq("num kosong", T.num("", 0), 0)

# --- Pasal 17 progresif
eq("P17 50jt @5%", T.hitung_pasal17(50_000_000), 2_500_000)
eq("P17 100jt", T.hitung_pasal17(100_000_000), 3_000_000 + 6_000_000)
eq("P17 300jt", T.hitung_pasal17(300_000_000),
   3_000_000 + 28_500_000 + 12_500_000)
eq("P17 0", T.hitung_pasal17(0), 0)
eq("P17 6bn", T.hitung_pasal17(6_000_000_000),
   3_000_000 + 28_500_000 + 62_500_000 + 1_350_000_000 + 350_000_000)

# --- tarif marginal Pasal 17
eq("tarif 50jt", T.tarif_pasal17(50_000_000), 0.05)
eq("tarif 100jt", T.tarif_pasal17(100_000_000), 0.15)
eq("tarif 300jt", T.tarif_pasal17(300_000_000), 0.25)
eq("tarif 1M", T.tarif_pasal17(1_000_000_000), 0.30)
eq("tarif 6bn", T.tarif_pasal17(6_000_000_000), 0.35)

# --- TER bulanan kategori A (TK/0)
eq("TER A bruto 5jt -> 0%", T.hitung_pph21_bulanan(5_000_000, "TK/0")["pajak"], 0)
eq("TER A bruto 15,1jt -> 7%", T.hitung_pph21_bulanan(15_100_000, "TK/0")["pajak"],
   1_057_000)
eq("TER A bruto 15,1jt tarif", T.hitung_pph21_bulanan(15_100_000, "TK/0")["tarif"], "7%")
eq("TER A bruto 5,4jt -> 0%", T.hitung_pph21_bulanan(5_400_000, "TK/0")["pajak"], 0)
eq("TER A bruto 5,65jt -> 0,25%", T.hitung_pph21_bulanan(5_650_000, "TK/0")["pajak"], 14_125)

# --- TER kategori B/C untuk income sama -> tarif lebih rendah
eq("TER B 15,1jt tarif", T.hitung_pph21_bulanan(15_100_000, "TK/2")["tarif"], "6%")
eq("TER C 15,1jt tarif", T.hitung_pph21_bulanan(15_100_000, "K/3")["tarif"], "7%")

# --- TER harian
eq("TER harian 400rb -> 0%", T.hitung_pph21_harian(400_000)["pajak"], 0)
eq("TER harian 1jt -> 0,5%", T.hitung_pph21_harian(1_000_000)["pajak"], 5_000)

# --- pegawai tidak tetap: harian > 2,5jt -> Pasal 17 x 50%; <= 2,5jt -> TER harian
r = T.hitung_pph21_tidak_tetap(9_000_000, 3)
eq("tidak tetap harian 3jt/hari, DPP 50%", r["dpp"], 1_500_000)
eq("tidak tetap pajak", r["pajak"], 75_000)
r = T.hitung_pph21_tidak_tetap(500_000, 1)
eq("tidak tetap <=2,5jt pakai TER harian", r["metode"], "TER Harian")
eq("tidak tetap <=2,5jt pajak", r["pajak"], 2_500)
r = T.hitung_pph21_tidak_tetap(450_000, 1)
eq("tidak tepat <=450rb tarif 0%", r["pajak"], 0)

# --- bukan pegawai: 50% x Pasal 17
r = T.hitung_pph21_bukan_pegawai(100_000_000)
eq("bukan pegawai DPP", r["dpp"], 50_000_000)
eq("bukan pegawai pajak", r["pajak"], 2_500_000)

# --- masa terakhir: 600jt setahun, TK/0 -> PKP 546jt
r = T.hitung_pph21_masa_terakhir(600_000_000, "TK/0")
eq("masa terakhir PKP", r["pkp"], 546_000_000)
eq("masa terakhir pajak", r["pajak"], 3_000_000 + 28_500_000 + 62_500_000 + 13_800_000)

# --- PPh OP tahunan: neto 600jt, TK/0
r = T.hitung_pph_op_tahunan(600_000_000, "TK/0")
eq("OP PKP", r["pkp"], 546_000_000)
eq("OP PPh terutang", r["pph_terutang"], 3_000_000 + 28_500_000 + 62_500_000 + 13_800_000)
eq("OP status", T.hitung_pph_op_tahunan(600_000_000, "TK/0")["status"], "Kurang Bayar")
eq("OP nihil", T.hitung_pph_op_tahunan(50_000_000, "TK/0")["status"], "Nihil")
eq("OP lebih bayar", T.hitung_pph_op_tahunan(600_000_000, "TK/0", kredit_pajak=200_000_000)["status"], "Lebih Bayar")
eq("OP kurang bayar setelah kredit",
   T.hitung_pph_op_tahunan(600_000_000, "TK/0", kredit_pajak=50_000_000)["kurang_bayar"],
   3_000_000 + 28_500_000 + 62_500_000 + 13_800_000 - 50_000_000)

# --- PPN: 11% non-software, 12% mewah
r = T.hitung_ppn(100_000_000, 40_000_000)
eq("PPN keluar 11%", r["ppn_keluar"], 11_000_000)
eq("PPN masuk 11%", r["ppn_masuk"], 4_400_000)
eq("PPN terutang", r["ppn_terutang"], 6_600_000)
r = T.hitung_ppn(100_000_000, 0, mewah=True)
eq("PPN mewah 12%", r["ppn_keluar"], 12_000_000)

# --- PPh final
eq("PPh final UMKM 0,5%", T.hitung_pph_final(1_000_000_000, umkm=True)["pajak"], 5_000_000)
eq("PPh final non-UMKM 1%", T.hitung_pph_final(1_000_000_000, umkm=False)["pajak"], 10_000_000)

# --- angsuran PPh 25
eq("angsuran 25 bulanan", T.angsuran_pph25(120_000_000), 10_000_000)

# --- round down ribuan
eq("round down ribuan", T.round_down_ribuan(546_123_456), 546_123_000)

print()
if fails:
    print(f"{len(fails)} FAIL: {fails}")
    raise SystemExit(1)
print("SEMUA PASS")