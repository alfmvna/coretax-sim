"""Simulator Coretax DJP — model data + definisi form SPT.

Struktur form mengikuti Buku Manual Coretax DJP (DJP) dan alur live portal Coretax.
"""
from __future__ import annotations
import json
import os
import sqlite3
from datetime import date, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
# Lokasi DB bisa dipindah lewat env (dipakai Docker volume).
_DATA_DIR = os.environ.get("CORETAX_DATA_DIR") or os.path.join(ROOT, "data")
DB = os.path.join(_DATA_DIR, "coretax.db")

# ------------------------------------------------------------------ koneksi
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    # WAL: reader tidak terblokir writer -> mencegah "database is locked"
    # saat beberapa user mengisi form bersamaan.
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    c.execute("PRAGMA busy_timeout=15000")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------- master WP
DEFAULT_WP = {
    "npwp": "2171121009959003",
    "nama": "ALLIF MAULANA",
    "alamat": "Jl. Contoh-learning No. 1, Batam",
    "kpp": "KPP Pratama Batam",
    "telepon": "081234567890",
    "email": "allif@example.test",
    "ptkp_kode": "K/0",
    "status": "Wajib Pajak Orang Pribadi",
}

# Akun demo untuk latihan tim. NIK FIKTIF (bukan NIK asli) supaya tidak
# tercampur dengan data pajak nyata. 'role': WP (wajib pajak) atau OP (operator).
# Password awal = 'demo123' — WAJIB diganti sebelum dipakai di luar kelas.
DEMO_USERS = [
    {"npwp": "2171121009959003", "nama": "ALLIF MAULANA", "kpp": "KPP Pratama Batam",
     "ptkp_kode": "K/0", "role": "OP", "email": "allif@example.test"},
    {"npwp": "1111111111111", "nama": "TIM KELAS A", "kpp": "KPP Pratama Batam",
     "ptkp_kode": "TK/0", "role": "WP", "email": "tim-a@example.test"},
    {"npwp": "2222222222222", "nama": "TIM KELAS B", "kpp": "KPP Pratama Batam",
     "ptkp_kode": "K/0", "role": "WP", "email": "tim-b@example.test"},
    {"npwp": "3333333333333", "nama": "TIM KELAS C", "kpp": "KPP Pratama Batam",
     "ptkp_kode": "K/1", "role": "WP", "email": "tim-c@example.test"},
]
DEMO_PASSWORD = "demo123"

# ------------------------------------------------------- enum jenis SPT live
# Diambil dari wizard "Buat Konsep SPT" portal Coretax (akun OP).
JENIS_PAJAK = [
    {"kode": "PPh Final Pengungkapan Harta Bersih", "spt": "SPT Tahunan PPh Final Pengungkapan Harta Bersih"},
    {"kode": "PPh Orang Pribadi", "spt": "SPT Tahunan PPh Wajib Pajak Orang Pribadi"},
    {"kode": "PPh Pasal 21/26", "spt": "SPT Masa PPh Pasal 21/26"},
    {"kode": "PPh Unifikasi", "spt": "SPT Masa PPh Unifikasi"},
    # Portal Coretax hanya menampilkan 4 di atas untuk akun OP (PPN butuh status PKP).
    # Disini PPN tetap disediakan supaya tim bisa berlatih SPT Masa PPN.
    {"kode": "PPN", "spt": "SPT Masa PPN", "catatan": "SPT Masa PPN — tersedia untuk simulasi "
     "(pada portal resmi modul ini muncul untuk Wajib Pajak PKP)"},
]

STATUS_SPT = [
    {"kode": "Normal", "desc": "Pelaporan pertama pada masa pajak tersebut"},
    {"kode": "Pembetulan", "desc": "Pembetulan atas SPT yang sudah dilaporkan"},
]

STATUS_TABEL = ["Konsep SPT", "SPT Menunggu Pembayaran", "SPT Dilaporkan", "SPT Ditolak", "SPT Dibatalkan"]


