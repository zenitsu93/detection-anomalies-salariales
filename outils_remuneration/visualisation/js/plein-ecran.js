// Agrandir un graphe en plein écran : un bouton dans l'en-tête de chaque panneau qui contient un graphe.
// En plein écran, le graphe prend toute la hauteur disponible et ses filtres restent utilisables ;
// « Réduire » ou la touche Échap ramène à la page.
(function (E) {
  'use strict';
  const AGRANDIR = '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/></svg>Agrandir';
  const REDUIRE = '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M6 2v4H2M14 6h-4V2M10 14v-4h4M2 10h4v4"/></svg>Réduire';
  const boutons = [];

  if (!document.fullscreenEnabled) return;   // navigateur sans plein écran : pas de bouton

  document.querySelectorAll('section.panel').forEach(section => {
    if (!section.querySelector('.graphe')) return;
    // Le bouton se range à droite de l'en-tête, après l'unité.
    const tete = section.querySelector('.panel-head'), actions = document.createElement('div');
    actions.className = 'panel-actions';
    const unite = tete.querySelector('.panel-unit');
    if (unite) actions.append(unite);
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'agrandir';
    b.onclick = () => document.fullscreenElement === section ? document.exitFullscreen() : section.requestFullscreen();
    actions.append(b);
    tete.append(actions);
    boutons.push([b, section]);
  });

  function mettreAJour() {
    for (const [b, section] of boutons) {
      const plein = document.fullscreenElement === section;
      b.innerHTML = plein ? REDUIRE : AGRANDIR;
      b.title = plein ? 'Revenir à la page (Échap)' : 'Afficher ce graphe en plein écran';
    }
    // Le graphe prend la largeur et la hauteur que lui laisse le plein écran, puis reprend les siennes au retour
    // (largeur « null » : il suit de nouveau la largeur de la page).
    requestAnimationFrame(() => document.querySelectorAll('.graphe.js-plotly-plot').forEach(div => {
      const plein = document.fullscreenElement && document.fullscreenElement.contains(div);
      if (plein) Plotly.relayout(div, { height: E.communs.hauteurDisponible(div), width: Math.floor(div.getBoundingClientRect().width) });
      else if (div.layout.width || div.layout.height !== Number(div.dataset.hauteur)) Plotly.relayout(div, { height: Number(div.dataset.hauteur), width: null });
    }));
  }

  document.addEventListener('fullscreenchange', mettreAJour);
  mettreAJour();
})(window.Exploration = window.Exploration || {});
