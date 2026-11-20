// Lecture des trois fichiers Excel que l'utilisateur dépose dans la page ou choisit avec le bouton.
// Rien n'est gardé d'une ouverture à l'autre : le navigateur n'a aucune autorisation à demander.
// Une seule lecture se fait sans lui : celle des fichiers de input/, quand la page est lancée par lancer_interface.bat
// (voir parDefaut, plus bas).
(function (E) {
  'use strict';
  const FICHIERS = ['employes.xlsx', 'bands.xlsx', 'market.xlsx'];

  // Les fichiers reçus depuis l'ouverture de la page, par nom : un fichier du même nom remplace le précédent.
  const recus = {};

  // Garde les fichiers attendus et rend ce qu'il manque encore et ce qui a été ignoré (mauvais nom).
  function recevoir(fichiers) {
    const ignores = [];
    for (const f of fichiers) {
      const nom = f.name.toLowerCase();
      if (FICHIERS.includes(nom)) recus[nom] = f; else ignores.push(f.name);
    }
    return { recus: FICHIERS.filter(n => recus[n]), manquants: FICHIERS.filter(n => !recus[n]), ignores };
  }

  async function lireExcel(fichier) {
    const classeur = XLSX.read(await fichier.arrayBuffer(), { type: 'array' });
    return XLSX.utils.sheet_to_json(classeur.Sheets[classeur.SheetNames[0]], { defval: null });
  }

  // Les trois tables, une fois les trois fichiers reçus.
  async function tables() {
    const [employes, bands, market] = await Promise.all(FICHIERS.map(n => lireExcel(recus[n])));
    // La source affichée en haut de la page : « dossier input/ » tant que les trois fichiers sont ceux chargés
    // par défaut ; dès qu'on en dépose un à la main, « fichiers déposés ».
    const source = FICHIERS.every(n => recus[n].parDefaut) ? 'dossier input/' : 'fichiers déposés';
    return { tables: { employes, bands, market }, source };
  }

  // Les fichiers de input/, chargés tout seuls à l'ouverture de la page quand elle est lancée par
  // lancer_interface.bat : ce sont les mêmes que ceux de la détection et de l'aide à la décision.
  // Pourquoi seulement dans ce cas : le programme lancé par le .bat (decision_support/app.py) donne ces
  // fichiers à l'adresse /api/donnees/... Une page ouverte d'un double-clic (adresse en file:///) n'a pas
  // le droit de lire un fichier du PC toute seule : elle attend alors qu'on les dépose, comme avant.
  // Rend la liste des fichiers trouvés (vide s'il n'y en a pas ou si le programme ne répond pas).
  async function parDefaut() {
    if (!location.protocol.startsWith('http')) return [];
    const lus = await Promise.all(FICHIERS.map(async nom => {
      try {
        const reponse = await fetch('/api/donnees/' + nom);
        if (!reponse.ok) return null;
        const fichier = new File([await reponse.blob()], nom);
        fichier.parDefaut = true;
        return fichier;
      } catch (e) {
        return null;
      }
    }));
    return lus.filter(Boolean);
  }

  E.fichiers = { FICHIERS, recevoir, tables, parDefaut };
})(window.Exploration = window.Exploration || {});
