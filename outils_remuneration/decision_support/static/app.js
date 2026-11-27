'use strict';
const $ = id => document.getElementById(id);
const form = $('profile-form');
let meta, revision = 0, controller = null;
// La vue par salarié (depuis le 23/11/2026). Tant qu'aucun matricule n'est cherché, les trois restent
// vides et la page marche comme avant : un profil saisi à la main, un salaire prédit.
// - salarie : ce que le serveur sait du salarié trouvé (profil, salaire réel, détection) ;
// - vrai : son vrai profil, case par case, pour repérer les cases modifiées ;
// - preditVrai : le salaire prédit pour ce vrai profil. C'est la « situation actuelle » : elle est gardée
//   pour rester affichée à côté de la « situation cible », le profil une fois les cases modifiées.
let salarie = null, vrai = null, preditVrai = null;
const fmt = value => value == null ? 'Indisponible' : new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 2}).format(value);
// Un écart s'écrit avec son signe : « +20,7 » ou « −62,77 ».
const signe = value => (value > 0 ? '+' : value < 0 ? '−' : '') + fmt(Math.abs(value));
const node = (tag, text, cls) => { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; return e; };
// Les cases du profil : tout ce qui porte un nom dans le formulaire.
const champs = () => [...form.elements].filter(e => e.name);
function resetResult() {
  revision++;
  if (controller) controller.abort();
  $('result').hidden = true;
  $('empty').hidden = false;
  $('form-error').hidden = true;
  $('result-area').setAttribute('aria-busy', 'false');
}
// Les champs du profil, décrits par le serveur (ce que lit le modèle du salaire prédit) : une liste de
// choix pour une catégorie, un nombre borné pour le reste. Ils sont tous obligatoires : sans l'un
// d'eux, le modèle ne peut pas prédire, et la page n'aurait rien à montrer.
// Ils s'ajoutent à la suite du métier, du niveau et de l'ancienneté, sur la même ligne.
function renderModelFields(fields) {
  const box = $('profile-fields');
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
    // « was » : la place de la vraie valeur du salarié, écrite sous la case quand on la modifie.
    label.append(input, node('span', '', 'was'));
    box.append(label);
  }
}
function updateNiveaux() {
  $('niveau').replaceChildren(new Option('Choisir un niveau', ''));
  for (const niveau of meta.jobs[$('job').value] || []) $('niveau').append(new Option(niveau, niveau));
  $('niveau').disabled = !$('job').value;
}
// Dit si une case a encore la vraie valeur du salarié. Un nombre se compare en nombre : « 5 » et
// « 5.0 » sont la même ancienneté.
function pareil(champ, valeur) {
  if (valeur == null || valeur === '') return champ.value === '';
  return champ.type === 'number' ? champ.value !== '' && Number(champ.value) === Number(valeur) : champ.value === String(valeur);
}
// Passe en jaune les cases modifiées par rapport au vrai profil, écrit la vraie valeur dessous, et
// rend leur nombre. Sans salarié cherché, rien n'est « modifié » : il n'y a pas de vrai profil.
function marquer() {
  let nombre = 0;
  for (const champ of champs()) {
    const label = champ.closest('.field'), change = !!vrai && !pareil(champ, vrai[champ.name]);
    label.classList.toggle('changed', change);
    const valeur = vrai && vrai[champ.name];
    label.querySelector('.was').textContent = !change ? '' : `Actuel : ${ecrit(champ, valeur)}`;
    nombre += change;
  }
  $('restore').hidden = $('profile-foot').hidden = !nombre;
  $('changed-note').textContent = !nombre ? ''
    : `${nombre} ${nombre > 1 ? 'cases modifiées' : 'case modifiée'}, en jaune : c’est la situation cible. La valeur actuelle reste écrite dessous.`;
  // Avec un salarié cherché, le titre du profil dit à quoi sert de modifier une case.
  $('profile-hint').textContent = vrai ? 'Modifier une case pour construire la situation cible : le salaire prédit se refait dès qu’elle est validée'
    : 'Le salaire prédit se refait dès qu’une case est validée';
  return nombre;
}
// Écrit la valeur d'une case comme on la lit : un nombre avec sa virgule, « vide » s'il n'y a rien.
function ecrit(champ, valeur) {
  return valeur == null || valeur === '' ? 'vide' : champ.type === 'number' ? fmt(Number(valeur)) : valeur;
}
// Remet dans le formulaire le profil reçu du serveur. Le métier d'abord : c'est lui qui donne la
// liste des niveaux.
function remplir(profil) {
  $('job').value = profil.job_family;
  updateNiveaux();
  for (const champ of champs()) {
    if (champ.name !== 'job_family') champ.value = profil[champ.name] == null ? '' : profil[champ.name];
  }
}
// Dès qu'on touche une case : les cases modifiées sont remarquées, et le résultat affiché, qui est
// encore celui d'avant, pâlit. Le calcul repart quand la case est validée (événement change), si tout
// le profil est rempli. Pourquoi pas à chaque touche : « 12 » passerait par « 1 », une ancienneté
// qu'on n'a pas voulue.
form.addEventListener('input', () => {
  marquer();
  $('form-error').hidden = true;
  $('result').classList.add('stale');
});
form.addEventListener('change', event => {
  if (event.target === $('job')) { updateNiveaux(); marquer(); }
  if (form.checkValidity()) calculer(); else resetResult();
});
const at = (el, name, value) => { el.style.setProperty(name, value + '%'); return el; };
// La figure : une seule ligne. La grille du poste (du Min au Max), et dessus le salaire prédit avec
// la fourchette où tombent 9 salariés sur 10 qui ont ce profil. Pourquoi une seule ligne : avec une ligne par
// repère (grille, marché, collègues, proposition), la figure portait une dizaine de montants.
// Avec un salarié, deux repères de plus : un trait pour son salaire réel et, si des cases sont
// modifiées, un rond vide pour le salaire prédit de son vrai profil.
// Pourquoi style.setProperty : la CSP interdit les attributs style, pas le CSSOM.
// propose : le salaire proposé (la recommandation), dessiné par un losange quand il n'est pas au même
// endroit que le salaire prédit. Son montant est écrit dans le bloc « Recommandation », pas ici : la
// figure porte déjà assez de chiffres.
function renderRuler(band, r, reel, avant, propose) {
  const ruler = $('ruler'); ruler.replaceChildren();
  $('ruler-card').hidden = !band;
  if (!band) return;
  if (propose != null && propose === r.predicted) propose = null;
  $('key-proposed').hidden = propose == null;
  const values = [band.Min, band.Max, r.low, r.high, reel, avant, propose].filter(v => v != null);
  let lo = Math.min(...values), hi = Math.max(...values);
  // Un peu de marge de chaque côté, pour que la grille ne colle pas aux bords.
  const pad = (hi - lo) * .04 || 1;
  lo -= pad; hi += pad;
  const pos = v => (v - lo) / (hi - lo) * 100;
  const value = (v, cls, text) => at(node('span', text || fmt(v), 'val ' + cls), '--x', pos(v));
  const track = node('div', '', 'track' + (reel != null ? ' with-real' : ''));
  track.append(at(at(node('span', '', 'bar band'), '--a', pos(band.Min)), '--b', pos(band.Max)),
    value(band.Min, 'below from', `Min ${fmt(band.Min)}`), value(band.Max, 'below upto', `Max ${fmt(band.Max)}`));
  if (r.predicted != null) {
    // Les deux bouts de la fourchette s'écrivent vers l'extérieur, pour laisser la place au salaire
    // prédit, écrit au-dessus du point. Près d'un bord, ils reviennent vers l'intérieur.
    track.append(at(at(node('span', '', 'bar range'), '--a', pos(r.low)), '--b', pos(r.high)));
    if (avant != null) track.append(at(node('span', '', 'pip before'), '--x', pos(avant)));
    track.append(at(node('span', '', 'pip target'), '--x', pos(r.predicted)),
      value(r.low, 'ends ' + (pos(r.low) < 12 ? 'from' : 'upto')), value(r.high, 'ends ' + (pos(r.high) > 88 ? 'upto' : 'from')),
      value(r.predicted, 'top'));
  }
  if (propose != null) track.append(at(node('span', '', 'pip proposed'), '--x', pos(propose)));
  if (reel != null) {
    // Le salaire réel s'écrit sous son trait, centré ; près d'un bord, il part vers l'intérieur.
    const x = pos(reel);
    track.append(at(node('span', '', 'tick'), '--x', x), value(reel, 'real ' + (x < 12 ? 'from' : x > 88 ? 'upto' : 'mid'), `Salaire réel ${fmt(reel)}`));
  }
  $('key-target').hidden = $('key-range').hidden = r.predicted == null;
  $('key-before').hidden = r.predicted == null || avant == null;
  $('key-real').hidden = reel == null;
  ruler.append(track);
}
// Remplit une petite liste « nom : valeur » sous un grand chiffre, et la cache s'il n'y a rien à écrire.
function lister(liste, lignes) {
  liste.replaceChildren(...lignes.map(([nom, valeur]) => { const d = node('div', ''); d.append(node('dt', nom), node('dd', valeur)); return d; }));
  liste.hidden = !lignes.length;
}
// Le profil en une ligne : métier, niveau, ancienneté.
const ligneProfil = p => [`${p.job_family} · Niveau ${p.niveau}`,
  p.seniority == null || p.seniority === '' ? null : `${fmt(Number(p.seniority))} ${p.seniority < 2 ? 'an' : 'ans'} d’ancienneté`].filter(Boolean).join(' · ');