# ------------------------------------------------- definisi form SPT Tahunan OP
# 12 bagian formulir induk (Buku Manual SPT Tahunan PPh OP, gambar 00012)
BAGIAN_INDUK_OP = [
    {"kode": "HEADER", "judul": "Header (Tajuk)",
     "field": [
         ("tahun_pajak", "Tahun Pajak", "readonly", "Tahun Pajak"),
         ("periode_akuntansi", "Periode Akuntansi", "readonly", "Periode Akuntansi"),
         ("status_spt", "Status SPT", "readonly", "Status SPT"),
         ("jenis_pembukuan", "Jenis Pembukuan / Pencatatan", "select",
          ["Pembukuan Stelsel Akrual", "Pembukuan Stelsel Kas", "Pencatatan"]),
         ("sumber_penghasilan", "Sumber Penghasilan", "select",
          ["Kegiatan Usaha", "Pekerjaan", "Pekerjaan Bebas", "Lainnya"]),
     ]},
    {"kode": "A", "judul": "A. Identity of Taxpayers (Identitas Wajib Pajak)",
     "field": [("npwp", "NPWP", "readonly", "NPWP"),
               ("nama", "Nama", "readonly", "Nama"),
               ("telepon", "Nomor Handphone", "readonly", "Telepon"),
               ("email", "Email", "readonly", "Email"),
               ("status_kewajiban", "Status Kewajiban Perpajakan", "readonly", "Status"),
               ("npwp_pasangan", "NPWP Suami/Istri", "readonly", "NPWP Pasangan")]},
    {"kode": "B", "judul": "B. Summary of Income (Ikhtisar Penghasilan Neto)",
     "field": [
         ("q_1a", "Apakah Anda menerima penghasilan dalam negeri dari pekerjaan?", "yn", None),
         ("q_1b1", "Apakah Anda menerima penghasilan dalam negeri dari usaha dan/atau pekerjaan bebas?", "yn", None),
         ("q_1b2", "Apakah Anda termasuk Wajib Pajak Orang Pribadi yang memiliki peredaran bruto tertentu atau Orang Pribadi Pengusaha Tertentu (OPPT)?", "yn", None),
         ("q_1b3", "Apakah Anda menggunakan Norma dalam menghitung penghasilan neto?", "yn", None),
         ("q_1b4", "Anda menyelenggarakan pembukuan. Sebutkan sektor usaha yang Anda lakukan?", "select",
          ["Dagang", "Jasa", "Industri"]),
         ("q_1c", "Apakah Anda menerima penghasilan dalam negeri lainnya?", "yn", None),
         ("q_1d", "Apakah Anda menerima penghasilan luar negeri?", "yn", None),
     ]},
    {"kode": "C", "judul": "C. Income Tax Payable Calculation (Perhitungan PPh Terutang)",
     "field": [
         ("q_2", "Penghasilan neto setahun (1a+1b+1c+1d)", "number", "Penghasilan Neto Setahun"),
         ("q_3", "Apakah terdapat pengurang penghasilan neto seperti kompensasi kerugian atau zakat?", "yn", None),
         ("pengurang_neto", "Jumlah pengurang penghasilan neto", "number", "Pengurang Neto"),
         ("q_4", "Penghasilan neto setelah pengurang penghasilan neto (2-3)", "calc", "Neto Setelah Pengurang"),
         ("q_5", "Penghasilan tidak kena pajak", "calc", "PTKP"),
         ("q_6", "Penghasilan kena pajak (4-5)", "calc", "PKP"),
         ("q_7", "PPh terutang", "calc", "PPh Terutang"),
         ("q_8", "Apakah terdapat pengurang PPh terutang?", "yn", None),
         ("pengurang_pph", "Jumlah pengurang PPh terutang", "number", "Pengurang PPh"),
         ("q_9", "PPh terutang setelah pengurang PPh terutang (7-8)", "calc", "PPh Terutang Setelah Pengurang"),
     ]},
    {"kode": "D", "judul": "D. Income Tax Credit (Kredit Pajak)",
     "field": [
         ("q_10a", "Apakah terdapat PPh yang telah dipotong/dipungut oleh pihak lain?", "yn", None),
         ("q_10b", "Angsuran PPh Pasal 25", "number", "Angsuran PPh 25"),
         ("q_10c", "STP PPh Pasal 25 (hanya pokok pajak)", "number", "STP PPh 25"),
         ("q_10d", "Apakah Anda menerima pengembalian/pengurangan kredit PPh luar negeri yang telah dikreditkan?", "yn", None),
         ("kredit_luar_negeri", "Jumlah pengembalian/pengurangan kredit PPh luar negeri", "number", "Kredit Luar Negeri"),
         ("kredit_pajak", "Jumlah kredit pajak (dihitung otomatis dari bukti potong, angsuran 25, STP, dan kredit luar negeri)", "calc", "Kredit Pajak"),
     ]},
    {"kode": "E", "judul": "E. Underpayment/Overpayment Income Tax (PPh Kurang/Lebih Bayar)",
     "field": [
         ("q_11a", "PPh kurang/lebih bayar (9-10a-10b-10c+10d)", "calc", "Kurang/Lebih Bayar"),
         ("q_11b", "Apakah terdapat Surat Keputusan Persetujuan Pengangsuran atau Penundaan Pembayaran Pajak?", "yn", None),
         ("nilai_pengangsuran", "Jumlah yang disetujui untuk diangsur/ditunda", "number", "Pengangsuran Disetujui"),
         ("q_11c", "PPh yang masih harus dibayar (11a-11b)", "calc", "PPh Masih Harus Dibayar"),
     ]},
    {"kode": "F", "judul": "F. Amendment Tax Return (hanya jika status SPT Pembetulan)",
     "field": [
         ("kurang_bayar_sblm", "PPh kurang/lebih bayar SPT sebelum pembetulan", "number", "Kurang Bayar SPT_normal"),
         ("kurang_bayar_pemb", "PPh kurang/lebih bayar karena pembetulan", "number", "Kurang Bayar Pembetulan"),
     ]},
    {"kode": "G", "judul": "G. Refund (hanya jika status SPT Lebih Bayar)",
     "field": [
         ("metode_refund", "Permohonan pengembalian PPh lebih bayar", "select",
          ["Dikembalikan melalui Pemeriksaan", "Dikembalikan melalui Permohonan Pengembalian Pendahuluan"]),
         ("rekening", "Nomor rekening tujuan pengembalian", "text", "No. Rekening"),
     ]},
    {"kode": "H", "judul": "H. Income Tax Installment (Angsuran PPh Pasal 25 Tahun Berikutnya)",
     "field": [
         ("q_13a", "Apakah Anda hanya menerima penghasilan teratur dan berkewajiban membayar angsuran PPh Pasal 25 tahun pajak berikutnya?", "yn", None),
         ("q_13b", "Apakah Anda menyusun perhitungan tersendiri angsuran PPh Pasal 25 tahun pajak berikutnya?", "yn", None),
         ("q_13c", "Apakah Anda membayar angsuran PPh Pasal 25 OPPT tahun pajak berikutnya?", "yn", None),
         ("angsuran_pph25", "Angsuran PPh Pasal 25 tahun berikutnya", "calc", "Angsuran PPh 25"),
     ]},
    {"kode": "I", "judul": "I. Statement of Other Transactions (Pernyataan Transaksi Lainnya)",
     "field": [
         ("q_14a", "Harta pada akhir tahun pajak", "number", "Harta Akhir Tahun Pajak"),
         ("q_14b", "Apakah Anda memiliki utang pada akhir tahun pajak?", "yn", None),
         ("q_14c", "Apakah Anda menerima penghasilan yang dikenakan pajak penghasilan bersifat final?", "yn", None),
         ("q_14d", "Apakah Anda menerima penghasilan yang tidak termasuk objek pajak?", "yn", None),
         ("q_14e", "Apakah Anda melaporkan biaya penyusutan dan/atau amortisasi fiskal?", "yn", None),
         ("q_14f", "Whether you declare entertainment expense, promotion expense and bad debt expense", "yn", None),
         ("q_14g", "Apakah Anda menerima dividen dan melaporkannya sebagai penghasilan tidak termasuk objek pajak?", "yn", None),
         ("q_14h", "Kelebihan PPh Final atas penghasilan dari usaha dengan peredaran bruto tertentu", "number", "Kelebihan PPh Final"),
     ]},
    {"kode": "J", "judul": "J. Additional Attachments (Lampiran Tambahan)",
     "field": [
         ("lamp_laporan_keuangan", "Laporan keuangan / laporan keuangan yang telah diaudit", "file", None),
         ("lamp_zakat", "Bukti pembayaran zakat / sumbangan keagamaan", "file", None),
         ("lamp_kredit_luar_negeri", "Bukti pemotongan sehubungan dengan kredit pajak luar negeri", "file", None),
         ("lamp_surat_kuasa", "Surat kuasa khusus", "file", None),
         ("lamp_lainnya", "Dokumen lain", "file", None),
     ]},
    {"kode": "K", "judul": "K. Statement (Pernyataan)",
     "field": [
         ("jabatan_penandatangan", "Jabatan penandatangan SPT", "text", "Jabatan"),
         ("pernyataan", "Pernyataan SPT lengkap benar dan jelas", "textarea", "Pernyataan"),
     ]},
]

