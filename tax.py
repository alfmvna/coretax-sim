"""Engine perhitungan pajak untuk simulasi Coretax.

Sumber tarif:
  - PPh Pasal 21: PP 58/2023 + PMK 168/2023 (TER), Pasal 17 UU HPP No. 7/2021
  - PTKP: PMK 101/PMK.010/2016
  - PPN: PMK 131/2024 (tarif 12% untuk barang/jasa subject PPnBM, 11% non-software)
Semua fungsi murni (pure function) agar bisa diuji tanpa I/O.
"""
from __future__ import annotations

# ---------------------------------------------------------------- tarif Pasal 17
PASAL17 = [
    (60_000_000, 0.05),
    (250_000_000, 0.15),
    (500_000_000, 0.25),
    (5_000_000_000, 0.30),
    (None, 0.35),
]

PTKP = {
    "TK/0": 54_000_000, "TK/1": 58_500_000, "TK/2": 63_000_000, "TK/3": 67_500_000,
    "K/0": 58_500_000, "K/1": 63_000_000, "K/2": 67_500_000, "K/3": 72_000_000,
    "K/I/0": 112_500_000,
}

TER_KATEGORI = {
    # (batas atas, tarif) — tarif tunggal atas seluruh penghasilan bruto
    "A": [
        (5_400_000, 0.00), (5_650_000, 0.0025), (5_950_000, 0.005), (6_300_000, 0.0075),
        (6_750_000, 0.01), (7_500_000, 0.0125), (8_550_000, 0.015), (9_650_000, 0.02),
        (10_050_000, 0.0225), (10_350_000, 0.025), (10_700_000, 0.03), (11_050_000, 0.035),
        (11_600_000, 0.04), (12_500_000, 0.05), (13_750_000, 0.06), (15_100_000, 0.07),
        (16_950_000, 0.08), (19_750_000, 0.09), (24_150_000, 0.10), (26_450_000, 0.11),
        (28_000_000, 0.12), (30_050_000, 0.13), (32_400_000, 0.14), (35_400_000, 0.15),
        (39_100_000, 0.16), (43_850_000, 0.17), (47_800_000, 0.18), (51_400_000, 0.19),
        (56_300_000, 0.20), (62_200_000, 0.21), (68_600_000, 0.22), (77_500_000, 0.23),
        (89_000_000, 0.24), (103_000_000, 0.25), (125_000_000, 0.26), (157_000_000, 0.27),
        (206_000_000, 0.28), (337_000_000, 0.29), (454_000_000, 0.30), (550_000_000, 0.31),
        (695_000_000, 0.32), (910_000_000, 0.33), (None, 0.34),
    ],
    "B": [
        (6_200_000, 0.00), (6_500_000, 0.0025), (6_850_000, 0.005), (7_300_000, 0.0075),
        (9_200_000, 0.01), (10_750_000, 0.015), (11_250_000, 0.02), (11_600_000, 0.025),
        (12_600_000, 0.03), (13_600_000, 0.04), (14_950_000, 0.05), (16_400_000, 0.06),
        (18_450_000, 0.07), (21_850_000, 0.08), (26_000_000, 0.09), (27_700_000, 0.10),
        (29_350_000, 0.11), (31_450_000, 0.12), (33_950_000, 0.13), (37_100_000, 0.14),
        (41_100_000, 0.15), (45_800_000, 0.16), (49_500_000, 0.17), (53_800_000, 0.18),
        (58_500_000, 0.19), (64_000_000, 0.20), (71_000_000, 0.21), (80_000_000, 0.22),
        (93_000_000, 0.23), (109_000_000, 0.24), (129_000_000, 0.25), (163_000_000, 0.26),
        (211_000_000, 0.27), (374_000_000, 0.28), (459_000_000, 0.29), (555_000_000, 0.30),
        (704_000_000, 0.31), (957_000_000, 0.32), (None, 0.33),
    ],
    "C": [
        (6_600_000, 0.00), (6_950_000, 0.0025), (7_350_000, 0.005), (7_800_000, 0.0075),
        (8_850_000, 0.01), (9_800_000, 0.015), (10_950_000, 0.02), (11_200_000, 0.03),
        (12_050_000, 0.04), (12_950_000, 0.05), (14_150_000, 0.06), (15_550_000, 0.07),
        (17_050_000, 0.08), (19_500_000, 0.09), (22_700_000, 0.10), (29_350_000, 0.11),
        (30_350_000, 0.12), (32_500_000, 0.13), (35_000_000, 0.14), (38_600_000, 0.15),
        (43_000_000, 0.16), (47_400_000, 0.17), (51_200_000, 0.18), (55_800_000, 0.19),
        (60_400_000, 0.20), (66_700_000, 0.21), (74_500_000, 0.22), (86_000_000, 0.23),
        (103_000_000, 0.24), (124_000_000, 0.25), (157_000_000, 0.26), (206_000_000, 0.27),
        (337_000_000, 0.28), (454_000_000, 0.29), (550_000_000, 0.30), (695_000_000, 0.31),
        (910_000_000, 0.32), (None, 0.33),
    ],
}

