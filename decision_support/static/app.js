'use strict';
const $ = id => document.getElementById(id);
const form = $('profile-form');
let meta, revision = 0, controller = null;
const fmt = value => value == null ? 'Indisponible' : new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 2}).format(value);
const node = (tag, text, cls) => { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; return e; };
const SUBMIT_LABEL = 'Prédire le salaire';
function resetResult() {
  revision++;
  if (controller) controller.abort();
  $('result').hidden = true;
  $('empty').hidden = false;
  $('form-error').hidden = true;
  $('result-area').setAttribute('aria-busy', 'false');
  $('submit').disabled = !meta;
  $('submit').textContent = SUBMIT_LABEL;
}
// Les champs du profil, décrits par le serveur (ce que lit le modèle du salaire prédit) : une liste de
// choix pour une catégorie, un nombre borné pour le reste. Ils sont tous obligatoires : sans l'un
// d'eux, le modèle ne peut pas prédire, et la page n'aurait rien à montrer.
function renderModelFields(fields) {
  const box = $('model-fields');
  for (const f of fields) {
    const id = 'model-' + f.name, label = node('label', '', 'field');
    label.htmlFor = id;
    label.append(node('span', f.label, 'field-name'));
    let input;
    if (f.kind === 'choice') {
      input = document.createElement('select');
      input.append(new Option('Choisir', ''), ...f.options.map(o => new Option(o, o)));
    } else {
      input = document.createElement('input');
      Object.assign(input, {type: 'number', min: f.min, max: f.max, step: f.step, placeholder: `De ${fmt(f.min)} à ${fmt(f.max)}`});
    }
    Object.assign(input, {id, name: f.name, required: true});
    label.append(input);
    box.append(label);
  }
  box.hidden = fields.length === 0;
}
function updateNiveaux() {
  $('niveau').replaceChildren(new Option('Choisir un niveau', ''));
  for (const niveau of meta.jobs[$('job').value] || []) $('niveau').append(new Option(niveau, niveau));
  $('niveau').disabled = !$('job').value;
}
form.addEventListener('input', resetResult);
$('job').addEventListener('change', updateNiveaux);
const at = (el, name, value) => { el.style.setProperty(name, value + '%'); return el; };
// La figure : une seule ligne. La grille du poste (du Min au Max), et dessus le salaire prédit avec
// la fourchette où le vrai salaire tombe 9 fois sur 10. Pourquoi une seule ligne : avec une ligne par
// repère (grille, marché, collègues, proposition), la figure portait une dizaine de montants.
// Pourquoi style.setProperty : la CSP interdit les attributs style, pas le CSSOM.
function renderRuler(band, r) {
  const ruler = $('ruler'); ruler.replaceChildren();
  $('ruler-card').hidden = !band;
  if (!band) return;
  const values = [band.Min, band.Max, r.low, r.high].filter(v => v != null);
  let lo = Math.min(...values), hi = Math.max(...values);
  // Un peu de marge de chaque côté, pour que la grille ne colle pas aux bords.
  const pad = (hi - lo) * .04 || 1;
  lo -= pad; hi += pad;
  const pos = v => (v - lo) / (hi - lo) * 100;
  const value = (v, cls, text) => at(node('span', text || fmt(v), 'val ' + cls), '--x', pos(v));
  const track = node('div', '', 'track');
  track.append(at(at(node('span', '', 'bar band'), '--a', pos(band.Min)), '--b', pos(band.Max)),
    value(band.Min, 'below from', `Min ${fmt(band.Min)}`), value(band.Max, 'below upto', `Max ${fmt(band.Max)}`));
  if (r.predicted != null) {
    // Les deux bouts de la fourchette s'écrivent vers l'extérieur, pour laisser la place au salaire
    // prédit, écrit au-dessus du point. Près d'un bord, ils reviennent vers l'intérieur.
    track.append(at(at(node('span', '', 'bar range'), '--a', pos(r.low)), '--b', pos(r.high)),
      at(node('span', '', 'pip target'), '--x', pos(r.predicted)),
      value(r.low, 'ends ' + (pos(r.low) < 12 ? 'from' : 'upto')), value(r.high, 'ends ' + (pos(r.high) > 88 ? 'upto' : 'from')),
      value(r.predicted, 'top'));
  }
  $('legend').hidden = r.predicted == null;
  ruler.append(track);
}
// Le résultat : un seul grand chiffre, le salaire prédit, et sa fourchette. Sans salaire prédit, la
// phrase dit pourquoi.
function render(data) {
  $('empty').hidden = true;
  $('result').hidden = false;
  const {profile, band, market, peers, regression: r} = data;
  $('verdict').className = 'panel verdict' + (r.predicted == null ? ' insufficient' : '');
  $('result-profile').textContent = [`${profile.job_family} · Niveau ${profile.niveau}`,
    profile.seniority == null ? null : `${fmt(profile.seniority)} ${profile.seniority < 2 ? 'an' : 'ans'} d’ancienneté`].filter(Boolean).join(' · ');
  $('predicted').textContent = r.predicted == null ? '—' : fmt(r.predicted);
  $('predicted-note').textContent = r.predicted != null ? `9 fois sur 10, le vrai salaire tombe entre ${fmt(r.low)} et ${fmt(r.high)}.`
    : !r.available ? 'Le modèle n’a pas pu apprendre sur les fichiers chargés.'
    : r.missing.length ? `À renseigner : ${r.missing.join(', ')}.`
    : 'Pas de grille ou de marché exploitable pour ce métier et ce niveau.';
  renderRuler(band, r);
  // Les deux autres repères, en une phrase : la médiane du marché et celle des collègues comparables.
  $('ruler-note').textContent = [
    market ? `Médiane du marché : ${fmt(market.Median)}` : 'Marché : indisponible',
    peers.available ? `Médiane des ${fmt(peers.count)} collègues comparables (${peers.scope}) : ${fmt(peers.median)}`
      : `Collègues : pas assez de collègues comparables (${fmt(peers.count)})`].join(' · ') + '.';
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
      $('submit').textContent = SUBMIT_LABEL;
      $('result-area').setAttribute('aria-busy', 'false');
    }
  }
});
(async () => {
  try {
    const response = await fetch('/api/metadata');
    if (!response.ok) throw new Error('Impossible de charger les références.');
    meta = await response.json();
    $('job').replaceChildren(new Option('Choisir un métier', ''));
    for (const job of Object.keys(meta.jobs)) $('job').append(new Option(job, job));
    $('job').disabled = false; $('submit').disabled = false;
    renderModelFields(meta.fields || []);
    for (const label of document.querySelectorAll('.unit-label')) label.textContent = meta.unit;
    $('employees-count').textContent = `${fmt(meta.employees)} salaires`;
    $('source-note').textContent = 'Références chargées au démarrage : redémarrer l’application après modification des sources.';
  } catch (error) {
    $('form-error').textContent = error.message; $('form-error').hidden = false;
    $('source-note').textContent = 'Références indisponibles. Vérifiez le serveur local.';
  }
})();
