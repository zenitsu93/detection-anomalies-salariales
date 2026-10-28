// Les graphes ajoutés au notebook pour piloter la rémunération : masse salariale, salaires hors grille, position face au marché,
// talents et rémunération, métiers en tension.
(function (E) {
  'use strict';
  const C = E.calculs, F = E.filtres;
  const { fr, pct, echapper, constat, COULEURS: K, transparent, titreAxe, grille, montrer } = E.communs;
  // Mêmes seuils que la règle CompaRatio de la détection (compa_ratio_low et compa_ratio_high de config/rules.yaml).
  const COMPA_BAS = 0.85, COMPA_HAUT = 1.15;

  // ---------- Masse salariale et effectifs par pôle (filtrable par niveau) ----------
  // Trois petits graphes alignés sur les mêmes pôles, plutôt qu'un graphe à deux échelles qui se lit mal.
  // Le Compa-Ratio par pôle n'est pas repris ici : il est dans le graphe « Équité femmes / hommes et pratiques par pôle », plus détaillé.

  function masseSalariale(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel));
    const stats = C.modalites(lignes, 'Entite_N1').map(p => {
      const g = lignes.filter(l => l.Entite_N1 === p), sal = g.map(l => l.Fixe_Annuel_MAD).filter(Number.isFinite);
      return { pole: String(p), n: g.length, masse: C.somme(sal), moyen: C.moyenne(sal) };
    }).sort((a, b) => a.masse - b.masse);   // en barres horizontales, la dernière est en haut : le pôle le plus lourd
    const total = C.somme(stats.map(s => s.masse)), effectif = C.somme(stats.map(s => s.n));
    const y = stats.map(s => s.pole), masses = stats.map(s => s.masse / 1000);   // kMAD → millions de MAD
    const L = grille({ colonnes: 3, espH: 0.06, titres: ['Effectif', 'Masse salariale (millions de MAD)', 'Salaire moyen (kMAD)'] });
    const barre = (s, x, textes, couleur) => ({ type: 'bar', orientation: 'h', y, x, text: textes, textposition: 'outside', cliponaxis: false,
      textfont: { size: 11, color: K.ENCRE }, marker: { color: couleur }, showlegend: false, xaxis: 'x' + s, yaxis: 'y' + s,
      hovertemplate: '%{y}<br><b>%{text}</b><extra></extra>' });
    const traces = [
      barre('', stats.map(s => s.n), stats.map(s => `${fr(s.n)} · ${pct(s.n, effectif, 0)}`), K.ARDOISE),
      barre('2', masses, stats.map(s => `${fr(s.masse / 1000, 1)} · ${pct(s.masse, total, 0)}`), K.BRUN),
      barre('3', stats.map(s => s.moyen), stats.map(s => fr(s.moyen, 1)), K.ARDOISE),
    ];
    // Les trois graphes partagent la liste des pôles : seuls les noms du premier sont écrits.
    Object.assign(L.yaxis, { type: 'category', showgrid: false });
    for (const s of ['2', '3']) Object.assign(L['yaxis' + s], { matches: 'y', showticklabels: false, showgrid: false });
    const plusGrand = v => Math.max(0, ...v.filter(Number.isFinite));
    [['', stats.map(s => s.n)], ['2', masses], ['3', stats.map(s => s.moyen)]].forEach(([s, v]) =>
      Object.assign(L['xaxis' + s], { range: [0, plusGrand(v) * 1.45 || 1], showgrid: false, showticklabels: false }));
    // Clic sur une barre, dans l'un des trois graphes : les salariés du pôle.
    const clic = p => ({ titre: 'Pôle ' + p.y, lignes: lignes.filter(l => String(l.Entite_N1) === p.y) });
    montrer('g-masse', traces, L, 150 + 46 * Math.max(4, stats.length), clic, F.libelle(sel));
    if (!stats.length) return constat('s-masse', 'Aucun salarié pour ce filtre.');
    const lourd = stats[stats.length - 1], cher = [...stats].sort((a, b) => b.moyen - a.moyen)[0];
    constat('s-masse', `${F.libelle(sel)} : ${fr(effectif)} salariés, ${fr(total / 1000, 1)} millions de MAD de masse salariale. Pôle le plus lourd : ${echapper(lourd.pole)} (${pct(lourd.masse, total, 0)} de la masse, ${pct(lourd.n, effectif, 0)} des effectifs). Salaire moyen le plus haut : ${echapper(cher.pole)} (${fr(cher.moyen, 1)} kMAD).`);
  }

  // ---------- Salaires hors grille par pôle et par niveau (filtrable par métier) ----------

  function horsGrille(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel) && [l.Fixe_Annuel_MAD, l.Min, l.Max].every(Number.isFinite));
    const poles = C.modalites(lignes, 'Entite_N1'), niveaux = C.modalites(lignes, 'Niveau');
    const sousMin = l => l.Fixe_Annuel_MAD < l.Min, surMax = l => l.Fixe_Annuel_MAD > l.Max;
    // Chaque case : la part des salariés du pôle et du niveau hors de leur grille, puis leur nombre.
    const carte = (test, couleur, axes) => {
      const cases = poles.map(p => niveaux.map(g => { const grp = lignes.filter(l => l.Entite_N1 === p && l.Niveau === g); return [grp.filter(test).length, grp.length]; }));
      return { type: 'heatmap', x: niveaux.map(String), y: poles.map(String), z: cases.map(r => r.map(([n, t]) => t ? 100 * n / t : null)),
        text: cases.map(r => r.map(([n, t]) => n ? `${fr(100 * n / t, 1)} %<br>${fr(n)}` : (t ? '0' : ''))), texttemplate: '%{text}', textfont: { size: 11 },
        customdata: cases, colorscale: [[0, '#ffffff'], [1, couleur]], zmin: 0, showscale: false, xgap: 2, ygap: 2, ...axes,
        hovertemplate: '%{y} · niveau %{x}<br><b>%{customdata[0]} salariés sur %{customdata[1]}</b> (%{z:.1f} %)<extra></extra>' };
    };
    const traces = [carte(sousMin, K.ROUGE, {}), carte(surMax, K.OR, { xaxis: 'x2', yaxis: 'y2' })];
    const L = grille({ colonnes: 2, espH: 0.06, titres: ['Sous le Min de leur grille', 'Au-dessus du Max de leur grille'] });
    for (const s of ['', '2']) {
      Object.assign(L['xaxis' + s], { type: 'category', title: titreAxe('Niveau'), showgrid: false });
      Object.assign(L['yaxis' + s], { type: 'category', showgrid: false, autorange: 'reversed' });
    }
    L.yaxis2.showticklabels = false;
    // Clic sur une case : les salariés de ce pôle et de ce niveau sous le Min (carte de gauche) ou au-dessus du Max (carte de droite).
    const clic = p => {
      const [i, j] = p.pointNumber, [test, quoi] = p.curveNumber ? [surMax, 'Au-dessus du Max'] : [sousMin, 'Sous le Min'];
      return { titre: `${quoi} de leur grille : ${poles[i]}, niveau ${niveaux[j]}`, lignes: lignes.filter(l => l.Entite_N1 === poles[i] && l.Niveau === niveaux[j] && test(l)) };
    };
    montrer('g-hors-grille', traces, L, 130 + 52 * Math.max(4, poles.length), clic, F.libelle(sel));
    const n = lignes.length, ns = lignes.filter(sousMin).length, nm = lignes.filter(surMax).length;
    // La case où la part sous le Min est la plus forte.
    let pire = null;
    for (const p of poles) for (const g of niveaux) {
      const grp = lignes.filter(l => l.Entite_N1 === p && l.Niveau === g), k = grp.filter(sousMin).length;
      if (k && (!pire || k / grp.length > pire.part)) pire = { p, g, k, part: k / grp.length };
    }
    constat('s-hors-grille', `${F.libelle(sel)} : ${fr(ns)} salariés sous le Min de leur grille (${pct(ns, n)}) et ${fr(nm)} au-dessus du Max (${pct(nm, n)}).`
      + (pire ? ` Part la plus forte sous le Min : ${echapper(pire.p)}, niveau ${pire.g} (${fr(100 * pire.part, 1)} %, ${fr(pire.k)} salariés).` : ''));
  }

  // ---------- Position face au marché, par pôle ou par métier (filtrable par niveau) ----------

  // Ordre d'empilement depuis la médiane : à gauche ce qui est sous la médiane, à droite ce qui est au-dessus.
  const SEGMENTS = [['Entre P25 et médiane', '#8fb0d3', -1, K.ENCRE, 2], ['Sous le P25', '#2f5785', -1, '#fff', 1],
                    ['Entre médiane et P75', '#d9ab8c', 1, K.ENCRE, 3], ['Au-dessus du P75', '#7a3f1f', 1, '#fff', 4]];

  function marche(df, sel) {
    if (!df.some(l => l.Position_Marche)) {
      Plotly.purge('g-marche');
      return constat('s-marche', "Le fichier market.xlsx n'a pas de colonnes P25 et P75 : ce graphe a besoin de la fourchette du marché.");
    }
    const axe = sel.vue, lignes = df.filter(l => F.garder(l, sel) && l.Position_Marche);
    const groupes = C.modalites(lignes, axe).map(g => {
      const grp = lignes.filter(l => l[axe] === g);
      return { nom: String(g), n: grp.length, parts: Object.fromEntries(C.POSITIONS_MARCHE.map(p => [p, grp.filter(l => l.Position_Marche === p).length])) };
    });
    const auDessus = g => (g.parts['Entre médiane et P75'] + g.parts['Au-dessus du P75']) / g.n;
    groupes.sort((a, b) => auDessus(a) - auDessus(b));   // le mieux placé face au marché en haut
    const y = groupes.map(g => g.nom);
    const traces = SEGMENTS.map(([pos, couleur, sens, texte, rang]) => {
      const v = groupes.map(g => 100 * g.parts[pos] / g.n);
      return { type: 'bar', orientation: 'h', name: pos, legendrank: rang, y, x: v.map(x => sens * x),
        marker: { color: couleur, line: { color: '#fff', width: 1 } },
        text: v.map(x => x >= 6 ? fr(x, 0) + ' %' : ''), textposition: 'inside', insidetextanchor: 'middle', textfont: { size: 11, color: texte },
        customdata: groupes.map((g, i) => [fr(v[i], 1), g.parts[pos], g.n]),
        hovertemplate: `%{y}<br>${pos} : <b>%{customdata[0]} %</b><br>%{customdata[1]} salariés sur %{customdata[2]}<extra></extra>` };
    });
    const L = grille({ titres: [`Part des salariés sous la médiane du marché (à gauche) et au-dessus (à droite), ${axe === 'Entite_N1' ? 'par pôle' : 'par métier'}`] });
    L.barmode = 'relative';
    Object.assign(L.xaxis, { range: [-100, 100], tickvals: [-100, -75, -50, -25, 0, 25, 50, 75, 100],
      ticktext: ['100 %', '75 %', '50 %', '25 %', 'Médiane', '25 %', '50 %', '75 %', '100 %'], zeroline: true, zerolinecolor: K.ENCRE, zerolinewidth: 1.5 });
    Object.assign(L.yaxis, { type: 'category', showgrid: false });
    L.legend = { traceorder: 'normal' };
    // Clic sur un morceau de barre : les salariés de ce pôle (ou métier) dans cette position face au marché.
    const clic = p => {
      const pos = SEGMENTS[p.curveNumber][0];
      return { titre: `${p.y} · ${pos}`, lignes: lignes.filter(l => String(l[axe]) === p.y && l.Position_Marche === pos) };
    };
    montrer('g-marche', traces, L, 150 + 32 * Math.max(5, groupes.length), clic, F.libelle(sel));
    if (!groupes.length) return constat('s-marche', 'Aucun salarié pour ce filtre.');
    const sous = lignes.filter(l => l.Position_Marche === 'Sous le P25' || l.Position_Marche === 'Entre P25 et médiane').length;
    const bas = groupes[0], haut = groupes[groupes.length - 1];
    constat('s-marche', `${F.libelle(sel)} : ${pct(sous, lignes.length, 0)} des salariés sont payés sous la médiane du marché de leur métier et niveau. Le mieux placé : ${echapper(haut.nom)} (${fr(100 * auDessus(haut), 0)} % au-dessus de la médiane) ; le moins bien placé : ${echapper(bas.nom)} (${fr(100 * auDessus(bas), 0)} %).`);
  }

  // ---------- Talents et rémunération : Compa-Ratio et 9-Box (filtrable par pôle, métier, Hot_job) ----------

  const PAS = 0.05;   // largeur d'une tranche de Compa-Ratio pour former les bulles
  const ZONES = [['Compa-Ratio sous 0,85', K.ROUGE], ['Entre 0,85 et 1,15', K.ARDOISE], ['Au-dessus de 1,15', K.OR]];

  function talents(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel) && Number.isFinite(l.Compa_Ratio) && Number.isFinite(l.Positionnement_9BOX));
    // Une bulle par case 9-Box et tranche de Compa-Ratio ; sa taille dit combien de salariés elle regroupe.
    const bulles = new Map();
    for (const l of lignes) {
      const t = Math.floor(l.Compa_Ratio / PAS), cle = l.Positionnement_9BOX + '|' + t;
      if (!bulles.has(cle)) bulles.set(cle, { y: l.Positionnement_9BOX, de: t * PAS, n: 0, lignes: [] });
      bulles.get(cle).n++;
      bulles.get(cle).lignes.push(l);   // les salariés de la bulle, pour la liste qui s'ouvre au clic
    }
    const toutes = [...bulles.values()], plusGrosse = Math.max(1, ...toutes.map(b => b.n));
    const zone = b => b.de + PAS / 2 < COMPA_BAS ? 0 : b.de + PAS / 2 > COMPA_HAUT ? 2 : 1;
    const parZone = [];
    const traces = ZONES.map(([nom, couleur], z) => {
      const bs = toutes.filter(b => zone(b) === z);
      parZone.push(bs);
      return { type: 'scatter', mode: 'markers', name: nom, x: bs.map(b => b.de + PAS / 2), y: bs.map(b => b.y),
        marker: { size: bs.map(b => b.n), sizemode: 'area', sizeref: 2 * plusGrosse / (36 ** 2), sizemin: 3, color: transparent(couleur, 0.8), line: { color: '#fff', width: 1 } },
        customdata: bs.map(b => [fr(b.de, 2), fr(b.de + PAS, 2), b.n]),
        hovertemplate: '9-Box %{y} · Compa-Ratio de %{customdata[0]} à %{customdata[1]}<br><b>%{customdata[2]} salariés</b><extra></extra>' };
    });
    const L = grille({ titres: ['Compa-Ratio et positionnement 9-Box (taille de la bulle = nombre de salariés)'] });
    // Zones de lecture : sous 0,85 et au-dessus de 1,15, les seuils de la règle CompaRatio de la détection.
    L.shapes.push(
      { type: 'rect', xref: 'x', x0: 0, x1: COMPA_BAS, yref: 'y domain', y0: 0, y1: 1, fillcolor: transparent(K.ROUGE, 0.06), line: { width: 0 }, layer: 'below' },
      { type: 'rect', xref: 'x', x0: COMPA_HAUT, x1: 3, yref: 'y domain', y0: 0, y1: 1, fillcolor: transparent(K.OR, 0.1), line: { width: 0 }, layer: 'below' },
      { type: 'line', xref: 'x', x0: 1, x1: 1, yref: 'y domain', y0: 0, y1: 1, line: { color: K.PALE, dash: 'dash', width: 1.5 } });
    L.annotations.push(
      { text: 'Sous-positionnés', x: COMPA_BAS, xref: 'x', xanchor: 'right', xshift: -6, y: 1, yref: 'y domain', yanchor: 'top', showarrow: false, font: { size: 11, color: K.GRIS } },
      { text: 'Sur-positionnés', x: COMPA_HAUT, xref: 'x', xanchor: 'left', xshift: 6, y: 1, yref: 'y domain', yanchor: 'top', showarrow: false, font: { size: 11, color: K.GRIS } });
    const cases = C.modalites(lignes, 'Positionnement_9BOX');
    Object.assign(L.xaxis, { range: [0.55, 1.45], dtick: 0.1, title: titreAxe('Compa-Ratio (Salaire / Mid)') });
    Object.assign(L.yaxis, { dtick: 1, range: [Math.min(0, ...cases) - 0.7, Math.max(6, ...cases) + 0.7], title: titreAxe('Positionnement 9-Box (0 à 6)') });
    // Clic sur une bulle : ses salariés.
    const clic = p => {
      const b = parZone[p.curveNumber][p.pointNumber];
      return { titre: `9-Box ${b.y} · Compa-Ratio de ${fr(b.de, 2)} à ${fr(b.de + PAS, 2)}`, lignes: b.lignes };
    };
    montrer('g-talents', traces, L, 580, clic, F.libelle(sel));
    if (!lignes.length) return constat('s-talents', 'Aucun salarié pour ce filtre.');
    const haut = Math.max(...cases), bas = Math.min(...cases);
    const sous = lignes.filter(l => l.Compa_Ratio < COMPA_BAS), sur = lignes.filter(l => l.Compa_Ratio > COMPA_HAUT);
    constat('s-talents', `${F.libelle(sel)} (${fr(lignes.length)} salariés) : ${fr(sous.length)} sous 0,85 et ${fr(sur.length)} au-dessus de 1,15. Case 9-Box la plus haute (${haut}) avec un Compa-Ratio sous 0,85 : ${fr(sous.filter(l => l.Positionnement_9BOX === haut).length)} salariés ; case la plus basse (${bas}) au-dessus de 1,15 : ${fr(sur.filter(l => l.Positionnement_9BOX === bas).length)}.`);
  }

  // ---------- Métiers en tension : Compa-Ratio moyen par métier et Hot_job (filtrable par niveau et pôle) ----------

  // Trois paliers : rouge sous 0,90, gris de 0,90 à 1,00, vert au-dessus de 1,00 (de 0,80 à 1,10, chaque palier fait un tiers).
  const PALIERS = [[0, '#f4c7c2'], [1 / 3, '#f4c7c2'], [1 / 3, '#eef0f2'], [2 / 3, '#eef0f2'], [2 / 3, '#cfe7d7'], [1, '#cfe7d7']];

  function tension(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel) && Number.isFinite(l.Compa_Ratio));
    const tensions = C.modalites(lignes, 'Hot_job');
    const familles = C.modalites(lignes, 'Job_Family')
      .map(f => [f, C.moyenne(lignes.filter(l => l.Job_Family === f).map(l => l.Compa_Ratio))])
      .sort((a, b) => a[1] - b[1]).map(x => x[0]);   // le Compa-Ratio moyen le plus bas en haut
    const cases = familles.map(f => tensions.map(h => lignes.filter(l => l.Job_Family === f && l.Hot_job === h)));
    const compa = cases.map(r => r.map(g => g.length ? C.moyenne(g.map(l => l.Compa_Ratio)) : null));
    const salaire = cases.map(r => r.map(g => g.length ? C.moyenne(g.map(l => l.Fixe_Annuel_MAD)) : null));
    const traces = [{
      type: 'heatmap', x: tensions.map(h => `Hot_job ${h}`), y: familles.map(String), z: compa, zmin: 0.8, zmax: 1.1, colorscale: PALIERS,
      text: compa.map((r, i) => r.map((c, j) => c === null ? '' : `${fr(c, 2)}<br>${fr(salaire[i][j], 0)} k`)), texttemplate: '%{text}',
      textfont: { size: 11, color: K.ENCRE }, customdata: cases.map((r, i) => r.map((g, j) => [g.length, fr(salaire[i][j], 1)])), xgap: 2, ygap: 2,
      colorbar: { thickness: 12, tickvals: [0.85, 0.95, 1.05], ticktext: ['sous 0,90', '0,90 à 1,00', 'au-dessus de 1,00'], tickfont: { size: 11 },
        title: { text: 'Compa-Ratio<br>moyen', font: { size: 11 } } },
      hovertemplate: '%{y} · %{x}<br><b>Compa-Ratio moyen : %{z:.3f}</b><br>Salaire moyen : %{customdata[1]} kMAD<br>%{customdata[0]} salariés<extra></extra>',
    }];
    const L = grille({ titres: ['Compa-Ratio moyen et salaire moyen (kMAD) par métier et tension du métier'] });
    Object.assign(L.xaxis, { type: 'category', showgrid: false, title: titreAxe('Hot_job : 0 = tension faible, 2 = forte') });
    Object.assign(L.yaxis, { type: 'category', showgrid: false, autorange: 'reversed' });
    // Clic sur une case : les salariés de ce métier et de cette tension.
    const clic = p => { const [i, j] = p.pointNumber; return { titre: `${familles[i]} · Hot_job ${tensions[j]}`, lignes: cases[i][j] }; };
    montrer('g-tension', traces, L, 140 + 40 * Math.max(5, familles.length), clic, F.libelle(sel));
    if (!familles.length) return constat('s-tension', 'Aucun salarié pour ce filtre.');
    const forte = tensions.length - 1, enRetrait = familles.filter((f, i) => compa[i][forte] !== null && compa[i][forte] < 1);
    constat('s-tension', `${F.libelle(sel)} : métiers dont le Compa-Ratio moyen est sous 1 pour la tension la plus forte (Hot_job ${tensions[forte]}) : ${enRetrait.length ? enRetrait.map(echapper).join(', ') : 'aucun'}.`);
  }

  E.pilotage = { masseSalariale, horsGrille, marche, talents, tension };
})(window.Exploration = window.Exploration || {});
