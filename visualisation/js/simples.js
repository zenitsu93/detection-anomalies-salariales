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
  // Les catégories qui ont au moins un salarié, avec leur numéro d'origine (i) pour garder leur couleur. Pourquoi
  // (demande du 09/11/2026) : avec un filtre, des barres « 0 », des parts vides ou des lignes vides encombraient le
  // graphe sans rien dire ; une catégorie sans personne n'est plus dessinée. Les constats, eux, se calculent toujours
  // sur toutes les catégories.
  const nonVides = (groupes, libelles) => groupes.map((g, i) => ({ g, lib: libelles[i], i })).filter(x => x.g.length);

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
    const v = nonVides(groupes, o.tranches), vg = v.map(x => x.g);
    const L = sansTitre();
    axesHorizontaux(L, vg, o.axe);
    const clic = p => ({ titre: `${o.nom} ${p.y} ans`, lignes: vg[p.pointNumber] });
    montrer('g-' + o.id, [barresEffectif(vg, v.map(x => x.lib))], L, 110 + 36 * Math.max(3, v.length), clic, F.libelle(sel));
    const s = 's-' + o.id, lib = F.libelle(sel), avec = compte(groupes), sans = lignes.length - avec;
    if (!lignes.length) return constat(s, 'Aucun salarié pour ce filtre.');
    if (!avec) return constat(s, `${lib} (${salaries(lignes.length)}) : ${o.aucun}.`);
    // Les salariés sans tranche (case vide ou valeur négative) ne comptent ni dans les barres ni dans la moyenne : le constat le dit.
    const ans = groupes.flat().map(l => l[o.colonne]);
    constat(s, `${lib} (${salaries(avec)} avec ${o.quoi}${sans ? `, ${fr(sans)} sans ${o.sansQuoi}` : ''}) : tranche la plus nombreuse, `
      + `${plusNombreuse(groupes, i => o.tranches[i] + ' ans', avec)}. ${o.moyen} : ${fr(C.moyenne(ans), 1)} ans ; ${o.median} : ${fr(C.mediane(ans), 1)} ans.`);
  }

  const effectifAge = (df, sel) => effectifParTranche(df, sel, { id: 'effectif-age', colonne: 'Age', tranche: 'Tranche_Age', tranches: C.TRANCHES_AGE,
    axe: "Tranche d'âge (années)", nom: 'Âge', quoi: 'un âge', sansQuoi: 'âge valable', aucun: 'aucun âge renseigné', moyen: 'Âge moyen', median: 'âge médian' });

  // ---------- effectif-anciennete : effectif par tranche d'ancienneté ----------
  // Le même graphe que pour l'âge, avec les tranches d'ancienneté : inf à 2, [2, 5[, puis des pas de 5 ans (voir
  // tranchesAnciennete dans calculs.js). Elles sont recalculées sur le fichier entier, comme celles de chaque salarié.
  const tranchesAnciennete = df => C.tranchesAnciennete(C.colonne(df, 'Anciennete')).libelles;

  const effectifAnciennete = (df, sel) => effectifParTranche(df, sel, { id: 'effectif-anciennete', colonne: 'Anciennete', tranche: 'Tranche_Anciennete',
    tranches: tranchesAnciennete(df), axe: "Tranche d'ancienneté (années)", nom: 'Ancienneté', quoi: 'une ancienneté', sansQuoi: 'ancienneté valable', aucun: 'aucune ancienneté renseignée',
    moyen: 'Ancienneté moyenne', median: 'ancienneté médiane' });

  // ---------- effectif-niveau : effectif par niveau ----------

  function effectifNiveau(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel));
    // Les niveaux sont lus dans le fichier entier ; un niveau sans personne dans le filtre n'est plus dessiné (voir nonVides).
    const niveaux = C.modalites(df, 'Niveau'), libelles = niveaux.map(String), groupes = grouper(lignes, niveaux, l => l.Niveau);
    const v = nonVides(groupes, libelles), vg = v.map(x => x.g);
    const L = sansTitre();
    axesHorizontaux(L, vg, 'Niveau');
    const clic = p => ({ titre: 'Niveau ' + p.y, lignes: vg[p.pointNumber] });
    montrer('g-effectif-niveau', [barresEffectif(vg, v.map(x => x.lib))], L, 110 + 32 * Math.max(4, v.length), clic, F.libelle(sel));
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
    // Une part vide n'est pas dessinée (voir nonVides) : sur un anneau, elle laissait son nom et « 0 % » autour.
    let ordre = groupes.map((_, i) => i).filter(i => groupes[i].length);
    if (trier) ordre.sort((a, b) => groupes[b].length - groupes[a].length);   // la plus grosse part d'abord
    const g = ordre.map(i => groupes[i]), lib = ordre.map(i => libelles[i]), total = compte(g);
    const clic = p => ({ titre: `${titreClic}${lib[p.pointNumber]}`, lignes: g[p.pointNumber] });
    if (ordre.length > PARTS_MAX) {
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

  // Médiane en cuivre, comme dans « SAR et effectifs par pôle », où le brun est déjà pris par le SAR : la médiane a la même couleur partout.
  const STATS = [['Salaire moyen', C.moyenne, K.ARDOISE], ['Salaire médian', C.mediane, K.CUIVRE]];

  function salaireParTranche(df, sel, o) {
    const lignes = df.filter(l => F.garder(l, sel)), groupes = grouper(lignes, o.tranches, l => l[o.tranche]);
    const sal = groupes.map(g => g.map(l => l.Fixe_Annuel_MAD).filter(Number.isFinite));
    const valeurs = STATS.map(([, f]) => sal.map(s => s.length ? f(s) : null));
    // Seules les tranches où quelqu'un a un salaire sont dessinées (voir nonVides) : une tranche vide restait sur l'axe, sans barre.
    const k0 = o.tranches.map((_, i) => i).filter(i => sal[i].length), x = k0.map(i => o.tranches[i]);
    const traces = STATS.map(([nom, , couleur], k) => ({ type: 'bar', name: nom, x, y: k0.map(i => valeurs[k][i]), marker: { color: couleur },
      text: k0.map(i => fr(valeurs[k][i], 0)), textposition: 'outside', cliponaxis: false, textfont: { size: 11, color: K.ENCRE },
      customdata: k0.map(i => sal[i].length), hovertemplate: `%{x} ans<br>${nom} : <b>%{y:,.1f} kMAD</b><br>%{customdata:,} salariés avec un salaire<extra></extra>` }));
    const L = sansTitre();
    L.barmode = 'group';
    Object.assign(L.xaxis, { type: 'category', showgrid: false, title: titreAxe(o.axe) });
    L.yaxis.title = titreAxe('Fixe_Annuel_MAD (kMAD)');
    const clic = p => ({ titre: `${o.nom} ${p.x} ans`, lignes: groupes[k0[p.pointNumber]] });
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
  // Le même graphe que pour l'âge, avec les tranches du graphe « Effectif par tranche d'ancienneté ».

  const salaireAnciennete = (df, sel) => salaireParTranche(df, sel, { id: 'salaire-anciennete', tranche: 'Tranche_Anciennete', tranches: tranchesAnciennete(df),
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
    const v = nonVides(groupes, t.libelles), vg = v.map(x => x.g);
    const L = sansTitre();
    axesVerticaux(L, '', vg, `Fixe_Annuel_MAD (kMAD), tranches de ${fr(t.pas)}`);
    const clic = p => ({ titre: `Salaire ${p.x} kMAD`, lignes: vg[p.pointNumber] });
    montrer('g-tranches-salaire', [barresEffectif(vg, v.map(x => x.lib), { horizontal: false })], L, 440, clic, F.libelle(sel));
    if (!lignes.length) return constat('s-tranches-salaire', 'Aucun salarié avec un salaire pour ce filtre.');
    const sal = lignes.map(l => l.Fixe_Annuel_MAD);
    constat('s-tranches-salaire', `${F.libelle(sel)} (${salaries(lignes.length)} avec un salaire) : tranche la plus nombreuse, `
      + `${plusNombreuse(groupes, i => t.libelles[i] + ' kMAD', lignes.length)}. Salaire moyen : ${fr(C.moyenne(sal), 1)} kMAD ; médian : ${fr(C.mediane(sal), 1)} kMAD.`);
  }

  // ---------- ecart-mid : effectif par tranche d'écart au milieu de la grille ----------

  // Écart au Mid = de combien le salaire est au-dessus ou en dessous du milieu de sa grille, en % (Compa-Ratio − 1).
  // Tranches de 10 %, écrites comme les tranches d'évolution du Total Cash de la présentation (« [0% ; 5%[ »).
  const BORNES_ECART = [-20, -10, 0, 10, 20];
  const ECARTS = ['inf à -20 %', '[-20 % ; -10 %[', '[-10 % ; 0 %[', '[0 % ; 10 %[', '[10 % ; 20 %[', 'sup à 20 %'];
  // Arrondi au millionième : sans lui, un Compa-Ratio de 0,9 donne −10,000000000000009 % et tomberait dans la mauvaise tranche.
  const ecartMid = l => Math.round((l.Compa_Ratio - 1) * 1e8) / 1e6;

  function ecartAuMid(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel)), avec = lignes.filter(l => Number.isFinite(l.Compa_Ratio));
    const groupes = grouper(avec, ECARTS, l => C.trancheDe(ecartMid(l), BORNES_ECART, ECARTS));
    const v = nonVides(groupes, ECARTS), vg = v.map(x => x.g);
    const L = sansTitre();
    axesVerticaux(L, '', vg, 'Écart du salaire au milieu de sa grille (Mid)');
    // Sous le Mid en ardoise, au-dessus en gris clair : seul le trop bas compte comme anomalie (décision du 29/10/2026).
    // La couleur suit la tranche d'origine (x.i) : une tranche masquée ne décale pas les couleurs des suivantes.
    const couleurs = v.map(x => x.i < 3 ? K.ARDOISE : K.PALE);
    const clic = p => ({ titre: `Écart au Mid ${p.x}`, lignes: vg[p.pointNumber] });
    montrer('g-ecart-mid', [barresEffectif(vg, v.map(x => x.lib), { horizontal: false, couleurs })], L, 440, clic, F.libelle(sel));
    const lib = F.libelle(sel), n = avec.length, sans = lignes.length - n;
    if (!lignes.length) return constat('s-ecart-mid', 'Aucun salarié pour ce filtre.');
    if (!n) return constat('s-ecart-mid', `${lib} (${salaries(lignes.length)}) : aucun n'a à la fois un salaire et une grille (Mid) pour son métier et son niveau.`);
    const sous = groupes.slice(0, 3).reduce((a, g) => a + g.length, 0), loin = groupes[0].length;
    constat('s-ecart-mid', `${lib} (${salaries(n)} avec un salaire et une grille${sans ? `, ${fr(sans)} sans` : ''}) : ${pct(sous, n, 0)} sont payés sous le milieu `
      + `de leur grille, dont ${salaries(loin)} à plus de 20 % en dessous (${pct(loin, n)}).`);
  }

  // ---------- sous-min : part des salariés sous le Min de la grille et sous le P25 du marché, par pôle ----------
  // L'équivalent du « taux de turnover par pôle » de la présentation : une part en %, pôle par pôle. Seul le trop bas est
  // regardé : depuis le 29/10/2026, un salaire trop haut n'est plus une anomalie.

  function sousMin(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel) && Number.isFinite(l.Fixe_Annuel_MAD));
    const poles = C.modalites(lignes, 'Entite_N1');
    const groupes = [['Ensemble', lignes], ...poles.map(p => [String(p), lignes.filter(l => l.Entite_N1 === p)])];
    // Chaque part se calcule sur les salariés qui ont la borne : ceux sans grille ne comptent pas pour le Min, ceux sans P25 pas pour le marché.
    const series = [['Sous le Min de la grille', 'Min', K.ROUGE], ['Sous le P25 du marché', 'Market_P25', K.BLEU]]
      .filter(([, c]) => df.some(l => Number.isFinite(l[c])));   // sans aucun P25 dans market.xlsx, seule la grille est montrée
    const calc = series.map(([, c]) => groupes.map(([, g]) => { const avec = g.filter(l => Number.isFinite(l[c])); return [avec.filter(l => l.Fixe_Annuel_MAD < l[c]), avec.length]; }));
    const traces = series.map(([nom, , couleur], k) => {
      const v = calc[k].map(([sous, n]) => n ? 100 * sous.length / n : null);
      return { type: 'bar', name: nom, x: groupes.map(g => g[0]), y: v, marker: { color: couleur }, text: v.map(p => p === null ? '' : fr(p, 1) + ' %'),
        textposition: 'outside', cliponaxis: false, textfont: { size: 11, color: K.ENCRE }, customdata: calc[k].map(([sous, n]) => [sous.length, n]),
        hovertemplate: `%{x}<br>${nom} : <b>%{y:.1f} %</b><br>%{customdata[0]:,} salariés sur %{customdata[1]:,}<extra></extra>` };
    });
    const L = sansTitre();
    L.barmode = 'group';
    Object.assign(L.xaxis, { type: 'category', showgrid: false, title: titreAxe('Pôle') });
    Object.assign(L.yaxis, { rangemode: 'tozero', ticksuffix: ' %', title: titreAxe('Part des salariés') });
    if (groupes.length > 1) L.shapes.push({ type: 'line', xref: 'x', x0: 0.5, x1: 0.5, yref: 'y domain', y0: 0, y1: 1, line: { color: K.TRAIT, dash: 'dot', width: 1.5 } });
    const clic = p => ({ titre: `${series[p.curveNumber][0]} · ${groupes[p.pointNumber][0]}`, lignes: calc[p.curveNumber][p.pointNumber][0] });
    montrer('g-sous-min', traces, L, 460, clic, F.libelle(sel));
    const lib = F.libelle(sel);
    if (!lignes.length) return constat('s-sous-min', 'Aucun salarié avec un salaire pour ce filtre.');
    const phrases = series.map(([nom], k) => {
      const [sous, n] = calc[k][0], quoi = nom.charAt(0).toLowerCase() + nom.slice(1);
      if (!n) return `${quoi} : aucun salarié n'a cette borne`;
      const pp = groupes.slice(1).map((g, i) => ({ nom: g[0], v: calc[k][i + 1][1] ? 100 * calc[k][i + 1][0].length / calc[k][i + 1][1] : NaN }));
      const ex = extremes(pp, x => x.v, 1);
      const pire = ex && pp.length > 1 && !ex.egaux ? ` ; part la plus forte : ${enumerer(ex.haut.map(x => echapper(x.nom)))} (${fr(ex.haut[0].v, 1)} %)` : '';
      return `${quoi} : ${salaries(sous.length)} sur ${fr(n)} (${pct(sous.length, n)})${pire}`;
    });
    constat('s-sous-min', `${lib}. ${phrases.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join('. ')}.`);
  }

  // ---------- evaluations : effectif par tranche de compétences et par case 9-Box ----------

  // Tranches de note de 0,5 point, sur l'échelle lue dans le fichier entier (jamais supposée de 1 à 5). La dernière
  // tranche est fermée à droite (« [4,5 ; 5] ») pour garder la note la plus haute. Plus de 12 tranches : la largeur double.
  function tranchesCompetence(df) {
    const v = df.map(l => l.Competence_N1).filter(Number.isFinite);
    if (!v.length) return null;
    const min = Math.min(...v), max = Math.max(...v);
    let pas = 0.5;
    while (Math.ceil(max / pas) - Math.floor(min / pas) > 12) pas *= 2;
    const debut = Math.floor(min / pas) * pas, k = Math.max(1, Math.ceil(max / pas - 1e-9) - Math.floor(min / pas));
    const note = x => fr(x, Number.isInteger(Math.round(x * 1e6) / 1e6) ? 0 : 1);
    const libelles = Array.from({ length: k }, (_, i) => `[${note(debut + i * pas)} ; ${note(debut + (i + 1) * pas)}${i === k - 1 ? ']' : '['}`);
    // 1e-9 : une note pile sur une borne (3,0) tombe dans la tranche qui commence à cette borne, malgré les arrondis du calcul.
    return { libelles, tranche: x => Number.isFinite(x) ? libelles[Math.min(k - 1, Math.max(0, Math.floor((x - debut) / pas + 1e-9)))] : null };
  }

  function evaluations(df, sel) {
    const lignes = df.filter(l => F.garder(l, sel)), t = tranchesCompetence(df), cases = C.modalites(df, 'Positionnement_9BOX');
    const gc = t ? grouper(lignes, t.libelles, l => t.tranche(l.Competence_N1)) : [], g9 = grouper(lignes, cases, l => l.Positionnement_9BOX);
    const vc = nonVides(gc, t ? t.libelles : []), v9 = nonVides(g9, cases.map(String));
    const L = grille({ colonnes: 2, titres: ['Note de compétences (Competence_N1), par tranche', 'Case 9-Box (Positionnement_9BOX)'] });
    axesVerticaux(L, '', vc.map(x => x.g), 'Competence_N1');
    axesVerticaux(L, '2', v9.map(x => x.g), 'Case 9-Box');
    const traces = [barresEffectif(vc.map(x => x.g), vc.map(x => x.lib), { horizontal: false }),
      barresEffectif(v9.map(x => x.g), v9.map(x => x.lib), { horizontal: false, axes: { xaxis: 'x2', yaxis: 'y2' } })];
    const clic = p => p.curveNumber ? { titre: '9-Box ' + p.x, lignes: v9[p.pointNumber].g } : { titre: 'Competence_N1 ' + p.x, lignes: vc[p.pointNumber].g };
    montrer('g-evaluations', traces, L, 440, clic, F.libelle(sel));
    const lib = F.libelle(sel);
    if (!lignes.length) return constat('s-evaluations', 'Aucun salarié pour ce filtre.');
    const notes = gc.flat().map(l => l.Competence_N1), n9 = compte(g9);
    const comp = notes.length ? `Note de compétences médiane : ${fr(C.mediane(notes), 2)} ; tranche la plus nombreuse, ${plusNombreuse(gc, i => t.libelles[i], notes.length)}.`
      : 'Aucune note de compétences.';
    const box = n9 ? ` Case 9-Box la plus fréquente : ${plusNombreuse(g9, i => fr(cases[i]), n9)}.` : ' Aucune case 9-Box.';
    constat('s-evaluations', `${lib} (${salaries(lignes.length)}). ${comp}${box}`);
  }

  // ---------- matrice : matrice de positionnement, position dans la grille × évaluation, en % ----------
  // Décision du point du 29/10/2026 : une matrice sur le modèle des campagnes d'augmentations individuelles. En colonnes,
  // la position du salaire dans sa grille ; en lignes, l'évaluation (case 9-Box ou note de compétences, au choix) ; dans
  // chaque case, la part des salariés. Les colonnes coupent la grille en quatre quarts du Min au Max, comme les matrices
  // de campagne : le Mid sépare le 2e du 3e quart. Sous le Min et au-dessus du Max ont chacun leur colonne.

  const QUARTS = ['Sous le Min', '1er quart', '2e quart', '3e quart', '4e quart', 'Au-dessus du Max'];
  // Range_Penetration : 0 = au Min, 0,5 = au Mid, 1 = au Max. Un salaire pile au Max reste dans le 4e quart.
  const quart = rp => !Number.isFinite(rp) ? null : QUARTS[rp < 0 ? 0 : rp > 1 ? 5 : Math.min(4, 1 + Math.floor(rp * 4))];
  const minuscule = t => t.charAt(0).toLowerCase() + t.slice(1);   // « sous le Min », pas « sous le min »

  function matrice(df, sel) {
    const parBox = sel.vue === 'Positionnement_9BOX', t = parBox ? null : tranchesCompetence(df);
    // Les lignes vont de la meilleure évaluation (en haut) à la moins bonne. Elles sont lues dans le fichier entier, jamais
    // supposées : toutes les cases 9-Box, ou les tranches de notes du graphe « Notes de compétences et cases 9-Box ».
    const rangs = parBox ? C.modalites(df, 'Positionnement_9BOX').reverse() : (t ? [...t.libelles].reverse() : []);
    const rang = parBox ? (l => l.Positionnement_9BOX) : (l => t.tranche(l.Competence_N1));
    const quoi = parBox ? 'une case 9-Box' : 'une note de compétences';
    const nomRang = r => parBox ? 'case 9-Box ' + fr(r) : 'note ' + r;
    const lignes = df.filter(l => F.garder(l, sel));
    // Seuls les salariés qui ont une grille (Min et Max) et une évaluation ont une case : les autres sont comptés à part.
    const avec = lignes.filter(l => quart(l.Range_Penetration) !== null && rangs.includes(rang(l))), n = avec.length;
    const cases = rangs.map(r => QUARTS.map(q => avec.filter(l => rang(l) === r && quart(l.Range_Penetration) === q)));
    // Dans chaque case : la part de tous les salariés de la matrice (les cases font 100 % ensemble). Au survol, aussi la
    // part de la ligne : « parmi les salariés de cette case 9-Box, combien sont dans ce quart ».
    const z = cases.map(ligne => ligne.map(g => n ? 100 * g.length / n : 0));
    // Une ligne ou une colonne sans aucun salarié n'est pas dessinée (voir nonVides) ; une case vide au milieu, elle,
    // reste blanche et sans texte. Une case de quelques salariés sur des milliers s'écrirait « 0,0 % », comme une case
    // vide : elle s'écrit « < 0,1 % ».
    const li = rangs.map((_, i) => i).filter(i => compte(cases[i])), co = QUARTS.map((_, j) => j).filter(j => li.some(i => cases[i][j].length));
    const trace = { type: 'heatmap', x: co.map(j => QUARTS[j]), y: li.map(i => String(rangs[i])), z: li.map(i => co.map(j => z[i][j])), zmin: 0,
      colorscale: [[0, '#ffffff'], [1, K.ARDOISE]], showscale: false, xgap: 2, ygap: 2,
      text: li.map(i => co.map(j => !cases[i][j].length ? '' : z[i][j] < 0.05 ? '< 0,1 %' : fr(z[i][j], 1) + ' %')), texttemplate: '%{text}', textfont: { size: 12 },
      customdata: li.map(i => { const tot = compte(cases[i]); return co.map(j => [cases[i][j].length, tot ? fr(100 * cases[i][j].length / tot, 1) : '–']); }),
      hovertemplate: `${parBox ? 'Case 9-Box' : 'Note'} %{y} · %{x}<br><b>%{z:.1f} % des salariés</b> (%{customdata[0]:,})<br>%{customdata[1]} % de cette ligne<extra></extra>` };
    const L = sansTitre();
    Object.assign(L.xaxis, { type: 'category', showgrid: false, title: titreAxe('Position du salaire dans sa grille, du Min au Max (le Mid sépare le 2e et le 3e quart)') });
    Object.assign(L.yaxis, { type: 'category', showgrid: false, autorange: 'reversed',
      title: titreAxe(parBox ? 'Case 9-Box (la plus haute en haut)' : 'Note de compétences (Competence_N1)') });
    // Un trait marque le Mid, entre le 2e et le 3e quart : à gauche, les salariés payés sous le milieu de leur grille.
    // Sa place se compte en colonnes dessinées : celles avant le 3e quart (le 3e quart est la colonne 3 de QUARTS).
    const mid = co.filter(j => j < 3).length - 0.5;
    if (mid > -0.5 && mid < co.length - 0.5) {
      L.shapes.push({ type: 'line', xref: 'x', x0: mid, x1: mid, yref: 'y domain', y0: 0, y1: 1, line: { color: K.BRUN, dash: 'dash', width: 2 } });
      L.annotations.push({ text: 'Mid', x: mid, xref: 'x', y: 1, yref: 'y domain', yanchor: 'bottom', showarrow: false, font: { size: 11, color: K.BRUN } });
    }
    const clic = p => { const [a, b] = p.pointNumber, i = li[a], j = co[b], nom = nomRang(rangs[i]);
      return { titre: `${nom.charAt(0).toUpperCase() + nom.slice(1)} · ${minuscule(QUARTS[j])}`, lignes: cases[i][j] }; };
    montrer('g-matrice', n ? [trace] : [], L, 140 + 52 * Math.max(4, li.length), clic, F.libelle(sel));
    const lib = F.libelle(sel);
    if (!lignes.length) return constat('s-matrice', 'Aucun salarié pour ce filtre.');
    if (!n) return constat('s-matrice', `${lib} (${salaries(lignes.length)}) : aucun n'a à la fois une grille (Min et Max) et ${quoi}.`);
    const sans = lignes.length - n;
    const toutes = cases.flatMap((ligne, i) => ligne.map((g, j) => ({ nom: `${nomRang(rangs[i])}, ${minuscule(QUARTS[j])}`, n: g.length })));
    const ex = extremes(toutes, c => c.n, 0);
    const pleine = ` Case la plus remplie : ${enumerer(ex.haut.map(c => echapper(c.nom)))} (${pct(ex.haut[0].n, n)}${ex.haut.length > 1 ? ' chacune' : ''}).`;
    // Les mieux évalués payés sous le milieu de leur grille : ceux qu'une campagne d'augmentations regarde en premier.
    const nh = compte(cases[0]), sousMid = compte(cases[0].slice(0, 3));
    const meilleurs = rangs.length < 2 ? '' : !nh ? ` Personne dans la meilleure évaluation (${nomRang(rangs[0])}).`
      : ` Parmi les mieux évalués (${nomRang(rangs[0])}${parBox ? ', la case la plus haute, supposée la meilleure' : ''}), ${pct(sousMid, nh)} sont payés `
        + `sous le milieu de leur grille (sous le Min, 1er ou 2e quart), soit ${salaries(sousMid)} sur ${fr(nh)}.`;
    constat('s-matrice', `${lib} (${salaries(n)} avec une grille et ${quoi}${sans ? `, ${fr(sans)} sans` : ''}) : chaque case donne la part de ces salariés.${pleine}${meilleurs}`);
  }

  E.simples = { effectifAge, effectifAnciennete, effectifNiveau, effectifMetier, femmesHommes, hotJob,
    salaireAge, salaireAnciennete, salaireSexe, salaireEnTranches, ecartAuMid, sousMin, evaluations, matrice };
})(window.Exploration = window.Exploration || {});
