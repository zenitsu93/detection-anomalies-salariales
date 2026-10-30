// Barres de filtres au-dessus des graphes : boutons (vue, niveau, Hot_job) et listes (pôle, métier).
// Chaque changement redessine le graphe concerné, et lui seul. Plusieurs niveaux peuvent être choisis à la fois.
(function (E) {
  'use strict';
  const C = E.calculs, { $, echapper, enumerer } = E.communs;

  // options : { vues: [[valeur, libellé]...], niveau, hotjob, pole, metier } ; dessiner(sel) reçoit le choix en cours.
  // sel.niveau : null (tous les niveaux) ou la liste des niveaux choisis ; les autres : null (tous) ou une seule valeur.
  function filtrer(id, df, options, dessiner) {
    const zone = $(id);
    const sel = { vue: options.vues ? options.vues[0][0] : null, niveau: null, hotjob: null, pole: null, metier: null };
    // aide : une précision écrite après les boutons (pour les niveaux : on peut en choisir plusieurs).
    const boutons = (nom, cle, valeurs, aide = '') => `<div class="filtre"><span class="filtre-nom">${nom}</span><div class="views" role="group" aria-label="${nom}">`
      + valeurs.map(([v, t], i) => `<button type="button" data-cle="${cle}" data-valeur="${echapper(v)}" aria-pressed="${i === 0}">${echapper(t)}</button>`).join('')
      + '</div>' + (aide && `<span class="filtre-aide">${aide}</span>`) + '</div>';
    const liste = (nom, cle, valeurs, tous) => `<label class="filtre"><span class="filtre-nom">${nom}</span><select data-cle="${cle}">`
      + [['', tous], ...valeurs.map(v => [String(v), String(v)])].map(([v, t]) => `<option value="${echapper(v)}">${echapper(t)}</option>`).join('')
      + '</select></label>';
    const tous = colonne => [['', 'Tous'], ...C.modalites(df, colonne).map(v => [String(v), String(v)])];

    zone.innerHTML = [
      options.vues && boutons('Vue', 'vue', options.vues),
      options.niveau && boutons('Niveau', 'niveau', tous('Niveau'), 'plusieurs choix possibles'),
      options.hotjob && boutons('Hot_job', 'hotjob', tous('Hot_job')),
      options.pole && liste('Pôle', 'pole', C.modalites(df, 'Entite_N1'), 'Tous les pôles'),
      options.metier && liste('Métier', 'metier', C.modalites(df, 'Job_Family'), 'Tous les métiers'),
    ].filter(Boolean).join('');

    // Niveau et Hot_job sont des nombres ; « Tous » (valeur vide) veut dire « pas de filtre ».
    const valeur = (cle, v) => v === '' ? null : (cle === 'niveau' || cle === 'hotjob') ? Number(v) : v;
    zone.onclick = e => {
      const b = e.target.closest('button[data-cle]');
      if (!b) return;
      const cle = b.dataset.cle, groupe = [...zone.querySelectorAll(`button[data-cle="${cle}"]`)];
      if (cle === 'niveau' && b.dataset.valeur !== '') {
        // Pourquoi plusieurs niveaux (point du 29/10/2026) : pour regarder par exemple les niveaux 3 à 5 ensemble. Un clic
        // ajoute ou retire le niveau. Aucun niveau choisi, ou tous, revient à « Tous » (pas de filtre).
        b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true'));
        const choisis = groupe.filter(x => x.dataset.valeur !== '' && x.getAttribute('aria-pressed') === 'true');
        const aucunFiltre = !choisis.length || choisis.length === groupe.length - 1;
        groupe[0].setAttribute('aria-pressed', String(aucunFiltre));   // le premier bouton est « Tous »
        if (aucunFiltre) choisis.forEach(x => x.setAttribute('aria-pressed', 'false'));
        sel.niveau = aucunFiltre ? null : choisis.map(x => Number(x.dataset.valeur));
      } else {
        // « Tous », la vue et Hot_job : un seul bouton allumé à la fois.
        groupe.forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        sel[cle] = valeur(cle, b.dataset.valeur);
      }
      dessiner(sel);
    };
    zone.onchange = e => {
      const s = e.target.closest('select[data-cle]');
      if (!s) return;
      sel[s.dataset.cle] = valeur(s.dataset.cle, s.value);
      dessiner(sel);
    };
    dessiner(sel);
  }

  const garder = (l, sel) => (sel.niveau === null || sel.niveau.includes(l.Niveau)) && (sel.hotjob === null || l.Hot_job === sel.hotjob)
    && (sel.pole === null || String(l.Entite_N1) === sel.pole) && (sel.metier === null || String(l.Job_Family) === sel.metier);

  // « Niveau 5, IT », « Niveaux 3, 4 et 5 » ou « Tous les salariés » : rappelé en tête du constat, pour savoir sur qui il porte.
  function libelle(sel) {
    const niveaux = sel.niveau === null ? null : (sel.niveau.length > 1 ? 'niveaux ' : 'niveau ') + enumerer(sel.niveau.map(String));
    const t = [niveaux, sel.hotjob === null ? null : 'Hot_job ' + sel.hotjob,
      sel.pole, sel.metier].filter(v => v !== null).map(echapper).join(', ');
    return t ? t.charAt(0).toUpperCase() + t.slice(1) : 'Tous les salariés';
  }

  // Les salariés gardés par le filtre, avec leur texte de survol.
  function sousEnsemble(df, survol, sel) {
    const lignes = [], textes = [];
    df.forEach((l, i) => { if (garder(l, sel)) { lignes.push(l); textes.push(survol[i]); } });
    return { lignes, survol: textes };
  }

  E.filtres = { filtrer, garder, libelle, sousEnsemble };
})(window.Exploration = window.Exploration || {});