TER_HARIAN = [(450_000, 0.00), (2_500_000, 0.005)]

PTKP_TER_KAT = {
    "TK/0": "A", "TK/1": "A", "K/0": "A",
    "TK/2": "B", "TK/3": "B", "K/1": "B", "K/2": "B",
    "K/3": "C", "K/I/0": "C",
}

# ------------------------------------------------------------------ util angka
def num(v, default=0.0) -> float:
    """Terima '1.234.567' / '1,234,567' / '1234,56' / '1.234.567,89' -> float."""
    if v is None or v == "":
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("Rp", "").replace(" ", "")
    if "," in s and "." in s:
        # yang terakhir = desimal, yang lain = ribuan
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # koma: ribuan bila dipakai berulang / trailing 3 digit
        parts = s.split(",")
        if len(parts) > 2 or (len(parts[1]) == 3 and parts[0].isdigit() and len(parts[0]) <= 3):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2 or (len(parts[1]) == 3 and parts[0].isdigit() and len(parts[0]) <= 3):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return default


def round_down_ribuan(v: float) -> float:
    return float(int(v // 1000) * 1000)


# --------------------------------------------------------------- tarif lookup
def tarif_pasal17(pkp: float) -> float:
    """Tarif marginal Pasal 17 untuk PKP tahunan."""
    for batas, tarif in PASAL17:
        if batas is None or pkp <= batas:
            return tarif
    return 0.35


def hitung_pasal17(pkp: float) -> float:
    """PPh terutang dengan tarif progresif Pasal 17 atas PKP tahunan."""
    if pkp <= 0:
        return 0.0
    tax, sisa = 0.0, pkp
    bawah = 0.0
    for batas, tarif in PASAL17:
        if batas is None:
            tax += sisa * tarif
            break
        lebar = batas - bawah
        if sisa <= lebar:
            tax += sisa * tarif
            break
        tax += lebar * tarif
        sisa -= lebar
        bawah = batas
    return tax


def _ter_rate(tabel, nilai: float) -> float:
    for batas, tarif in tabel:
        if batas is None or nilai <= batas:
            return tarif
    return 0.0


def ter_bulanan(bruto: float, ptkp_kode: str) -> tuple[float, str]:
    """TER bulanan pegawai tetap/pensiunan (Jan-Nov)."""
    kat = PTKP_TER_KAT.get(ptkp_kode, "A")
    tarif = _ter_rate(TER_KATEGORI[kat], bruto)
    return round(bruto * tarif), f"{tarif*100:g}%"


def ter_harian(bruto_harian: float) -> tuple[float, str]:
    """TER harian pegawai tidak tetap (<= Rp2,5 juta/hari)."""
    tarif = _ter_rate(TER_HARIAN, bruto_harian)
    return round(bruto_harian * tarif), f"{tarif*100:g}%"


# ----------------------------------------------------------- PPh Pasal 21/26
def hitung_pph21_bulanan(bruto: float, ptkp_kode: str) -> dict:
    """Pegawai tetap / pensiunan, masa pajak selain terakhir -> TER bulanan."""
    pajak, tarif = ter_bulanan(bruto, ptkp_kode)
    return {"dpp": bruto, "tarif": tarif, "pajak": pajak, "metode": "TER Bulanan"}


def hitung_pph21_harian(bruto_harian: float) -> dict:
    """TER harian untuk pegawai tidak tetap dengan penghasilan <= Rp2,5 juta/hari."""
    pajak, tarif = ter_harian(bruto_harian)
    return {"dpp": bruto_harian, "tarif": tarif, "pajak": pajak, "metode": "TER Harian"}


def hitung_pph21_tidak_tetap(bruto_total: float, hari_kerja: int) -> dict:
    """Pegawai tidak tetap: bruto harian = total / hari.
    <= 2,5 jt/hari -> TER harian; > 2,5 jt/hari -> Pasal 17 x 50% atas DPP harian."""
    hari = max(1, hari_kerja)
    harian = bruto_total / hari
    if harian <= 2_500_000:
        r = hitung_pph21_harian(harian)
        r["dpp"] = bruto_total
        r["tarif_harian"] = harian
        return r
    dpp = harian * 0.5
    return {"dpp": dpp, "tarif": f"{round(tarif_pasal17(dpp)*50,4)*100:g}%",
            "pajak": round(dpp * tarif_pasal17(dpp)),
            "metode": "Pasal 17 x 50% (harian > 2,5 jt)", "tarif_harian": harian}


def hitung_pph21_masa_terakhir(bruto_tahunan: float, ptkp_kode: str,
                               *,Terbilang: bool = False) -> dict:
    """Masa pajak terakhir (Desember) -> hitung tahunan dengan Pasal 17.

    Sesuai PP 58/2023: masa pajak terakhir memakai akumulasi penghasilan setahun
    dengan pemotongan biasa (bukan TER), kecuali ada circumstances tertentu.
    """
    ptkp = PTKP.get(ptkp_kode, 54_000_000)
    pkp = round_down_ribuan(max(0.0, bruto_tahunan - ptkp))
    pajak = hitung_pasal17(pkp)
    return {"dpp": bruto_tahunan, "ptkp": ptkp, "pkp": pkp,
            "tarif": f"{tarif_pasal17(pkp)*100:g}%", "pajak": round(pajak),
            "metode": "Pasal 17 (masa pajak terakhir)"}


def hitung_pph21_bukan_pegawai(bruto: float) -> dict:
    """Bukan pegawai: DPP = 50% bruto, tarif Pasal 17 atas PKP tahunan."""
    dpp = bruto * 0.5
    return {"dpp": dpp, "tarif": f"{round(tarif_pasal17(dpp)*100,4):g}%",
            "pajak": round(dpp * tarif_pasal17(dpp)), "metode": "Pasal 17 x 50%"}


# ------------------------------------------------------------------- PPh OP
def hitung_pph_op_tahunan(neto: float, ptkp_kode: str, kredit_pajak: float = 0.0,
                           pengurang_pph: float = 0.0) -> dict:
    """SPT Tahunan PPh Orang Pribadi: neto - PTKP = PKP; PPh terutang; dikurangi kredit."""
    ptkp = PTKP.get(ptkp_kode, 54_000_000)
    pkp = max(0.0, neto - ptkp)
    pph_terutang = hitung_pasal17(pkp)
    pph_terutang_setelah = max(0.0, pph_terutang - pengurang_pph)
    kurang_bayar = pph_terutang_setelah - kredit_pajak
    return {"neto": neto, "ptkp": ptkp, "pkp": pkp,
            "pph_terutang": round(pph_terutang),
            "pengurang_pph": pengurang_pph,
            "pph_terutang_setelah": round(pph_terutang_setelah),
            "kredit_pajak": kredit_pajak,
            "kurang_bayar": round(kurang_bayar),
            "status": "Kurang Bayar" if kurang_bayar > 0 else ("Lebih Bayar" if kurang_bayar < 0 else "Nihil")}


# --------------------------------------------------------------------- PPN
PPN_TARIF = 0.12          # PMK 131/2024 untuk subject PPnBM
PPN_TARIF_NONS = 0.11     # tarif non-software


def hitung_ppn(dpp_keluar: float, dpp_masuk: float, *, mewah: bool = False,
               ppnbm: float = 0.0) -> dict:
    """Penghitungan PPN Masa. DPP sudah nilai lain (tanpa PPN)."""
    tarif = PPN_TARIF if mewah else PPN_TARIF_NONS
    ppn_keluar = dpp_keluar * tarif
    ppn_masuk = dpp_masuk * tarif
    ppn_terutang = ppn_keluar - ppn_masuk
    return {"tarif": tarif, "ppn_keluar": round(ppn_keluar), "ppn_masuk": round(ppn_masuk),
            "ppnbm": round(ppnbm), "ppn_terutang": round(ppn_terutang),
            "kurang_bayar": round(ppn_terutang)}


# ------------------------------------------------- PPh Final (bayar per tahun)
PPh_FINAL = {
    "umkm": 0.005,          # 0,5% omzet bruto (UU HPP)
    "bukan_umkm": 0.01,    # 1% omzet bruto
}


def hitung_pph_final(omzet: float, *, umkm: bool = True) -> dict:
    tarif = PPh_FINAL["umkm"] if umkm else PPh_FINAL["bukan_umkm"]
    return {"omzet": omzet, "tarif": tarif, "pajak": round(omzet * tarif),
            "kategori": "UMKM" if umkm else "Bukan UMKM"}


# ---------------------------------------------------------- angsuran PPh 25
def angsuran_pph25(pajak_setahun: float, bulan_angsuran: int = 12) -> float:
    """Angsuran PPh Pasal 25 = pajak setahun / jumlah bulan angsuran."""
    return round(pajak_setahun / max(1, bulan_angsuran))