# 11 lampiran SPT Tahunan PPh OP
LAMPIRAN_OP = [
    {"kode": "L-1", "judul": "Lampiran 1 — Harta, Utang, Tanggungan, Penghasilan Neto, Bukti Potong",
     "bagian": [
         {"kode": "A", "judul": "A. Assets at The End of Tax Year (Harta di Akhir Tahun Pajak)",
          "sub": [
              {"kode": "1", "judul": "Cash and Cash Equivalents (Kas dan Setara Kas)", "jenis": "harta",
               "desc": ["Uang Tunai/Bank Note/Koin", "Tabungan (Bank/Lembaga Keuangan)", "Giro", "Deposito",
                        "Uang elektronik", "Cek", "Wessel", "Kertas komersial", "Setara Kas Lainnya"],
               "field": [("code", "Code", "prepop"), ("description", "Description", "text"),
                         ("account_number", "Account Number", "text"), ("on_behalf_of", "On Behalf Of", "text"),
                         ("bank_name", "Bank/Institution Name", "text"),
                         ("country", "Country Where The Asset Is Located", "text"),
                         ("year_acquisition", "Year Of Acquisition", "number"),
                         ("balance", "Balance", "number"), ("remark", "Remark", "text")]},
              {"kode": "2", "judul": "Account Receivable (Piutang)", "jenis": "harta",
               "desc": ["Piutang Usaha", "Afiliasi Piutang", "Piutang lainnya"],
               "field": [("description", "Description", "text"), ("account_number", "Account Number", "text"),
                         ("on_behalf_of", "On Behalf Of", "text"), ("balance", "Balance", "number")]},
              {"kode": "3", "judul": "Investments/Securities (Investasi dan Sekuritas)", "jenis": "harta",
               "desc": ["Saham", "Obligasi", "Reksa Dana", "Deposito Berjangka", "Emas", "Investasi Lainnya"],
               "field": [("description", "Description", "text"), ("account_number", "Account Number", "text"),
                         ("on_behalf_of", "On Behalf Of", "text"), ("balance", "Balance", "number")]},
              {"kode": "4", "judul": "Movable Assets (Harta Bergerak)", "jenis": "harta",
               "desc": ["Kendaraan Bermotor", "Alat dan Mesin", "Perlengkapan", "Harta Bergerak Lainnya"],
               "field": [("description", "Description", "text"), ("account_number", "Account Number", "text"),
                         ("on_behalf_of", "On Behalf Of", "text"),
                         ("year_acquisition", "Year Of Acquisition", "number"),
                         ("balance", "Balance", "number")]},
              {"kode": "5", "judul": "Non Movable Assets — Land And Building (Harta Tidak Bergerak)", "jenis": "harta",
               "desc": ["Tanah", "Bangunan", "Tanah dan Bangunan", "Harta Tidak Bergerak Lainnya"],
               "field": [("description", "Description", "text"), ("on_behalf_of", "On Behalf Of", "text"),
                         ("year_acquisition", "Year Of Acquisition", "number"),
                         ("balance", "Balance", "number")]},
              {"kode": "6", "judul": "Other Assets (Harta Lainnya)", "jenis": "harta",
               "desc": ["Harta Lainnya"], "field": [("description", "Description", "text"),
                         ("balance", "Balance", "number")]},
              {"kode": "7", "judul": "Summary Of Assets (Rekapitulasi Harta)", "jenis": "rekap_harta",
               "field": [("total", "Total Harta", "number")]},
          ]},
         {"kode": "B", "judul": "B. Debts at The End of Tax Year (Hutang di Akhir Tahun Pajak)",
          "sub": [
              {"kode": "1", "judul": "Utang Usaha", "jenis": "hutang",
               "desc": ["Utang Usaha"],
               "field": [("description", "Description", "text"), ("amount", "Amount", "number"),
                         ("creditor", "Creditor", "text")]},
              {"kode": "2", "judul": "Utang Bank", "jenis": "hutang", "desc": ["Utang Bank"],
               "field": [("description", "Description", "text"), ("amount", "Amount", "number"),
                         ("creditor", "Creditor", "text")]},
              {"kode": "3", "judul": "Utang Lainnya", "jenis": "hutang", "desc": ["Utang Lainnya"],
               "field": [("description", "Description", "text"), ("amount", "Amount", "number"),
                         ("creditor", "Creditor", "text")]},
          ]},
         {"kode": "C", "judul": "C. List Of Dependants Family Members (Daftar Tanggungan)",
          "sub": [
              {"kode": "1", "judul": "Daftar Tanggungan", "jenis": "tanggungan",
               "field": [("name", "Name", "text"), ("relation", "Relation", "text"),
                         ("date_of_birth", "Date Of Birth", "date")]},
          ]},
         {"kode": "D", "judul": "D. Net Income Form Employment (Penghasilan Neto dari Pekerjaan)",
          "sub": [
              {"kode": "1", "judul": "Daftar Penghasilan Neto dari Pekerjaan", "jenis": " neto",
               "field": [("employer", "Employer Name", "text"), ("npwp", "NPWP", "text"),
                         ("gross_income", "Gross Income", "number"),
                         ("net_income", "Net Income", "number"),
                         ("withholding_tax", "Withholding Tax", "number")]},
          ]},
         {"kode": "E", "judul": "E. List Of Withholding Tax Slip (Daftar Bukti Pemotongan)",
          "sub": [
              {"kode": "1", "judul": "Daftar Bukti Pemotongan", "jenis": "bupot",
               "field": [("no_bupot", "Nomor Bukti Pemotongan", "text"), ("npwp", "NPWP", "text"),
                         ("name", "Name", "text"), ("gross_income", "Gross Income", "number"),
                         ("withholding_tax", "Withholding Tax", "number")]},
          ]},
     ]},
    {"kode": "L-2", "judul": "Lampiran 2 — Penghasilan Luar Negeri / Bebas Pajak / Final",
     "bagian": [
         {"kode": "A", "judul": "A. Final Income Tax (Pajak Penghasilan Bersifat Final)",
          "sub": [
              {"kode": "1", "judul": "Daftar Penghasilan Final", "jenis": "final",
               "desc": ["Penghasilan dari Usaha", "Penghasilan dari Pekerjaan Bebas", "Penghasilan dari Sewa",
                        "Hadiah", " Dividen", "Bunga", " Penghasilan lain"],
               "field": [("code", "Code", "prepop"), ("income_type", "Income Type", "text"),
                         ("tin", "TIN/MPWP", "text"), ("name", "Name", "text"),
                         ("gross_income", "Gross Income", "number"), ("final_tax", "Final Tax", "number")]},
          ]},
         {"kode": "B", "judul": "B. Income Excluded From Tax (Penghasilan Tidak Termasuk Objek Pajak)",
          "sub": [
              {"kode": "1", "judul": "Daftar Penghasilan yang Dikecualikan", "jenis": "final",
               "desc": ["Dividen", "Bunga", "Warisan", "Hibah", "Bantuan/Sumbangan", "Penerimaan Zakat",
                        "SHU", "Hadiah/Undian", "Penghasilan lain yang tidak termasuk objek pajak"],
               "field": [("code", "Code", "prepop"), ("income_type", "Income Type", "text"),
                         ("tin", "TIN/MPWP", "text"), ("name", "Name", "text"),
                         ("gross_income", "Gross Income", "number")]},
          ]},
         {"kode": "C", "judul": "C. Foreign Income (Penghasilan Luar Negeri)",
          "sub": [
              {"kode": "1", "judul": "Daftar Penghasilan Luar Negeri", "jenis": "final",
               "field": [("name", "Name", "text"), ("country_code", "Country Code", "text"),
                         ("date_transaction", "Date Of Transaction", "date"),
                         ("income_type", "Income Type", "text"), ("income_code", "Income Code", "text"),
                         ("net_income", "Net Income", "number"),
                         ("amount_foreign", "Amount In Foreign Currency", "number"),
                         ("amount_idr", "Amount In Rupiah", "number"), ("currency", "Currency", "text"),
                         ("tax_credit", "Tax Credit", "number")]},
          ]},
     ]},
    {"kode": "L-3A-1", "judul": "Lampiran 3A-1 — Penghasilan Dalam Negeri Usaha Dagang (Laba-Rugi)",
     "bagian": [
         {"kode": "A", "judul": "Laba Rugi (Income Statement)",
          "sub": [
              {"kode": "1", "judul": "Laporan Laba Rugi", "jenis": "laba_rugi",
               "field": [("omzet_penjualan", "Omzet Penjualan", "number"),
                         ("hpp", "Harga Pokok Penjualan", "number"),
                         ("beban_pegawai", "Beban Pegawai", "number"),
                         ("beban_sewa", "Beban Sewa", "number"),
                         ("beban_utilitas", "Beban Utilitas", "number"),
                         ("beban_lainnya", "Beban Lainnya", "number"),
                         ("laba_kotor", "Laba Kotor", "calc"),
                         ("laba_bersih", "Laba Bersih", "calc")]},
          ]},
     ]},
    {"kode": "L-3A-2", "judul": "Lampiran 3A-2 — Penghasilan Dalam Negeri Usaha Jasa",
     "bagian": [
         {"kode": "A", "judul": "Laporan Laba Rugi Jasa",
          "sub": [
              {"kode": "1", "judul": "Laporan Laba Rugi Jasa", "jenis": "laba_rugi",
               "field": [("omzet_penjualan", "Omzet Penjualan", "number"),
                         ("beban_pegawai", "Beban Pegawai", "number"),
                         ("beban_sewa", "Beban Sewa", "number"),
                         ("beban_utilitas", "Beban Utilitas", "number"),
                         ("beban_lainnya", "Beban Lainnya", "number"),
                         ("laba_bersih", "Laba Bersih", "calc")]},
          ]},
     ]},
    {"kode": "L-3A-3", "judul": "Lampiran 3A-3 — Penghasilan Dalam Negeri Usaha Industri",
     "bagian": [
         {"kode": "A", "judul": "Laporan Laba Rugi Industri",
          "sub": [
              {"kode": "1", "judul": "Laporan Laba Rugi Industri", "jenis": "laba_rugi",
               "field": [("omzet_penjualan", "Omzet Penjualan", "number"),
                         ("hpp", "Harga Pokok Penjualan", "number"),
                         ("beban_pegawai", "Beban Pegawai", "number"),
                         ("beban_sewa", "Beban Sewa", "number"),
                         ("beban_utilitas", "Beban Utilitas", "number"),
                         ("beban_lainnya", "Beban Lainnya", "number"),
                         ("laba_bersih", "Laba Bersih", "calc")]},
          ]},
     ]},
    {"kode": "L-3A-4", "judul": "Lampiran 3A-4 — Penghasilan Dalam Negeri Lainnya (NPPN)",
     "bagian": [
         {"kode": "A", "judul": "Penghasilan Lainnya",
          "sub": [
              {"kode": "1", "judul": "Daftar Penghasilan Lainnya", "jenis": "final",
               "field": [("description", "Description", "text"), ("gross_income", "Gross Income", "number")]},
          ]},
         {"kode": "B", "judul": "B. Penghasilan Lainnya (Bagian B)",
          "sub": [
              {"kode": "1", "judul": "Daftar Penghasilan Lainnya B", "jenis": "final",
               "field": [("description", "Description", "text"), ("gross_income", "Gross Income", "number")]},
          ]},
     ]},
    {"kode": "L-3B", "judul": "Lampiran 3B — Omzet Brutto (Usaha dengan Peradaran Bruto Tertentu)",
     "bagian": [
         {"kode": "A", "judul": "A. Omzet Brutto (Omzet dan-io)",
          "sub": [
              {"kode": "1", "judul": "Perincian Omzet", "jenis": "final",
               "field": [("bulan", "Bulan", "text"), ("omzet", "Omzet", "number"),
                         ("periode", "Periode", "text")]},
          ]},
         {"kode": "B", "judul": "B. Pemecoinan (Pelaporan)",
          "sub": [
              {"kode": "1", "judul": "Pernyataan Pemecoinan", "jenis": "final",
               "field": [("pernyataan", "Pernyataan", "textarea")]},
          ]},
     ]},
    {"kode": "L-3C", "judul": "Lampiran 3C — Biaya Penyusutan dan Amortisasi Fiskal",
     "bagian": [
         {"kode": "A", "judul": "A. Penyusutan dan Amortisasi",
          "sub": [
              {"kode": "1", "judul": "Daftar Aset yang Disusutkan", "jenis": "final",
               "field": [("asset", "Nama Aset", "text"), ("acquisition_cost", "Biaya Perolehan", "number"),
                         ("useful_life", "Masa Manfaat", "number"),
                         ("depreciation", "Beban Penyusutan", "number")]},
          ]},
     ]},
    {"kode": "L-3D", "judul": "Lampiran 3D — Biaya Entertainment, Promosi, Natura/Kenikmatan, Piutang Tidak Tertagih",
     "bagian": [
         {"kode": "A", "judul": "Biaya entertainment, promosi, natura/kenikmatan, piutang",
          "sub": [
              {"kode": "1", "judul": "Daftar Biaya", "jenis": "final",
               "field": [("description", "Description", "text"), ("amount", "Amount", "number"),
                         ("keterangan", "Keterangan", "text")]},
          ]},
     ]},
    {"kode": "L-4", "judul": "Lampiran 4 — Perhitungan Sendiri Angsuran PPh Pasal 25",
     "bagian": [
         {"kode": "A", "judul": "A. Perhitungan Angsuran",
          "sub": [
              {"kode": "1", "judul": "Perhitungan Angsuran PPh 25", "jenis": "final",
               "field": [("pajak_setahun", "PPh Setahun", "number"),
                         ("jumlah_bulan", "Jumlah Bulan Angsuran", "number"),
                         ("angsuran", "Angsuran per Bulan", "calc")]},
          ]},
     ]},
    {"kode": "L-5", "judul": "Lampiran 5 — Pengurang Penghasilan Neto dan Pengurang PPh Terutang",
     "bagian": [
         {"kode": "A", "judul": "A. Pengurang Penghasilan Neto (Kompensasi Kerugian / Zakat)",
          "sub": [
              {"kode": "1", "judul": "Daftar Pengurang Neto", "jenis": "final",
               "field": [("description", "Description", "text"), ("amount", "Amount", "number")]},
          ]},
         {"kode": "B", "judul": "B. Pengurang Neto Lainnya",
          "sub": [
              {"kode": "1", "judul": "Daftar Pengurang Neto Lainnya", "jenis": "final",
               "field": [("description", "Description", "text"), ("amount", "Amount", "number")]},
          ]},
         {"kode": "C", "judul": "C. Pengurang PPh Terutang",
          "sub": [
              {"kode": "1", "judul": "Daftar Pengurang PPh", "jenis": "final",
               "field": [("description", "Description", "text"), ("amount", "Amount", "number")]},
          ]},
     ]},
]


