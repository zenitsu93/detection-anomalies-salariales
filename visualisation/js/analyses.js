// Les analyses reprises du notebook EDA_Positionnement_Salarial_Comite.ipynb, une fonction par graphe.
(function (E) {
  'use strict';
  const C = E.calculs, F = E.filtres;
  const { fr, echapper, constat, salaries, enumerer, extremes, COULEURS: K, transparent,
    nomAxe, titreAxe, grille, montrer, salarie, dansBarre, boite, barresEtCourbe, ligneH, indices, texteNiveau } = E.communs;
  const logPositif = x => x > 0 ? Math.log(x) : NaN;
  // Une corrélation ou une pente demande au moins deux salariés aux valeurs différentes : sinon, le constat le dit.
  const ouNon = (x, d) => Number.isFinite(x) ? fr(x, d) : 'non calculable';

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
    // Clic : une barre donne les salariés de cette tranche de salaire ; la boîte, tous les salariés ; un point isolé, son salarié.
    const clic = p => {
      const log = ['x2', 'x4'].includes(p.data.xaxis), v = log ? logsal : sal, nom = log ? 'Logarithme du salaire' : 'Salaire brut';
      if (p.data.type === 'box') return p.hoverOnBox ? { titre: nom, lignes: df } : salarie(df[p.pointNumber]);
      return { titre: `${nom} de ${fr(p.customdata[0], 2)} à ${fr(p.customdata[1], 2)}`, lignes: df.filter((l, i) => dansBarre(p, v[i])) };
    };
    montrer('g-distribution', traces, L, 560, clic);
    const n = sal.filter(Number.isFinite).length;
    // L'asymétrie demande au moins 3 salaires, et des salaires différents.
    if (!Number.isFinite(asym[0])) return constat('s-distribution', `Tous les salariés : ${salaries(n)} avec un salaire, pas assez pour mesurer l'asymétrie.`);
    // Le sens et la comparaison se lisent sur les valeurs arrondies, celles écrites : « 0,00 » ne peut pas être dit « étiré ».
    const a = asym.map(x => Math.round(x * 100) / 100);
    const sens = a[0] > 0 ? 'étirée vers les hauts salaires' : a[0] < 0 ? 'étirée vers les bas salaires' : 'symétrique';
    const effetLog = !Number.isFinite(a[1]) ? '' : Math.abs(a[1]) < Math.abs(a[0])
      ? ` ; le logarithme la rapproche de la symétrie (${fr(a[1], 2)}).` : ` ; le logarithme ne la rend pas plus symétrique (${fr(a[1], 2)}).`;
    constat('s-distribution', `Tous les salariés (${salaries(n)} avec un salaire) : asymétrie de ${fr(a[0], 2)}, la distribution du salaire brut est ${sens}${effetLog || '.'} 0 = parfaitement symétrique.`);
  }

  // ---------- Niveaux, grille et marché (filtrable par métier) ----------

  function grilleEtMarche(df, survol, sel) {
    const { lignes, survol: surv } = F.sousEnsemble(df, survol, sel);
    const niveaux = C.modalites(lignes, 'Niveau'), g = niveaux.map(String);
    const moy = c => niveaux.map(gr => C.moyenne(lignes.filter(l => l.Niveau === gr).map(l => l[c])));
    // Avec un métier choisi, la grille et le marché sont exactement ceux du métier (et non une moyenne de métiers).
    const moyenne = sel.metier === null ? ', moyenne' : '';
    const L = grille({ colonnes: 2, titres: ['Salaires réels, grille interne et marché par niveau', 'Position dans la bande salariale (Range Penetration)'] });
    const traces = [
      // Bande [Min - Max] en premier, pour qu'elle passe sous les boîtes : le Max, puis le Min colorié jusqu'au Max.
      { type: 'scatter', x: g, y: moy('Max'), mode: 'lines', line: { width: 0 }, showlegend: false, hoverinfo: 'skip' },
      { type: 'scatter', x: g, y: moy('Min'), mode: 'lines', line: { width: 0 }, fill: 'tonexty', fillcolor: transparent(K.OR, 0.18), name: `Bande de la grille [Min - Max]${moyenne}`, hoverinfo: 'skip' },
      // Boîtes à fond blanc : elles se détachent de la bande de la grille.
      boite(K.ARDOISE, { x: lignes.map(l => texteNiveau(l.Niveau)), y: lignes.map(l => l.Fixe_Annuel_MAD), text: surv, name: 'Salaires réels', fillcolor: 'rgba(255,255,255,0.92)' }),
      { type: 'scatter', x: g, y: moy('Mid'), mode: 'lines+markers', line: { color: K.BRUN, width: 2.5 }, marker: { size: 8 }, name: `Milieu de grille (Mid)${moyenne}`,
        hovertemplate: 'Niveau %{x}<br>Mid : %{y:,.1f} kMAD<extra></extra>' },
      { type: 'scatter', x: g, y: moy('Median'), mode: 'lines+markers', line: { color: K.BLEU, width: 2.5, dash: 'dash' }, marker: { size: 8, symbol: 'diamond' },
        name: `Médiane du marché${moyenne}`, hovertemplate: 'Niveau %{x}<br>Médiane marché : %{y:,.1f} kMAD<extra></extra>' },
      ...barresEtCourbe(lignes.map(l => l.Range_Penetration), 40, { xaxis: 'x2', yaxis: 'y2' }),
    ];
    // 'category' : chaque niveau prend la même largeur, même si des numéros de niveau manquent.
    Object.assign(L.xaxis, { type: 'category', categoryorder: 'array', categoryarray: g, title: titreAxe('Niveau') });
    L.yaxis.title = titreAxe('Fixe_Annuel_MAD (kMAD)');
    L.xaxis2.title = titreAxe('0 = Min · 0,5 = Mid · 1 = Max');
    L.yaxis2.title = titreAxe('Nombre de salariés');
    L.legend = { traceorder: 'normal' };   // sinon plotly inverse la légende à cause de la zone coloriée
    for (const [x, couleur, trait, texte, cote] of [[0, K.ROUGE, 'dash', 'Min', 'right'], [0.5, K.BRUN, 'solid', 'Mid', 'left'], [1, K.ROUGE, 'dash', 'Max', 'left']]) {
      L.shapes.push({ type: 'line', xref: 'x2', x0: x, x1: x, yref: 'y2 domain', y0: 0, y1: 1, line: { color: couleur, dash: trait, width: 1.5 } });
      L.annotations.push({ text: texte, x, xref: 'x2', y: 1, yref: 'y2 domain', xanchor: cote, yanchor: 'top', xshift: cote === 'left' ? 4 : -4,
        showarrow: false, font: { size: 11, color: K.GRIS } });
    }
    // Clic : une boîte (ou un point du Mid, de la médiane) donne les salariés du niveau ; une barre de droite, ceux de cette position dans la bande.
    const parNiveau = gr => ({ titre: 'Niveau ' + gr, lignes: lignes.filter(l => texteNiveau(l.Niveau) === gr) });
    const clic = p => {
      if (p.data.type === 'box') return p.hoverOnBox ? parNiveau(p.x) : salarie(lignes[p.pointNumber]);
      if (p.data.xaxis !== 'x2') return parNiveau(p.x);
      return { titre: `Position dans la bande de ${fr(p.customdata[0], 2)} à ${fr(p.customdata[1], 2)}`, lignes: lignes.filter(l => dansBarre(p, l.Range_Penetration)) };
    };
    montrer('g-grille', traces, L, 520, clic, F.libelle(sel));
    // Le décompte des salariés hors grille n'est pas répété ici : il est dans les chiffres clés et dans le graphe « Salaires hors grille ».
    // Seuls les salariés qui ont un salaire et une grille (Min et Max) ont une position dans la bande : le constat compte sur eux.
    if (!lignes.length) return constat('s-grille', 'Aucun salarié pour ce filtre.');
    const position = lignes.map(l => l.Range_Penetration).filter(Number.isFinite), lib = F.libelle(sel);
    if (!position.length) return constat('s-grille', `${lib} (${salaries(lignes.length)}) : aucun n'a à la fois un salaire et une grille (Min et Max) pour son métier et son niveau.`);
    const avecGrille = salaries(position.length) + ' avec un salaire et une grille' + (position.length < lignes.length ? ` sur ${fr(lignes.length)}` : '');
    const moitie = position.length > 1 ? ` ; la moitié d'entre eux se situe entre ${fr(C.quantile(position, 0.25), 2)} et ${fr(C.quantile(position, 0.75), 2)}` : '';
    constat('s-grille', `${lib} (${avecGrille}) : position médiane dans la bande ${fr(C.mediane(position), 2)} (0 = Min, 1 = Max)${moitie}. Le détail des salariés hors grille est dans le graphe « Salaires hors grille ».`);
  }

  // ---------- Familles de métier (filtrable par niveau) ----------

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
    // Clic : une boîte donne les salariés du métier ; un point isolé, son salarié.
    const clic = p => {
      const idx = indices(lignes, l => l.Job_Family === p.data.name);
      return p.hoverOnBox ? { titre: 'Métier ' + p.data.name, lignes: idx.map(i => lignes[i]) } : salarie(lignes[idx[p.pointNumber]]);
    };
    montrer('g-metiers', traces, L, 760, clic, F.libelle(sel));
    if (!lignes.length) return constat('s-metiers', 'Aucun salarié pour ce filtre.');
    const med = ordre.map(jf => ({ nom: echapper(jf), v: C.mediane(lignes.filter(l => l.Job_Family === jf).map(l => l.Compa_Ratio)) }));
    const ex = extremes(med, m => m.v, 2), lib = F.libelle(sel), noms = t => enumerer(t.map(m => m.nom));
    if (!ex) return constat('s-metiers', `${lib} : aucun Compa-Ratio, faute de grille (Mid) pour ces métiers et niveaux.`);
    // Un seul métier, ou tous au même Compa-Ratio médian : il n'y a ni plus haut ni plus bas à citer.
    if (ex.egaux) return constat('s-metiers', ex.haut.length > 1 ? `${lib} : même Compa-Ratio médian (${fr(ex.haut[0].v, 2)}) pour tous les métiers.`
      : `${lib} : un seul métier${med.length > 1 ? ' avec un Compa-Ratio' : ''}, ${ex.haut[0].nom}, de Compa-Ratio médian ${fr(ex.haut[0].v, 2)}.`);
    constat('s-metiers', `${lib} : Compa-Ratio médian le plus haut pour ${noms(ex.haut)} (${fr(ex.haut[0].v, 2)}), le plus bas pour ${noms(ex.bas)} (${fr(ex.bas[0].v, 2)}). Les métiers sont rangés du plus haut au plus bas.`);
  }

  // ---------- Ancienneté (par tranche) et âge à l'embauche (filtrable par niveau et métier) ----------

  function anciennete(df, survol, sel) {
    const { lignes, survol: surv } = F.sousEnsemble(df, survol, sel);
    const L = grille({ colonnes: 2, titres: ["Compa-Ratio par tranche d'ancienneté", "Compa-Ratio selon l'âge à l'embauche (Age − Anciennete)"] });
    // Par tranche : la médiane et le nombre de salariés qui ont un Compa-Ratio (ceux sans grille ne comptent pas).
    const medianes = C.TRANCHES.map(t => { const v = lignes.filter(l => l.Tranche_Anciennete === t).map(l => l.Compa_Ratio).filter(Number.isFinite); return [v.length ? C.mediane(v) : null, v.length]; });
    const y = lignes.map(l => l.Compa_Ratio), x = lignes.map(l => l.Age_Embauche), courbe = C.lowess(x, y);
    const traces = [
      boite(K.ARDOISE, { x: lignes.map(l => l.Tranche_Anciennete), y, text: surv, name: 'Salariés' }),
      { type: 'scatter', mode: 'lines+markers', x: C.TRANCHES, y: medianes.map(m => m[0]), customdata: medianes.map(m => m[1]),
        line: { color: K.BRUN, width: 3 }, marker: { size: 8 }, name: 'Médiane par tranche',
        hovertemplate: 'Ancienneté %{x} ans<br><b>Compa-Ratio médian : %{y:.3f}</b><br>%{customdata:,} salariés<extra></extra>' },
      // Points gris clair : la courbe de tendance, en brun, se lit par-dessus.
      { type: 'scattergl', mode: 'markers', x, y, text: surv, name: 'Salariés', showlegend: false,
        marker: { color: K.PALE, size: 5, opacity: 0.2 }, xaxis: 'x2', yaxis: 'y2' },
      { type: 'scatter', mode: 'lines', x: courbe.x, y: courbe.y, line: { color: K.BRUN, width: 3 }, name: 'Tendance non linéaire (Lowess)',
        hovertemplate: "Âge à l'embauche %{x}<br>tendance : %{y:.3f}<extra></extra>", xaxis: 'x2', yaxis: 'y2' },
    ];
    Object.assign(L.xaxis, { type: 'category', categoryorder: 'array', categoryarray: C.TRANCHES, title: titreAxe("Ancienneté (tranches d'années)") });
    L.xaxis2.title = titreAxe("Âge à l'embauche (années)");
    for (const s of ['', '2']) { L['yaxis' + s].title = titreAxe('Compa-Ratio (Salaire / Mid)'); L.shapes.push(ligneH(s, 1, K.PALE)); }
    // Clic, dans l'ordre des courbes : boîte (la tranche, ou le salarié d'un point isolé), médianes (la tranche),
    // nuage (le salarié), tendance (les salariés embauchés à cet âge).
    const parTranche = t => ({ titre: `Ancienneté ${t} ans`, lignes: lignes.filter(l => l.Tranche_Anciennete === t) });
    const clic = p => [
      () => p.hoverOnBox ? parTranche(p.x) : salarie(lignes[p.pointNumber]),
      () => parTranche(p.x),
      () => salarie(lignes[p.pointNumber]),
      () => ({ titre: `Embauchés à ${String(p.x).replace('.', ',')} ans`, lignes: lignes.filter(l => l.Age_Embauche === p.x) }),
    ][p.curveNumber]();
    montrer('g-anciennete', traces, L, 520, clic, F.libelle(sel));
    if (!lignes.length) return constat('s-anciennete', 'Aucun salarié pour ce filtre.');
    const corr = [C.correlation(lignes.map(l => l.Age), lignes.map(l => l.Anciennete)), C.correlation(x, lignes.map(l => l.Anciennete))];
    // Une tranche sans médiane dit pourquoi : personne dans la tranche, ou personne avec une grille.
    const vide = t => lignes.some(l => l.Tranche_Anciennete === t) ? 'pas de Compa-Ratio' : 'aucun salarié';
    const lecture = C.TRANCHES.map((t, i) => `${t} ans : ${medianes[i][1] ? fr(medianes[i][0], 2) : vide(t)}`).join(' · ');
    constat('s-anciennete', `${F.libelle(sel)} (${salaries(lignes.length)}). Compa-Ratio médian par tranche : ${lecture}.
      Corrélation Age / Anciennete : ${ouNon(corr[0], 2)} ; Age_Embauche / Anciennete : ${ouNon(corr[1], 2)}.`);
  }

  // ---------- Compétences et tension métier (filtrable par niveau et métier) ----------
  // La matrice 9-Box x Hot_job du notebook n'est pas reprise ici : le graphe « Talents et rémunération » montre le même croisement, en plus détaillé.

  // Trois teintes bien distinctes pour Hot_job, de la tension faible (bleu) à la forte (cuivre), lisibles aussi par un daltonien.
  const TENSION = [K.BLEU, K.OR, K.CUIVRE];

  function performance(df, survol, sel) {
    const { lignes, survol: surv } = F.sousEnsemble(df, survol, sel);
    const L = grille({ titres: ['Compa-Ratio selon la note Competence_N1, par tension du métier'] });
    const traces = [], pentes = [], parCourbe = [];
    C.modalites(lignes, 'Hot_job').forEach((h, k) => {
      const idx = indices(lignes, l => l.Hot_job === h), nom = `Hot_job = ${h}`, couleur = TENSION[k] || K.ARDOISE;
      parCourbe.push([nom, idx], [nom, idx]);   // le nuage et la droite de cette tension
      const x = idx.map(i => lignes[i].Competence_N1), y = idx.map(i => lignes[i].Compa_Ratio), d = C.droite(x, y);
      pentes.push(`${nom} : ${ouNon(d.pente, 3)}`);
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
    // Clic : un point donne son salarié ; une droite, tous les salariés de sa tension.
    const clic = p => {
      const [nom, idx] = parCourbe[p.curveNumber];
      return p.data.mode === 'markers' ? salarie(lignes[idx[p.pointNumber]]) : { titre: nom, lignes: idx.map(i => lignes[i]) };
    };
    montrer('g-competences', traces, L, 500, clic, F.libelle(sel));
    if (!lignes.length) return constat('s-competences', 'Aucun salarié pour ce filtre.');
    if (!pentes.length) return constat('s-competences', `${F.libelle(sel)} (${salaries(lignes.length)}) : Hot_job est vide, pas de droite par tension à tracer.`);
    constat('s-competences', `${F.libelle(sel)} (${salaries(lignes.length)}). Pente de la droite Competence_N1 → Compa-Ratio, par tension : ${pentes.join(' · ')}.`);
  }

  // ---------- Équité F / M et pôles (filtrable par métier) ----------

  function equite(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel));
    const L = grille({ colonnes: 2, titres: ['Compa-Ratio des femmes et des hommes, à niveau égal', 'Compa-Ratio par pôle (Entite_N1)'] });
    const niveaux = C.modalites(lignes, 'Niveau').map(String), couleurs = { F: K.OR, M: K.BLEU }, noms = { F: 'Femmes', M: 'Hommes' }, traces = [];
    const sexes = C.modalites(lignes, 'Sexe');
    // Pas de points isolés sur ces boîtes, comme dans le notebook.
    sexes.forEach(s => {
      const g = lignes.filter(l => l.Sexe === s);
      traces.push(boite(couleurs[s] || K.ARDOISE, { x: g.map(l => texteNiveau(l.Niveau)), y: g.map(l => l.Compa_Ratio), name: noms[s] || String(s), boxpoints: false,
        alignmentgroup: 'sexe', offsetgroup: String(s) }));
    });
    const ordre = C.ordreParMediane(lignes, 'Entite_N1', 'Compa_Ratio');
    // Un groupe à part : sinon plotly réserve aussi aux pôles une place de femmes et d'hommes, et leurs boîtes se décalent de leur nom.
    traces.push(boite(K.ARDOISE, { x: lignes.map(l => l.Entite_N1), y: lignes.map(l => l.Compa_Ratio), name: 'Pôles', boxpoints: false, showlegend: false, xaxis: 'x2', yaxis: 'y2',
      alignmentgroup: 'poles', offsetgroup: 'poles' }));
    Object.assign(L.xaxis, { type: 'category', categoryorder: 'array', categoryarray: niveaux, title: titreAxe('Niveau') });
    Object.assign(L.xaxis2, { type: 'category', categoryorder: 'array', categoryarray: ordre, tickangle: -30, title: titreAxe('Pôle, du Compa-Ratio médian le plus haut au plus bas') });
    L.yaxis.title = titreAxe('Compa-Ratio');
    L.yaxis2.title = titreAxe('Compa-Ratio');
    L.shapes.push(ligneH('', 1, K.BRUN, { name: 'Milieu de grille (Compa-Ratio = 1)', showlegend: true }), ligneH('2', 1, K.BRUN));
    L.boxmode = 'group';   // les boîtes F et M d'un même niveau se placent côte à côte
    // Clic : une boîte de gauche donne les femmes (ou les hommes) du niveau ; une boîte de droite, les salariés du pôle.
    const clic = p => {
      if (p.data.xaxis === 'x2') return { titre: 'Pôle ' + p.x, lignes: lignes.filter(l => String(l.Entite_N1) === p.x) };
      const s = sexes[p.curveNumber];
      return { titre: `${noms[s] || s}, niveau ${p.x}`, lignes: lignes.filter(l => l.Sexe === s && texteNiveau(l.Niveau) === p.x) };
    };
    montrer('g-equite', traces, L, 520, clic, F.libelle(sel));
    if (!lignes.length) return constat('s-equite', 'Aucun salarié pour ce filtre.');
    const lib = F.libelle(sel), nF = lignes.filter(l => l.Sexe === 'F').length, nM = lignes.filter(l => l.Sexe === 'M').length;
    // L'écart ne se calcule qu'entre M et F : un autre code dans Sexe (H, Femme, case vide...) est signalé, pas deviné.
    const autres = C.modalites(lignes.filter(l => l.Sexe !== 'M' && l.Sexe !== 'F'), 'Sexe').map(s => `« ${echapper(s)} »`);
    const horsMF = lignes.length - nF - nM;
    const nonComptes = horsMF ? ` Non comptés : ${salaries(horsMF)} dont le Sexe n'est ni M ni F${autres.length ? ` (${enumerer(autres)})` : ''}.` : '';
    if (!nF || !nM) {
      const manque = [!nF && 'F (femmes)', !nM && 'M (hommes)'].filter(Boolean).join(' ni ');
      return constat('s-equite', `${lib} (${salaries(lignes.length)}) : aucun salarié codé ${manque} dans la colonne Sexe, l'écart entre femmes et hommes ne peut pas être calculé.${nonComptes}`);
    }
    // Le sens de l'écart est dit en toutes lettres, sur la valeur arrondie écrite : « 0,00 % » veut dire « égal ».
    // Sans valeur des deux côtés (salaires vides, pas de grille), la comparaison n'est pas faite.
    const e = ecartsFH(lignes).map(x => Math.round(x * 100) / 100);
    const compare = (x, quoi) => !Number.isFinite(x) ? `${quoi} : pas de comparaison possible, faute de valeurs pour les femmes ou pour les hommes`
      : `${quoi} des hommes ${x > 0 ? `${fr(x, 2)} % au-dessus de` : x < 0 ? `${fr(-x, 2)} % en dessous de` : 'égal à'} celui des femmes`;
    constat('s-equite', `${lib} (${fr(nF)} femme${nF > 1 ? 's' : ''}, ${fr(nM)} homme${nM > 1 ? 's' : ''}). ${compare(e[0], 'Salaire moyen')} (écart brut, sans tenir compte du métier ni du niveau). `
      + `${compare(e[1], 'Compa-Ratio moyen')} (à métier et niveau égaux : chacun est comparé au milieu de sa propre grille).${nonComptes}`);
  }

  E.analyses = { ecartsFH, logPositif, distribution, grilleEtMarche, metiers, anciennete, performance, equite };
})(window.Exploration = window.Exploration || {});
