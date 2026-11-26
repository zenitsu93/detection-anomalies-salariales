"""Le salaire prédit pour un profil, placé dans la grille de son poste, sans modifier les sources.

Depuis le 23/11/2026, le profil peut aussi être celui d'un salarié du fichier : on tape son matricule
(salarie, plus bas), la page se remplit, et chaque case modifiée refait le salaire prédit.

Depuis le 17/11/2026, l'application ne donne plus qu'un résultat : le salaire que le modèle prédit
pour le profil saisi, et la fourchette où tombent 9 salariés sur 10 qui ont ce profil. La grille, le marché
et les collègues ne sont plus que des repères à côté. Pourquoi : la fourchette et la cible tirées des
règles faisaient un deuxième résultat, à côté du salaire prédit ; la page montrait trop de chiffres.

Depuis le 26/11/2026, la page donne aussi un salaire PROPOSÉ (_recommandation, plus bas) : le salaire
prédit, passé par des garde-fous tirés de la grille, du marché, de la détection et du salaire actuel.
C'est le chiffre à proposer pour une embauche, ou pour une revalorisation après une mobilité."""

import math
from pathlib import Path
import re
import sys
import threading

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parent.parent
# Pourquoi : les fichiers de detection/ s'importent entre eux par leur seul nom (« from anomaly_pretraitement
# import ... ») ; Python doit donc aussi chercher dans ce dossier.
sys.path.insert(0, str(ROOT / "detection"))

from anomaly_pretraitement import ORDRE_PERFORMANCE, ajouter_diplomes, bucket_anciennete, rang_etude
# Le modèle du salaire prédit (M5) est écrit dans ce fichier-là : la détection et cette page lisent le même.
from anomaly_signal_regression import LOG_MID, VIDE_ACCEPTE, entrainer_m5, tableau_m5

# Même unité que les CSV : aucune conversion.
UNIT = "kMAD / an"
# Le périmètre d'un groupe de collègues, écrit en clair colonne par colonne.
SCOPE = {"Niveau": "même niveau", "Job_Family": "même métier", "Anciennete_Bucket": "ancienneté {} ans"}
# Les colonnes que le modèle calcule, et ce que la page demande à la place : on saisit « BAC+5 », pas
# son rang ; l'âge, pas l'âge à l'embauche.
SAISIE = {"Rang_Etude_Max": "Niveau_Etude_Max", "Age_Embauche": "Age", "Rang_Performance": "Performance_N1"}
# Les colonnes du modèle que la page ne demande pas dans « Profil de la personne » : le niveau et
# l'ancienneté sont déjà en haut du formulaire ; le ratio grille / marché et le Mid viennent de la
# grille et du marché du métier + niveau.
DEJA_CONNUES = {"Niveau", "Anciennete", "Ratio_Grille_Marche", LOG_MID}
# Le nom affiché de chaque champ du profil.
LABELS = {"Age": "Âge", "Competence_N1": "Compétence N-1", "Performance_N1": "Performance N-1",
          "Hot_job": "Hot job", "Niveau_Etude_Max": "Niveau d'études"}

# La vue par salarié (depuis le 23/11/2026) : on tape un matricule, la page se remplit avec son profil et
# montre ce que la détection dit de lui. Ces trois tables servent à écrire en clair ce que la détection
# a noté dans output/detection/anomalies.xlsx.
# Le nom affiché de chaque priorité : les mêmes mots que dans le tableau de bord.
PRIORITES = {"Critical": "Critique", "Major": "Majeure", "Minor": "Mineure", "Info": "Info (sans action)",
             "Outlier positif": "Outlier positif (au-dessus du Max)"}