# ------------------------------------------------- form SPT Masa PPh 21/26
BAGIAN_INDUK_PPH21 = [
    {"kode": "IDENTITAS", "judul": "Identitas Pemotong Pajak",
     "field": [("npwp_pemotong", "NPWP Pemotong", "readonly", "NPWP Pemotong"),
               ("nama_pemotong", "Nama Pemotong", "readonly", "Nama Pemotong"),
               ("jabatan_penandatangan", "Jabatan Penandatangan", "text", "Jabatan")]},
    {"kode": "PEMOTONGAN", "judul": "Rincian Pemotongan",
     "field": [("jumlah_bupot", "Jumlah Bukti Pemotongan", "number", "Jumlah Bupot"),
               ("total_bruto", "Total Penghasilan Bruto", "number", "Total Bruto"),
               ("total_dpp", "Total DPP", "number", "Total DPP"),
               ("total_pajak", "Total PPh Pasal 21 Dipotong", "number", "Total Pajak Dipotong"),
               ("pajak_ditanggung", "PPh yang Ditanggung Pemerintah", "number", "PPh Ditanggung Pemerintah")]},
    {"kode": "PENYAMPAIAN", "judul": "Penyampaian",
     "field": [("masa_pajak", "Masa Pajak", "readonly", "Masa Pajak"),
               ("tahun_pajak", "Tahun Pajak", "readonly", "Tahun Pajak"),
               ("status_spt", "Status SPT", "readonly", "Status SPT"),
               ("keterangan", "Keterangan", "textarea", "Keterangan")]},
]