// La phrase sous un salaire prédit : sa fourchette habituelle et, s'il manque une information, laquelle.
// Sans salaire prédit, la phrase dit pourquoi.
const notePredit = r => r.predicted != null ? `Fourchette habituelle pour ce profil : entre ${fmt(r.low)} et ${fmt(r.high)}.`
    // Le niveau d'études non déterminé est signalé : le modèle ne met rien à sa place.
    + (r.education_unknown ? ' Niveau d’études non déterminé : le salaire est prédit sans cette information.' : '')
    // La performance N-1 inconnue aussi, pour la même raison.
    + (r.performance_unknown ? ' Performance N-1 inconnue : le salaire est prédit sans cette information.' : '')
  : !r.available ? 'Le modèle n’a pas pu apprendre sur les fichiers chargés.'
  : r.missing.length ? `À renseigner : ${r.missing.join(', ')}.`
  : 'Pas de grille ou de marché exploitable pour ce métier et ce niveau.';
// Le salaire réel du salarié face à un salaire prédit : l'écart en montant et en pourcentage.
const reelFace = predit => { const ecart = salarie.salary - predit; return `${signe(ecart)} (${signe(ecart / predit * 100)} %)`; };
// La situation actuelle (bloc de gauche, avec un salarié cherché) : son profil du fichier, le salaire
// prédit pour ce profil, et son salaire réel en face. Elle ne bouge pas quand on modifie une case.
function renderActuelle() {
  const r = preditVrai;
  $('actuelle-profile').textContent = ligneProfil(salarie.profile);
  $('actuelle-predicted').textContent = r && r.predicted != null ? fmt(r.predicted) : '—';
  // Sans salaire prédit gardé : le fichier ne donne pas tout le profil de ce salarié, le modèle n'a pas pu prédire.
  $('actuelle-note').textContent = r ? notePredit(r) : 'Il manque des informations dans le fichier pour ce salarié : pas de salaire prédit pour sa situation actuelle.';
  const lignes = [['Salaire réel', fmt(salarie.salary)]];
  if (r && r.predicted != null) lignes.push(['Salaire réel par rapport au salaire prédit', reelFace(r.predicted)]);
  lister($('actuelle-compare'), lignes);
}
// Sous le grand chiffre de la situation cible : ce qui change par rapport à la situation actuelle (une
// ligne par case modifiée), l'effet sur le salaire prédit, puis le salaire réel en face du nouveau
// salaire prédit.
// Pourquoi un seul effet pour toutes les cases, et pas un par case : les effets ne s'additionnent
// pas. Changer l'ancienneté ne pèse pas pareil selon la performance choisie à côté.
function renderCible(r) {
  const lignes = champs().filter(c => !pareil(c, vrai[c.name])).map(c =>
    [c.closest('.field').querySelector('.field-name').textContent, `${ecrit(c, vrai[c.name])} → ${ecrit(c, c.value)}`]);
  const avant = preditVrai && preditVrai.predicted;
  if (r.predicted != null) {
    if (avant != null) lignes.push(['Salaire prédit par rapport à la situation actuelle', `${signe(r.predicted - avant)} (${signe((r.predicted - avant) / avant * 100)} %)`]);
    lignes.push(['Salaire réel par rapport au salaire prédit', reelFace(r.predicted)]);
  }
  lister($('compare'), lignes);
}
// Les repères pour décider (depuis le 26/11/2026). Le bloc ne décide rien : il met sous les yeux de
// quoi décider, pour une embauche ou une revalorisation étudiée au cas par cas.
// Le salaire proposé est calculé par le serveur (_recommandation dans engine.py). Il part du salaire
// prédit et passe par des garde-fous : le Max de la grille, puis les planchers (Min de la grille,
// seuils de la détection, salaire actuel). Ce bloc écrit le chiffre, sa marge, le tableau qui situe le
// salaire actuel et le salaire proposé dans chaque repère. Pas de phrases sur la façon dont le chiffre
// est construit : elles n'aidaient pas à décider (retirées le 26/11/2026). Le calcul est expliqué dans
// le README de ce dossier.
function renderReco(data, modifiees) {
  const reco = data.recommendation, {band, market, peers, regression: r} = data;
  $('reco').hidden = !reco;
  if (!reco) return;
  const p = reco.proposed;
  const c = reco.current;
  $('reco-kind').textContent = c == null ? 'Nouvelle recrue, ou profil saisi à la main' : 'Salarié du fichier : la décision reste à prendre au cas par cas';
  $('proposed').textContent = fmt(p);
  $('proposed-note').textContent = reco.minimum === reco.maximum ? '' : `Marge : de ${fmt(reco.minimum)} à ${fmt(reco.maximum)}.`;
  // Sous le chiffre, pour un salarié : le rappel des deux situations (salaire actuel, salaire prédit de
  // la situation actuelle, et celui de la situation cible si des cases sont modifiées), puis l'écart
  // entre le salaire proposé et le salaire actuel.
  const lignes = [];
  if (c != null) {
    const avant = preditVrai && preditVrai.predicted;
    lignes.push(['Salaire actuel', fmt(c)]);
    if (avant != null) lignes.push(['Salaire prédit, situation actuelle', fmt(avant)]);
    if (modifiees && r.predicted != null) lignes.push(['Salaire prédit, situation cible', fmt(r.predicted)]);
    lignes.push(['Salaire proposé par rapport au salaire actuel', p > c ? `${signe(p - c)} (${signe((p - c) / c * 100)} %)` : 'Aucun écart']);
  }
  lister($('reco-compare'), lignes);
  // Le tableau des repères : une ligne par repère (grille, marché, collègues, profil), et pour chacun
  // où se situent le salaire actuel (pour un salarié) et le salaire proposé. Avec un profil modifié
  // (une mobilité), le salaire actuel est situé dans le NOUVEAU poste : on voit où il le placerait.
  const montants = c == null ? [p] : [c, p];
  const ecart = (m, ref) => `${signe((m / ref - 1) * 100)} %`;
  const reperes = [['Grille du poste', `Min ${fmt(band.Min)} · milieu ${fmt(band.Mid)} · Max ${fmt(band.Max)}`,
    ...montants.map(m => `${fmt(m / band.Mid)} du milieu`)]];
  if (market) reperes.push(['Marché', `Médiane ${fmt(market.Median)}`, ...montants.map(m => ecart(m, market.Median))]);
  reperes.push(peers.available
    ? [`Collègues comparables (${fmt(peers.count)})`,
      `${peers.scope[0].toUpperCase() + peers.scope.slice(1)} : de ${fmt(peers.min)} à ${fmt(peers.max)}, médiane ${fmt(peers.median)}, la moitié entre ${fmt(peers.q1)} et ${fmt(peers.q3)}`,
      ...(c == null ? ['proposed'] : ['current', 'proposed']).map(nom => `Mieux payé que ${fmt(Math.round(peers.below[nom]))} % d’entre eux`)]
    : ['Collègues comparables', `Moins de ${fmt(meta.minimum_peers)} collègues comparables : pas de comparaison`, ...montants.map(() => '—')]);
  reperes.push(['Profil (modèle)', `Salaire habituel ${fmt(r.predicted)}, fourchette de ${fmt(r.low)} à ${fmt(r.high)}`,
    ...montants.map(m => ecart(m, r.predicted))]);
  const rangee = (cases, tag) => { const tr = document.createElement('tr'); tr.append(...cases.map(t => node(tag, t))); return tr; };
  const tete = document.createElement('thead'), corps = document.createElement('tbody');
  tete.append(rangee(['Repère', 'Référence', ...(c == null ? [] : [`Salaire actuel (${fmt(c)})`]), `Salaire proposé (${fmt(p)})`], 'th'));
  corps.append(...reperes.map(l => rangee(l, 'td')));
  $('reco-stats').replaceChildren(tete, corps);
}
// Le résultat. Avec un salarié cherché (depuis le 27/11/2026), deux blocs côte à côte : à gauche la
// situation actuelle (son profil du fichier et le salaire prédit pour ce profil), à droite la situation
// cible (le profil une fois les cases modifiées et son salaire prédit), puis la figure et, en bas, la
// conclusion. Pourquoi deux blocs : avant, un seul grand chiffre changeait de sens dès qu'une case était
// modifiée, et le salaire prédit du vrai profil partait dans une petite ligne ; on ne savait plus ce
// qu'on lisait.
// Sans salarié cherché (profil saisi à la main), il n'y a pas de situation actuelle : un seul bloc, le
// salaire prédit, et la figure à côté.
function render(data, modifiees) {
  $('empty').hidden = true;
  $('result').hidden = false;
  $('result').classList.remove('stale');
  const {profile, band, regression: r} = data;
  // Tant qu'aucune case n'est modifiée, la situation cible n'existe pas encore : une phrase dit quoi faire.
  const cibleVide = !!salarie && !modifiees;
  $('sim').classList.toggle('deux', !!salarie);
  $('actuelle').hidden = $('cible-title').hidden = !salarie;
  $('cible-vide').hidden = !cibleVide;
  $('cible').hidden = cibleVide;
  if (salarie) renderActuelle();
  $('verdict').className = 'verdict' + (cibleVide || r.predicted == null ? ' insufficient' : '');
  $('result-profile').textContent = ligneProfil(profile);
  $('key-target-text').textContent = !salarie ? 'Salaire prédit' : modifiees ? 'Salaire prédit, situation cible' : 'Salaire prédit, situation actuelle';
  $('predicted').textContent = r.predicted == null ? '—' : fmt(r.predicted);
  $('predicted-note').textContent = notePredit(r);
  if (salarie) renderCible(r); else lister($('compare'), []);
  renderRuler(band, r, salarie ? salarie.salary : null, modifiees && preditVrai ? preditVrai.predicted : null,
    data.recommendation ? data.recommendation.proposed : null);
  renderReco(data, modifiees);
}
async function demander(adresse, corps, signal) {
  const response = await fetch(adresse, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corps), signal});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Le calcul a échoué.');
  return data;
}
// Demande le salaire prédit pour le profil du formulaire et l'affiche. Si le profil est exactement
// celui du salarié cherché, son salaire prédit est gardé (preditVrai) pour les comparaisons.
async function calculer() {
  if (!form.checkValidity()) return;
  revision++;
  if (controller) controller.abort();
  const requestRevision = revision, modifiees = marquer();
  controller = new AbortController();
  $('form-error').hidden = true;
  $('result-area').setAttribute('aria-busy', 'true');
  try {
    // Avec un salarié cherché, son matricule part avec le profil : le serveur retrouve son salaire actuel,
    // sous lequel la recommandation ne descend pas. Sans matricule, c'est une nouvelle recrue.
    const profil = {...Object.fromEntries(new FormData(form).entries()), ...(salarie ? {matricule: salarie.matricule} : {})};
    const data = await demander('/api/analyze', profil, controller.signal);
    if (requestRevision !== revision) return;
    if (salarie && !modifiees) preditVrai = data.regression;
    render(data, modifiees);
  } catch (error) {
    if (error.name !== 'AbortError' && requestRevision === revision) {
      $('form-error').textContent = error.message; $('form-error').hidden = false;
    }
  } finally {
    if (requestRevision === revision) $('result-area').setAttribute('aria-busy', 'false');
  }
}
// Pas de bouton pour lancer le calcul (retiré le 24/11/2026) : il part tout seul quand une case est
// validée (voir plus haut). La touche Entrée dans une case ne doit donc pas envoyer le formulaire.
form.addEventListener('submit', event => event.preventDefault());
// Le bloc « Ce salarié aujourd'hui » : ce que le fichier et la détection disent de lui. Il ne bouge pas
// pendant la simulation.
const BADGES = {Critical: 'critical', Major: 'major', Minor: 'minor', Info: 'info', 'Outlier positif': 'outlier'};
function renderToday(s) {
  const d = s.detection;
  $('today').hidden = false;
  // Le nom du salarié, en simple texte au-dessus de son profil. Rien si le fichier ne le donne pas.
  $('profile-name').textContent = s.nom || '';
  $('profile-name').hidden = !s.nom;
  $('today-id').textContent = [s.matricule, s.profile.job_family, `Niveau ${s.profile.niveau}`, s.entite].filter(Boolean).join(' · ') + ' — ne change pas pendant la simulation';
  $('today-salary').textContent = fmt(s.salary);
  $('today-compa').textContent = s.compa == null ? '—' : fmt(s.compa);
  $('today-compa-note').textContent = s.mid == null ? 'Pas de grille pour ce métier et ce niveau.' : `Salaire ÷ milieu de la grille (${fmt(s.mid)})`;
  $('today-severity').className = 'badge ' + (d ? BADGES[d.severity] || 'info' : 'none');
  $('today-severity').textContent = d ? d.label : s.detection_loading ? 'En cours de chargement' : 'Indisponible';
  $('today-score').textContent = d ? (d.score == null ? '' : `Score de ${fmt(d.score)} sur 100`)
    : s.detection_loading ? 'La détection finit de se charger : rechercher à nouveau dans quelques secondes.'
    : 'Pas de résultat de la détection pour ce matricule : la relancer.';
  $('today-reco').textContent = d && d.reco ? d.reco : d ? 'Aucune' : '—';
  $('today-cost').textContent = d && d.cost != null ? `Coût : ${fmt(d.cost)} ${meta.unit}` : '';
  // Le titre de la dernière case dépend du résultat. Un salarié « Info » ou payé au-dessus du Max ne
  // remonte pas : la détection ne demande rien pour lui. La case dit alors seulement ce qu'elle a relevé.
  $('today-why').textContent = d && ['Critical', 'Major', 'Minor'].includes(d.severity)
    ? 'Pourquoi la détection le fait remonter' : 'Ce que la détection a relevé';
  // Sans raison écrite par la détection : une phrase qui dit pourquoi il n'y en a pas.
  const raisons = !d ? [] : d.reasons.length ? d.reasons
    : d.severity === 'Outlier positif' ? ['Payé au-dessus du Max de sa grille : ce n’est pas une anomalie.']
    : ['Rien à signaler.'];
  $('today-reasons').replaceChildren(...raisons.map(r => node('li', r)));
  $('today-peers').textContent = d && d.peers != null && d.peer_median != null
    ? `${fmt(d.peers)} collègues comparables, médiane de leurs salaires : ${fmt(d.peer_median)}` : '';
}
// « Chercher » : retrouve le salarié, remplit le formulaire avec son vrai profil, puis calcule son
// salaire prédit.
$('lookup-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('lookup-error').hidden = true;
  $('lookup').disabled = true;
  try {
    const s = await demander('/api/salarie', {matricule: $('matricule').value});
    // Un métier absent de la grille n'est pas dans la liste : on ne peut pas remplir le formulaire.
    if (!(s.profile.job_family in meta.jobs)) throw new Error(`Pas de grille pour le métier de ce salarié (${s.profile.job_family}).`);
    salarie = s; preditVrai = null;
    remplir(s.profile);
    // Le vrai profil est relu dans le formulaire : il est ainsi écrit comme les cases l'écrivent.
    vrai = Object.fromEntries(champs().map(c => [c.name, c.value]));
    renderToday(s);
    marquer();
    resetResult();
    if (form.checkValidity()) await calculer();
    else { $('form-error').textContent = 'Il manque des informations dans le fichier pour ce salarié : remplir les cases vides.'; $('form-error').hidden = false; }
  } catch (error) {
    $('lookup-error').textContent = error.message; $('lookup-error').hidden = false;
  } finally {
    $('lookup').disabled = false;
  }
});
// Les propositions pendant la frappe : à chaque lettre tapée dans « Matricule », le serveur renvoie les
// matricules qui contiennent ce texte (8 au plus) et le navigateur les affiche sous la case.
// Pourquoi demander au serveur à chaque lettre plutôt que charger tous les matricules à l'ouverture :
// avec des milliers de salariés, la liste déroulante du navigateur serait lente et sans fin.
let derniereFrappe = 0;
$('matricule').addEventListener('input', async event => {
  // Choisir une proposition dans la liste lance la recherche tout de suite, sans cliquer sur « Chercher ».
  // Le navigateur signale ce choix par « insertReplacementText » (ou par un événement sans type de frappe).
  if (!(event instanceof InputEvent) || event.inputType === 'insertReplacementText') {
    if (!$('lookup').disabled) $('lookup-form').requestSubmit();
    return;
  }
  // Pourquoi numéroter les frappes : si la réponse à « Mat0 » arrive après celle à « Mat00 », on l'ignore.
  const frappe = ++derniereFrappe;
  try {
    const reponse = await demander('/api/matricules', {texte: $('matricule').value || ' '});
    if (frappe === derniereFrappe) $('matricules').replaceChildren(...reponse.matricules.map(m => new Option(m, m)));
  } catch (error) {
    // Pas de proposition si le serveur ne répond pas : la recherche par « Chercher » dira ce qui ne va pas.
  }
});
// « Revenir à la situation actuelle » : toutes les cases reprennent les valeurs du salarié.
$('restore').addEventListener('click', () => { remplir(vrai); marquer(); if (form.checkValidity()) calculer(); else resetResult(); });
// « Nouvelle recrue (profil vide) » : on quitte le salarié, pour saisir un profil à la main. La
// recommandation se fait alors sans salaire actuel.
$('blank').addEventListener('click', () => {
  salarie = vrai = preditVrai = null;
  $('lookup-form').reset(); form.reset();
  if (meta) updateNiveaux();
  $('today').hidden = $('profile-name').hidden = true; $('lookup-error').hidden = true;
  marquer(); resetResult();
  $('job').focus();
});
(async () => {
  try {
    const response = await fetch('/api/metadata');
    if (!response.ok) throw new Error('Impossible de charger les références.');
    meta = await response.json();
    $('job').replaceChildren(new Option('Choisir un métier', ''));
    for (const job of Object.keys(meta.jobs)) $('job').append(new Option(job, job));
    $('job').disabled = false; $('lookup').disabled = false;
    renderModelFields(meta.fields || []);
    for (const label of document.querySelectorAll('.unit-label')) label.textContent = meta.unit;
    $('employees-count').textContent = `${fmt(meta.employees)} salaires`;
  } catch (error) {
    $('form-error').textContent = error.message; $('form-error').hidden = false;
    $('source-note').textContent = 'Références indisponibles. Vérifiez le serveur local.'; $('source-note').hidden = false;
  }
})();
