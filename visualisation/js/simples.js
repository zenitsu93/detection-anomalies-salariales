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

  // ---------- femmes-hommes : part des femmes et des hommes, dans l'ensemble et par pôle ----------

  // Femmes et hommes : les couleurs du graphe de l'équité. Un autre code dans Sexe garde son code et une couleur neutre.
  const SEXES = { F: ['Femmes', K.OR], M: ['Hommes', K.BLEU] };
  const nomSexe = s => SEXES[s] ? SEXES[s][0] : `Sexe « ${s} »`;
  const couleurSexe = s => SEXES[s] ? SEXES[s][1] : K.PALE;

  function femmesHommes(df, sel) {
    // Femmes, puis hommes, puis les autres codes éventuels : l'ordre alphabétique aurait glissé un code « H » entre les deux.
    const lignes = df.filter(l => F.garder(l, sel)), sexes = C.modalites(lignes, 'Sexe').sort((a, b) => !!SEXES[b] - !!SEXES[a] || (a === 'M') - (b === 'M'));
    const aSexe = l => sexes.includes(l.Sexe);   // la part se calcule sur les salariés dont le Sexe est renseigné
    // « Ensemble » d'abord, puis chaque pôle : on compare chaque pôle à l'entreprise entière.
    const groupes = [['Ensemble', lignes.filter(aSexe)],
      ...C.modalites(lignes, 'Entite_N1').map(p => [String(p), lignes.filter(l => l.Entite_N1 === p && aSexe(l))])];
    const x = groupes.map(g => g[0]);
    const part = (s, g) => g.length ? 100 * g.filter(l => l.Sexe === s).length / g.length : null;
    const traces = sexes.map(s => {
      const v = groupes.map(([, g]) => part(s, g));
      return { type: 'bar', name: nomSexe(s), x, y: v, marker: { color: couleurSexe(s) }, text: v.map(p => p === null ? '' : fr(p, 0) + ' %'),
        textposition: 'outside', cliponaxis: false, textfont: { size: 11, color: K.ENCRE },
        customdata: groupes.map(([, g]) => [g.filter(l => l.Sexe === s).length, g.length]),
        hovertemplate: `%{x}<br>${nomSexe(s)} : <b>%{y:.1f} %</b><br>%{customdata[0]:,} salariés sur %{customdata[1]:,}<extra></extra>` };
    });
    const L = sansTitre();
    L.barmode = 'group';   // les barres des femmes et des hommes d'un même pôle côte à côte, comme « Turnover par genre »
    Object.assign(L.xaxis, { type: 'category', showgrid: false, title: titreAxe('Pôle') });
    Object.assign(L.yaxis, { range: [0, 110], tickvals: [0, 25, 50, 75, 100], ticktext: ['0 %', '25 %', '50 %', '75 %', '100 %'], title: titreAxe('Part des salariés') });
    // Un trait sépare « Ensemble » des pôles.
    if (groupes.length > 1) L.shapes.push({ type: 'line', xref: 'x', x0: 0.5, x1: 0.5, yref: 'y domain', y0: 0, y1: 1, line: { color: K.TRAIT, dash: 'dot', width: 1.5 } });
    const clic = p => {
      const s = sexes[p.curveNumber], g = groupes[p.pointNumber];
      return { titre: `${nomSexe(s)} · ${g[0]}`, lignes: g[1].filter(l => l.Sexe === s) };
    };
    montrer('g-femmes-hommes', traces, L, 460, clic, F.libelle(sel));
    const lib = F.libelle(sel), tous = groupes[0][1], sans = lignes.length - tous.length;
    if (!lignes.length) return constat('s-femmes-hommes', 'Aucun salarié pour ce filtre.');
    if (!tous.length) return constat('s-femmes-hommes', `${lib} (${salaries(lignes.length)}) : la colonne Sexe est vide.`);
    // « femmes 46 % » en minuscules au milieu de la phrase ; un autre code reste écrit tel quel (« Sexe « H » »).
    const ensemble = sexes.map(s => `${SEXES[s] ? nomSexe(s).toLowerCase() : echapper(nomSexe(s))} ${fr(part(s, tous), 0)} %`);
    // Un code autre que F ou M (H, Femme…) est montré tel quel et signalé : la page ne devine pas ce qu'il veut dire.
    const autres = sexes.filter(s => !SEXES[s]).map(s => `« ${echapper(s)} »`);
    const signal = autres.length ? ` Codes de Sexe autres que F et M : ${enumerer(autres)}.` : '';
    const debut = `${lib} (${salaries(tous.length)} dont le Sexe est renseigné${sans ? `, ${fr(sans)} sans` : ''}) : ${enumerer(ensemble)}.`;
    const poles = groupes.slice(1).filter(([, g]) => g.length);
    if (!sexes.includes('F') || poles.length < 2) return constat('s-femmes-hommes', debut + signal);
    // Le pôle le plus et le moins féminisé, comparés sur la part arrondie telle qu'elle est écrite.
    const ex = extremes(poles, ([, g]) => part('F', g), 0), noms = t => enumerer(t.map(g => echapper(g[0]))), ecrit = t => fr(part('F', t[0][1]), 0) + ' %';
    const comparaison = ex.egaux ? ` Même part de femmes dans tous les pôles (${ecrit(ex.haut)}).`
      : ` Part de femmes la plus forte : ${noms(ex.haut)} (${ecrit(ex.haut)}) ; la plus faible : ${noms(ex.bas)} (${ecrit(ex.bas)}).`;
    constat('s-femmes-hommes', debut + comparaison + signal);
  }

  // ---------- hot-job : répartition des salariés selon la tension du métier ----------

  // Les mêmes teintes que dans le graphe « Compétences et tension métier » : bleu = tension faible, cuivre = forte.
  const TENSION = [K.BLEU, K.OR, K.CUIVRE];

  function hotJob(df, sel) {
    // Les valeurs de Hot_job sont lues dans le fichier entier, jamais supposées de 0 à 2 : la plus haute est la tension la plus forte.
    const lignes = df.filter(l => F.garder(l, sel)), echelle = C.modalites(df, 'Hot_job'), groupes = grouper(lignes, echelle, l => l.Hot_job);
    // Les parts restent dans l'ordre de l'échelle (de la tension la plus faible à la plus forte) : leur ordre a un sens.
    repartition('hot-job', groupes, echelle.map(h => 'Hot_job ' + fr(h)),
      { couleurs: echelle.length <= TENSION.length ? TENSION : TEINTES, trier: false, titreClic: '', sel });
    const lib = F.libelle(sel), avec = compte(groupes), sans = lignes.length - avec;
    if (!lignes.length) return constat('s-hot-job', 'Aucun salarié pour ce filtre.');
    if (!avec) return constat('s-hot-job', `${lib} (${salaries(lignes.length)}) : Hot_job est vide.`);
    const parts = echelle.map((h, i) => `Hot_job ${fr(h)} : ${pct(groupes[i].length, avec)}`).join(' · ');
    const sens = echelle.length > 1 ? ` (${fr(echelle[0])} = tension la plus faible, ${fr(echelle[echelle.length - 1])} = la plus forte)` : '';
    constat('s-hot-job', `${lib} (${salaries(avec)} avec un Hot_job${sans ? `, ${fr(sans)} sans` : ''}) : ${parts}${sens}.`);
  }

  // ---------- salaire-age : salaire moyen et médian par tranche d'âge ----------
  // La même fonction sert aussi pour l'ancienneté (graphe suivant). Deux barres par tranche : la moyenne et la médiane. La médiane ne bouge pas pour un seul très haut salaire, la moyenne
  // si : quand les deux s'écartent, quelques salaires hors norme tirent la moyenne.

  const STATS = [['Salaire moyen', C.moyenne, K.ARDOISE], ['Salaire médian', C.mediane, K.BRUN]];

  function salaireParTranche(df, sel, o) {
    const lignes = df.filter(l => F.garder(l, sel)), groupes = grouper(lignes, o.tranches, l => l[o.tranche]);
    const sal = groupes.map(g => g.map(l => l.Fixe_Annuel_MAD).filter(Number.isFinite));
    const valeurs = STATS.map(([, f]) => sal.map(s => s.length ? f(s) : null));
    const traces = STATS.map(([nom, , couleur], k) => ({ type: 'bar', name: nom, x: o.tranches, y: valeurs[k], marker: { color: couleur },
      text: valeurs[k].map(v => v === null ? '' : fr(v, 0)), textposition: 'outside', cliponaxis: false, textfont: { size: 11, color: K.ENCRE },
      customdata: sal.map(s => s.length), hovertemplate: `%{x} ans<br>${nom} : <b>%{y:,.1f} kMAD</b><br>%{customdata:,} salariés avec un salaire<extra></extra>` }));
    const L = sansTitre();
    L.barmode = 'group';
    Object.assign(L.xaxis, { type: 'category', showgrid: false, title: titreAxe(o.axe) });
    L.yaxis.title = titreAxe('Fixe_Annuel_MAD (kMAD)');
    const clic = p => ({ titre: `${o.nom} ${p.x} ans`, lignes: groupes[p.pointNumber] });
    montrer('g-' + o.id, traces, L, 460, clic, F.libelle(sel));
    const s = 's-' + o.id, lib = F.libelle(sel), avec = sal.reduce((a, v) => a + v.length, 0);
    if (!lignes.length) return constat(s, 'Aucun salarié pour ce filtre.');
    if (!avec) return constat(s, `${lib} (${salaries(lignes.length)}) : aucun n'a à la fois ${o.quoi} et un salaire.`);
    const tranches = o.tranches.map((t, i) => ({ t, v: valeurs[0][i] })).filter(x => x.v !== null);
    const ex = extremes(tranches, x => x.v, 0), noms = t => enumerer(t.map(x => x.t + ' ans'));
    const lecture = tranches.length < 2 ? ` Une seule tranche a des salariés : ${noms(tranches)} (${fr(tranches[0].v, 0)} kMAD de salaire moyen).`
      : ex.egaux ? ` Même salaire moyen dans toutes les tranches (${fr(ex.haut[0].v, 0)} kMAD).`
      : ` Salaire moyen le plus haut : ${noms(ex.haut)} (${fr(ex.haut[0].v, 0)} kMAD) ; le plus bas : ${noms(ex.bas)} (${fr(ex.bas[0].v, 0)} kMAD).`;
    // Sans filtre de niveau, une tranche peut sembler mieux payée seulement parce qu'elle compte plus de niveaux élevés : le constat le rappelle.
    const conseil = sel.niveau === null || sel.niveau.length > 1
      ? ' Plusieurs niveaux sont mélangés : choisir un seul niveau dans le filtre pour comparer des salariés de même niveau.' : '';
    constat(s, `${lib} (${salaries(avec)} avec ${o.quoi} et un salaire).${lecture}${conseil}`);
  }

  const salaireAge = (df, sel) => salaireParTranche(df, sel, { id: 'salaire-age', tranche: 'Tranche_Age', tranches: C.TRANCHES_AGE,
    axe: "Tranche d'âge (années)", nom: 'Âge', quoi: 'un âge' });

  // ---------- salaire-anciennete : salaire moyen et médian par tranche d'ancienneté ----------
  // Le même graphe que pour l'âge, avec les tranches d'ancienneté de 2 ans.

  const salaireAnciennete = (df, sel) => salaireParTranche(df, sel, { id: 'salaire-anciennete', tranche: 'Tranche_Anciennete', tranches: C.TRANCHES,
    axe: "Tranche d'ancienneté (années)", nom: 'Ancienneté', quoi: 'une ancienneté' });

  // ---------- salaire-sexe : salaire moyen des femmes et des hommes, par niveau ----------

  function salaireSexe(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel) && Number.isFinite(l.Fixe_Annuel_MAD));
    const niveaux = C.modalites(lignes, 'Niveau'), x = niveaux.map(String);
    const groupe = (s, n) => lignes.filter(l => l.Sexe === s && l.Niveau === n);
    const moyennes = { F: [], M: [] };
    const traces = ['F', 'M'].map(s => {
      const g = niveaux.map(n => groupe(s, n)), v = g.map(x => x.length ? C.moyenne(x.map(l => l.Fixe_Annuel_MAD)) : null);
      moyennes[s] = v;
      return { type: 'bar', name: nomSexe(s), x, y: v, marker: { color: couleurSexe(s) }, text: v.map(m => m === null ? '' : fr(m, 0)),
        textposition: 'outside', cliponaxis: false, textfont: { size: 11, color: K.ENCRE }, customdata: g.map(x => x.length),
        hovertemplate: `Niveau %{x} · ${nomSexe(s)}<br>Salaire moyen : <b>%{y:,.1f} kMAD</b><br>%{customdata:,} salariés<extra></extra>` };
    });
    const L = sansTitre();
    L.barmode = 'group';   // femmes et hommes d'un même niveau côte à côte, comme « Turnover par genre » dans la présentation
    Object.assign(L.xaxis, { type: 'category', showgrid: false, title: titreAxe('Niveau') });
    L.yaxis.title = titreAxe('Salaire moyen (kMAD)');
    const clic = p => { const s = ['F', 'M'][p.curveNumber]; return { titre: `${nomSexe(s)}, niveau ${p.x}`, lignes: groupe(s, niveaux[p.pointNumber]) }; };
    montrer('g-salaire-sexe', traces, L, 460, clic, F.libelle(sel));
    const lib = F.libelle(sel), nF = lignes.filter(l => l.Sexe === 'F').length, nM = lignes.filter(l => l.Sexe === 'M').length;
    if (!lignes.length) return constat('s-salaire-sexe', 'Aucun salarié avec un salaire pour ce filtre.');
    // Seuls F et M sont comparés : un autre code est signalé, pas deviné (comme dans le graphe de l'équité).
    const horsMF = lignes.length - nF - nM, autres = C.modalites(lignes.filter(l => l.Sexe !== 'F' && l.Sexe !== 'M'), 'Sexe').map(s => `« ${echapper(s)} »`);
    const nonComptes = horsMF ? ` Non comptés : ${salaries(horsMF)} dont le Sexe n'est ni F ni M${autres.length ? ` (${enumerer(autres)})` : ''}.` : '';
    const debut = `${lib} (${fr(nF)} femme${nF > 1 ? 's' : ''} et ${fr(nM)} homme${nM > 1 ? 's' : ''} avec un salaire)`;
    // L'écart de chaque niveau où il y a des femmes et des hommes, arrondi à 0,1 % comme il est écrit : « 0,0 % » veut dire « égal ».
    const ecarts = niveaux.map((n, i) => ({ n, e: moyennes.F[i] > 0 && moyennes.M[i] !== null ? Math.round(1000 * (moyennes.M[i] / moyennes.F[i] - 1)) / 10 : null }))
      .filter(x => x.e !== null);
    if (!ecarts.length) return constat('s-salaire-sexe', `${debut} : aucun niveau ne compte à la fois des femmes et des hommes, pas de comparaison possible.${nonComptes}`);
    const dessus = ecarts.filter(x => x.e > 0).length, dessous = ecarts.filter(x => x.e < 0).length, egal = ecarts.length - dessus - dessous;
    const niv = k => `${fr(k)} niveau${k > 1 ? 'x' : ''}`;
    const repart = [dessus && `au-dessus de celui des femmes dans ${niv(dessus)}`, dessous && `en dessous dans ${niv(dessous)}`, egal && `égal dans ${niv(egal)}`].filter(Boolean);
    const plusGrand = ecarts.reduce((a, b) => Math.abs(b.e) > Math.abs(a.e) ? b : a);
    const max = plusGrand.e ? ` Plus grand écart : niveau ${plusGrand.n}, où le salaire moyen des hommes est ${fr(Math.abs(plusGrand.e), 1)} % `
      + `${plusGrand.e > 0 ? 'au-dessus de' : 'en dessous de'} celui des femmes.` : '';
    constat('s-salaire-sexe', `${debut} : sur ${fr(ecarts.length)} niveau${ecarts.length > 1 ? 'x' : ''} qui comptent des femmes et des hommes, `
      + `le salaire moyen des hommes est ${enumerer(repart)}.${max} Le graphe « Équité femmes / hommes et pratiques par pôle » compare aussi à métier égal.${nonComptes}`);
  }

  // ---------- tranches-salaire : effectif par tranche de salaire ----------

  // Même chose en barres verticales : de la place en haut pour le nombre écrit au-dessus de la plus haute barre.
  function axesVerticaux(L, s, groupes, titre) {
    Object.assign(L['xaxis' + s], { type: 'category', showgrid: false, title: titreAxe(titre) });
    Object.assign(L['yaxis' + s], { range: [0, Math.max(1, ...groupes.map(g => g.length)) * 1.15], title: titreAxe('Nombre de salariés') });
  }

  // Tranches de 50 kMAD. Les tranches sont calculées sur le fichier entier, pour ne pas changer d'un filtre à l'autre.
  // Les salaires les plus bas (5 %) et les plus hauts (5 %) sont regroupés dans « inf à … » et « sup à … » : sinon, un
  // seul très haut salaire étirerait le graphe sur des dizaines de barres vides. S'il fallait plus de 20 barres, la
  // largeur double (100 kMAD, puis 200…), pour que le graphe reste lisible.
  const PAS_SALAIRE = 50;
  function tranchesSalaire(df) {
    const v = df.map(l => l.Fixe_Annuel_MAD).filter(Number.isFinite);
    if (!v.length) return null;
    const bas = C.quantile(v, 0.05), haut = C.quantile(v, 0.95);
    let pas = PAS_SALAIRE;
    while (Math.ceil(haut / pas) - Math.floor(bas / pas) > 20) pas *= 2;
    // « inf à 0 » n'aurait pas de sens : la première borne est au moins une largeur de tranche.
    const debut = Math.max(pas, Math.floor(bas / pas) * pas), fin = Math.max(debut + pas, Math.ceil(haut / pas) * pas), bornes = [];
    for (let b = debut; b <= fin; b += pas) bornes.push(b);
    return { pas, bornes, libelles: C.libellesTranches(bornes) };
  }

  function salaireEnTranches(df, sel) {
    const t = tranchesSalaire(df), lignes = df.filter(l => F.garder(l, sel) && Number.isFinite(l.Fixe_Annuel_MAD));
    if (!t) { Plotly.purge('g-tranches-salaire'); return constat('s-tranches-salaire', 'Aucun salaire renseigné dans employes.xlsx.'); }
    const groupes = grouper(lignes, t.libelles, l => C.trancheDe(l.Fixe_Annuel_MAD, t.bornes, t.libelles));
    const L = sansTitre();
    axesVerticaux(L, '', groupes, `Fixe_Annuel_MAD (kMAD), tranches de ${fr(t.pas)}`);
    const clic = p => ({ titre: `Salaire ${p.x} kMAD`, lignes: groupes[p.pointNumber] });
    montrer('g-tranches-salaire', [barresEffectif(groupes, t.libelles, { horizontal: false })], L, 440, clic, F.libelle(sel));
    if (!lignes.length) return constat('s-tranches-salaire', 'Aucun salarié avec un salaire pour ce filtre.');
    const sal = lignes.map(l => l.Fixe_Annuel_MAD);
    constat('s-tranches-salaire', `${F.libelle(sel)} (${salaries(lignes.length)} avec un salaire) : tranche la plus nombreuse, `
      + `${plusNombreuse(groupes, i => t.libelles[i] + ' kMAD', lignes.length)}. Salaire moyen : ${fr(C.moyenne(sal), 1)} kMAD ; médian : ${fr(C.mediane(sal), 1)} kMAD.`);
  }

  E.simples = { effectifAge, effectifAnciennete, effectifNiveau, effectifMetier, femmesHommes, hotJob, salaireAge, salaireAnciennete, salaireSexe, salaireEnTranches };
})(window.Exploration = window.Exploration || {});