# Les colonnes du fichier des salariés où se lit le nom de la personne (voir salarie()).
NOMS = {"nom", "prenom", "nomprenom", "nometprenom", "nomcomplet"}
# Les seules colonnes lues dans le fichier de la détection.
DETECTION = {"Matricule", "Severity", "RiskScore", "Reco", "Cout_Ajustement", "Reason_Principale", "Cohort_Size", "Cohort_Median"}
RECOS = {"Ajuster vers MID": "Ajuster vers le milieu de la grille", "Ajuster au MIN": "Ajuster au Min de la grille"}
# Les raisons courtes de la détection, et la phrase affichée à la place.
RAISONS = {"Sous la mediane marche": "Salaire sous la médiane du marché",
           "Salaire sous MIN interne": "Salaire sous le Min de sa grille"}


def raison_en_clair(texte):
    """Une raison écrite par la détection, récrite pour être lue sans connaître ses codes.
    Exemple : « CompaRatio=0.80 (<0.85) » devient « Position dans la grille de 0,80, sous le seuil de
    0,85 ». Une raison que cette fonction ne connaît pas est rendue telle quelle."""
    texte = str(texte).strip()
    if texte in RAISONS:
        return RAISONS[texte]
    ratio = re.fullmatch(r"CompaRatio=([\d.]+) \(<([\d.]+)\)", texte)
    if ratio:
        position, seuil = (v.replace(".", ",") for v in ratio.groups())
        return f"Position dans la grille de {position}, sous le seuil de {seuil}"
    if texte.startswith("Sous ses collegues"):
        return "Salaire très en dessous de ses collègues comparables"
    if texte.startswith("IA : "):
        # Pourquoi retirer la parenthèse des montants : le « salaire attendu » de la détection vient du
        # même modèle que cette page, mais d'un modèle qui n'a pas vu le salarié (pour qu'un salaire
        # anormal ne se cache pas). Il diffère donc un peu du salaire prédit affiché ici. Les deux côte à
        # côte feraient deux chiffres pour la même chose. On garde l'écart en %, en disant d'où il vient.
        texte = re.sub(r" \([^()]*kMAD[^()]*\)", "", texte[len("IA : "):])
        texte = texte.replace("salaire attendu pour son profil", "salaire attendu par la détection pour son profil")
        return texte[:1].upper() + texte[1:]
    return texte


def number(value, name, *, optional=False):
    if optional and (value is None or value == ""):
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} : saisir un nombre valide.") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} : valeur hors limites.")
    return result


