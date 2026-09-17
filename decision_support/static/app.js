'use strict';
const $ = id => document.getElementById(id);
const form = $('profile-form');
let meta, currentResult = null, revision = 0, controller = null;
const fmt = value => value == null ? 'Indisponible' : new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 2}).format(value);
const node = (tag, text, cls) => { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; return e; };
const mode = () => form.elements.mode.value;
function resetResult() {
  revision++;
  if (controller) controller.abort();
  currentResult = null;
  $('result').hidden = true;
  $('empty').hidden = false;
  $('form-error').hidden = true;
  $('result-area').setAttribute('aria-busy', 'false');
  $('submit').disabled = !meta;
  $('submit').textContent = mode() === 'evaluate' ? 'Vérifier le salaire →' : 'Obtenir une proposition →';
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
function render(data) {
  currentResult = data;
  $('empty').hidden = true;
  $('result').hidden = false;
  $('verdict').className = 'verdict ' + data.status;
  $('result-title').textContent = data.title;
  $('result-mode').textContent = data.mode === 'evaluate' ? 'ÉVALUATION DU SALAIRE' : 'PROPOSITION DE RÉFÉRENCE';
  $('result-profile').textContent = `${data.profile.job_family} · Grade ${data.profile.grade}` + (data.salary == null ? '' : ` · ${fmt(data.salary)} ${data.unit}`);
  const p = data.proposal;
  const values = $('proposal-values'); values.replaceChildren();
  if (p.target == null) {
    values.append(node('p', p.reason === 'conflict' ? 'Pas de fourchette commune' : 'Pas de proposition chiffrée', 'target'));
  } else {
    values.append(node('div', `${fmt(p.low)} – ${fmt(p.high)}`, 'range'), node('p', `Montant cible indicatif : ${fmt(p.target)} ${data.unit}`, 'target'));
  }
  $('proposal-context').textContent = p.target == null ? 'Consultez les références et les points à examiner ci-dessous.' : 'Une fourchette de discussion, issue des références disponibles. La cible est ramenée dans cette fourchette.';
  const refs = $('references'); refs.replaceChildren();
  const items = [
    ['Grille métier · milieu', data.band?.Mid, data.band ? `Min ${fmt(data.band.Min)} · Max ${fmt(data.band.Max)}` : 'Aucune grille exploitable'],
    ['Marché · médiane', data.market?.Median, 'Même métier et même grade'],
    ['Collègues · médiane', data.peers.median, `${data.peers.count} collègues · ${data.peers.scope}`]
  ];
  for (const [title, value, caption] of items) {
    const card = node('section', '', 'card reference');
    card.append(node('h3', title), node('strong', fmt(value)), node('p', caption)); refs.append(card);
  }
  $('checks-card').hidden = data.mode !== 'evaluate';
  $('checks').replaceChildren();
  for (const c of data.checks) {
    const row = node('div', '', 'check ' + c.status);
    const label = {ok: 'Dans les repères', review: 'À examiner', unavailable: 'Indisponible'}[c.status];
    row.append(node('strong', c.name), node('span', label), node('p', c.detail + (c.value == null ? '' : ` Valeur : ${fmt(c.value)}.`)));
    $('checks').append(row);
  }
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
      $('submit').textContent = mode() === 'evaluate' ? 'Vérifier le salaire →' : 'Obtenir une proposition →';
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
(async () => {
  try {
    const response = await fetch('/api/metadata');
    if (!response.ok) throw new Error('Impossible de charger les références.');
    meta = await response.json();
    $('job').replaceChildren(new Option('Choisir un métier', ''));
    for (const job of Object.keys(meta.jobs)) $('job').append(new Option(job, job));
    $('job').disabled = false; $('submit').disabled = false;
    for (const label of document.querySelectorAll('.unit-label')) label.textContent = meta.unit;
    $('source-note').textContent = `${fmt(meta.employees)} salaires de référence · Montants en ${meta.unit} · Redémarrer l’application après modification des sources.`;
  } catch (error) {
    $('form-error').textContent = error.message; $('form-error').hidden = false;
    $('source-note').textContent = 'Références indisponibles. Vérifiez le serveur local.';
  }
})();
