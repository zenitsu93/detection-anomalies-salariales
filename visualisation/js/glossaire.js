// Rechercher dans le glossaire : une case au-dessus des mots. À chaque lettre tapée, seuls restent les mots dont le
// nom ou l'explication contient le texte cherché, et ce texte est surligné en jaune. Les accents et les majuscules ne
// comptent pas : « mediane » trouve « Médiane ». Avec plusieurs mots tapés (« grille marché »), un mot du glossaire
// reste affiché s'il les contient tous, dans n'importe quel ordre. La touche Échap vide la case.
(function () {
  'use strict';
  const corps = document.querySelector('#glossaire .glossaire');
  if (!corps) return;

  // « Médiane » devient « mediane » : sans accents, en minuscules, les espaces insécables changés en espaces simples.
  const simple = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s/g, ' ').toLowerCase();

  // Chaque mot du glossaire, avec son texte simplifié (lu une seule fois) et son thème (le titre au-dessus de lui).
  const themes = [...corps.querySelectorAll('h3')].map(h3 => ({ titre: h3, liste: h3.nextElementSibling }));
  const entrees = [...corps.querySelectorAll('dl > div')].map(div => ({ div, texte: simple(div.textContent), morceaux: morceaux(div) }));

  // Pour surligner, il faut retrouver dans le vrai texte la place de ce qu'on a trouvé dans le texte simplifié. Les deux
  // n'ont pas toujours la même longueur (« é » simplifié passe par « e » + accent, puis l'accent est retiré) : on garde,
  // pour chaque lettre du texte simplifié, la place de la lettre d'origine.
  function morceaux(div) {
    const parcours = document.createTreeWalker(div, NodeFilter.SHOW_TEXT), liste = [];
    for (let noeud = parcours.nextNode(); noeud; noeud = parcours.nextNode()) {
      const vrai = noeud.data, place = [];
      let texte = '';
      for (let i = 0; i < vrai.length; i++) {
        const s = simple(vrai[i]);
        texte += s;
        for (let k = 0; k < s.length; k++) place.push(i);
      }
      liste.push({ noeud, texte, place, longueur: vrai.length });
    }
    return liste;
  }

  // Le surlignage passe par le navigateur (CSS Custom Highlight) : il ne touche pas au texte de la page. Un navigateur
  // trop ancien pour le connaître filtre quand même les mots, sans surligner.
  const surlignage = window.CSS && CSS.highlights && typeof Highlight === 'function';

  const barre = document.createElement('div');
  barre.className = 'gl-outils';
  barre.innerHTML = '<input type="search" placeholder="Rechercher un mot : médiane, Compa-Ratio, 9-Box…" aria-label="Rechercher dans le glossaire">'
    + '<span class="gl-compte" aria-live="polite"></span>';
  corps.prepend(barre);
  const recherche = barre.querySelector('input'), compte = barre.querySelector('.gl-compte');
  const vide = document.createElement('p');
  vide.className = 'gl-vide';
  corps.append(vide);

  function chercher() {
    const mots = simple(recherche.value).split(' ').filter(Boolean), zones = [];
    let n = 0;
    for (const e of entrees) {
      const garde = mots.every(m => e.texte.includes(m));
      e.div.hidden = !garde;
      if (!garde) continue;
      n++;
      // Chaque endroit où un mot cherché apparaît, morceau de texte par morceau de texte.
      if (surlignage) for (const m of mots) for (const t of e.morceaux) {
        for (let i = t.texte.indexOf(m); i >= 0; i = t.texte.indexOf(m, i + m.length)) {
          const z = new Range();
          z.setStart(t.noeud, t.place[i]);
          z.setEnd(t.noeud, i + m.length < t.place.length ? t.place[i + m.length] : t.longueur);
          zones.push(z);
        }
      }
    }
    // Un thème sans aucun mot gardé disparaît, titre compris.
    for (const t of themes) {
      const cache = !t.liste.querySelector('dl > div:not([hidden])');
      t.titre.hidden = cache;
      t.liste.hidden = cache;
    }
    if (surlignage) CSS.highlights.set('glossaire', new Highlight(...zones));
    compte.textContent = !mots.length ? `${entrees.length} mots` : `${n} mot${n > 1 ? 's' : ''} sur ${entrees.length}`;
    vide.textContent = mots.length && !n ? `Aucun mot du glossaire ne contient « ${recherche.value.trim()} ».` : '';
  }

  recherche.addEventListener('input', chercher);
  recherche.addEventListener('keydown', ev => { if (ev.key === 'Escape' && recherche.value) { recherche.value = ''; chercher(); } });
  chercher();
})();
