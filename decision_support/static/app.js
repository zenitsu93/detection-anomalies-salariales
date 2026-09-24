'use strict';
const $ = id => document.getElementById(id);
const form = $('profile-form');
let meta, currentResult = null, revision = 0, controller = null;
const fmt = value => value == null ? 'Indisponible' : new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 2}).format(value);
const dash = value => value == null ? '—' : fmt(value);
const pct = new Intl.NumberFormat('fr-FR', {style: 'percent', maximumFractionDigits: 1, signDisplay: 'exceptZero'});
const node = (tag, text, cls) => { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; return e; };
const mode = () => form.elements.mode.value;
const submitLabel = () => mode() === 'evaluate' ? 'Vérifier le salaire' : 'Obtenir une proposition';
function resetResult() {
  revision++;
  if (controller) controller.abort();
  currentResult = null;
  $('result').hidden = true;
  $('empty').hidden = false;
  $('form-error').hidden = true;
  $('result-area').setAttribute('aria-busy', 'false');
  $('submit').disabled = !meta;
  $('submit').textContent = submitLabel();
}
function updateGrades() {
  $('grade').replaceChildren(new Option('Choisir un grade', ''));
  for (const grade of meta.jobs[$('job').value] || []) $('grade').append(new Option(grade, grade));
  $('grade').disabled = !$('job').value;
}
form.addEventListener('input', resetResult);
$('job').addEventListener('change', updateGrades);
for (const radio of form.elements.mode) radio.addEventListener('change', () => {
  const evaluate = mode() === 'evaluate';
  $('salary-field').hidden = !evaluate;
  $('salary').required = evaluate;
  $('salary').disabled = !evaluate;
  resetResult();
});
const at = (el, name, value) => { el.style.setProperty(name, value + '%'); return el; };
// Pas « rond » (1, 2 ou 5 × 10^n) pour que les graduations restent lisibles quel que soit l'ordre de grandeur.
function niceStep(span) {
  const raw = span / 5, power = 10 ** Math.floor(Math.log10(raw)), n = raw / power;
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * power;
}
// Place tous les repères sur une même échelle : c'est l'écart entre eux qui aide à décider.
// Pourquoi style.setProperty : la CSP interdit les attributs style, pas le CSSOM.
function renderRuler(data) {
  const {band, market, peers, proposal: p, salary} = data;
  const values = [band?.Min, band?.Max, market?.Median, peers.q25, peers.q75, peers.median, p.low, p.high, p.target, salary]
    .filter(v => v != null && Number.isFinite(v));
  const ruler = $('ruler'); ruler.replaceChildren();
  $('ruler-card').hidden = values.length === 0;
  if (!values.length) return;
  let lo = Math.min(...values), hi = Math.max(...values);
  const pad = hi > lo ? (hi - lo) * .1 : Math.abs(lo) * .1 || 1;
  lo -= pad; hi += pad;
  const pos = v => (v - lo) / (hi - lo) * 100;
  const step = niceStep(hi - lo), ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(+t.toPrecision(12));
  // Lignes de graduation posées avant les lignes de repères pour rester en arrière-plan.
  const grid = node('div', '', 'overlay');
  for (const t of ticks) grid.append(at(node('span', '', 'gridline'), '--x', pos(t)));
  ruler.append(grid);
  // Barre : [classe, début, fin] ; point : [classe, valeur, null, préfixe du montant affiché au-dessus].
  const lanes = [
    ['Grille métier', band ? 'Min – Max' : 'Aucune grille exploitable',
      band && [['bar band', band.Min, band.Max], ['pip mid', band.Mid, null, 'Milieu']]],
    ['Marché', market ? 'Médiane' : 'Indisponible', market && [['pip market', market.Median, null, '']]],
    ['Collègues', peers.available ? 'P25 – P75' : 'Effectif insuffisant',
      peers.available && [['bar peers', peers.q25, peers.q75], ['pip median', peers.median, null, 'Médiane']]],
    ['Proposition', p.target == null ? 'Pas de fourchette' : 'Bas – Haut',
      p.target != null && [['bar proposal', p.low, p.high], ['pip target', p.target, null, 'Cible']]]
  ];
  // Montants écrits sur la règle : bornes sous la barre, à l'extérieur pour ne jamais se chevaucher
  // (ramenées à l'intérieur près des bords) ; points au-dessus.
  const value = (v, cls) => at(node('span', fmt(v), 'val ' + cls), '--x', pos(v));
  for (const [name, caption, marks] of lanes) {
    const lane = node('div', '', 'lane'), label = node('div', name, 'lane-label'), track = node('div', '', 'track');
    label.append(node('small', caption));
    if (!marks) track.append(node('span', 'Non disponible', 'lane-empty'));
    else for (const [cls, a, b, prefix] of marks) {
      const mark = at(node('span', '', cls), cls.startsWith('bar') ? '--a' : '--x', pos(a));
      track.append(mark);
      if (b != null) {
        at(mark, '--b', pos(b));
        track.append(value(a, 'below ' + (pos(a) < 12 ? 'inside-start' : 'start')),
          value(b, 'below ' + (pos(b) > 88 ? 'inside-end' : 'end')));
      } else {
        const label = value(a, 'above ' + cls.split(' ')[1]);
        label.textContent = prefix ? `${prefix} ${fmt(a)}` : fmt(a);
        track.append(label);
      }
    }
    lane.append(label, track); ruler.append(lane);
  }
  const axis = node('div', '', 'axis');
  for (const t of ticks) axis.append(at(node('span', fmt(t), 'tick'), '--x', pos(t)));
  ruler.append(axis);
  ruler.classList.toggle('has-cursor', salary != null);
  if (salary != null) {
    const x = pos(salary), overlay = node('div', '', 'overlay');
    const cursor = at(node('div', '', 'cursor' + (x < 15 ? ' edge-left' : x > 85 ? ' edge-right' : '')), '--x', x);
    cursor.append(node('span', `Salaire évalué · ${fmt(salary)}`));
    overlay.append(cursor); ruler.append(overlay);
  }
}
// Chiffres clés du bandeau : la décision à prendre. Le détail (bornes, médianes, ratios) est sur la
// règle et dans les contrôles ; on ne le répète pas ici.
function renderFigures(data) {
  const p = data.proposal, mid = data.band?.Mid;
  const items = [['Fourchette proposée', p.target == null ? '—' : `${fmt(p.low)} – ${fmt(p.high)}`], ['Cible', dash(p.target)]];
  if (data.mode === 'evaluate') {
    const gap = p.target == null ? null : (data.salary - p.target) / p.target;
    items.push(['Écart à la cible', gap == null ? '—' : pct.format(gap), gap == null || gap === 0 ? '' : gap < 0 ? 'neg' : 'pos']);
  } else {
    items.push(['CompaRatio cible', mid && p.target != null ? fmt(Math.round(p.target / mid * 100) / 100) : '—']);
  }
  $('summary-figures').replaceChildren(...items.map(([label, value, cls]) => {
    const cell = node('div', ''); cell.append(node('dt', label), node('dd', value, cls)); return cell;
  }));
}
function table(el, headers, rows) {
  const head = document.createElement('thead'), tr = document.createElement('tr');
  for (const [text, cls] of headers) tr.append(node('th', text, cls));
  head.append(tr);
  const body = document.createElement('tbody');
  for (const cells of rows) {
    const row = document.createElement('tr');
    for (const cell of cells) row.append(cell instanceof Node ? cell : node('td', cell[0], cell[1]));
    body.append(row);
  }
  el.replaceChildren(head, body);
}
function render(data) {
  currentResult = data;
  $('empty').hidden = true;
  $('result').hidden = false;
  $('verdict').className = 'panel verdict ' + data.status;
  $('result-title').textContent = data.title;
  $('result-mode').textContent = data.mode === 'evaluate' ? 'Évaluation du salaire' : 'Proposition de référence';
  $('result-mode').hidden = $('result-mode').textContent === data.title;
  const {profile, proposal: p, peers} = data;
  $('result-profile').textContent = [`${profile.job_family} · Grade ${profile.grade}`,
    profile.seniority == null ? null : `${fmt(profile.seniority)} ans d’ancienneté`,
    data.salary == null ? null : `${fmt(data.salary)} ${data.unit}`].filter(Boolean).join(' · ');
  renderFigures(data);
  renderRuler(data);
  $('ruler-note').textContent = `Collègues comparés : ${peers.count} · ${peers.scope.toLowerCase()}.` +
    (p.target == null ? '' : ' La cible est ramenée dans la fourchette proposée.');
  $('checks-card').hidden = data.mode !== 'evaluate';
  const labels = {ok: 'Dans les repères', review: 'À examiner', unavailable: 'Indisponible'};
  table($('checks'), [['Contrôle'], ['Valeur', 'num'], ['Règle appliquée'], ['Statut']], data.checks.map(c => {
    const status = document.createElement('td'); status.append(node('span', labels[c.status], 'status ' + c.status));
    return [[c.name], [dash(c.value), 'num'], [c.detail, 'sub'], status];
  }));
  $('warnings').replaceChildren(...data.warnings.map(w => node('li', w)));
  $('notes-card').hidden = data.warnings.length === 0;
  $('method').textContent = data.method;
  $('limits').textContent = data.limits;
  $('basis').replaceChildren(...p.basis.map(b => node('li', b)));
  $('loaded-at').textContent = data.provenance.loaded_at ? `Références chargées le ${new Date(data.provenance.loaded_at).toLocaleString('fr-FR')}.` : '';
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  resetResult();
  const requestRevision = revision;
  controller = new AbortController();
  $('submit').disabled = true;
  $('submit').textContent = 'Calcul en cours…';
  $('result-area').setAttribute('aria-busy', 'true');
  try {
    const payload = Object.fromEntries(new FormData(form).entries());
    const response = await fetch('/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal: controller.signal});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Le calcul a échoué.');
    if (requestRevision === revision) render(data);
  } catch (error) {
    if (error.name !== 'AbortError' && requestRevision === revision) {
      $('form-error').textContent = error.message; $('form-error').hidden = false;
    }
  } finally {
    if (requestRevision === revision) {
      $('submit').disabled = false;
      $('submit').textContent = submitLabel();
      $('result-area').setAttribute('aria-busy', 'false');
    }
  }
});
$('download').addEventListener('click', () => {
  if (!currentResult) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(currentResult, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'simulation-remuneration.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('print').addEventListener('click', () => window.print());
(async () => {
  try {
    const response = await fetch('/api/metadata');
    if (!response.ok) throw new Error('Impossible de charger les références.');
    meta = await response.json();
    $('job').replaceChildren(new Option('Choisir un métier', ''));
    for (const job of Object.keys(meta.jobs)) $('job').append(new Option(job, job));
    $('job').disabled = false; $('submit').disabled = false;
    for (const label of document.querySelectorAll('.unit-label')) label.textContent = meta.unit;
    $('employees-count').textContent = `${fmt(meta.employees)} salaires`;
    $('source-note').textContent = 'Références chargées au démarrage : redémarrer l’application après modification des sources.';
  } catch (error) {
    $('form-error').textContent = error.message; $('form-error').hidden = false;
    $('source-note').textContent = 'Références indisponibles. Vérifiez le serveur local.';
  }
})();