# ----------------------------------------------- form SPT Masa PPh Unifikasi
BAGIAN_INDUK_UNIFIKASI = [
    {"kode": "IDENTITAS", "judul": "Identitas Pemotong/Pemungut Pajak",
     "field": [("npwp_pemotong", "NPWP Pemotong", "readonly", "NPWP Pemotong"),
               ("nama_pemotong", "Nama Pemotong", "readonly", "Nama Pemotong"),
               ("jabatan_penandatangan", "Jabatan Penandatangan", "text", "Jabatan")]},
    {"kode": "RINGKASAN", "judul": "Ringkasan Pemotongan dan Pemungutan",
     "field": [("total_bruto", "Total Penghasilan Bruto", "number", "Total Bruto"),
               ("total_dpp", "Total DPP", "number", "Total DPP"),
               ("total_pajak", "Total Pajak Dipotong/Dipungut", "number", "Total Pajak"),
               ("jumlah_kode_objek", "Jumlah Kode Objek Pajak", "number", "Jumlah Kode Objek")]},
    {"kode": "PEMBUKUAN", "judul": "Pembukuan",
     "field": [("pembukuan", "Jenis Pembukuan", "select", ["Pembukuan Stelsel Akrual", "Pembukuan Stelsel Kas"]),
               ("sumber_penghasilan", "Sumber Penghasilan", "select",
                ["Kegiatan Usaha", "Pekerjaan", "Pekerjaan Bebas", "Lainnya"])]},
    {"kode": "PENYAMPAIAN", "judul": "Penyampaian",
     "field": [("masa_pajak", "Masa Pajak", "readonly", "Masa Pajak"),
               ("tahun_pajak", "Tahun Pajak", "readonly", "Tahun Pajak"),
               ("status_spt", "Status SPT", "readonly", "Status SPT"),
               ("keterangan", "Keterangan", "textarea", "Keterangan")]},
]

