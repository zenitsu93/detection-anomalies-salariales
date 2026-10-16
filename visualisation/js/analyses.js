// Les analyses reprises du notebook EDA_Positionnement_Salarial_Comite.ipynb, une fonction par graphe.
(function (E) {
  'use strict';
  const C = E.calculs, F = E.filtres;
  const { fr, signe, echapper, constat, COULEURS: K, transparent,
    nomAxe, titreAxe, grille, montrer, boite, barresEtCourbe, ligneH, indices, texteGrade } = E.communs;
  const logPositif = x => x > 0 ? Math.log(x) : NaN;

  // Écart hommes / femmes en % : salaire moyen, puis Compa-Ratio moyen (à grille et métier constants).
  function ecartsFH(lignes) {
    const moyenne = (s, c) => C.moyenne(lignes.filter(l => l.Sexe === s).map(l => l[c]));
    return [(moyenne('M', 'Fixe_Annuel_MAD') / moyenne('F', 'Fixe_Annuel_MAD') - 1) * 100, (moyenne('M', 'Compa_Ratio') / moyenne('F', 'Compa_Ratio') - 1) * 100];
  }

  // ---------- Salaire brut et logarithme ----------

  function distribution(df, survol) {
    const sal = C.colonne(df, 'Fixe_Annuel_MAD'), logsal = sal.map(logPositif), asym = [C.asymetrie(sal), C.asymetrie(logsal)];
    const L = grille({ lignes: 2, colonnes: 2, hauteurs: [0.76, 0.24], espV: 0.06, xPartage: true,
      titres: [`Salaire brut <span style="color:${K.GRIS}">· asymétrie ${fr(asym[0], 2)}</span>`, `Logarithme du salaire <span style="color:${K.GRIS}">· asymétrie ${fr(asym[1], 2)}</span>`] });
    const traces = [];
    [[sal, 'Fixe_Annuel_MAD (kMAD)'], [logsal, 'Log(Fixe_Annuel_MAD)']].forEach(([v, nom], c) => {
      const haut = nomAxe(c + 1), bas = nomAxe(c + 3);
      traces.push(...barresEtCourbe(v, 'auto', { xaxis: 'x' + haut, yaxis: 'y' + haut }));
      // En bas : boîte à moustaches ; la souris sur un point isolé dit de quel salarié il s'agit.
      traces.push(boite(K.ARDOISE, { x: v, orientation: 'h', name: '', text: survol, showlegend: false, xaxis: 'x' + bas, yaxis: 'y' + bas }));
      L['xaxis' + bas].title = titreAxe(nom);
      L['yaxis' + haut].title = titreAxe('Nombre de salariés');
      Object.assign(L['yaxis' + bas], { showticklabels: false, showgrid: false });
    });
    montrer('g-distribution', traces, L, 560);
    constat('s-distribution', `asymétrie de ${fr(asym[0], 2)} pour le salaire brut et de ${fr(asym[1], 2)} pour son logarithme. Plus le coefficient est proche de 0, plus la distribution est symétrique.`);
  }

  // ---------- Grades, grille et marché (filtrable par métier) ----------

  function grilleEtMarche(df, survol, sel) {
    const { lignes, survol: surv } = F.sousEnsemble(df, survol, sel);
    const grades = C.modalites(lignes, 'Grade'), g = grades.map(String);
    const moy = c => grades.map(gr => C.moyenne(lignes.filter(l => l.Grade === gr).map(l => l[c])));
    // Avec un métier choisi, la grille et le marché sont exactement ceux du métier (et non une moyenne de métiers).
    const moyenne = sel.metier === null ? ', moyenne' : '';
    const L = grille({ colonnes: 2, titres: ['Salaires réels, grille interne et marché par grade', 'Position dans la bande salariale (Range Penetration)'] });
    const traces = [
      // Bande [Min - Max] en premier, pour qu'elle passe sous les boîtes : le Max, puis le Min colorié jusqu'au Max.
      { type: 'scatter', x: g, y: moy('Max'), mode: 'lines', line: { width: 0 }, showlegend: false, hoverinfo: 'skip' },
      { type: 'scatter', x: g, y: moy('Min'), mode: 'lines', line: { width: 0 }, fill: 'tonexty', fillcolor: transparent(K.OR, 0.18), name: `Bande de la grille [Min - Max]${moyenne}`, hoverinfo: 'skip' },
      // Boîtes à fond blanc : elles se détachent de la bande de la grille.
      boite(K.ARDOISE, { x: lignes.map(l => texteGrade(l.Grade)), y: lignes.map(l => l.Fixe_Annuel_MAD), text: surv, name: 'Salaires réels', fillcolor: 'rgba(255,255,255,0.92)' }),
      { type: 'scatter', x: g, y: moy('Mid'), mode: 'lines+markers', line: { color: K.BRUN, width: 2.5 }, marker: { size: 8 }, name: `Milieu de grille (Mid)${moyenne}`,
        hovertemplate: 'Grade %{x}<br>Mid : %{y:.1f} kMAD<extra></extra>' },
      { type: 'scatter', x: g, y: moy('Median'), mode: 'lines+markers', line: { color: K.BLEU, width: 2.5, dash: 'dash' }, marker: { size: 8, symbol: 'diamond' },
        name: `Médiane du marché${moyenne}`, hovertemplate: 'Grade %{x}<br>Médiane marché : %{y:.1f} kMAD<extra></extra>' },
      ...barresEtCourbe(lignes.map(l => l.Range_Penetration), 40, { xaxis: 'x2', yaxis: 'y2' }),
    ];
    // 'category' : chaque grade prend la même largeur, même si des numéros de grade manquent.
    Object.assign(L.xaxis, { type: 'category', categoryorder: 'array', categoryarray: g, title: titreAxe('Grade') });
    L.yaxis.title = titreAxe('Fixe_Annuel_MAD (kMAD)');
    L.xaxis2.title = titreAxe('0 = Min · 0,5 = Mid · 1 = Max');
    L.yaxis2.title = titreAxe('Nombre de salariés');
    L.legend = { traceorder: 'normal' };   // sinon plotly inverse la légende à cause de la zone coloriée
    for (const [x, couleur, trait, texte, cote] of [[0, K.ROUGE, 'dash', 'Min', 'right'], [0.5, K.BRUN, 'solid', 'Mid', 'left'], [1, K.ROUGE, 'dash', 'Max', 'left']]) {
      L.shapes.push({ type: 'line', xref: 'x2', x0: x, x1: x, yref: 'y2 domain', y0: 0, y1: 1, line: { color: couleur, dash: trait, width: 1.5 } });
      L.annotations.push({ text: texte, x, xref: 'x2', y: 1, yref: 'y2 domain', xanchor: cote, yanchor: 'top', xshift: cote === 'left' ? 4 : -4,
        showarrow: false, font: { size: 11, color: K.GRIS } });
    }
    montrer('g-grille', traces, L, 520);
    // Le décompte des salariés hors grille n'est pas répété ici : il est dans les chiffres clés et dans le graphe « Salaires hors grille ».
    const position = lignes.map(l => l.Range_Penetration);
    constat('s-grille', `${F.libelle(sel)} (${fr(lignes.length)} salariés) : position médiane dans la bande ${fr(C.mediane(position), 2)} (0 = Min, 1 = Max) ; la moitié des salariés se situe entre ${fr(C.quantile(position, 0.25), 2)} et ${fr(C.quantile(position, 0.75), 2)}. Le détail des salariés hors grille est dans le graphe « Salaires hors grille ».`);
  }

  // ---------- Familles de métier (filtrable par grade) ----------

  function metiers(df, survol, sel) {
    const { lignes, survol: surv } = F.sousEnsemble(df, survol, sel);
    const ordre = C.ordreParMediane(lignes, 'Job_Family', 'Compa_Ratio');
    const L = grille({ lignes: 2, espV: 0.12, xPartage: true,
      titres: ['Position dans la grille : Compa-Ratio = Salaire / Mid', 'Compétitivité de la grille face au marché : Mid / Median'] });
    const traces = [];
    [['Compa_Ratio', ''], ['Ratio_Grille_Marche', '2']].forEach(([c, s]) => ordre.forEach(jf => {
      const idx = indices(lignes, l => l.Job_Family === jf);
      traces.push(boite(K.ARDOISE, { x: idx.map(() => jf), y: idx.map(i => lignes[i][c]), text: idx.map(i => surv[i]), name: jf, showlegend: false,
        xaxis: 'x' + s, yaxis: 'y' + s }));
      L['yaxis' + s].title = titreAxe(c);
    }));
    for (const s of ['', '2']) Object.assign(L['xaxis' + s], { categoryorder: 'array', categoryarray: ordre });
    L.xaxis2.tickangle = -35;
    // Les lignes de repère sont nommées dans la légende : un texte posé sur le graphe cacherait des boîtes.
    L.shapes.push(ligneH('', 1, K.BRUN, { name: 'Cible : milieu de grille (Compa-Ratio = 1)', showlegend: true }),
                  ligneH('2', 1, K.PALE, { name: 'Parité grille = marché (Mid = Median)', showlegend: true }));
    L.boxmode = 'overlay';   // une seule boîte par métier, centrée sur son nom
    montrer('g-metiers', traces, L, 760);
    const med = ordre.map(jf => [jf, C.mediane(lignes.filter(l => l.Job_Family === jf).map(l => l.Compa_Ratio))]);
    constat('s-metiers', med.length ? `${F.libelle(sel)} : Compa-Ratio médian le plus haut pour ${echapper(med[0][0])} (${fr(med[0][1], 2)}), le plus bas pour ${echapper(med[med.length - 1][0])} (${fr(med[med.length - 1][1], 2)}). Les métiers sont rangés du plus haut au plus bas.` : 'Aucun salarié pour ce filtre.');
  }

  // ---------- Ancienneté (par tranche) et âge à l'embauche (filtrable par grade et métier) ----------

  function anciennete(df, survol, sel) {
    const { lignes, survol: surv } = F.sousEnsemble(df, survol, sel);
    const L = grille({ colonnes: 2, titres: ["Compa-Ratio par tranche d'ancienneté", "Compa-Ratio selon l'âge à l'embauche (Age − Anciennete)"] });
    const medianes = C.TRANCHES.map(t => { const v = lignes.filter(l => l.Tranche_Anciennete === t).map(l => l.Compa_Ratio); return [v.length ? C.mediane(v) : null, v.length]; });
    const y = lignes.map(l => l.Compa_Ratio), x = lignes.map(l => l.Age_Embauche), courbe = C.lowess(x, y);
    const traces = [
      boite(K.ARDOISE, { x: lignes.map(l => l.Tranche_Anciennete), y, text: surv, name: 'Salariés' }),
      { type: 'scatter', mode: 'lines+markers', x: C.TRANCHES, y: medianes.map(m => m[0]), customdata: medianes.map(m => m[1]),
        line: { color: K.BRUN, width: 3 }, marker: { size: 8 }, name: 'Médiane par tranche',
        hovertemplate: 'Ancienneté %{x} ans<br><b>Compa-Ratio médian : %{y:.3f}</b><br>%{customdata} salariés<extra></extra>' },
      // Points gris clair : la courbe de tendance, en brun, se lit par-dessus.
      { type: 'scattergl', mode: 'markers', x, y, text: surv, name: 'Salariés', showlegend: false,
        marker: { color: K.PALE, size: 5, opacity: 0.2 }, xaxis: 'x2', yaxis: 'y2' },
      { type: 'scatter', mode: 'lines', x: courbe.x, y: courbe.y, line: { color: K.BRUN, width: 3 }, name: 'Tendance non linéaire (Lowess)',
        hovertemplate: "Âge à l'embauche %{x}<br>tendance : %{y:.3f}<extra></extra>", xaxis: 'x2', yaxis: 'y2' },
    ];
    Object.assign(L.xaxis, { type: 'category', categoryorder: 'array', categoryarray: C.TRANCHES, title: titreAxe("Ancienneté (tranches d'années)") });
    L.xaxis2.title = titreAxe("Âge à l'embauche (années)");
    for (const s of ['', '2']) { L['yaxis' + s].title = titreAxe('Compa-Ratio (Salaire / Mid)'); L.shapes.push(ligneH(s, 1, K.PALE)); }
    montrer('g-anciennete', traces, L, 520);
    const corr = [C.correlation(lignes.map(l => l.Age), lignes.map(l => l.Anciennete)), C.correlation(x, lignes.map(l => l.Anciennete))];
    const lecture = C.TRANCHES.map((t, i) => `${t} ans : ${fr(medianes[i][0], 2)}`).join(' · ');
    constat('s-anciennete', `${F.libelle(sel)} (${fr(lignes.length)} salariés). Compa-Ratio médian par tranche : ${lecture}.
      Corrélation Age / Anciennete : ${fr(corr[0], 2)} ; Age_Embauche / Anciennete : ${fr(corr[1], 2)}.`);
  }

  // ---------- Compétences et tension métier (filtrable par grade et métier) ----------
  // La matrice 9-Box x Hot_job du notebook n'est pas reprise ici : le graphe « Talents et rémunération » montre le même croisement, en plus détaillé.

  // Trois teintes bien distinctes pour Hot_job, de la tension faible (bleu) à la forte (cuivre), lisibles aussi par un daltonien.
  const TENSION = [K.BLEU, K.OR, K.CUIVRE];

  function performance(df, survol, sel) {
    const { lignes, survol: surv } = F.sousEnsemble(df, survol, sel);
    const L = grille({ titres: ['Compa-Ratio selon la note Competence_N1, par tension du métier'] });
    const traces = [], pentes = [];
    C.modalites(lignes, 'Hot_job').forEach((h, k) => {
      const idx = indices(lignes, l => l.Hot_job === h), nom = `Hot_job = ${h}`, couleur = TENSION[k] || K.ARDOISE;
      const x = idx.map(i => lignes[i].Competence_N1), y = idx.map(i => lignes[i].Compa_Ratio), d = C.droite(x, y);
      pentes.push(`${nom} : ${fr(d.pente, 3)}`);
      // Les points restent discrets ; ce sont les droites, bien visibles, qui portent la légende.
      traces.push({ type: 'scattergl', mode: 'markers', x, y, text: idx.map(i => surv[i]), name: nom, legendgroup: nom, showlegend: false,
        marker: { color: couleur, size: 5, opacity: 0.25 } });
      traces.push({ type: 'scatter', mode: 'lines', x: d.x, y: d.y, line: { color: couleur, width: 3 }, name: nom, legendgroup: nom,
        hovertemplate: `Droite de tendance ${nom}<br>pente : ${fr(d.pente, 3)}<extra></extra>` });
    });
    L.shapes.push(ligneH('', 1, K.PALE));
    L.xaxis.title = titreAxe('Competence_N1');
    L.yaxis.title = titreAxe('Compa-Ratio');
    L.legend = { title: { text: 'Tension : ', font: { size: 12, color: K.GRIS } } };
    montrer('g-competences', traces, L, 500);
    constat('s-competences', `${F.libelle(sel)} (${fr(lignes.length)} salariés). Pente de la droite Competence_N1 → Compa-Ratio, par tension : ${pentes.join(' · ') || '–'}.`);
  }

  // ---------- Équité F / M et pôles (filtrable par métier) ----------

  function equite(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel));
    const L = grille({ colonnes: 2, titres: ['Compa-Ratio des femmes et des hommes, à grade égal', 'Compa-Ratio par pôle (Entite_N1)'] });
    const grades = C.modalites(lignes, 'Grade').map(String), couleurs = { F: K.OR, M: K.BLEU }, noms = { F: 'Femmes', M: 'Hommes' }, traces = [];
    // Pas de points isolés sur ces boîtes, comme dans le notebook.
    C.modalites(lignes, 'Sexe').forEach(s => {
      const g = lignes.filter(l => l.Sexe === s);
      traces.push(boite(couleurs[s] || K.ARDOISE, { x: g.map(l => texteGrade(l.Grade)), y: g.map(l => l.Compa_Ratio), name: noms[s] || String(s), boxpoints: false }));
    });
    const ordre = C.ordreParMediane(lignes, 'Entite_N1', 'Compa_Ratio');
    traces.push(boite(K.ARDOISE, { x: lignes.map(l => l.Entite_N1), y: lignes.map(l => l.Compa_Ratio), name: 'Pôles', boxpoints: false, showlegend: false, xaxis: 'x2', yaxis: 'y2' }));
    Object.assign(L.xaxis, { type: 'category', categoryorder: 'array', categoryarray: grades, title: titreAxe('Grade') });
    Object.assign(L.xaxis2, { type: 'category', categoryorder: 'array', categoryarray: ordre, tickangle: -30, title: titreAxe('Pôle, du Compa-Ratio médian le plus haut au plus bas') });
    L.yaxis.title = titreAxe('Compa-Ratio');
    L.yaxis2.title = titreAxe('Compa-Ratio');
    L.shapes.push(ligneH('', 1, K.BRUN, { name: 'Milieu de grille (Compa-Ratio = 1)', showlegend: true }), ligneH('2', 1, K.BRUN));
    L.boxmode = 'group';   // les boîtes F et M d'un même grade se placent côte à côte
    montrer('g-equite', traces, L, 520);
    const e = ecartsFH(lignes);
    constat('s-equite', `${F.libelle(sel)} (${fr(lignes.length)} salariés). Écart salarial moyen non corrigé (M vs F) : ${signe(e[0])} ; à grille et métier constants (Compa-Ratio) : ${signe(e[1])}.`);
  }

  E.analyses = { ecartsFH, logPositif, distribution, grilleEtMarche, metiers, anciennete, performance, equite };
})(window.Exploration = window.Exploration || {});
