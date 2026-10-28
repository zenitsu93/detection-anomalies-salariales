// Barres de filtres au-dessus des graphes : boutons (vue, niveau, Hot_job) et listes (pôle, métier).
// Chaque changement redessine le graphe concerné, et lui seul.
(function (E) {
  'use strict';
  const C = E.calculs, { $, echapper } = E.communs;

  // options : { vues: [[valeur, libellé]...], niveau, hotjob, pole, metier } ; dessiner(sel) reçoit le choix en cours.
  function filtrer(id, df, options, dessiner) {
    const zone = $(id);
    const sel = { vue: options.vues ? options.vues[0][0] : null, niveau: null, hotjob: null, pole: null, metier: null };
    const boutons = (nom, cle, valeurs) => `<div class="filtre"><span class="filtre-nom">${nom}</span><div class="views" role="group" aria-label="${nom}">`
      + valeurs.map(([v, t], i) => `<button type="button" data-cle="${cle}" data-valeur="${echapper(v)}" aria-pressed="${i === 0}">${echapper(t)}</button>`).join('')
      + '</div></div>';
    const liste = (nom, cle, valeurs, tous) => `<label class="filtre"><span class="filtre-nom">${nom}</span><select data-cle="${cle}">`
      + [['', tous], ...valeurs.map(v => [String(v), String(v)])].map(([v, t]) => `<option value="${echapper(v)}">${echapper(t)}</option>`).join('')
      + '</select></label>';
    const tous = colonne => [['', 'Tous'], ...C.modalites(df, colonne).map(v => [String(v), String(v)])];

    zone.innerHTML = [
      options.vues && boutons('Vue', 'vue', options.vues),
      options.niveau && boutons('Niveau', 'niveau', tous('Niveau')),
      options.hotjob && boutons('Hot_job', 'hotjob', tous('Hot_job')),
      options.pole && liste('Pôle', 'pole', C.modalites(df, 'Entite_N1'), 'Tous les pôles'),
      options.metier && liste('Métier', 'metier', C.modalites(df, 'Job_Family'), 'Tous les métiers'),
    ].filter(Boolean).join('');

    // Niveau et Hot_job sont des nombres ; « Tous » (valeur vide) veut dire « pas de filtre ».
    const valeur = (cle, v) => v === '' ? null : (cle === 'niveau' || cle === 'hotjob') ? Number(v) : v;
    zone.onclick = e => {
      const b = e.target.closest('button[data-cle]');
      if (!b) return;
      zone.querySelectorAll(`button[data-cle="${b.dataset.cle}"]`).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      sel[b.dataset.cle] = valeur(b.dataset.cle, b.dataset.valeur);
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

  const garder = (l, sel) => (sel.niveau === null || l.Niveau === sel.niveau) && (sel.hotjob === null || l.Hot_job === sel.hotjob)
    && (sel.pole === null || String(l.Entite_N1) === sel.pole) && (sel.metier === null || String(l.Job_Family) === sel.metier);

  // « Niveau 5, IT » ou « Tous les salariés » : rappelé en tête du constat, pour savoir sur qui il porte.
  function libelle(sel) {
    const t = [sel.niveau === null ? null : 'niveau ' + sel.niveau, sel.hotjob === null ? null : 'Hot_job ' + sel.hotjob,
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