def key(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


class DecisionEngine:
    def __init__(self, employees, bands, market, rules, detection=None):
        self.rules = dict(rules)
        # Ce que la détection dit de chaque salarié, rangé par matricule (voir lire_detection). Vide si la
        # détection n'a pas encore été lancée. detection_prete passe à False le temps de la lecture du
        # fichier en arrière-plan (voir from_project).
        self.detection, self.detection_prete = {}, True
        self.lire_detection(detection)
        # Mêmes valeurs par défaut que src/anomaly_cohortes.py.
        self.minimum_peers = int(self.rules.get("cohort_min_size", 15))
        if self.minimum_peers < 2:
            raise ValueError("cohort_min_size doit être au moins égal à 2.")
        self.steps = self.rules.get("cohort_widening_steps",
                                    ["Niveau|Job_Family|Anciennete_Bucket", "Niveau|Job_Family", "Niveau"])
        keys = ["Job_Family", "Niveau"]
        self.employees = self._prepare(employees, keys + ["Fixe_Annuel_MAD"], "Employés")
        # Pourquoi drop_duplicates : un métier + niveau en double garde sa première ligne, comme dans
        # src/anomaly_pretraitement.py.
        self.bands = self._prepare(bands, keys + ["Min", "Mid", "Max"], "Grille").drop_duplicates(keys)
        self.market = (self._prepare(market, keys + ["Median"], "Marché").drop_duplicates(keys)
                       if market is not None else None)
        if "Matricule" in self.employees:
            # Pourquoi : un matricule en double garde lui aussi sa première ligne.
            self.employees = self.employees.drop_duplicates(subset="Matricule")
        pay = pd.to_numeric(self.employees.Fixe_Annuel_MAD, errors="coerce")
        # Un salaire illisible, nul ou négatif n'est pas comparé.
        valid = np.isfinite(pay) & pay.gt(0)
        self.employees = self.employees.loc[valid].copy()
        self.employees["Fixe_Annuel_MAD"] = pay.loc[valid]
        # Pourquoi ce nom de colonne : c'est celui des groupes de collègues (cohort_widening_steps).
        self.employees["Anciennete_Bucket"] = (self.employees.Anciennete.map(bucket_anciennete)
                                               if "Anciennete" in self.employees else "NA")
        # Le modèle du salaire prédit, appris au démarrage sur les mêmes salariés : la façon de faire du
        # modèle M5 de notebooks/Prediction_Compa_Ratio.ipynb (voir _train_regression).
        self.regression, self.regression_base = self._train_regression()
        self.fields = self._model_fields()

    def lire_detection(self, detection):
        """Range le tableau de la détection par matricule, en majuscules, pour que « mat00045 » trouve
        « Mat00045 »."""
        if detection is not None and "Matricule" in detection:
            self.detection = {key(ligne["Matricule"]).upper(): ligne for ligne in detection.to_dict("records")}

    def _model_fields(self):
        """Les champs du profil à saisir : les colonnes que lit le modèle, sauf celles que
        la page connaît déjà (niveau, ancienneté) ou qu'elle calcule (le ratio grille / marché et le
        Mid, tirés de la grille et du marché du métier + niveau). Une colonne calculée se saisit par ce dont elle
        vient (SAISIE) : le niveau d'études (BAC+5...) pour son rang, la performance pour son rang,
        l'âge pour l'âge à l'embauche.
        Pour chaque champ : une liste de choix (les valeurs du fichier des salariés) pour un libellé, ou
        un nombre, borné par le plus petit et le plus grand du fichier. Pourquoi ces bornes : hors de
        ce que le modèle a vu, sa prédiction ne vaut plus grand-chose."""
        if self.regression is None:
            return []
        base, fields = self.regression_base, []
        for column in self.regression["colonnes"]:
            if column in DEJA_CONNUES:
                continue
            column = SAISIE.get(column, column)
            values = base[column].dropna()
            field = {"name": column, "label": LABELS.get(column, column)}
            if column == "Niveau_Etude_Max" or not pd.api.types.is_numeric_dtype(values):
                uniques = list(dict.fromkeys(values.tolist()))
                if column == "Niveau_Etude_Max":
                    rangs = dict(zip(uniques, rang_etude(pd.Series(uniques, dtype=object))))
                    uniques.sort(key=lambda v: (pd.isna(rangs[v]), 0 if pd.isna(rangs[v]) else rangs[v], str(v)))
                elif column == "Performance_N1" and set(map(str, uniques)) <= set(ORDRE_PERFORMANCE):
                    uniques.sort(key=lambda v: ORDRE_PERFORMANCE.index(str(v)))
                else:
                    uniques.sort(key=lambda v: (not isinstance(v, (int, float)), v if isinstance(v, (int, float)) else str(v)))
                # key : « 2 » et 2.0 désignent la même case, comme pour le métier et le niveau.
                options = {key(v): v for v in uniques}
                # Une case vide dans le fichier (un niveau d'études inconnu...) : la page peut aussi la
                # choisir. Elle reste alors vide pour le modèle, comme à l'apprentissage.
                if base[column].isna().any():
                    options["Inconnu"] = None
                field.update(kind="choice", options=options)
            else:
                entiers = bool((values % 1 == 0).all())
                field.update(kind="number", min=float(values.min()), max=float(values.max()), step=1 if entiers else 0.01)
            fields.append(field)
        return fields

    def _train_regression(self):
        """Le modèle du salaire prédit et le tableau sur lequel il a appris. Si le modèle ne peut pas
        apprendre (pas de grille...), pas de salaire prédit (None).

        Le modèle est M5, celui de notebooks/Prediction_Compa_Ratio.ipynb, retenu le 17/11/2026. Il est
        écrit une seule fois, dans detection/anomaly_signal_regression.py (entrainer_m5) : depuis le
        24/11/2026, la détection lit le même pour son salaire attendu. Ici, on lui prépare seulement le
        tableau des salariés, avec le Mid de leur grille et leur ratio grille / marché."""
        keys = ["Job_Family", "Niveau"]
        grille = self.bands[keys + ["Mid"]].assign(Mid=lambda t: pd.to_numeric(t.Mid, errors="coerce"))
        base = self.employees.merge(grille, on=keys, how="left")
        if self.market is not None:
            marche = self.market[keys + ["Median"]].assign(Median=lambda t: pd.to_numeric(t.Median, errors="coerce"))
            base = base.merge(marche, on=keys, how="left")
            base["Ratio_Grille_Marche"] = base.Mid / base.pop("Median").replace(0, np.nan)
        base = ajouter_diplomes(base)
        return entrainer_m5(base), base

    @staticmethod
    def _prepare(table, columns, label):
        missing = set(columns) - set(table.columns)
        if missing:
            raise ValueError(f"{label} : colonnes absentes : {', '.join(sorted(missing))}.")
        result = table.copy(deep=True)
        result["Job_Family"] = result.Job_Family.map(key)
        result["Niveau"] = result.Niveau.map(key)
        return result

    @classmethod
    def from_project(cls, root=ROOT):
        root = Path(root)
        rules = yaml.safe_load((root / "config" / "rules.yaml").read_text(encoding="utf-8"))["rules"]

        # Même lecture que src/anomaly_pretraitement.py : les fichiers d'entrée sont des fichiers Excel.
        def read(name):
            return pd.read_excel(root / "input" / name)

        market = read("market.xlsx") if (root / "input" / "market.xlsx").exists() else None
        engine = cls(read("employes.xlsx"), read("bands.xlsx"), market, rules)

        # Le résultat de la détection, pour la vue par salarié.
        # Pourquoi en arrière-plan : ce gros fichier Excel met une vingtaine de secondes à se lire. Lu
        # ici, il retarderait d'autant l'ouverture de l'interface. La page marche tout de suite ; pendant
        # ces secondes, elle dit seulement que la priorité se charge.
        # Pourquoi un try : ce fichier n'existe pas avant la première détection, et il peut être ouvert
        # dans Excel. La page dira alors que la priorité n'est pas disponible.
        def lire():
            try:
                engine.lire_detection(pd.read_excel(root / "output" / "detection" / "anomalies.xlsx", usecols=lambda c: c in DETECTION))
            except (OSError, ValueError):
                pass
            engine.detection_prete = True

        engine.detection_prete = False
        threading.Thread(target=lire, daemon=True).start()
        return engine

    def metadata(self):
        pairs = self.bands.loc[self.bands.Job_Family.ne("") & self.bands.Niveau.ne(""), ["Job_Family", "Niveau"]]
        jobs = {job: sorted(group.Niveau.unique().tolist()) for job, group in pairs.groupby("Job_Family")}
        fields = [{**f, "options": list(f["options"])} if f["kind"] == "choice" else f for f in self.fields]
        return {"jobs": jobs, "unit": UNIT, "minimum_peers": self.minimum_peers,
                "employees": len(self.employees), "fields": fields}

    def _reference(self, table, profile, columns):
        # Rend les montants de la grille ou du marché pour ce métier + niveau, ou None s'ils manquent ou
        # sont inutilisables (absents, nuls, négatifs, ou Min / Mid / Max dans le désordre).
        if table is None:
            return None
        rows = table.loc[(table.Job_Family == profile["job_family"]) & (table.Niveau == profile["niveau"]), columns]
        # Pourquoi une seule ligne : les doublons de métier + niveau sont déjà retirés.
        if rows.empty:
            return None
        result = {c: float(v) for c, v in pd.to_numeric(rows.iloc[0], errors="coerce").items()}
        if not all(math.isfinite(v) and v > 0 for v in result.values()):
            return None
        if columns == ["Min", "Mid", "Max"] and not result["Min"] <= result["Mid"] <= result["Max"]:
            return None
        return result

    def _peers(self, profile, montants=None):
        """Les collègues comparables du profil, et de quoi situer un salaire parmi eux.
        montants : des salaires à situer (le salaire actuel, le salaire proposé...). Pour chacun, below
        donne la part des collègues payés moins que lui, en % : 22 veut dire « mieux payé que 22 % d'entre
        eux ». Ajouté le 26/11/2026, pour la fiche de repères."""
        values = {"Job_Family": profile["job_family"], "Niveau": profile["niveau"],
                  "Anciennete_Bucket": None if profile["seniority"] is None else bucket_anciennete(profile["seniority"])}
        others = self.employees
        # Même choix que src/anomaly_cohortes.py : le groupe le plus précis qui compte au moins
        # cohort_min_size collègues. Un groupe qui dépend d'une information non saisie (l'ancienneté) est sauté.
        peers, scope = others.iloc[:0], "aucun groupe"
        for step in self.steps:
            columns = step.split("|")
            if any(values.get(c) is None for c in columns):
                continue
            peers = others
            for column in columns:
                peers = peers.loc[peers[column] == values[column]]
            scope = ", ".join(SCOPE[c].format(values[c]) for c in columns)
            if len(peers) >= self.minimum_peers:
                break
        if len(peers) < self.minimum_peers:
            return {"count": len(peers), "available": False, "scope": scope}
        salaires = peers.Fixe_Annuel_MAD
        # q1 et q3 : les deux montants entre lesquels se trouve la moitié des collègues (ceux du milieu).
        bas, q1, mediane, q3, haut = (round(float(v), 2) for v in salaires.quantile([0, 0.25, 0.5, 0.75, 1]))
        return {"count": len(peers), "available": True, "scope": scope, "median": mediane,
                "min": bas, "q1": q1, "q3": q3, "max": haut,
                "below": {nom: round(float((salaires < montant).mean()) * 100, 2)
                          for nom, montant in (montants or {}).items() if montant is not None}}

    def analyze(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Le profil doit être un objet.")
        job, niveau = key(payload.get("job_family", "")), key(payload.get("niveau", ""))
        if not job or not niveau:
            raise ValueError("Le métier et le niveau sont obligatoires.")
        seniority = number(payload.get("seniority"), "Ancienneté", optional=True)
        profile = {"job_family": job, "niveau": niveau, "seniority": seniority}
        inputs = self._read_inputs(payload)
        band = self._reference(self.bands, profile, ["Min", "Mid", "Max"])
        market = self._reference(self.market, profile, ["Median"])
        regression = self._regression(profile, band, market, inputs)
        # Avec un matricule, la page étudie un salarié du fichier : son salaire actuel compte dans la
        # recommandation (on ne propose pas moins). Sans matricule, c'est une nouvelle recrue.
        actuel = self._salaire_actuel(payload.get("matricule"))
        reco = self._recommandation(profile, band, market, regression, actuel)
        # Le salaire actuel et le salaire proposé sont situés parmi les collègues comparables du profil.
        peers = self._peers(profile, {"current": actuel, "proposed": reco["proposed"] if reco else None})
        return {"profile": profile, "unit": UNIT, "band": band, "market": market,
                "peers": peers, "regression": regression, "recommendation": reco}

    def _salaire_actuel(self, matricule):
        """Le salaire d'aujourd'hui du salarié étudié, ou None si la page n'a pas donné de matricule (une
        nouvelle recrue, un profil saisi à la main) ou si ce matricule n'est pas dans le fichier."""
        cle = key(matricule).upper() if matricule is not None else ""
        if not cle or "Matricule" not in self.regression_base:
            return None
        lignes = self.regression_base.loc[self.regression_base.Matricule.map(key).str.upper() == cle]
        return None if lignes.empty else float(lignes.iloc[0].Fixe_Annuel_MAD)

    def _recommandation(self, profile, band, market, regression, actuel):
        """Le salaire proposé pour ce profil (depuis le 26/11/2026). None s'il n'y a pas de salaire prédit.

        L'idée : on part du salaire prédit par le modèle (ce que la banque paie d'habitude à un tel
        profil), et on le fait passer par des garde-fous, pour ne pas proposer un salaire que la
        détection ferait remonter le lendemain :
        1. le plafond : le Max de la grille du poste. Au-dessus, le salaire sortirait de la grille ;
        2. les planchers. Le salaire proposé ne descend sous aucun d'eux :
           - le Min de la grille ;
           - le seuil de la règle « position dans la grille » (compa_ratio_low × Mid, 85 % du milieu) ;
           - le seuil de la règle « marché » (market_low × médiane du marché, 90 %) ;
           - le plancher du niveau (min_salary_by_niveau), s'il y en a un pour ce niveau ;
           - le seuil du signal de l'IA : ml_signal_z écarts habituels sous le salaire prédit ;
           - le salaire actuel, pour un salarié du fichier : on ne propose pas de baisse.
        Les planchers passent après le plafond : si un plancher est au-dessus du Max, c'est lui qui gagne.
        Pourquoi les seuils de la détection : c'est le lien entre les deux outils. Les règles et le
        signal de l'IA disent à partir de quand un salaire est trop bas ; la recommandation s'en sert
        pour ne jamais tomber dessous. Seule la règle « écart aux collègues » n'y est pas : elle demande
        tout le groupe de collègues, pas seulement un profil.

        Ce que rend le dictionnaire :
        - proposed : le salaire proposé ;
        - minimum, maximum : la marge autour. minimum est le plus haut des planchers ; maximum est le
          haut de la fourchette habituelle du profil, sans dépasser le Max de la grille ;
        - predicted : le salaire prédit, le point de départ ;
        - current : le salaire actuel du salarié, ou None pour une nouvelle recrue."""
        predit = regression.get("predicted")
        if predit is None or band is None:
            return None
        regles = self.rules
        planchers = [("min", band["Min"])]
        if regles.get("compa_ratio_low") is not None:
            planchers.append(("compa", float(regles["compa_ratio_low"]) * band["Mid"]))
        if market and regles.get("market_low") is not None:
            planchers.append(("market", float(regles["market_low"]) * market["Median"]))
        # Les niveaux du fichier de règles sont des nombres (5), ceux de la page du texte (« 5 »).
        par_niveau = {key(n): v for n, v in (regles.get("min_salary_by_niveau") or {}).items()}
        if profile["niveau"] in par_niveau:
            planchers.append(("level", float(par_niveau[profile["niveau"]])))
        # Le seuil du signal de l'IA. La détection le lève quand le salaire est ml_signal_z écarts
        # habituels sous le salaire attendu ; centre et echelle sont ceux du modèle (entrainer_m5).
        z = float(regles.get("ml_signal_z", 2.0))
        planchers.append(("signal", predit * math.exp(self.regression["centre"] - z * self.regression["echelle"])))
        if actuel is not None:
            planchers.append(("current", actuel))
        # Le nom de chaque plancher ne sert qu'à lire cette liste : seul le plus haut montant compte.
        plancher = max(montant for _, montant in planchers)
        propose = max(min(predit, band["Max"]), plancher)
        haut = max(min(regression["high"], band["Max"]), propose)
        return {"proposed": round(propose, 2), "minimum": round(plancher, 2), "maximum": round(haut, 2),
                "predicted": predit, "current": None if actuel is None else round(actuel, 2)}

    def matricules(self, texte, limite=8):
        """Les matricules à proposer pendant la frappe : ceux qui contiennent le texte tapé, sans tenir
        compte des majuscules. Ceux qui commencent par ce texte passent en premier, puis l'ordre
        alphabétique. Pourquoi « contiennent » : taper « 45 » suffit pour se voir proposer Mat00045.
        Pourquoi limite : la page n'affiche qu'une courte liste, inutile d'en envoyer des milliers."""
        cle = key(texte).upper()
        if not cle or "Matricule" not in self.regression_base:
            return {"matricules": []}
        tous = self.regression_base.Matricule.map(key)
        trouves = tous[tous.str.upper().str.contains(cle, regex=False)]
        trouves = sorted(trouves, key=lambda m: (not m.upper().startswith(cle), m))
        return {"matricules": trouves[:limite]}

    def salarie(self, matricule):
        """La vue par salarié : pour un matricule, son profil (de quoi remplir le formulaire de la page),
        son salaire réel, sa position dans la grille et ce que la détection dit de lui.
        Le salaire prédit n'est pas calculé ici : la page le demande ensuite avec ce profil, exactement
        comme pour un profil saisi à la main. Une case modifiée repasse donc par le même calcul."""
        cle = key(matricule).upper()
        if not cle:
            raise ValueError("Saisir un matricule.")
        base = self.regression_base
        if "Matricule" not in base:
            raise ValueError("Le fichier des salariés n'a pas de colonne Matricule.")
        lignes = base.loc[base.Matricule.map(key).str.upper() == cle]
        if lignes.empty:
            # Un salarié dont le salaire est illisible n'est pas gardé au démarrage : il n'est pas trouvé non plus.
            raise ValueError(f"Matricule introuvable : {key(matricule)}.")
        ligne = lignes.iloc[0]

        def nombre(valeur):
            valeur = pd.to_numeric(valeur, errors="coerce")
            return None if pd.isna(valeur) or not math.isfinite(valeur) else round(float(valeur), 2)

        profil = {"job_family": ligne.Job_Family, "niveau": ligne.Niveau, "seniority": nombre(ligne.get("Anciennete"))}
        for field in self.fields:
            valeur = ligne.get(field["name"])
            if field["kind"] == "choice":
                # Une case vide du fichier se choisit par « Inconnu », comme dans le formulaire.
                profil[field["name"]] = "Inconnu" if pd.isna(valeur) else key(valeur)
            else:
                valeur = nombre(valeur)
                # Pourquoi borner : l'arrondi à 2 chiffres peut faire dépasser d'un cheveu le plus grand
                # nombre du fichier, et le formulaire refuserait alors la valeur du salarié lui-même.
                profil[field["name"]] = None if valeur is None else min(max(valeur, field["min"]), field["max"])
        salaire = float(ligne.Fixe_Annuel_MAD)
        mid = nombre(ligne.get("Mid"))
        entite = ligne.get("Entite_N1")
        # Le nom et le prénom, pour les écrire au-dessus du profil. Pourquoi chercher plusieurs colonnes :
        # selon le fichier, ils sont dans une seule colonne (« Nom ») ou dans deux (« Nom », « Prénom »).
        # Les majuscules, les accents, les espaces et les « _ » ne comptent pas pour les reconnaître.
        # Une case vide ne donne rien : la page n'écrit alors pas de nom.
        nom = " ".join(key(ligne[c]) for c in base.columns
                       if str(c).lower().replace("é", "e").replace("_", "").replace(" ", "") in NOMS and not pd.isna(ligne[c]))
        return {"matricule": key(ligne.Matricule), "nom": nom or None,
                "entite": None if pd.isna(entite) else str(entite), "profile": profil,
                "salary": round(salaire, 2), "mid": mid, "compa": round(salaire / mid, 2) if mid else None,
                "detection": self._detection(cle), "detection_loading": not self.detection_prete}

    def _detection(self, cle):
        """Ce que la détection dit du salarié : sa priorité, son score, la recommandation et les raisons,
        écrites en clair. None si la détection n'a pas de ligne pour lui."""
        ligne = self.detection.get(cle)
        if ligne is None:
            return None

        def nombre(colonne):
            valeur = pd.to_numeric(ligne.get(colonne), errors="coerce")
            return None if pd.isna(valeur) or not math.isfinite(valeur) else round(float(valeur), 2)

        def texte(colonne):
            valeur = ligne.get(colonne)
            return None if valeur is None or pd.isna(valeur) else str(valeur).strip()

        priorite = texte("Severity")
        # Les raisons sont écrites à la suite, séparées par « & ».
        raisons = [raison_en_clair(r) for r in (texte("Reason_Principale") or "").split(" & ") if r.strip()]
        reco = texte("Reco")
        return {"severity": priorite, "label": PRIORITES.get(priorite, priorite), "score": nombre("RiskScore"),
                "reco": RECOS.get(reco, reco), "cost": nombre("Cout_Ajustement") or None, "reasons": raisons,
                "peers": nombre("Cohort_Size"), "peer_median": nombre("Cohort_Median")}

    def _read_inputs(self, payload):
        """Les champs du profil saisis dans la page, contrôlés : un choix doit être une valeur du
        fichier des salariés, un nombre doit rester entre ses bornes. Un champ vide est simplement
        absent : le résultat dit alors lesquels manquent pour le salaire prédit."""
        inputs = {}
        for field in self.fields:
            raw = payload.get(field["name"])
            if raw is None or str(raw).strip() == "":
                continue
            if field["kind"] == "choice":
                if key(raw) not in field["options"]:
                    raise ValueError(f"{field['label']} : valeur inconnue.")
                inputs[field["name"]] = field["options"][key(raw)]
            else:
                value = number(raw, field["label"])
                if not field["min"] <= value <= field["max"]:
                    raise ValueError(f"{field['label']} : saisir une valeur entre {field['min']:g} et {field['max']:g}.")
                inputs[field["name"]] = value
        return inputs

    def _regression(self, profile, band, market, inputs):
        # Le résultat de la page : le salaire que le modèle prédit pour le profil saisi, avec la grille et
        # le marché du métier + niveau choisis, et la fourchette où tombent 9 salariés sur 10 qui ont ce profil.
        # missing : les champs encore vides, que la page demande de remplir.
        # education_unknown : le niveau d'études du profil est non déterminé ; la page l'écrit sous le résultat.
        # performance_unknown : pareil pour la performance N-1, quand elle est inconnue.
        result = {"predicted": None, "low": None, "high": None, "missing": [], "education_unknown": False,
                  "performance_unknown": False, "available": self.regression is not None}
        if self.regression is None:
            return result
        missing = ([] if profile["seniority"] is not None else ["Ancienneté"]) + [
            f["label"] for f in self.fields if f["name"] not in inputs]
        if missing:
            return {**result, "missing": missing}
        ligne = pd.DataFrame([{"Niveau": profile["niveau"], "Mid": band["Mid"] if band else np.nan,
                               "Ratio_Grille_Marche": band["Mid"] / market["Median"] if band and market else np.nan,
                               "Anciennete": profile["seniority"], **inputs}])
        if "Niveau_Etude_Max" in ligne:
            ligne["Rang_Etude_Max"] = rang_etude(ligne["Niveau_Etude_Max"])
        # Les mêmes colonnes qu'à l'apprentissage, dans le même ordre. Un niveau d'études non déterminé ou
        # une performance inconnue restent vides (VIDE_ACCEPTE) : rien n'est mis à leur place, le modèle
        # prédit sans cette information, et la page le signale.
        X = tableau_m5(ligne)[self.regression["colonnes"]]
        vides = [c for c in VIDE_ACCEPTE if c in X and bool(X[c].isna().iloc[0])]
        result["education_unknown"] = "Rang_Etude_Max" in vides
        result["performance_unknown"] = "Rang_Performance" in vides
        # Pas de grille pour ce métier + niveau (ou pas de marché) : une case reste vide, pas de
        # prédiction. Pourquoi le vérifier ici : le gradient boosting accepte une case vide et
        # répondrait quand même.
        if not X.drop(columns=vides).notna().all(axis=1).iloc[0]:
            return result
        # Le modèle prédit le logarithme du salaire : on revient au salaire par l'exponentielle. La
        # fourchette se pose autour, en proportion.
        log_salaire = float(self.regression["modele"].predict(X)[0])
        bas, haut = self.regression["fourchette"]
        return {**result, "predicted": round(math.exp(log_salaire), 2),
                "low": round(math.exp(log_salaire + bas), 2), "high": round(math.exp(log_salaire + haut), 2)}
