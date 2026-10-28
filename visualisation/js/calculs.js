// Calculs de la page d'exploration, sans aucun affichage : ce sont ceux du notebook
// notebooks/EDA_Positionnement_Salarial_Comite.ipynb, refaits ici pour que la page tourne seule dans le
// navigateur, sans Python. Le même fichier se charge aussi dans Node, pour comparer ses résultats au notebook.
(function (racine) {
  'use strict';

  // ---------- Outils de statistique ----------

  // Une case vide ou du texte devient NaN : elle est ignorée dans les calculs, comme dans pandas.
  const nombre = v => (v === null || v === undefined || v === '') ? NaN : Number(v);
  const valides = t => t.filter(Number.isFinite);
  const somme = t => t.reduce((a, b) => a + b, 0);
  const moyenne = t => { const v = valides(t); return v.length ? somme(v) / v.length : NaN; };

  // Quantile avec interpolation linéaire (la méthode par défaut de numpy et de pandas).
  function quantile(t, q) {
    const v = valides(t).sort((a, b) => a - b);
    if (!v.length) return NaN;
    const pos = (v.length - 1) * q, bas = Math.floor(pos);
    return bas + 1 < v.length ? v[bas] + (pos - bas) * (v[bas + 1] - v[bas]) : v[bas];
  }
  const mediane = t => quantile(t, 0.5);

  function ecartType(t) {   // écart-type « ddof=1 », comme pandas
    const v = valides(t), m = moyenne(v);
    return Math.sqrt(somme(v.map(x => (x - m) ** 2)) / (v.length - 1));
  }

  // Coefficient d'asymétrie corrigé, la formule de pandas (Series.skew).
  function asymetrie(t) {
    const v = valides(t), n = v.length, m = moyenne(v);
    const m2 = somme(v.map(x => (x - m) ** 2)) / n, m3 = somme(v.map(x => (x - m) ** 3)) / n;
    if (n < 3 || m2 === 0) return NaN;
    return Math.sqrt(n * (n - 1)) / (n - 2) * m3 / m2 ** 1.5;
  }

  function correlation(a, b) {   // Pearson, sur les lignes où les deux valeurs existent (comme pandas)
    const x = [], y = [];
    a.forEach((v, i) => { if (Number.isFinite(v) && Number.isFinite(b[i])) { x.push(v); y.push(b[i]); } });
    const mx = moyenne(x), my = moyenne(y);
    let sxy = 0, sxx = 0, syy = 0;
    x.forEach((v, i) => { sxy += (v - mx) * (y[i] - my); sxx += (v - mx) ** 2; syy += (y[i] - my) ** 2; });
    return sxy / Math.sqrt(sxx * syy);
  }

  // Histogramme comme np.histogram : bins = nombre de barres, ou 'auto' (règle de numpy).
  function histogramme(t, bins = 'auto') {
    const v = valides(t);
    let min = Math.min(...v), max = Math.max(...v);
    if (min === max) { min -= 0.5; max += 0.5; }
    let nb = bins;
    if (bins === 'auto') {
      const sturges = (max - min) / (Math.log2(v.length) + 1);
      const fd = 2 * (quantile(v, 0.75) - quantile(v, 0.25)) * v.length ** (-1 / 3);
      nb = Math.max(1, Math.ceil((max - min) / (fd > 0 ? Math.min(fd, sturges) : sturges)));
    }
    const bords = Array.from({ length: nb + 1 }, (_, i) => min + (max - min) * i / nb);
    const effectifs = new Array(nb).fill(0);
    for (const x of v) {
      let i = Math.min(nb - 1, Math.floor((x - min) / (max - min) * nb));
      if (x < bords[i]) i--;
      else if (i < nb - 1 && x >= bords[i + 1]) i++;
      effectifs[i]++;
    }
    return { bords, effectifs, largeur: bords[1] - bords[0], centres: effectifs.map((_, i) => (bords[i] + bords[i + 1]) / 2) };
  }

  // Courbe lissée (noyau gaussien, largeur de Scott, comme scipy.stats.gaussian_kde), à la hauteur des barres.
  function courbeLissee(t, hist, nbPoints = 300) {
    const v = valides(t), n = v.length;
    const sigma = ecartType(v) * n ** (-1 / 5);
    const min = Math.min(...v), max = Math.max(...v);
    const xs = Array.from({ length: nbPoints }, (_, i) => min + (max - min) * i / (nbPoints - 1));
    const k = 1 / (n * sigma * Math.sqrt(2 * Math.PI));
    const ys = xs.map(x => {
      let s = 0;
      for (const xi of v) { const u = (x - xi) / sigma; s += Math.exp(-0.5 * u * u); }
      return s * k * n * hist.largeur;
    });
    return { x: xs, y: ys };
  }

  // Droite des moindres carrés (trendline='ols' de plotly express).
  function droite(x, y) {
    const px = [], py = [];
    x.forEach((v, i) => { if (Number.isFinite(v) && Number.isFinite(y[i])) { px.push(v); py.push(y[i]); } });
    const mx = moyenne(px), my = moyenne(py);
    let sxy = 0, sxx = 0;
    px.forEach((v, i) => { sxy += (v - mx) * (py[i] - my); sxx += (v - mx) ** 2; });
    const pente = sxy / sxx, origine = my - pente * mx;
    const xmin = Math.min(...px), xmax = Math.max(...px);
    return { x: [xmin, xmax], y: [origine + pente * xmin, origine + pente * xmax], pente };
  }

  // Courbe de tendance non linéaire LOWESS (trendline='lowess' de plotly express : frac = 2/3, 3 itérations
  // de robustesse, comme statsmodels). Calculée une fois par valeur distincte de x.
  function lowess(x, y, frac = 2 / 3, iterations = 3) {
    const pts = [];
    x.forEach((v, i) => { if (Number.isFinite(v) && Number.isFinite(y[i])) pts.push([v, y[i]]); });
    pts.sort((a, b) => a[0] - b[0]);
    const n = pts.length, xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const k = Math.max(2, Math.floor(frac * n + 1e-10));
    const uniques = [...new Set(xs)];
    let robustesse = new Array(n).fill(1), ajuste = [];
    for (let it = 0; it <= iterations; it++) {
      ajuste = [];
      let g = 0;
      for (const x0 of uniques) {
        // Les k points les plus proches de x0 forment une fenêtre continue dans les x triés.
        while (g + k < n && x0 - xs[g] > xs[g + k] - x0) g++;
        const rayon = Math.max(x0 - xs[g], xs[g + k - 1] - x0);
        let sw = 0, swx = 0, swy = 0, swxx = 0, swxy = 0;
        for (let j = g; j < g + k; j++) {
          const d = rayon > 0 ? Math.abs(xs[j] - x0) / rayon : 0;
          const w = (d < 1 ? (1 - d ** 3) ** 3 : 0) * robustesse[j];
          sw += w; swx += w * xs[j]; swy += w * ys[j]; swxx += w * xs[j] ** 2; swxy += w * xs[j] * ys[j];
        }
        const mx = swx / sw, my = swy / sw, varx = swxx / sw - mx * mx;
        ajuste.push(varx > 1e-12 * (Math.abs(mx) + 1) ** 2 ? my + (swxy / sw - mx * my) / varx * (x0 - mx) : my);
      }
      if (it === iterations) break;
      const parX = new Map(uniques.map((u, i) => [u, ajuste[i]]));
      const residus = xs.map((v, i) => ys[i] - parX.get(v));
      const s = mediane(residus.map(Math.abs));
      robustesse = residus.map(r => { const u = s > 0 ? r / (6 * s) : 0; return Math.abs(u) < 1 ? (1 - u * u) ** 2 : 0; });
    }
    return { x: uniques, y: ajuste };
  }

  // Tranche d'ancienneté, les mêmes que pour les groupes de collègues de la détection (src/anomaly_pretraitement.py).
  const TRANCHES = ['0-2', '3-5', '6-12', '13-20', '>20'];
  function tranche(annees) {
    if (!Number.isFinite(annees) || annees < 0) return null;
    return annees <= 2 ? '0-2' : annees <= 5 ? '3-5' : annees <= 12 ? '6-12' : annees <= 20 ? '13-20' : '>20';
  }

  // Position du salaire dans la fourchette du marché du métier + niveau (P25, médiane, P75).
  const POSITIONS_MARCHE = ['Sous le P25', 'Entre P25 et médiane', 'Entre médiane et P75', 'Au-dessus du P75'];
  function positionMarche(l) {
    const s = l.Fixe_Annuel_MAD;
    if (![s, l.Market_P25, l.Median, l.Market_P75].every(Number.isFinite)) return null;
    return POSITIONS_MARCHE[s < l.Market_P25 ? 0 : s < l.Median ? 1 : s <= l.Market_P75 ? 2 : 3];
  }

  // ---------- Étape 0 : sources, doublons, contrôles et indicateurs ----------

  const COLONNES_REQUISES = {
    employes: ['Matricule', 'Job_Family', 'Job_Title', 'Niveau', 'Entite_N1', 'Sexe', 'Fixe_Annuel_MAD', 'Age',
               'Anciennete', 'Competence_N1', 'Positionnement_9BOX', 'Hot_job'],
    bands: ['Job_Family', 'Niveau', 'Min', 'Mid', 'Max'],
    market: ['Job_Family', 'Niveau', 'Median'],
  };

  function colonnesManquantes(tables) {
    const manque = {};
    for (const [nom, cols] of Object.entries(COLONNES_REQUISES)) {
      const presentes = new Set(Object.keys(tables[nom][0] || {}));
      const m = cols.filter(c => !presentes.has(c));
      if (m.length) manque[nom] = m;
    }
    return manque;
  }

  function preparer({ employes, bands, market }) {
    const cle = (jf, g) => String(jf) + '|' + String(g);
    // Dédoublonnage sur le Matricule : la première ligne est gardée.
    const vus = new Set(), emp = [];
    for (const e of employes) { if (vus.has(e.Matricule)) continue; vus.add(e.Matricule); emp.push(e); }
    // Grille et marché retrouvés par métier + niveau.
    const grille = new Map(), marche = new Map();
    for (const b of bands) if (!grille.has(cle(b.Job_Family, b.Niveau))) grille.set(cle(b.Job_Family, b.Niveau), b);
    for (const m of market) if (!marche.has(cle(m.Job_Family, m.Niveau))) marche.set(cle(m.Job_Family, m.Niveau), m);

    const df = emp.map(e => {
      const b = grille.get(cle(e.Job_Family, e.Niveau)) || {}, m = marche.get(cle(e.Job_Family, e.Niveau)) || {};
      const l = {
        Matricule: e.Matricule, Nom: e.Nom, Job_Title: e.Job_Title, Job_Family: e.Job_Family, Entite_N1: e.Entite_N1,
        Sexe: e.Sexe, Niveau: nombre(e.Niveau), Fixe_Annuel_MAD: nombre(e.Fixe_Annuel_MAD), Age: nombre(e.Age),
        Anciennete: nombre(e.Anciennete), Competence_N1: nombre(e.Competence_N1),
        Positionnement_9BOX: nombre(e.Positionnement_9BOX), Hot_job: nombre(e.Hot_job),
        Min: nombre(b.Min), Mid: nombre(b.Mid), Max: nombre(b.Max), Median: nombre(m.Median),
        // P25 et P75 du marché : facultatifs, ils servent seulement au graphe de positionnement face au marché.
        Market_P25: nombre(m.P25), Market_P75: nombre(m.P75),
      };
      l.Age_Embauche = l.Age - l.Anciennete;
      l.Tranche_Anciennete = tranche(l.Anciennete);
      l.Compa_Ratio = l.Fixe_Annuel_MAD / l.Mid;
      l.Range_Penetration = (l.Fixe_Annuel_MAD - l.Min) / (l.Max - l.Min);
      l.Market_Ratio = l.Fixe_Annuel_MAD / l.Median;
      l.Ratio_Grille_Marche = l.Mid / l.Median;
      l.Amplitude_Grille = (l.Max - l.Min) / l.Mid;
      l.Position_Marche = positionMarche(l);
      return l;
    });

    // Postes (Job_Title) qui ont plusieurs valeurs de Hot_job.
    const hotjob = new Map();
    for (const l of df) {
      if (l.Job_Title === null || l.Job_Title === undefined || !Number.isFinite(l.Hot_job)) continue;
      if (!hotjob.has(l.Job_Title)) hotjob.set(l.Job_Title, new Set());
      hotjob.get(l.Job_Title).add(l.Hot_job);
    }
    const controles = {
      lignesInitiales: employes.length,
      lignesRetenues: df.length,
      doublons: employes.length - df.length,
      sansGrille: df.filter(l => !Number.isFinite(l.Mid)).length,
      sansMarche: df.filter(l => !Number.isFinite(l.Median)).length,
      ageEmbaucheIncoherent: df.filter(l => l.Age_Embauche < 18).length,
      postesPlusieursHotjob: [...hotjob.values()].filter(s => s.size > 1).length,
      sousMin: df.filter(l => l.Fixe_Annuel_MAD < l.Min).length,
      surMax: df.filter(l => l.Fixe_Annuel_MAD > l.Max).length,
    };
    return { df, controles };
  }

  const colonne = (df, c) => df.map(l => l[c]);

  // Les valeurs distinctes d'une colonne, triées (nombres, puis texte).
  function modalites(df, c) {
    return [...new Set(df.map(l => l[c]).filter(v => v !== null && v !== undefined && !(typeof v === 'number' && isNaN(v))))]
      .sort((a, b) => (typeof a === 'number' && typeof b === 'number') ? a - b : String(a).localeCompare(String(b), 'fr'));
  }

  // Les modalités triées par médiane décroissante d'une colonne (ordre des boîtes du notebook).
  function ordreParMediane(df, groupe, valeur) {
    return modalites(df, groupe)
      .map(g => [g, mediane(df.filter(l => l[groupe] === g).map(l => l[valeur]))])
      .sort((a, b) => b[1] - a[1]).map(x => x[0]);
  }

  const api = {
    nombre, somme, moyenne, mediane, quantile, ecartType, asymetrie, correlation, histogramme, courbeLissee, droite, lowess,
    TRANCHES, tranche, POSITIONS_MARCHE, positionMarche, COLONNES_REQUISES, colonnesManquantes, preparer, colonne, modalites, ordreParMediane,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (racine.Exploration = racine.Exploration || {}).calculs = api;
})(this);