# --------------------------------------------------------- form SPT Masa PPN
BAGIAN_INDUK_PPN = [
    {"kode": "PENYERAHAN", "judul": "Delivery Of Goods And Services (Penyerahan Barang dan/atau Jasa)",
     "field": [("nilai_penyerahan", "Total Nominal Transaksi Penyerahan", "number", "Nilai Penyerahan"),
               ("jumlah_faktur_keluar", "Jumlah Faktur Pajak Keluaran", "number", "Jml Faktur Keluaran"),
               ("jumlah_faktur_masuk", "Jumlah Faktur Pajak Masukan", "number", "Jml Faktur Masukan")]},
    {"kode": "PERHITUNGAN", "judul": "Underpayment/Overpayment VAT Calculation (Penghitungan PPN Kurang/Lebih Bayar)",
     "field": [("dpp_keluar", "DPP PPN Keluaran", "number", "DPP Keluaran"),
               ("ppn_keluar", "PPN Keluaran", "calc", "PPN Keluaran"),
               ("dpp_masuk", "DPP PPN Masukan (dapat dikreditkan)", "number", "DPP Masukan"),
               ("ppn_masuk", "PPN Masukan", "calc", "PPN Masukan"),
               ("ppnbm", "PPnBM", "number", "PPnBM"),
               ("ppn_terutang", "PPN Terutang", "calc", "PPN Terutang"),
               ("jumlah_kurang_bayar", "PPN Kurang Bayar", "calc", "Kurang Bayar")]},
    {"kode": "PEMBULAN", "judul": "Informasi PPN yang Dipungut",
     "field": [("ppn_dipungut", "PPN yang dipungut oleh pihak lain", "number", "PPN Dipungut"),
               ("keterangan", "Keterangan", "textarea", "Keterangan")]},
    {"kode": "KELENGKAPAN", "judul": "Completeness & Statement (Kelengkapan Dokumen dan Identitas)",
     "field": [("upload_xml", "Upload XML kelengkapan", "file", None),
               ("jabatan_penandatangan", "Position / Jabatan penandatangan", "text", "Jabatan")]},
    {"kode": "PENYAMPAIAN", "judul": "Penyampaian",
     "field": [("masa_pajak", "Masa Pajak", "readonly", "Masa Pajak"),
               ("tahun_pajak", "Tahun Pajak", "readonly", "Tahun Pajak"),
               ("status_spt", "Status SPT", "readonly", "Status SPT")]},
]

