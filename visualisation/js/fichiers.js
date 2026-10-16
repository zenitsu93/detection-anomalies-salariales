// Lecture des trois fichiers Excel, et mémoire du navigateur (le dossier choisi, les dernières données lues).
(function (E) {
  'use strict';
  const FICHIERS = ['employes.xlsx', 'bands.xlsx', 'market.xlsx'];

  // ---------- Mémoire du navigateur (IndexedDB) ----------
  // Sans elle (navigation privée, mémoire bloquée), la page marche quand même : il faut juste rechoisir le dossier.

  function base() {
    return new Promise((ok, ko) => {
      const r = indexedDB.open('exploration-salaires', 1);
      r.onupgradeneeded = () => r.result.createObjectStore('etat');
      r.onsuccess = () => ok(r.result);
      r.onerror = () => ko(r.error);
    });
  }

  async function lire(cle) {
    try {
      const db = await base();
      return await new Promise(ok => { const r = db.transaction('etat').objectStore('etat').get(cle); r.onsuccess = () => ok(r.result); r.onerror = () => ok(undefined); });
    } catch { return undefined; }
  }

  async function ecrire(cle, valeur) {
    try { const db = await base(); db.transaction('etat', 'readwrite').objectStore('etat').put(valeur, cle); } catch { /* sans mémoire */ }
  }

  // ---------- Fichiers Excel ----------

  async function lireExcel(fichier) {
    const classeur = XLSX.read(await fichier.arrayBuffer(), { type: 'array' });
    return XLSX.utils.sheet_to_json(classeur.Sheets[classeur.SheetNames[0]], { defval: null });
  }

  // parNom : { 'employes.xlsx': File, ... } ; ou : texte qui dit où on a cherché, pour le message d'erreur.
  async function lireTables(parNom, ou) {
    const manquants = FICHIERS.filter(f => !parNom[f]);
    if (manquants.length) throw new Error(`Fichier introuvable dans ${ou} : ${manquants.join(', ')}. Les trois fichiers doivent s'appeler exactement employes.xlsx, bands.xlsx et market.xlsx.`);
    const [employes, bands, market] = await Promise.all(FICHIERS.map(f => lireExcel(parNom[f])));
    return { employes, bands, market };
  }

  // Les trois fichiers d'un dossier choisi avec showDirectoryPicker (Edge, Chrome).
  async function depuisDossier(dossier) {
    const parNom = {};
    for await (const [nom, h] of dossier.entries()) {
      if (h.kind === 'file' && FICHIERS.includes(nom.toLowerCase())) parNom[nom.toLowerCase()] = await h.getFile();
    }
    return { tables: await lireTables(parNom, `le dossier « ${dossier.name} »`), source: `dossier « ${dossier.name} »` };
  }

  // Les trois fichiers choisis un par un (tous les navigateurs).
  async function depuisListe(fichiers) {
    const parNom = {};
    for (const f of fichiers) parNom[f.name.toLowerCase()] = f;
    return { tables: await lireTables(parNom, 'les fichiers choisis'), source: 'fichiers choisis' };
  }

  E.fichiers = { lire, ecrire, depuisDossier, depuisListe };
})(window.Exploration = window.Exploration || {});
