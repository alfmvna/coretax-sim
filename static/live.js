/* Live hitung SPT di browser — field .rov.calc & ringkasan (.sum-row) di-update
   begitu input berubah, seperti perilaku Coretax DJP asli.
   Tarif & PTKP: cerminan tax.py (PP 58/2023, PMK 168/2023, UU HPP, PMK 101/2016). */
(function () {
  const N = v => {
    const s = String(v || '').trim().replace(/Rp|\s/g, '');
    if (!s) return 0;
    if (s.includes(',') && s.includes('.')) return parseFloat(s.replace(/\./g, '').replace(',', '.')) || 0;
    if (s.includes(',')) return parseFloat(s.replace(',', '.')) || 0;
    return parseFloat(s) || 0;
  };

  const PASAL17 = [[60e6, .05], [250e6, .15], [500e6, .25], [5e9, .30], [null, .35]];
  const p17 = pkp => {
    let t = 0, s = pkp, b = 0;
    for (const [lim, r] of PASAL17) {
      if (lim === null) { t += s * r; break; }
      const w = lim - b;
      if (s <= w) { t += s * r; break; }
      t += w * r; s -= w; b = lim;
    }
    return t;
  };

  const PTKP = { "TK/0": 54e6, "TK/1": 58.5e6, "TK/2": 63e6, "TK/3": 67.5e6,
                 "K/0": 58.5e6, "K/1": 63e6, "K/2": 67.5e6, "K/3": 72e6, "K/I/0": 112.5e6 };

  const TER_A = [[5.4e6, 0], [5.65e6, .0025], [5.95e6, .005], [6.3e6, .0075], [6.75e6, .01],
    [7.5e6, .0125], [8.55e6, .015], [9.65e6, .02], [10.05e6, .0225], [10.35e6, .025],
    [10.7e6, .03], [11.05e6, .035], [11.6e6, .04], [12.5e6, .05], [13.75e6, .06],
    [15.1e6, .07], [16.95e6, .08], [19.75e6, .09], [24.15e6, .10], [26.45e6, .11],
    [28e6, .12], [30.05e6, .13], [32.4e6, .14], [35.4e6, .15], [39.1e6, .16],
    [43.85e6, .17], [47.8e6, .18], [51.4e6, .19], [56.3e6, .20], [62.2e6, .21],
    [68.6e6, .22], [77.5e6, .23], [89e6, .24], [103e6, .25], [125e6, .26],
    [157e6, .27], [206e6, .28], [337e6, .29], [454e6, .30], [550e6, .31],
    [695e6, .32], [910e6, .33], [null, .34]];
  const TER_B = [[6.2e6, 0], [6.5e6, .0025], [6.85e6, .005], [7.3e6, .0075], [9.2e6, .01],
    [10.75e6, .015], [11.25e6, .02], [11.6e6, .025], [12.6e6, .03], [13.6e6, .04],
    [14.95e6, .05], [16.4e6, .06], [18.45e6, .07], [21.85e6, .08], [26e6, .09],
    [27.7e6, .10], [29.35e6, .11], [31.45e6, .12], [33.95e6, .13], [37.1e6, .14],
    [41.1e6, .15], [45.8e6, .16], [49.5e6, .17], [53.8e6, .18], [58.5e6, .19],
    [64e6, .20], [71e6, .21], [80e6, .22], [93e6, .23], [109e6, .24], [129e6, .25],
    [163e6, .26], [211e6, .27], [374e6, .28], [459e6, .29], [555e6, .30], [704e6, .31],
    [957e6, .32], [null, .33]];
  const TER_C = [[6.6e6, 0], [6.95e6, .0025], [7.35e6, .005], [7.8e6, .0075], [8.85e6, .01],
    [9.8e6, .015], [10.95e6, .02], [11.2e6, .03], [12.05e6, .04], [12.95e6, .05],
    [14.15e6, .06], [15.55e6, .07], [17.05e6, .08], [19.5e6, .09], [22.7e6, .10],
    [29.35e6, .11], [30.35e6, .12], [32.5e6, .13], [35e6, .14], [38.6e6, .15],
    [43e6, .16], [47.4e6, .17], [51.2e6, .18], [55.8e6, .19], [60.4e6, .20],
    [66.7e6, .21], [74.5e6, .22], [86e6, .23], [103e6, .24], [124e6, .25],
    [157e6, .26], [206e6, .27], [337e6, .28], [454e6, .29], [550e6, .30],
    [695e6, .31], [910e6, .32], [null, .33]];
  const TER_HARIAN = [[450e3, 0], [2.5e6, .005]];

  const KAT = { "TK/0": "A", "TK/1": "A", "K/0": "A", "TK/2": "B", "TK/3": "B",
                "K/1": "B", "K/2": "B", "K/3": "C", "K/I/0": "C" };
  const terRate = (tab, v) => {
    for (const [lim, r] of tab) if (lim === null || v <= lim) return r;
    return 0;
  };
  const F = n => new Intl.NumberFormat('id-ID',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);

  function fieldVal(name) {
    const el = document.querySelector('[name="' + name + '"]');
    if (!el) return 0;
    if (el.type === 'radio') {
      const c = document.querySelector('[name="' + name + '"]:checked');
      return c ? c.value : '';
    }
    return N(el.value);
  }

  function setCalc(label, value) {
    document.querySelectorAll('.rov.calc').forEach(el => {
      const lb = el.parentElement && el.parentElement.querySelector('label');
      if (lb && lb.textContent.trim() === label) el.textContent = F(value);
    });
  }

  function setSum(label, value) {
    document.querySelectorAll('.sum-row').forEach(r => {
      const sp = r.querySelector('span'), b = r.querySelector('b');
      if (sp && b && sp.textContent.trim() === label) b.textContent = F(value);
    });
  }

  function compute() {
    if (!document.querySelector('.rov.calc') && !document.querySelector('.sum')) return;

    /* ---- SPT Tahunan PPh Orang Pribadi ---- */
    const neto = fieldVal('q_2');
    const pengNeto = fieldVal('pengurang_neto');
    const neto2 = Math.max(0, neto - pengNeto);
    // PTKP dikirim server lewat data-ptkp pada <body> (form SPT tidak punya field ini).
    const ptkpCode = (document.body && document.body.dataset.ptkp) || 'K/0';
    const ptkp = PTKP[ptkpCode] || 54e6;
    const pkp = Math.max(0, neto2 - ptkp);
    const pphTerutang = p17(pkp);
    const pengPph = fieldVal('pengurang_pph');
    const pphSetelah = Math.max(0, pphTerutang - pengPph);
    // kredit = bukti potong (lampiran L-1 bagian E) + angsuran 25 + STP
    const kredit = fieldVal('kredit_dipotong')
      + fieldVal('q_10b') + fieldVal('q_10c') + fieldVal('kredit_luar_negeri');
    const kurangBayar = pphSetelah - kredit;
    const pengangsuran = fieldVal('nilai_pengangsuran');
    const masihBayar = Math.max(0, kurangBayar - pengangsuran);
    const angsuran = pphSetelah / 12;

    setCalc('Penghasilan neto setelah pengurang penghasilan neto (2-3)', neto2);
    setCalc('Penghasilan tidak kena pajak', ptkp);
    setCalc('Penghasilan kena pajak (4-5)', pkp);
    setCalc('PPh terutang', pphTerutang);
    setCalc('PPh terutang setelah pengurang PPh terutang (7-8)', pphSetelah);
    setCalc('Jumlah kredit pajak (dihitung otomatis dari bukti potong, angsuran 25, STP, dan kredit luar negeri)', kredit);
    setCalc('PPh kurang/lebih bayar (9-10a-10b-10c+10d)', kurangBayar);
    setCalc('PPh yang masih harus dibayar (11a-11b)', masihBayar);
    setCalc('Angsuran PPh Pasal 25 tahun berikutnya', angsuran);

    setSum('Penghasilan neto setahun', neto);
    setSum('Pengurang penghasilan neto', pengNeto);
    setSum('Penghasilan neto setelah pengurang', neto2);
    setSum('Penghasilan tidak kena pajak (PTKP)', ptkp);
    setSum('Penghasilan kena pajak', pkp);
    setSum('PPh terutang', pphTerutang);
    setSum('Pengurang PPh terutang', pengPph);
    setSum('PPh terutang setelah pengurang', pphSetelah);
    setSum('Kredit pajak', kredit);
    setSum('PPh kurang/lebih bayar', kurangBayar);
    setSum('PPh yang masih harus dibayar', masihBayar);
    setSum('Angsuran PPh Pasal 25 tahun berikutnya', angsuran);

    /* ---- SPT Masa PPN ---- */
    const dppK = fieldVal('dpp_keluar'), dppM = fieldVal('dpp_masuk'), ppnbm = fieldVal('ppnbm');
    const ppnK = dppK * 0.11, ppnM = dppM * 0.11, ppnT = ppnK - ppnM + ppnbm;
    setCalc('PPN Keluaran', ppnK);
    setCalc('PPN Masukan', ppnM);
    setCalc('PPN Terutang', ppnT);
    setCalc('PPN Kurang Bayar', ppnT);
    setSum('PPN keluaran', ppnK);
    setSum('PPN masukan', ppnM);
    setSum('PPnBM', ppnbm);
    setSum('PPN terutang', ppnT);
    setSum('PPN kurang bayar', ppnT);

    /* ---- SPT Masa PPh 21/26 (total sudah dihitung server) ---- */
    const tBruto = fieldVal('total_bruto');
    const tPajak = fieldVal('total_pajak');
    if (tBruto || tPajak) {
      setSum('Total penghasilan bruto', tBruto);
      setSum('Total pajak', tPajak);
      setSum('Pajak yang harus dibayar', tPajak);
    }

    /* ---- status line ---- */
    const sl = document.querySelector('.status-line');
    if (sl) {
      const bs = sl.querySelectorAll('b');
      const posisi = bs[1] ? bs[1].textContent : '';
      const jtt = bs[2] ? bs[2].textContent : '';
      const st = kurangBayar > 0 ? 'Kurang Bayar' : (kurangBayar < 0 ? 'Lebih Bayar' : 'Nihil');
      sl.innerHTML = 'Status: <b>' + st + '</b> · Posisi: <b>' + posisi +
        '</b> · Jatuh tempo: <b>' + jtt + '</b>';
    }
  }

  document.addEventListener('input', e => {
    if (e.target.matches('input,select,textarea')) compute();
  });
  document.addEventListener('change', e => {
    if (e.target.matches('input,select,textarea')) compute();
  });
  if (document.querySelector('.rov.calc')) compute();
})();