LAMPIRAN_PPN = [
    {"kode": "A-1", "judul": "Lampiran A-1 — Daftar Barang/Jasa Kena Pajak (Ekspor, Tidak Berwujud, Jasa)",
     "keterangan": "Barang Kena Pajak Ekspor, Barang Kena Pajak Tidak Berwujud, dan/atau Jasa Kena Pajak",
     "kolom": [("nama", "Nama Barang/Jasa", "text"), ("kode", "Kode", "text"),
               ("jumlah", "Jumlah", "number"), ("harga_satuan", "Harga Satuan", "number"),
               ("nilai", "Nilai (DPP)", "number")]},
    {"kode": "A-2", "judul": "Lampiran A-2 — Pajak Keluaran atas Pengiriman Dalam Negeri (Faktur Pajak)",
     "keterangan": "Daftar Pajak Keluaran atas Pengiriman Dalam Negeri yang telah diterbitkan dengan Faktur Pajak",
     "kolom": [("no_faktur", "Nomor Faktur Pajak", "text"), ("tanggal", "Tanggal", "date"),
               ("nama_pembeli", "Nama Pembeli", "text"), ("npwp", "NPWP Pembeli", "text"),
               ("nilai", "Nilai (DPP)", "number"), ("ppn", "PPN", "number")]},
    {"kode": "B-1", "judul": "Lampiran B-1 — Pajak Masukan yang Dapat Dikreditkan (Impor)",
     "keterangan": "Pajak Masukan atas Impor Barang Kena Pajak dan Pemanfaatan Barang/Jasa dari Luar Daerah Pabean",
     "kolom": [("no_faktur", "Nomor Faktur Pajak", "text"), ("tanggal", "Tanggal", "date"),
               ("nama_pemasok", "Nama Pemasok", "text"), ("nilai", "Nilai (DPP)", "number"),
               ("ppn", "PPN", "number")]},
    {"kode": "B-2", "judul": "Lampiran B-2 — Pajak Masukan yang Dapat Dikreditkan (Dalam Negeri)",
     "keterangan": "Pajak Masukan atas Perolehan Barang/Jasa Kena Pajak dalam Negeri",
     "kolom": [("no_faktur", "Nomor Faktur Pajak", "text"), ("tanggal", "Tanggal", "date"),
               ("nama_pemasok", "Nama Pemasok", "text"), ("nilai", "Nilai (DPP)", "number"),
               ("ppn", "PPN", "number")]},
    {"kode": "B-3", "judul": "Lampiran B-3 — Pajak Masukan yang Tidak Dikreditkan atau dengan Fasilitas",
     "keterangan": "Pajak Masukan yang Tidak Dikreditkan atau dengan Fasilitas",
     "kolom": [("no_faktur", "Nomor Faktur Pajak", "text"), ("tanggal", "Tanggal", "date"),
               ("nama_pemasok", "Nama Pemasok", "text"), ("nilai", "Nilai", "number"),
               ("ppn", "PPN", "number"), ("alasan", "Alasan", "text")]},
    {"kode": "C", "judul": "Lampiran C — Pajak yang Dipungut oleh Pihak Lain",
     "keterangan": "Daftar Pajak yang Dipungut oleh Pihak Lain",
     "kolom": [("pemungut", "Nama Pemungut", "text"), ("npwp", "NPWP", "text"),
               ("pajak", "Pajak", "number"), ("keterangan", "Keterangan", "text")]},
]


def form_for(jenis_pajak: str):
    """Kembalikan (daftar_bagian_induk, daftar_lampiran) sesuai jenis SPT."""
    if jenis_pajak == "PPh Orang Pribadi":
        return BAGIAN_INDUK_OP, LAMPIRAN_OP
    if jenis_pajak == "PPh Pasal 21/26":
        return BAGIAN_INDUK_PPH21, []
    if jenis_pajak == "PPh Unifikasi":
        return BAGIAN_INDUK_UNIFIKASI, []
    if jenis_pajak == "PPN":
        return BAGIAN_INDUK_PPN, LAMPIRAN_PPN
    if jenis_pajak == "PPh Final Pengungkapan Harta Bersih":
        return [], []
    return [], []


