// La vue simple de la page : des graphes usuels, à lire sans connaître les indicateurs de rémunération.
// Pourquoi cette partie (point du 29/10/2026, « aller du simple au complexe ») : la page commence par des graphes que
// RPB a l'habitude de voir. Leur forme et leurs tranches reprennent la présentation « Analyse prédictive des départs »
// (30/08/2024) : barres horizontales avec le nombre au bout, tranches dans leur ordre naturel (pas triées par taille),
// barres côte à côte pour comparer deux groupes, anneau quand il y a peu de parts. Les couleurs, elles, restent celles
// de la page, pour qu'une couleur garde le même sens d'un graphe à l'autre.
(function (E) {
  'use strict';
  const C = E.calculs, F = E.filtres;
  const { fr, pct, echapper, constat, salaries, enumerer, extremes, COULEURS: K, titreAxe, grille, montrer } = E.communs;

  // ---------- Outils de la vue simple ----------

  // Les salariés de chaque catégorie, dans l'ordre des catégories ; cle(l) dit dans quelle catégorie tombe un salarié.
  // Un salarié dont la catégorie n'est pas dans la liste (case vide, par exemple) n'est dans aucun groupe.
  function grouper(lignes, categories, cle) {
    const m = new Map(categories.map(c => [c, []]));
    for (const l of lignes) { const g = m.get(cle(l)); if (g) g.push(l); }
    return categories.map(c => m.get(c));
  }
  const compte = groupes => groupes.reduce((a, g) => a + g.length, 0);

  // Un seul graphe, sans titre au-dessus (le titre est déjà en tête du panneau) : la marge du haut, prévue pour un titre,
  // laisserait un grand vide ; on garde juste la place du nombre écrit au-dessus de la plus haute barre.
  const sansTitre = () => Object.assign(grille({}), { margin: { t: 24 } });

  // Une barre par catégorie, le nombre de salariés écrit au bout, comme dans la présentation des départs ; la part
  // en % s'affiche au survol. horizontal : les catégories se lisent de haut en bas.
  function barresEffectif(groupes, libelles, { horizontal = true, couleurs = K.ARDOISE, axes = {} } = {}) {
    const n = groupes.map(g => g.length), total = n.reduce((a, b) => a + b, 0);
    const [cat, val] = horizontal ? ['y', 'x'] : ['x', 'y'];
    return { type: 'bar', orientation: horizontal ? 'h' : 'v', [cat]: libelles, [val]: n, text: n.map(v => fr(v)), textposition: 'outside',
      cliponaxis: false, textfont: { size: 11, color: K.ENCRE }, marker: { color: couleurs }, showlegend: false, customdata: n.map(v => pct(v, total)),
      hovertemplate: `%{${cat}}<br><b>%{${val}:,} salariés</b> (%{customdata})<extra></extra>`, ...axes };
  }

  // Axes d'un graphe en barres horizontales : la première catégorie en haut (la plus jeune tranche, le plus petit niveau),
  // comme dans la présentation, et de la place à droite pour le nombre écrit au bout de la plus longue barre.
  function axesHorizontaux(L, groupes, titre) {
    Object.assign(L.yaxis, { type: 'category', autorange: 'reversed', showgrid: false, title: titreAxe(titre) });
    Object.assign(L.xaxis, { range: [0, Math.max(1, ...groupes.map(g => g.length)) * 1.15], title: titreAxe('Nombre de salariés') });
  }
  // « [30, 35[ (1 234 salariés, 12,3 %) » : la catégorie qui compte le plus de salariés. Les ex aequo sont tous cités,
  // plutôt que d'en choisir un au hasard. nom(i) écrit le nom de la catégorie i ; masculin : « chacun » (niveau) au lieu de
  // « chacune » (tranche, famille, case).
  function plusNombreuse(groupes, nom, total, masculin = false) {
    const ex = extremes(groupes.map((g, i) => ({ i, n: g.length })), e => e.n, 0);
    if (!ex || !ex.haut[0].n) return '';
    const egalite = ex.haut.length > 1;
    return `${egalite ? 'à égalité, ' : ''}${enumerer(ex.haut.map(e => nom(e.i)))} (${salaries(ex.haut[0].n)}${egalite ? (masculin ? ' chacun' : ' chacune') : ''}, ${pct(ex.haut[0].n, total)})`;
  }

  // ---------- effectif-age : effectif par tranche d'âge ----------
  // Une barre par tranche, puis l'âge moyen et médian, comme la présentation qui donnait « un âge moyen de 29 ans ».
  // La même fonction sert aussi pour l'ancienneté : ce qui change d'un graphe à l'autre est dans ses réglages (o).

  function effectifParTranche(df, sel, o) {
    const lignes = df.filter(l => F.garder(l, sel)), groupes = grouper(lignes, o.tranches, l => l[o.tranche]);
    const L = sansTitre();
    axesHorizontaux(L, groupes, o.axe);
    const clic = p => ({ titre: `${o.nom} ${p.y} ans`, lignes: groupes[p.pointNumber] });
    montrer('g-' + o.id, [barresEffectif(groupes, o.tranches)], L, 110 + 36 * o.tranches.length, clic, F.libelle(sel));
    const s = 's-' + o.id, lib = F.libelle(sel), avec = compte(groupes), sans = lignes.length - avec;
    if (!lignes.length) return constat(s, 'Aucun salarié pour ce filtre.');
    if (!avec) return constat(s, `${lib} (${salaries(lignes.length)}) : ${o.aucun}.`);
    // Les salariés sans tranche (case vide ou valeur négative) ne comptent ni dans les barres ni dans la moyenne : le constat le dit.
    const v = groupes.flat().map(l => l[o.colonne]);
    constat(s, `${lib} (${salaries(avec)} avec ${o.quoi}${sans ? `, ${fr(sans)} sans ${o.sansQuoi}` : ''}) : tranche la plus nombreuse, `
      + `${plusNombreuse(groupes, i => o.tranches[i] + ' ans', avec)}. ${o.moyen} : ${fr(C.moyenne(v), 1)} ans ; ${o.median} : ${fr(C.mediane(v), 1)} ans.`);
  }

  const effectifAge = (df, sel) => effectifParTranche(df, sel, { id: 'effectif-age', colonne: 'Age', tranche: 'Tranche_Age', tranches: C.TRANCHES_AGE,
    axe: "Tranche d'âge (années)", nom: 'Âge', quoi: 'un âge', sansQuoi: 'âge valable', aucun: 'aucun âge renseigné', moyen: 'Âge moyen', median: 'âge médian' });

  // ---------- effectif-anciennete : effectif par tranche d'ancienneté ----------
  // Le même graphe que pour l'âge, avec les tranches d'ancienneté de 2 ans.

  const effectifAnciennete = (df, sel) => effectifParTranche(df, sel, { id: 'effectif-anciennete', colonne: 'Anciennete', tranche: 'Tranche_Anciennete',
    tranches: C.TRANCHES, axe: "Tranche d'ancienneté (années)", nom: 'Ancienneté', quoi: 'une ancienneté', sansQuoi: 'ancienneté valable', aucun: 'aucune ancienneté renseignée',
    moyen: 'Ancienneté moyenne', median: 'ancienneté médiane' });

  // ---------- effectif-niveau : effectif par niveau ----------

  function effectifNiveau(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel));
    // Les niveaux sont lus dans le fichier entier : un niveau sans personne dans le filtre garde sa place, avec 0.
    const niveaux = C.modalites(df, 'Niveau'), libelles = niveaux.map(String), groupes = grouper(lignes, niveaux, l => l.Niveau);
    const L = sansTitre();
    axesHorizontaux(L, groupes, 'Niveau');
    const clic = p => ({ titre: 'Niveau ' + p.y, lignes: groupes[p.pointNumber] });
    montrer('g-effectif-niveau', [barresEffectif(groupes, libelles)], L, 110 + 32 * Math.max(4, niveaux.length), clic, F.libelle(sel));
    const lib = F.libelle(sel), avec = compte(groupes), sans = lignes.length - avec;
    if (!lignes.length) return constat('s-effectif-niveau', 'Aucun salarié pour ce filtre.');
    if (!avec) return constat('s-effectif-niveau', `${lib} (${salaries(lignes.length)}) : aucun niveau renseigné.`);
    constat('s-effectif-niveau', `${lib} (${salaries(avec)} avec un niveau${sans ? `, ${fr(sans)} sans` : ''}) : niveau le plus nombreux, `
      + `${plusNombreuse(groupes, i => 'niveau ' + libelles[i], avec, true)}.`);
  }

  // ---------- effectif-metier : effectif par famille de métier ----------

  // Un anneau quand il y a peu de parts (6 au plus), comme les anneaux de la présentation des départs. Au-delà, les
  // petites parts ne se lisent plus : des barres rangées de la plus longue à la plus courte prennent le relais.
  const PARTS_MAX = 6;
  const TEINTES = [K.ARDOISE, K.OR, K.BLEU, K.CUIVRE, K.BRUN, K.PALE];
  function repartition(id, groupes, libelles, { couleurs = TEINTES, trier = true, titreClic, sel }) {
    let ordre = groupes.map((_, i) => i);
    if (trier) ordre.sort((a, b) => groupes[b].length - groupes[a].length);   // la plus grosse part d'abord
    const g = ordre.map(i => groupes[i]), lib = ordre.map(i => libelles[i]), total = compte(g);
    const clic = p => ({ titre: `${titreClic}${lib[p.pointNumber]}`, lignes: g[p.pointNumber] });
    if (libelles.length > PARTS_MAX) {
      const L = sansTitre();
      axesHorizontaux(L, g, '');
      return montrer('g-' + id, [barresEffectif(g, lib)], L, 120 + 30 * lib.length, clic, F.libelle(sel));
    }
    const n = g.map(x => x.length);
    // Le nom et la part s'écrivent autour de l'anneau ; le centre rappelle sur combien de salariés portent les parts.
    const trace = { type: 'pie', hole: 0.55, labels: lib.map(String), values: n, sort: false, direction: 'clockwise', rotation: 0,
      marker: { colors: ordre.map(i => couleurs[i % couleurs.length]), line: { color: '#fff', width: 2 } },
      text: n.map((v, i) => `${echapper(lib[i])}<br>${pct(v, total)}`), textinfo: 'text', textposition: 'outside', textfont: { size: 12, color: K.ENCRE },
      customdata: n.map(v => pct(v, total)), hovertemplate: '%{label}<br><b>%{value:,} salariés</b> (%{customdata})<extra></extra>', showlegend: false };
    const L = { margin: { t: 40, b: 40 }, annotations: [{ text: `<b>${fr(total)}</b><br>${total > 1 ? 'salariés' : 'salarié'}`, x: 0.5, y: 0.5,
      xref: 'paper', yref: 'paper', showarrow: false, font: { size: 14, color: K.ENCRE } }] };
    montrer('g-' + id, total ? [trace] : [], L, 420, clic, F.libelle(sel));
  }

  function effectifMetier(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel)), familles = C.modalites(df, 'Job_Family'), groupes = grouper(lignes, familles, l => l.Job_Family);
    repartition('effectif-metier', groupes, familles.map(String), { titreClic: 'Métier ', sel });
    const lib = F.libelle(sel), avec = compte(groupes), sans = lignes.length - avec;
    if (!lignes.length) return constat('s-effectif-metier', 'Aucun salarié pour ce filtre.');
    if (!avec) return constat('s-effectif-metier', `${lib} (${salaries(lignes.length)}) : aucun métier renseigné.`);
    const n = groupes.filter(g => g.length).length;
    constat('s-effectif-metier', `${lib} (${salaries(avec)} avec un métier${sans ? `, ${fr(sans)} sans` : ''}, répartis dans ${fr(n)} famille${n > 1 ? 's' : ''}) : `
      + `famille la plus nombreuse, ${plusNombreuse(groupes, i => echapper(familles[i]), avec)}.`);
  }

  E.simples = { effectifAge, effectifAnciennete, effectifNiveau, effectifMetier };
})(window.Exploration = window.Exploration || {});
