// Chef d'orchestre de la page : boutons, messages, chiffres clés, contrôles de qualité et affichage de tous les graphes.
(function (E) {
  'use strict';
  const C = E.calculs, Fi = E.fichiers, A = E.analyses, P = E.pilotage, { filtrer } = E.filtres;
  const { $, fr, pct, signe, echapper } = E.communs;

  // ---------- Messages et actions ----------

  function avertir(texte, genre) {
    const n = $('notice');
    n.hidden = !texte;
    n.className = 'notice' + (genre === 'erreur' ? ' error' : '');
    n.innerHTML = (genre === 'attente' ? '<span class="spinner" aria-hidden="true"></span>' : '') + '<span></span>';
    n.lastChild.textContent = texte;
  }

  // Lance une action en montrant « calculs en cours », puis l'éventuelle erreur.
  async function executer(action) {
    const boutons = document.querySelectorAll('.head-actions button, #commencer');
    boutons.forEach(b => b.disabled = true);
    avertir('Lecture des fichiers et calculs en cours…', 'attente');
    await new Promise(r => setTimeout(r, 30));   // laisse le message s'afficher avant les calculs
    try { await action(); avertir(''); }
    catch (e) { avertir(e.name === 'AbortError' ? '' : e.message, 'erreur'); }
    finally { boutons.forEach(b => b.disabled = false); }
  }

  async function charger({ tables, source }) {
    afficher({ tables, source, date: new Date().toISOString() });
  }

  // ---------- Affichage ----------

  function afficher({ tables, source, date }) {
    const manque = C.colonnesManquantes(tables);
    if (Object.keys(manque).length) {
      throw new Error('Colonnes manquantes : ' + Object.entries(manque).map(([f, c]) => `${f}.xlsx (${c.join(', ')})`).join(' ; ')
        + '. Les noms de colonnes doivent être écrits exactement comme dans le notebook.');
    }
    const { df, controles } = C.preparer(tables);
    const quand = new Date(date);
    $('ctx-source').textContent = source;
    $('ctx-source').title = source;
    $('ctx-date').textContent = `${quand.toLocaleDateString('fr-FR')} à ${quand.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;
    $('ctx-effectif').textContent = `${fr(df.length)} salariés`;
    $('lignes-lues').textContent = `Lignes lues : employes ${fr(tables.employes.length)} · bands ${fr(tables.bands.length)} · market ${fr(tables.market.length)}`;
    $('accueil').hidden = true;
    $('contenu').hidden = false;

    // Les infos du salarié affichées au survol d'un point (seulement les colonnes présentes dans le fichier).
    const presentes = new Set(Object.keys(tables.employes[0] || {}));
    const infos = ['Matricule', 'Nom', 'Job_Title', 'Niveau', 'Fixe_Annuel_MAD'].filter(c => presentes.has(c));
    const survol = df.map(l => infos.map(c => `${c} : ${typeof l[c] === 'number' ? fr(l[c], c === 'Fixe_Annuel_MAD' ? 2 : 0) : echapper(l[c] ?? '')}`).join('<br>'));

    // Les chiffres clés portent toujours sur tous les salariés, quels que soient les filtres des graphes.
    const sal = C.colonne(df, 'Fixe_Annuel_MAD');
    chiffresCles(controles, { asym: [C.asymetrie(sal), C.asymetrie(sal.map(A.logPositif))], ecarts: A.ecartsFH(df) });
    qualite(controles);
    // Les nombres de salariés des chiffres clés et des contrôles ouvrent la liste de ces salariés.
    const listes = listesDeControle(df, tables.employes);
    document.querySelectorAll('[data-liste]').forEach(b => b.onclick = () => E.liste.ouvrir(...listes[b.dataset.liste]));

    // Chaque graphe et ses filtres ; l'ordre d'affichage, lui, se règle dans la page HTML.
    filtrer('f-masse', df, { niveau: true }, sel => P.masseSalariale(df, sel));
    A.distribution(df, survol);
    filtrer('f-grille', df, { metier: true }, sel => A.grilleEtMarche(df, survol, sel));
    filtrer('f-hors-grille', df, { metier: true }, sel => P.horsGrille(df, sel));
    filtrer('f-metiers', df, { niveau: true }, sel => A.metiers(df, survol, sel));
    filtrer('f-marche', df, { vues: [['Entite_N1', 'Par pôle'], ['Job_Family', 'Par métier']], niveau: true }, sel => P.marche(df, sel));
    filtrer('f-tension', df, { niveau: true, pole: true }, sel => P.tension(df, sel));
    filtrer('f-anciennete', df, { niveau: true, metier: true }, sel => A.anciennete(df, survol, sel));
    filtrer('f-competences', df, { niveau: true, metier: true }, sel => A.performance(df, survol, sel));
    filtrer('f-talents', df, { hotjob: true, pole: true, metier: true }, sel => P.talents(df, sel));
    filtrer('f-equite', df, { metier: true }, sel => A.equite(df, sel));
  }

  // Un nombre de salariés qui ouvre leur liste (voir listesDeControle) ; sans salarié, un simple texte.
  const versListe = (cle, n, texte) => n ? `<button type="button" class="lien" data-liste="${cle}">${texte}</button>` : texte;

  function chiffresCles(c, r) {
    const cellule = (titre, valeur, detail, lien) =>
      `<div><dt>${titre}</dt><dd><a href="${lien}">${valeur}</a><small>${detail}</small></dd></div>`;
    $('vue').innerHTML = [
      cellule('Salariés analysés', fr(c.lignesRetenues), `sur ${fr(c.lignesInitiales)} lignes lues · ${versListe('tous', c.lignesRetenues, 'voir la liste')}`, '#qualite'),
      cellule('Sous le Min de la grille', pct(c.sousMin, c.lignesRetenues), versListe('sousMin', c.sousMin, `${fr(c.sousMin)} salariés`), '#hors-grille'),
      cellule('Au-dessus du Max', pct(c.surMax, c.lignesRetenues), versListe('surMax', c.surMax, `${fr(c.surMax)} salariés`), '#hors-grille'),
      cellule('Asymétrie du salaire', `${fr(r.asym[0], 2)} → ${fr(r.asym[1], 2)}`, 'brut → logarithme', '#distribution'),
      cellule('Écart H / F non corrigé', signe(r.ecarts[0]), 'salaire moyen, M vs F', '#equite'),
      cellule('Écart H / F à grille égale', signe(r.ecarts[1]), 'Compa-Ratio moyen, M vs F', '#equite'),
    ].join('');
  }

  function qualite(c) {
    const statut = n => n > 0
      ? '<span class="tag warn"><svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5 15 14H1z" fill="currentColor"/><path d="M8 6v4M8 11.5v1" stroke="#fff" stroke-width="1.6"/></svg>À vérifier</span>'
      : '<span class="tag ok"><svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m3 8.5 3 3 7-7"/></svg>Conforme</span>';
    const ligne = (titre, detail, n, texte) => `<tr><td>${titre}<span class="detail">${detail}</span></td><td>${texte}</td><td>${statut(n)}</td></tr>`;
    $('controles').innerHTML = [
      ligne('Doublons de matricule', 'La première ligne de chaque matricule est gardée.', c.doublons,
        c.doublons ? versListe('doublons', c.doublons, `${fr(c.doublons)} lignes en double écartées`) : 'Aucun doublon'),
      ligne('Rattachement à la grille interne', 'Chaque métier + niveau doit exister dans bands.xlsx.', c.sansGrille,
        c.sansGrille ? versListe('sansGrille', c.sansGrille, `${fr(c.sansGrille)} salariés sans grille`) : 'Tous les salariés ont une grille'),
      ligne('Rattachement au marché', 'Chaque métier + niveau doit exister dans market.xlsx.', c.sansMarche,
        c.sansMarche ? versListe('sansMarche', c.sansMarche, `${fr(c.sansMarche)} salariés sans médiane de marché`) : 'Tous les salariés ont une médiane de marché'),
      ligne('Cohérence âge / ancienneté', "L'âge d'embauche (Age − Anciennete) doit être d'au moins 18 ans.", c.ageEmbaucheIncoherent,
        c.ageEmbaucheIncoherent ? versListe('ageEmbauche', c.ageEmbaucheIncoherent, `${fr(c.ageEmbaucheIncoherent)} salariés embauchés avant 18 ans`) : 'Aucune incohérence'),
      ligne('Tension métier par poste', 'Un poste (Job_Title) doit avoir une seule valeur de Hot_job.', c.postesPlusieursHotjob,
        c.postesPlusieursHotjob ? versListe('postes', c.postesPlusieursHotjob, `${fr(c.postesPlusieursHotjob)} postes avec plusieurs valeurs`) : 'Une seule valeur par poste'),
    ].join('');
  }

  // Les listes ouvertes par les nombres de salariés, [titre, lignes, origine, unité] : les mêmes tests que les contrôles (calculs.js).
  function listesDeControle(df, employes) {
    const compte = new Map(), hotjob = new Map();
    for (const e of employes) compte.set(e.Matricule, (compte.get(e.Matricule) || 0) + 1);
    for (const l of df) if (l.Job_Title !== null && l.Job_Title !== undefined && Number.isFinite(l.Hot_job)) hotjob.set(l.Job_Title, (hotjob.get(l.Job_Title) || new Set()).add(l.Hot_job));
    const chiffres = 'Chiffres clés', controle = 'Qualité des données';
    return {
      tous: ['Tous les salariés analysés', df, chiffres],
      sousMin: ['Sous le Min de leur grille', df.filter(l => l.Fixe_Annuel_MAD < l.Min), chiffres],
      surMax: ['Au-dessus du Max de leur grille', df.filter(l => l.Fixe_Annuel_MAD > l.Max), chiffres],
      // Toutes les lignes des matricules en double, celle gardée comme celles écartées, pour les comparer.
      doublons: ['Matricules en double (toutes leurs lignes)', employes.filter(e => compte.get(e.Matricule) > 1), controle, 'ligne'],
      sansGrille: ['Salariés sans grille interne', df.filter(l => !Number.isFinite(l.Mid)), controle],
      sansMarche: ['Salariés sans médiane de marché', df.filter(l => !Number.isFinite(l.Median)), controle],
      ageEmbauche: ['Salariés embauchés avant 18 ans', df.filter(l => l.Age_Embauche < 18), controle],
      postes: ['Salariés des postes à plusieurs valeurs de Hot_job', df.filter(l => (hotjob.get(l.Job_Title) || new Set()).size > 1), controle],
    };
  }

  // ---------- Fichiers : déposés dans la page ou choisis avec le bouton ----------

  // Pas de dossier mémorisé : le navigateur n'a aucune autorisation à demander. La page lit seulement les fichiers
  // qu'on lui donne, et dessine les graphes dès que les trois sont là ; un fichier redonné remplace celui du même nom.
  const liste = noms => noms.join(', ').replace(/, ([^,]*)$/, ' et $1');
  function recevoir(fichiers) {
    if (!fichiers.length) return;
    const { recus, manquants, ignores } = Fi.recevoir(fichiers);
    document.querySelectorAll('[data-fichier]').forEach(t => t.classList.toggle('recu', recus.includes(t.dataset.fichier)));
    const ignore = ignores.length ? `Fichier ignoré : ${liste(ignores)}. Les fichiers doivent s'appeler employes.xlsx, bands.xlsx et market.xlsx.` : '';
    // Il en manque encore, ou rien d'utile n'a été donné (seulement des fichiers ignorés) : on dit où on en est, sans recalculer.
    if (manquants.length || ignores.length === fichiers.length) {
      const etat = manquants.length ? `${recus.length ? `Reçu : ${liste(recus)}. ` : ''}Il manque ${liste(manquants)}.` : '';
      return avertir([ignore, etat].filter(Boolean).join(' '), ignores.length ? 'erreur' : '');
    }
    executer(async () => charger(await Fi.tables()));
  }

  $('choisirFichiers').onclick = $('commencer').onclick = () => $('fichiers').click();
  $('fichiers').onchange = e => { const choisis = [...e.target.files]; e.target.value = ''; recevoir(choisis); };

  // Glisser-déposer n'importe où dans la page. Sans ces lignes, le navigateur ouvrirait le fichier déposé à la place
  // de la page. Pendant le glissement, le cadre d'accueil s'éclaire, ou, si les graphes sont affichés, un cadre recouvre la page.
  const avecFichiers = e => [...(e.dataTransfer?.types || [])].includes('Files');
  let dedans = 0;   // dragenter / dragleave se répètent à chaque élément survolé : on compte pour savoir quand on sort vraiment
  const glisser = actif => {
    $('accueil').classList.toggle('survol', actif);
    $('depot').hidden = !actif || !$('accueil').hidden;
  };
  document.addEventListener('dragenter', e => { if (avecFichiers(e) && dedans++ === 0) glisser(true); });
  document.addEventListener('dragleave', e => { if (avecFichiers(e) && --dedans === 0) glisser(false); });
  document.addEventListener('dragover', e => { if (avecFichiers(e)) e.preventDefault(); });
  document.addEventListener('drop', e => {
    if (!avecFichiers(e)) return;
    e.preventDefault();
    dedans = 0;
    glisser(false);
    recevoir([...e.dataTransfer.files]);
  });

  // ---------- Sommaire : la section à l'écran est mise en avant ----------

  const liens = [...document.querySelectorAll('.toc a')];
  const suivi = new IntersectionObserver(entrees => {
    for (const e of entrees) if (e.isIntersecting) liens.forEach(a => a.classList.toggle('actif', a.getAttribute('href') === '#' + e.target.id));
  }, { rootMargin: '-15% 0px -75% 0px' });
  liens.forEach(a => { const cible = document.querySelector(a.getAttribute('href')); if (cible) suivi.observe(cible); });

  // L'ancienne version gardait dans le navigateur le dossier choisi et une copie des dernières données lues : on l'efface,
  // pour qu'aucune donnée salariale n'y reste.
  try { indexedDB.deleteDatabase('exploration-salaires'); } catch { /* mémoire du navigateur bloquée : rien à effacer */ }

  // Utilisé par les tests de la page, qui lui donnent des données sans passer par le dépôt des fichiers.
  E.page = { charger, executer };
})(window.Exploration = window.Exploration || {});