# --------------------------------------------------------------- skema DB
SCHEMA = """
CREATE TABLE IF NOT EXISTS wp (
  id INTEGER PRIMARY KEY, npwp TEXT UNIQUE, nama TEXT, alamat TEXT, kpp TEXT,
  telepon TEXT, email TEXT, ptkp_kode TEXT, status TEXT,
  password_hash TEXT DEFAULT '', salt TEXT DEFAULT '', role TEXT DEFAULT 'WP',
  aktif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS session (
  token TEXT PRIMARY KEY, npwp TEXT, ip TEXT, dibuat REAL, kadaluarsa REAL, csrf TEXT
);
CREATE TABLE IF NOT EXISTS percobaan_login (
  id INTEGER PRIMARY KEY AUTOINCREMENT, npwp TEXT, ip TEXT, waktu REAL,
  gagal INTEGER DEFAULT 0, terblokir_sampai REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS spt (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  npwp TEXT, jenis_pajak TEXT, jenis_spt TEXT, masa_pajak TEXT, tahun_pajak TEXT,
  periode TEXT, status_spt TEXT, status_tabel TEXT, kanal TEXT,
  tgl_jatuh_tempo TEXT, tgl_dibuat TEXT, tgl_disampaikan TEXT,
  kurang_bayar REAL DEFAULT 0, lebih_bayar REAL DEFAULT 0,
  kode_billing TEXT, deposit REAL DEFAULT 0, tanda_tangan INTEGER DEFAULT 0,
  data TEXT DEFAULT '{}', hitung TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS lampiran (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  spt_id INTEGER, kode TEXT, sub TEXT, no INTEGER, data TEXT
);
CREATE TABLE IF NOT EXISTS e_faktur (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  npwp_penjual TEXT, npwp_pembeli TEXT, nama_pembeli TEXT, masa_pajak TEXT,
  tahun_pajak TEXT, tanggal TEXT, tipe TEXT, kode_barang TEXT, nama_barang TEXT,
  jumlah REAL, harga_satuan REAL, nilai REAL, ppn REAL, ppnbm REAL, status TEXT
);
CREATE TABLE IF NOT EXISTS bupot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  npwp_pemotong TEXT, npwp_penerima TEXT, nama_penerima TEXT, masa_pajak TEXT,
  tahun_pajak TEXT, jenis TEXT, bruto REAL, dpp REAL, pajak REAL, status TEXT
);
CREATE TABLE IF NOT EXISTS billing (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kode TEXT, spt_id INTEGER, npwp TEXT, nama_pajak TEXT, jumlah REAL,
  tgl_issued TEXT, tgl_jatuh_tempo TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS deposit (
  npwp TEXT PRIMARY KEY, saldo REAL
);
CREATE TABLE IF NOT EXISTS log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, actor TEXT, aksi TEXT, detail TEXT
);
"""


def init_db():
    """Buat schema + user demo. Idempoten — aman dipanggil tiap start."""
    import security as S

    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = conn()
    c.executescript(SCHEMA)
    # Migrasi ringan: tambah kolom yang belum ada (schema lama -> baru)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(wp)").fetchall()}
    for col, ddl in (("password_hash", "TEXT DEFAULT ''"),
                     ("salt", "TEXT DEFAULT ''"),
                     ("role", "TEXT DEFAULT 'WP'"),
                     ("aktif", "INTEGER DEFAULT 1")):
        if col not in cols:
            c.execute(f"ALTER TABLE wp ADD COLUMN {col} {ddl}")

    # User demo: isi kredensial bila belum ada password-nya.
    for u in DEMO_USERS:
        row = c.execute("SELECT password_hash FROM wp WHERE npwp=?", (u["npwp"],)).fetchone()
        if row is None:
            h, s = S.hash_password(DEMO_PASSWORD)
            c.execute("""INSERT INTO wp (npwp,nama,alamat,kpp,telepon,email,ptkp_kode,status,
                         password_hash,salt,role,aktif)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
                      (u["npwp"], u["nama"], "Jl. Contoh-learning No. 1, Batam", u["kpp"],
                       "081234567890", u["email"], u["ptkp_kode"],
                       "Wajib Pajak Orang Pribadi", h, s, u["role"]))
        elif not row["password_hash"]:
            h, s = S.hash_password(DEMO_PASSWORD)
            c.execute("UPDATE wp SET password_hash=?, salt=?, role=? WHERE npwp=?",
                      (h, s, u["role"], u["npwp"]))

    # Deposit awal per WP
    for u in DEMO_USERS:
        if not c.execute("SELECT 1 FROM deposit WHERE npwp=?", (u["npwp"],)).fetchone():
            c.execute("INSERT INTO deposit (npwp,saldo) VALUES (?,?)", (u["npwp"], 150_000_000))

    c.commit()
    c.close()


def log(actor: str, aksi: str, detail: str = "", db: sqlite3.Connection | None = None):
    """Catat audit trail. Pakai koneksi yang sama bila ada (hindari database locked)."""
    c = db or conn()
    try:
        c.execute("INSERT INTO log (waktu,actor,aksi,detail) VALUES (?,?,?,?)", (now(), actor, aksi, detail))
        if db is None:
            c.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        if db is None:
            c.close()