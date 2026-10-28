// Lecture des trois fichiers Excel que l'utilisateur dépose dans la page ou choisit avec le bouton.
// Rien n'est lu sans lui, et rien n'est gardé d'une ouverture à l'autre : le navigateur n'a aucune autorisation à demander.
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
    return { tables: { employes, bands, market }, source: 'fichiers déposés' };
  }

  E.fichiers = { FICHIERS, recevoir, tables };
})(window.Exploration = window.Exploration || {});
