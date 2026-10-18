// Liste des salariés derrière un clic (barre, boîte, case, bulle, point, chiffre clé ou contrôle de qualité) :
// un tableau comme dans Excel, le même que dans le tableau de bord de la détection (recherche, tri et filtre
// par colonne, export Excel).
(function (E) {
  'use strict';
  const { $, fr, echapper } = E.communs;
  // Dessiner des milliers de lignes rendrait la page lente : au-delà, les lignes ne sont pas dessinées,
  // mais elles restent comptées et exportées.
  const MAX_LIGNES = 300;

  // Les colonnes de la liste, dans l'ordre, avec leur nom affiché. Une colonne vide pour tous les salariés
  // de la liste n'est pas montrée (par exemple Nom, si le fichier ne le donne pas).
  const COLONNES = [
    ['Matricule', 'Matricule'], ['Nom', 'Nom'], ['Entite_N1', 'Pôle'], ['Job_Family', 'Métier'], ['Job_Title', 'Poste'],
    ['Grade', 'Grade'], ['Sexe', 'Sexe'], ['Age', 'Âge'], ['Anciennete', 'Ancienneté'], ['Fixe_Annuel_MAD', 'Salaire fixe (kMAD)'],
    ['Min', 'Min'], ['Mid', 'Mid'], ['Max', 'Max'], ['Compa_Ratio', 'Compa-Ratio'], ['Range_Penetration', 'Position dans la bande'],
    ['Median', 'Médiane marché'], ['Position_Marche', 'Face au marché'], ['Competence_N1', 'Competence_N1'],
    ['Positionnement_9BOX', '9-Box'], ['Hot_job', 'Hot_job'],
  ];
  const vide = v => v === null || v === undefined || v === '' || (typeof v === 'number' && !Number.isFinite(v));

  // Le texte affiché d'une case : les nombres au format français. La recherche et les filtres travaillent
  // sur ce texte, pour qu'on retrouve exactement ce qu'on lit.
  const texte = v => vide(v) ? '' : typeof v === 'number' ? v.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) : String(v);
  // Sans accents ni majuscules, pour que « ecart » trouve « Écart ». Les espaces des nombres français
  // (12 345) sont des espaces spéciaux : ils deviennent des espaces ordinaires, comme ceux qu'on tape.
  const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s/g, ' ').toLowerCase();
  // L'ordre alphabétique français, où « 9 » vient avant « 10 » même au milieu d'un texte (« JT90 », « JT100 »).
  const COLLATION = new Intl.Collator('fr', { numeric: true });
  const ENTONNOIR = '<svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><path d="M0 1h10L6 5.5V10L4 9V5.5z" fill="currentColor"/></svg>';

  // Range deux lignes selon la colonne c : les nombres comme des nombres, le reste selon le texte affiché.
  // Les cases vides vont toujours à la fin, dans un sens comme dans l'autre, comme dans Excel.
  function ordre(x, y, c, sens) {
    const vides = (x.t[c] === '') - (y.t[c] === '');
    if (vides || x.t[c] === '') return vides;
    const a = x.v[c], b = y.v[c];
    return sens * (typeof a === 'number' && typeof b === 'number' ? a - b : COLLATION.compare(x.t[c], y.t[c]));
  }

  // ---------- Menu d'une colonne (tri et filtre) : un seul ouvert à la fois ----------

  let menu = null, boutonMenu = null;
  function fermerMenu(revenir) {
    if (!menu) return;
    menu.remove();
    boutonMenu.setAttribute('aria-expanded', 'false');
    // Au clavier, on revient sur le bouton ▾ de la colonne, pour ne pas perdre sa place.
    if (revenir) boutonMenu.focus();
    menu = boutonMenu = null;
  }
  // Le menu se pose sous son bouton, ou au-dessus s'il y a plus de place, sans déborder de l'écran.
  function placerMenu() {
    const r = boutonMenu.getBoundingClientRect(), dessous = innerHeight - r.bottom - 12, dessus = r.top - 12;
    const bas = dessous >= 320 || dessous >= dessus;
    menu.style.left = Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8)) + 'px';
    menu.style.top = bas ? r.bottom + 4 + 'px' : '';
    menu.style.bottom = bas ? '' : innerHeight - r.top + 4 + 'px';
    menu.style.maxHeight = (bas ? dessous : dessus) + 'px';
  }
  // Un clic à côté ferme le menu ; si la liste défile ou si la fenêtre change de taille, il reste collé à son bouton.
  document.addEventListener('pointerdown', e => { if (menu && !menu.contains(e.target) && !boutonMenu.contains(e.target)) fermerMenu(false); });
  addEventListener('scroll', () => { if (menu) placerMenu(); }, true);
  addEventListener('resize', () => { if (menu) placerMenu(); });

  // ---------- Le tableau : recherche, compteur, « Effacer les filtres » et un bouton ▾ par colonne ----------

  // Renvoie de quoi relire les lignes gardées, dans l'ordre affiché (pour l'export).
  function tableau(boite, cols, lignes) {
    const noms = cols.map(c => c[1]);
    // Le texte affiché de chaque case est calculé une seule fois : la recherche le relit à chaque frappe.
    const items = lignes.map(l => { const v = cols.map(([c]) => l[c]), t = v.map(texte); return { v, t, k: t.map(norm) }; });
    const filtres = new Map();   // numéro de colonne -> valeurs gardées (texte affiché)
    let tri = null, gardes = items;
    boite.innerHTML = '<div class="tv-outils"><input type="search" placeholder="Rechercher dans la liste" aria-label="Rechercher dans la liste">'
      + '<span class="tv-compte" aria-live="polite"></span><button type="button" hidden>Effacer les filtres</button></div>'
      + '<div class="tv-defile"><table><thead><tr>'
      + noms.map(n => `<th>${echapper(n)}<button type="button" class="tv-btn" aria-haspopup="dialog" aria-expanded="false"></button></th>`).join('')
      + '</tr></thead><tbody></tbody></table></div>';
    const recherche = boite.querySelector('.tv-outils input'), compte = boite.querySelector('.tv-compte');
    const effacer = boite.querySelector('.tv-outils button'), corps = boite.querySelector('tbody');
    const ths = [...boite.querySelectorAll('th')], btns = ths.map(th => th.querySelector('button'));

    // Une ligne est gardée si l'une de ses cases contient le texte cherché, et si elle passe le filtre de
    // chaque colonne, sauf celui de la colonne sauf (voir ouvrirMenu).
    const garder = (it, q, sauf) => (!q || it.k.some(s => s.includes(q))) && [...filtres].every(([c, vals]) => c === sauf || vals.has(it.t[c]));

    function dessiner() {
      const q = norm(recherche.value.trim());
      gardes = items.filter(it => garder(it, q, -1));
      if (tri) gardes.sort((x, y) => ordre(x, y, tri.c, tri.sens));
      corps.innerHTML = gardes.slice(0, MAX_LIGNES).map(it => '<tr>' + it.v.map((v, i) =>
        `<td${typeof v === 'number' ? ' class="nombre"' : ''}>${echapper(it.t[i])}</td>`).join('') + '</tr>').join('');
      compte.textContent = `${fr(gardes.length)} ${gardes.length > 1 ? 'lignes' : 'ligne'} sur ${fr(items.length)}`
        + (gardes.length > MAX_LIGNES ? ` — les ${MAX_LIGNES} premières sont affichées, l'export les contient toutes` : '');
      effacer.hidden = !q && !filtres.size;
      btns.forEach((b, c) => {
        const actif = filtres.has(c), sens = tri && tri.c === c ? tri.sens : 0;
        // Comme l'entonnoir d'Excel : une colonne filtrée se voit sur son bouton ; une flèche montre le tri.
        b.classList.toggle('on', actif);
        b.innerHTML = (actif ? ENTONNOIR : '') + (sens > 0 ? '↑' : sens < 0 ? '↓' : '') + '▾';
        b.setAttribute('aria-label', 'Trier et filtrer : ' + noms[c] + (actif ? ' (filtrée)' : ''));
        if (sens) ths[c].setAttribute('aria-sort', sens > 0 ? 'ascending' : 'descending'); else ths[c].removeAttribute('aria-sort');
      });
    }

    function ouvrirMenu(c, btn) {
      fermerMenu(false);
      // Comme dans Excel, le menu liste les valeurs des lignes que laissent passer la recherche et les
      // filtres des AUTRES colonnes : celui de cette colonne est justement en train d'être choisi.
      const q = norm(recherche.value.trim()), premier = new Map();
      items.forEach(it => { if (!premier.has(it.t[c]) && garder(it, q, c)) premier.set(it.t[c], it); });
      const vals = [...premier.keys()].sort((a, b) => ordre(premier.get(a), premier.get(b), c, 1));
      const chiffres = items.some(it => typeof it.v[c] === 'number'), coches = filtres.get(c);
      menu = document.createElement('div');
      menu.className = 'tv-menu';
      menu.setAttribute('role', 'dialog');
      menu.setAttribute('aria-label', 'Trier et filtrer : ' + noms[c]);
      menu.innerHTML = `<button type="button">${chiffres ? 'Trier du plus petit au plus grand' : 'Trier de A à Z'}</button>`
        + `<button type="button">${chiffres ? 'Trier du plus grand au plus petit' : 'Trier de Z à A'}</button>`
        + '<input type="search" placeholder="Rechercher" aria-label="Rechercher une valeur">'
        + '<div class="tv-valeurs"><label><input type="checkbox"> (Tout sélectionner)</label>'
        + vals.map((v, i) => `<label><input type="checkbox" data-i="${i}"${!coches || coches.has(v) ? ' checked' : ''}> ${v === '' ? '(Vides)' : echapper(v)}</label>`).join('')
        + '</div><div class="tv-actions"><button type="button">OK</button><button type="button">Annuler</button></div>';
      boutonMenu = btn;
      btn.setAttribute('aria-expanded', 'true');
      boite.appendChild(menu);
      placerMenu();

      const [croissant, decroissant, ok, annuler] = menu.querySelectorAll('button');
      const cherche = menu.querySelector('input[type="search"]'), tout = menu.querySelector('.tv-valeurs input');
      const cases = [...menu.querySelectorAll('[data-i]')];
      // Les cases visibles : celles que laisse la petite recherche du menu.
      const visibles = () => cases.filter(x => !x.parentNode.hidden);
      // « (Tout sélectionner) » est coché quand tout est coché, à moitié quand une partie l'est. Sans aucune
      // valeur cochée, la liste serait vide : OK est alors grisé, comme dans Excel.
      const accorder = () => {
        const v = visibles(), n = v.filter(x => x.checked).length;
        tout.checked = n > 0 && n === v.length;
        tout.indeterminate = n > 0 && n < v.length;
        ok.disabled = !n;
      };
      menu.querySelector('.tv-valeurs').addEventListener('change', e => {
        if (e.target === tout) visibles().forEach(x => x.checked = tout.checked);
        accorder();
      });
      cherche.addEventListener('input', () => {
        const s = norm(cherche.value.trim());
        cases.forEach(x => x.parentNode.hidden = !norm(x.parentNode.textContent).includes(s));
        accorder();
      });
      croissant.addEventListener('click', () => { tri = { c, sens: 1 }; fermerMenu(true); dessiner(); });
      decroissant.addEventListener('click', () => { tri = { c, sens: -1 }; fermerMenu(true); dessiner(); });
      // OK garde les valeurs cochées ET visibles : chercher « fin » puis valider ne garde que les valeurs
      // qui contiennent « fin », comme dans Excel. Tout garder revient à ne plus filtrer la colonne.
      ok.addEventListener('click', () => {
        const gardees = visibles().filter(x => x.checked).map(x => vals[x.dataset.i]);
        if (gardees.length === vals.length) filtres.delete(c); else filtres.set(c, new Set(gardees));
        fermerMenu(true);
        dessiner();
      });
      annuler.addEventListener('click', () => fermerMenu(true));
      accorder();
      croissant.focus();
    }

    recherche.addEventListener('input', dessiner);
    // « Effacer les filtres » vide aussi la recherche : la liste revient complète (le tri, lui, reste).
    effacer.addEventListener('click', () => { filtres.clear(); recherche.value = ''; dessiner(); recherche.focus(); });
    btns.forEach((b, c) => b.addEventListener('click', () => { if (boutonMenu === b) fermerMenu(false); else ouvrirMenu(c, b); }));
    dessiner();
    return { lignes: () => gardes.map(it => it.v) };
  }

  // ---------- La fenêtre de la liste ----------

  const fenetre = $('liste');
  let vue = null, cols = [], titreEnCours = '', avant = null;

  // titre : ce qui a été cliqué (« Pôle 3 ») ; origine : le graphe et son filtre, en HTML (« Masse salariale · Grade 5 ») ;
  // unite : ce que compte la liste (« ligne » pour les doublons, où un salarié a plusieurs lignes).
  function ouvrir(titre, lignes, origine = '', unite = 'salarié') {
    fermerMenu(false);
    titreEnCours = titre;
    $('liste-titre').textContent = titre;
    $('liste-sous').innerHTML = (origine ? origine + ' · ' : '') + `${fr(lignes.length)} ${unite}${lignes.length > 1 ? 's' : ''}`;
    cols = COLONNES.filter(([c]) => lignes.some(l => !vide(l[c])));
    $('liste-export').disabled = !lignes.length;
    if (lignes.length) vue = tableau($('liste-corps'), cols, lignes);
    else { vue = null; $('liste-corps').innerHTML = '<p class="note liste-vide">Aucun salarié ne correspond à cette sélection.</p>'; }
    // Un graphe en plein écran cache tout le reste de la page : la liste s'ouvre alors par-dessus lui.
    (document.fullscreenElement || document.body).appendChild(fenetre);
    avant = document.activeElement;
    fenetre.hidden = false;
    const recherche = fenetre.querySelector('.tv-outils input');
    (recherche || $('liste-fermer')).focus();
  }

  function fermer() {
    fermerMenu(false);
    fenetre.hidden = true;
    if (avant && avant.focus) avant.focus();
  }

  $('liste-fermer').addEventListener('click', fermer);
  fenetre.addEventListener('click', e => { if (e.target === fenetre) fermer(); });
  // Échap ferme d'abord le menu d'une colonne s'il est ouvert, et seulement ensuite la liste.
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !fenetre.hidden) { if (menu) fermerMenu(true); else fermer(); } });
  // En quittant le plein écran, la liste revient dans la page (sinon elle disparaîtrait avec le graphe).
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && fenetre.parentNode !== document.body) document.body.appendChild(fenetre); });

  // Export Excel des lignes gardées par la recherche et les filtres, dans l'ordre du tri, TOUTES (même
  // au-delà des lignes dessinées). Les nombres restent des nombres : Excel peut les additionner ou les trier tout de suite.
  $('liste-export').addEventListener('click', () => {
    const classeur = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(classeur, XLSX.utils.aoa_to_sheet([cols.map(c => c[1])].concat(vue ? vue.lignes().map(l => l.map(v => vide(v) ? null : v)) : [])), 'Salariés');
    // Le nom du fichier reprend le titre de la liste, sans accents ni espaces (« Pôle 3 » → salaries_pole_3.xlsx).
    XLSX.writeFile(classeur, 'salaries_' + titreEnCours.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\w]+/g, '_').replace(/^_|_$/g, '').toLowerCase() + '.xlsx');
  });

  E.liste = { ouvrir };
})(window.Exploration = window.Exploration || {});
