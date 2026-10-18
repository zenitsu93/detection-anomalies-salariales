// Outils communs à toute la page : mise en forme des nombres, couleurs Repères et réglages des graphes Plotly.
(function (E) {
  'use strict';
  const C = E.calculs;
  const $ = id => document.getElementById(id);

  // ---------- Nombres et textes ----------

  const fr = (x, d = 0) => Number.isFinite(x) ? x.toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }) : '–';
  const pct = (n, total, d = 1) => total ? fr(100 * n / total, d) + ' %' : '–';
  const signe = (x, d = 2) => Number.isFinite(x) ? (x > 0 ? '+' : x < 0 ? '−' : '') + fr(Math.abs(x), d) + ' %' : '–';
  const echapper = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const constat = (id, html) => { $(id).innerHTML = '<b>Constat</b><span>' + html + '</span>'; };

  // ---------- Couleurs ----------

  // Repères : ardoise pour les effectifs, brun pour les repères, bleu pour le marché, rouge pour les bornes.
  const COULEURS = {
    ENCRE: '#1f2328', GRIS: '#5f6670', PALE: '#8b929b', TRAIT: '#dde0e4', GRILLE: '#eceef1',
    ARDOISE: '#5b6b7d', BRUN: '#4a2c1d', OR: '#e9a21b', BLEU: '#3d6fa8', CUIVRE: '#9a5530', ROUGE: '#b3261e',
  };
  const transparent = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;

  // ---------- Réglages Plotly ----------

  const POLICE = '"Segoe UI", system-ui, sans-serif';
  Plotly.register({
    moduleType: 'locale', name: 'fr',
    dictionary: {
      'Zoom': 'Zoom', 'Pan': 'Déplacer', 'Zoom in': 'Zoom avant', 'Zoom out': 'Zoom arrière', 'Autoscale': 'Ajuster aux données',
      'Reset axes': 'Revenir à la vue de départ', 'Reset view': 'Revenir à la vue de départ',
      'Download plot as a PNG': 'Enregistrer en image (PNG)', 'Download plot': 'Enregistrer en image',
      'Double-click to zoom back out': 'Double-cliquer pour revenir à la vue de départ',
    },
    format: { decimal: ',', thousands: ' ' },
  });
  const CONFIG = {
    locale: 'fr', displaylogo: false, scrollZoom: true, responsive: true,
    modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d', 'toggleSpikelines', 'hoverClosestCartesian', 'hoverCompareCartesian'],
    toImageButtonOptions: { format: 'png', scale: 2 },
  };
  const AXE = { gridcolor: COULEURS.GRILLE, linecolor: COULEURS.TRAIT, showline: true, zeroline: false, automargin: true,
    tickfont: { size: 11, color: COULEURS.GRIS } };
  const nomAxe = i => i === 1 ? '' : String(i);
  const titreAxe = texte => ({ text: texte, font: { size: 12, color: COULEURS.GRIS }, standoff: 10 });

  // Découpe la zone en sous-graphes ; xPartage : un même axe horizontal par colonne.
  function grille({ lignes = 1, colonnes = 1, titres = [], hauteurs = null, espV = 0.12, espH = 0.09, xPartage = false }) {
    const L = { annotations: [], shapes: [] };
    const parts = hauteurs || Array(lignes).fill(1 / lignes);
    const largeur = (1 - espH * (colonnes - 1)) / colonnes, dispo = 1 - espV * (lignes - 1);
    let haut = 1;
    for (let r = 0; r < lignes; r++) {
      const bas = haut - parts[r] * dispo;
      for (let c = 0; c < colonnes; c++) {
        const i = r * colonnes + c + 1, s = nomAxe(i), x0 = c * (largeur + espH);
        L['xaxis' + s] = { ...AXE, domain: [x0, x0 + largeur], anchor: 'y' + s };
        L['yaxis' + s] = { ...AXE, domain: [bas, haut], anchor: 'x' + s };
        if (xPartage && r < lignes - 1) Object.assign(L['xaxis' + s], { matches: 'x' + nomAxe((lignes - 1) * colonnes + c + 1), showticklabels: false });
        if (titres[i - 1]) L.annotations.push({ text: titres[i - 1], x: x0, y: haut, xref: 'paper', yref: 'paper', xanchor: 'left', yanchor: 'bottom',
          yshift: 8, showarrow: false, align: 'left', font: { size: 13, color: COULEURS.ENCRE } });
      }
      haut = bas - espV;
    }
    return L;
  }

  // En plein écran, le graphe prend toute la place que lui laisse son panneau (voir plein-ecran.js).
  const hauteurDisponible = div => Math.max(360, Math.floor(div.getBoundingClientRect().height));

  // Le nom du graphe, tel qu'écrit en tête de son panneau (sans son numéro) : il est rappelé en haut de la liste des salariés.
  const nomGraphe = div => [...div.closest('section').querySelector('.panel-title').childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();

  // clic(point) : les salariés derrière la barre, la boîte, la case ou le point cliqué, { titre, lignes } (null : rien à montrer).
  // filtre : le filtre en cours du graphe, rappelé avec son nom en haut de la liste.
  function montrer(id, traces, L, hauteur = 520, clic = null, filtre = 'Tous les salariés') {
    const div = $(id);
    div.dataset.hauteur = hauteur;   // la hauteur normale, reprise en sortant du plein écran
    if (document.fullscreenElement && document.fullscreenElement.contains(div)) hauteur = hauteurDisponible(div);
    Object.assign(L, {
      height: hauteur, margin: { t: 52, b: 64, l: 64, r: 24, ...(L.margin || {}) }, paper_bgcolor: '#fff', plot_bgcolor: '#fff',
      font: { family: POLICE, size: 12, color: COULEURS.GRIS }, separators: ', ',
      hoverlabel: { bgcolor: COULEURS.ENCRE, bordercolor: COULEURS.ENCRE, font: { family: POLICE, size: 12, color: '#fff' }, align: 'left' },
      legend: { orientation: 'h', x: 0, xanchor: 'left', y: -0.14, yanchor: 'top', font: { size: 12, color: COULEURS.ENCRE }, ...(L.legend || {}) },
    });
    Plotly.react(id, traces, L, CONFIG).then(gd => {
      // Chaque dessin remplace le clic du précédent : la liste suit toujours le filtre affiché.
      gd.removeAllListeners('plotly_click');
      if (clic) gd.on('plotly_click', e => {
        const choix = e.points[0] && clic(e.points[0]);
        if (choix) E.liste.ouvrir(choix.titre, choix.lignes, `${echapper(nomGraphe(gd))} · ${filtre}`);
      });
    });
  }

  // Un seul salarié : celui du point cliqué.
  const salarie = l => ({ titre: 'Salarié ' + l.Matricule, lignes: [l] });
  // Une valeur dans la barre cliquée d'un histogramme (barresEtCourbe) : du bord gauche (compris) au bord droit
  // (exclu, sauf pour la dernière barre), exactement comme le calcul de l'histogramme.
  const dansBarre = (p, x) => x >= p.customdata[0] && (x < p.customdata[1] || p.pointNumber === p.data.x.length - 1);

  // Boîte à moustaches aux couleurs de la page.
  const boite = (couleur, extra) => ({ type: 'box', marker: { color: couleur, size: 4, opacity: 0.7 }, line: { color: couleur, width: 1.5 },
    fillcolor: transparent(couleur, 0.22), boxpoints: 'outliers', ...extra });

  // Barres de l'histogramme et courbe lissée à la même hauteur que les barres.
  function barresEtCourbe(valeurs, bins, axes) {
    const v = valeurs.filter(Number.isFinite);
    if (!v.length) return [];
    const h = C.histogramme(v, bins), traces = [
      { type: 'bar', x: h.centres, y: h.effectifs, width: h.largeur, marker: { color: transparent(COULEURS.ARDOISE, 0.75), line: { color: '#fff', width: 1 } },
        showlegend: false, customdata: h.effectifs.map((_, i) => [h.bords[i], h.bords[i + 1]]),
        hovertemplate: 'De %{customdata[0]:.2f} à %{customdata[1]:.2f}<br><b>%{y} salariés</b><extra></extra>', ...axes }];
    if (v.length > 2 && C.ecartType(v) > 0) {
      const k = C.courbeLissee(v, h);
      traces.push({ type: 'scatter', mode: 'lines', x: k.x, y: k.y, line: { color: COULEURS.BRUN, width: 2 }, showlegend: false, hoverinfo: 'skip', ...axes });
    }
    return traces;
  }

  // Ligne horizontale de repère sur un sous-graphe (s = numéro d'axe : '', '2'...).
  const ligneH = (s, y, couleur, extra = {}) => ({ type: 'line', xref: `x${s} domain`, x0: 0, x1: 1, yref: 'y' + s, y0: y, y1: y,
    line: { color: couleur, dash: 'dash', width: 1.5 }, ...extra });
  const indices = (lignes, test) => lignes.reduce((t, l, i) => (test(l) && t.push(i), t), []);
  const texteGrade = g => Number.isFinite(g) ? String(g) : null;

  E.communs = {
    $, fr, pct, signe, echapper, constat, COULEURS, transparent,
    nomAxe, titreAxe, grille, hauteurDisponible, montrer, salarie, dansBarre, boite, barresEtCourbe, ligneH, indices, texteGrade,
  };
})(window.Exploration = window.Exploration || {});
