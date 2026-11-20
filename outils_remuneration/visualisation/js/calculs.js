// Calculs de la page d'exploration, sans aucun affichage : ce sont ceux du notebook
// notebooks/EDA_Positionnement_Salarial_Comite.ipynb, refaits ici pour que la page tourne seule dans le
// navigateur, sans Python. Le même fichier se charge aussi dans Node, pour comparer ses résultats au notebook.
(function (racine) {
  'use strict';

  // ---------- Outils de statistique ----------

  // Une case vide ou du texte devient NaN : elle est ignorée dans les calculs, comme dans pandas.
  const nombre = v => (v === null || v === undefined || v === '') ? NaN : Number(v);
  // Un texte (le diplôme) : une case vide ou faite d'espaces devient null, comme une case vide dans pandas.
  const texte = v => (v === null || v === undefined || String(v).trim() === '') ? null : String(v).trim();
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

  // Découpe une valeur en tranches écrites comme dans la présentation « Analyse prédictive des départs » (RPB, 30/08/2024),
  // pour que la page parle la même langue que les supports habituels : « inf à 2 », « [2, 4[ », …, « sup à 14 ».
  // « [2, 4[ » veut dire « de 2 compris à 4 non compris » : 3,9 ans tombe dans [2, 4[, 4 ans pile dans [4, 6[.
  // « sup à 14 » prend tout ce qui vaut 14 ou plus, comme dans la présentation, où [12, 14[ s'arrête juste avant.
  function libellesTranches(bornes) {
    return [`inf à ${bornes[0]}`, ...bornes.slice(1).map((b, i) => `[${bornes[i]}, ${b}[`), `sup à ${bornes[bornes.length - 1]}`];
  }
  function trancheDe(valeur, bornes, libelles) {
    if (!Number.isFinite(valeur)) return null;   // case vide : aucune tranche, plutôt qu'une fausse
    const i = bornes.findIndex(b => valeur < b);
    return libelles[i < 0 ? bornes.length : i];
  }

  // Tranches d'ancienneté : inf à 2, [2, 5[, puis des pas de 5 ans ([5, 10[, [10, 15[…), la dernière « sup à … ».
  // Pourquoi pas des tranches de 2 ans partout (avant, comme la présentation des départs) : au-delà de 5 ans, une
  // différence de 2 ans ne change plus grand-chose, et sur une banque où certains ont 30 ou 40 ans de maison, il
  // fallait une quinzaine de barres. Les deux premières tranches restent courtes : les premières années (arrivée,
  // confirmation) sont celles où tout bouge.
  // Pourquoi pas un pas « optimal » au sens des statistiques (règle de Freedman-Diaconis, comme pour un histogramme) :
  // il tombe sur des largeurs comme 3,7 ans, illisibles pour un comité. Ce qui est calculé, c'est où s'arrêter : la
  // dernière borne est la première qui dépasse l'ancienneté de 95 % des salariés (lue dans le fichier entier, pas dans
  // le filtre, pour que les tranches ne changent pas d'un filtre à l'autre). Les 5 % les plus anciens sont regroupés
  // dans « sup à … », comme les salaires extrêmes dans les tranches de salaire : sinon, deux ou trois salariés à 40 ans
  // de maison étireraient le graphe sur des barres presque vides. Et s'il fallait plus de 8 tranches après 5 ans, le
  // pas passe à 10 ans. La détection, elle, garde ses propres tranches (src/anomaly_pretraitement.py n'est pas touché).
  function tranchesAnciennete(valeurs) {
    const v = valides(valeurs).filter(a => a >= 0), haut = v.length ? quantile(v, 0.95) : 0;
    const pas = (haut - 5) / 5 > 8 ? 10 : 5, bornes = [2, 5];
    // La borne suivante est le multiple du pas juste au-dessus : 5 → 10 → 15 (pas de 5) ou 5 → 10 → 20 (pas de 10).
    while (bornes[bornes.length - 1] < haut) bornes.push((Math.floor(bornes[bornes.length - 1] / pas) + 1) * pas);
    const libelles = libellesTranches(bornes);
    // Une ancienneté négative est une erreur de saisie : pas de tranche.
    return { bornes, libelles, tranche: a => a < 0 ? null : trancheDe(a, bornes, libelles) };
  }

  // Le niveau d'études (colonne Niveau_Etude_Max, facultative) : son rang, pour ranger les niveaux du moins au plus élevé
  // dans le filtre « Diplôme ». C'est la même table que RANG_NIVEAU_ETUDE dans src/anomaly_pretraitement.py. Un niveau
  // absent de la table (« NON DETERMINE ») va à la fin.
  const RANG_ETUDE = { 'SECONDAIRE': 0, 'BAC': 1, 'BAC+1': 2, 'BAC+2': 3, 'BAC+3': 4, 'BAC+4': 5, 'BAC+5': 6, 'BAC+6': 6,
    'BAC+7': 7, 'EXPERTISE COMPTABLE': 7 };
  // Les espaces et les majuscules ne comptent pas : « Bac + 5 » vaut « BAC+5 », comme dans le Python.
  const SANS_ESPACES = Object.fromEntries(Object.entries(RANG_ETUDE).map(([n, r]) => [n.replace(/\s+/g, ''), r]));
  const rangEtude = n => SANS_ESPACES[String(n).replace(/\s+/g, '').toUpperCase()];
  function niveauxEtude(df) {
    const r = n => rangEtude(n) ?? 99;
    return modalites(df, 'Niveau_Etude_Max').sort((a, b) => r(a) - r(b) || String(a).localeCompare(String(b), 'fr'));
  }

  // Tranches d'âge de 5 ans, celles de la présentation des départs. Elle s'arrêtait à [50, 55[ parce qu'elle ne comptait
  // que des démissionnaires, souvent jeunes ; ici, tous les salariés sont comptés, donc les tranches vont jusqu'à 60.
  const BORNES_AGE = [25, 30, 35, 40, 45, 50, 55, 60];
  const TRANCHES_AGE = libellesTranches(BORNES_AGE);
  const trancheAge = age => age < 0 ? null : trancheDe(age, BORNES_AGE, TRANCHES_AGE);

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
        // Pourquoi en texte (10/11/2026) : le fichier donne le positionnement 9-Box en six catégories (« Talents »…) et la
        // performance N-1 en cinq libellés ; la page les lit tels quels (voir ORDRE_9BOX). Case vide → null.
        Positionnement_9BOX: texte(e.Positionnement_9BOX), Performance_N1: texte(e.Performance_N1), Hot_job: nombre(e.Hot_job),
        Min: nombre(b.Min), Mid: nombre(b.Mid), Max: nombre(b.Max), Median: nombre(m.Median),
        // P25 et P75 du marché : facultatifs, ils servent seulement au graphe de positionnement face au marché.
        Market_P25: nombre(m.P25), Market_P75: nombre(m.P75),
        // Le diplôme : facultatif, il sert au filtre « Diplôme » et à la liste des salariés. Case vide → null.
        Niveau_Etude_Max: texte(e.Niveau_Etude_Max), Cat_Ecole_Max: texte(e.Cat_Ecole_Max),
      };
      l.Age_Embauche = l.Age - l.Anciennete;
      l.Tranche_Age = trancheAge(l.Age);
      l.Compa_Ratio = l.Fixe_Annuel_MAD / l.Mid;
      l.Range_Penetration = (l.Fixe_Annuel_MAD - l.Min) / (l.Max - l.Min);
      l.Market_Ratio = l.Fixe_Annuel_MAD / l.Median;
      l.Ratio_Grille_Marche = l.Mid / l.Median;
      l.Amplitude_Grille = (l.Max - l.Min) / l.Mid;
      l.Position_Marche = positionMarche(l);
      return l;
    });
    // Les tranches d'ancienneté se calculent sur tous les salariés à la fois (voir tranchesAnciennete).
    const ta = tranchesAnciennete(colonne(df, 'Anciennete'));
    for (const l of df) l.Tranche_Anciennete = ta.tranche(l.Anciennete);

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

  // ---------- Positionnement 9-Box et performance N-1 ----------
  // Les six catégories du positionnement 9-Box, de la meilleure à celle qui demande une décision, avec les couleurs du
  // tableau de bord RH (capture du 09/11/2026). Le positionnement est LU dans le fichier des salariés, jamais recalculé.
  const ORDRE_9BOX = ['Hauts Potentiels', 'Talents', 'Performers', 'A repositionner', 'A développer', 'Décisions requises'];
  const COULEURS_9BOX = { 'Hauts Potentiels': '#2a9d8f', 'Talents': '#7b5ea7', 'Performers': '#e9c46a',
    'A repositionner': '#f4a261', 'A développer': '#8ab17d', 'Décisions requises': '#aab2bb' };
  // Les cinq libellés de la performance N-1, du plus bas au plus haut.
  const ORDRE_PERFORMANCE = ['Très en dessous', "Proche de l'objectif", "A l'objectif", "Supérieur à l'objectif", 'Très au-delà'];
  // Les valeurs d'une colonne dans l'ordre donné, puis celles que l'ordre ne connaît pas (écrites autrement dans un autre
  // fichier), par ordre alphabétique : aucune n'est perdue.
  function dansOrdre(df, c, ordre) {
    const v = modalites(df, c);
    return [...ordre.filter(x => v.includes(x)), ...v.filter(x => !ordre.includes(x))];
  }
  const cases9Box = df => dansOrdre(df, 'Positionnement_9BOX', ORDRE_9BOX);
  const performances = df => dansOrdre(df, 'Performance_N1', ORDRE_PERFORMANCE);

  // Les modalités triées par médiane décroissante d'une colonne (ordre des boîtes du notebook). Un groupe sans
  // aucune valeur (pas de médiane) va à la fin, comme dans pandas : sinon il dérègle le tri de tous les autres.
  function ordreParMediane(df, groupe, valeur) {
    return modalites(df, groupe)
      .map(g => [g, mediane(df.filter(l => l[groupe] === g).map(l => l[valeur]))])
      .sort((a, b) => (Number.isFinite(b[1]) - Number.isFinite(a[1])) || b[1] - a[1]).map(x => x[0]);
  }

  const api = {
    nombre, somme, moyenne, mediane, quantile, ecartType, asymetrie, correlation, histogramme, courbeLissee, droite, lowess,
    libellesTranches, trancheDe, tranchesAnciennete, niveauxEtude, TRANCHES_AGE, trancheAge, POSITIONS_MARCHE, positionMarche, COLONNES_REQUISES, colonnesManquantes, preparer, colonne, modalites, ordreParMediane,
    ORDRE_9BOX, COULEURS_9BOX, ORDRE_PERFORMANCE, cases9Box, performances,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (racine.Exploration = racine.Exploration || {}).calculs = api;
})(this);
