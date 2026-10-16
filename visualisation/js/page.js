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
    const donnees = { tables, source, date: new Date().toISOString() };
    afficher(donnees);
    await Fi.ecrire('donnees', donnees);
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
    const infos = ['Matricule', 'Nom', 'Job_Title', 'Grade', 'Fixe_Annuel_MAD'].filter(c => presentes.has(c));
    const survol = df.map(l => infos.map(c => `${c} : ${typeof l[c] === 'number' ? fr(l[c], c === 'Fixe_Annuel_MAD' ? 2 : 0) : echapper(l[c] ?? '')}`).join('<br>'));

    // Les chiffres clés portent toujours sur tous les salariés, quels que soient les filtres des graphes.
    const sal = C.colonne(df, 'Fixe_Annuel_MAD');
    chiffresCles(controles, { asym: [C.asymetrie(sal), C.asymetrie(sal.map(A.logPositif))], ecarts: A.ecartsFH(df) });
    qualite(controles);

    // Chaque graphe et ses filtres ; l'ordre d'affichage, lui, se règle dans la page HTML.
    filtrer('f-masse', df, { grade: true }, sel => P.masseSalariale(df, sel));
    A.distribution(df, survol);
    filtrer('f-grille', df, { metier: true }, sel => A.grilleEtMarche(df, survol, sel));
    filtrer('f-hors-grille', df, { metier: true }, sel => P.horsGrille(df, sel));
    filtrer('f-metiers', df, { grade: true }, sel => A.metiers(df, survol, sel));
    filtrer('f-marche', df, { vues: [['Entite_N1', 'Par pôle'], ['Job_Family', 'Par métier']], grade: true }, sel => P.marche(df, sel));
    filtrer('f-tension', df, { grade: true, pole: true }, sel => P.tension(df, sel));
    filtrer('f-anciennete', df, { grade: true, metier: true }, sel => A.anciennete(df, survol, sel));
    filtrer('f-competences', df, { grade: true, metier: true }, sel => A.performance(df, survol, sel));
    filtrer('f-talents', df, { hotjob: true, pole: true, metier: true }, sel => P.talents(df, sel));
    filtrer('f-equite', df, { metier: true }, sel => A.equite(df, sel));
  }

  function chiffresCles(c, r) {
    const cellule = (titre, valeur, detail, lien) =>
      `<div><dt>${titre}</dt><dd><a href="${lien}">${valeur}</a><small>${detail}</small></dd></div>`;
    $('vue').innerHTML = [
      cellule('Salariés analysés', fr(c.lignesRetenues), `sur ${fr(c.lignesInitiales)} lignes lues`, '#qualite'),
      cellule('Sous le Min de la grille', pct(c.sousMin, c.lignesRetenues), `${fr(c.sousMin)} salariés`, '#hors-grille'),
      cellule('Au-dessus du Max', pct(c.surMax, c.lignesRetenues), `${fr(c.surMax)} salariés`, '#hors-grille'),
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
        c.doublons ? `${fr(c.doublons)} lignes en double écartées` : 'Aucun doublon'),
      ligne('Rattachement à la grille interne', 'Chaque métier + grade doit exister dans bands.xlsx.', c.sansGrille,
        c.sansGrille ? `${fr(c.sansGrille)} salariés sans grille` : 'Tous les salariés ont une grille'),
      ligne('Rattachement au marché', 'Chaque métier + grade doit exister dans market.xlsx.', c.sansMarche,
        c.sansMarche ? `${fr(c.sansMarche)} salariés sans médiane de marché` : 'Tous les salariés ont une médiane de marché'),
      ligne('Cohérence âge / ancienneté', "L'âge d'embauche (Age − Anciennete) doit être d'au moins 18 ans.", c.ageEmbaucheIncoherent,
        c.ageEmbaucheIncoherent ? `${fr(c.ageEmbaucheIncoherent)} salariés embauchés avant 18 ans` : 'Aucune incohérence'),
      ligne('Tension métier par poste', 'Un poste (Job_Title) doit avoir une seule valeur de Hot_job.', c.postesPlusieursHotjob,
        c.postesPlusieursHotjob ? `${fr(c.postesPlusieursHotjob)} postes avec plusieurs valeurs` : 'Une seule valeur par poste'),
    ].join('');
  }

  // ---------- Boutons ----------

  const choisirDossier = () => executer(async () => {
    const dossier = await window.showDirectoryPicker({ id: 'exploration-salaires', mode: 'read' });
    await Fi.ecrire('dossier', dossier);
    $('relancer').hidden = false;
    await charger(await Fi.depuisDossier(dossier));
  });
  $('choisirDossier').onclick = choisirDossier;
  $('commencer').onclick = () => window.showDirectoryPicker ? choisirDossier() : $('fichiers').click();

  $('relancer').onclick = () => executer(async () => {
    const dossier = await Fi.lire('dossier');
    if (!dossier) throw new Error('Aucun dossier mémorisé : cliquez sur « Choisir le dossier ».');
    if (await dossier.requestPermission({ mode: 'read' }) !== 'granted') throw new Error('Le navigateur n\'a pas reçu l\'autorisation de lire le dossier.');
    await charger(await Fi.depuisDossier(dossier));
  });

  $('choisirFichiers').onclick = () => $('fichiers').click();
  $('fichiers').onchange = e => executer(async () => {
    const choisis = [...e.target.files];
    e.target.value = '';
    await charger(await Fi.depuisListe(choisis));
  });

  // ---------- Sommaire : la section à l'écran est mise en avant ----------

  const liens = [...document.querySelectorAll('.toc a')];
  const suivi = new IntersectionObserver(entrees => {
    for (const e of entrees) if (e.isIntersecting) liens.forEach(a => a.classList.toggle('actif', a.getAttribute('href') === '#' + e.target.id));
  }, { rootMargin: '-15% 0px -75% 0px' });
  liens.forEach(a => { const cible = document.querySelector(a.getAttribute('href')); if (cible) suivi.observe(cible); });

  // ---------- Ouverture : les fichiers du dossier s'ils sont lisibles sans redemander, sinon les dernières données lues ----------

  (async () => {
    if (!window.showDirectoryPicker) $('choisirDossier').hidden = true;
    const dossier = await Fi.lire('dossier');
    if (dossier) $('relancer').hidden = false;
    try {
      if (dossier && await dossier.queryPermission({ mode: 'read' }) === 'granted') return executer(async () => charger(await Fi.depuisDossier(dossier)));
    } catch { /* dossier déplacé ou supprimé : on affiche les dernières données lues */ }
    const donnees = await Fi.lire('donnees');
    if (donnees) executer(async () => afficher(donnees));
  })();

  // Utilisé par les tests de la page, qui lui donnent des données sans passer par le choix d'un dossier.
  E.page = { charger, executer };
})(window.Exploration = window.Exploration || {});
