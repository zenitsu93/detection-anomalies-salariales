"""Proposition salariale explicable, sur des références fixes, sans modifier les sources.

Pourquoi plus de mode « vérifier un salaire » : depuis le 09/11/2026, l'application ne sert qu'à
proposer une fourchette et une cible pour un profil. Les cinq règles servent encore, mais seulement à
vérifier que la cible proposée ne déclencherait elle-même aucune alerte (voir _proposal)."""

import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parent.parent
# Pourquoi : les fichiers de src/ s'importent entre eux par leur seul nom (« from anomaly_pretraitement
# import ... ») ; Python doit donc aussi chercher dans ce dossier.
sys.path.insert(0, str(ROOT / "src"))

from anomaly_pretraitement import ORDRE_9BOX, ORDRE_PERFORMANCE, ajouter_diplomes, bucket_anciennete, rang_etude
from anomaly_regles import apply_rulebook
from anomaly_signal_regression import COLONNES, entrainer, predire

# Même unité que les CSV : aucune conversion.
UNIT = "kMAD / an"
# Le périmètre d'un groupe de collègues, écrit en clair colonne par colonne.
SCOPE = {"Niveau": "même niveau", "Job_Family": "même métier", "Anciennete_Bucket": "ancienneté {} ans"}
# Les colonnes du modèle de régression que la page ne demande pas dans « Pour le salaire prédit » : le
# métier, le niveau et l'ancienneté sont déjà en haut du formulaire ; le Mid et le ratio grille / marché
# viennent de la grille et du marché du métier + niveau.
DEJA_CONNUES = {"Job_Family", "Niveau", "Anciennete", "Mid", "Ratio_Grille_Marche"}
# Le nom affiché de chaque champ du salaire prédit.
LABELS = {"Age": "Âge", "Competence_N1": "Compétence N-1", "Performance_N1": "Performance N-1",
          "Positionnement_9BOX": "Positionnement 9-Box", "Hot_job": "Hot job",
          "Niveau_Etude_Max": "Niveau d'études", "Cat_Ecole_Max": "Catégorie d'école"}


def number(value, name, *, optional=False, minimum=0, strict=False):
    if optional and (value is None or value == ""):
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} : saisir un nombre valide.") from None
    if not math.isfinite(result) or result < minimum or (strict and result == minimum):
        raise ValueError(f"{name} : valeur hors limites.")
    return result


def key(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


class DecisionEngine:
    def __init__(self, employees, bands, market, rules):
        self.rules = dict(rules)
        # Mêmes valeurs par défaut que src/anomaly_cohortes.py.
        self.minimum_peers = int(self.rules.get("cohort_min_size", 15))
        if self.minimum_peers < 2:
            raise ValueError("cohort_min_size doit être au moins égal à 2.")
        self.steps = self.rules.get("cohort_widening_steps",
                                    ["Niveau|Job_Family|Anciennete_Bucket", "Niveau|Job_Family", "Niveau"])
        for lo, hi, defaults in [("compa_ratio_low", "compa_ratio_high", (.85, 1.15)),
                                  ("market_low", "market_high", (.9, 1.2))]:
            low = number(self.rules.get(lo, defaults[0]), lo, strict=True)
            high = number(self.rules.get(hi, defaults[1]), hi, strict=True)
            if low >= high:
                raise ValueError(f"{lo} doit être inférieur à {hi}.")
            self.rules.update({lo: low, hi: high})
        self.peer_threshold = number(self.rules.get("peer_z_threshold_minor", 2),
                                     "peer_z_threshold_minor", strict=True)
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
        # Le modèle de src/anomaly_signal_regression.py, entraîné au démarrage sur les mêmes salariés
        # et de la même façon que lui : le repère affiché est celui de la ligne de commande.
        self.regression, self.regression_base = self._train_regression()
        self.fields = self._model_fields()

    def _model_fields(self):
        """Les champs à saisir pour le salaire prédit : les colonnes que lit le modèle, sauf celles que
        la page connaît déjà (métier, niveau, ancienneté) ou qu'elle calcule (Mid et ratio grille /
        marché, tirés de la grille et du marché du métier + niveau). Le diplôme se saisit par son niveau
        d'études (BAC+5...) : son rang, que lit le modèle, est calculé comme dans
        src/anomaly_pretraitement.py.
        Pour chaque champ : une liste de choix (les valeurs du fichier des salariés) pour une catégorie,
        ou un nombre, borné par le plus petit et le plus grand du fichier. Pourquoi ces bornes : hors de
        ce que le modèle a vu, sa prédiction ne vaut plus grand-chose."""
        if self.regression is None:
            return []
        base, fields = self.regression_base, []
        for column in self.regression["colonnes"]:
            if column in DEJA_CONNUES:
                continue
            column = "Niveau_Etude_Max" if column == "Rang_Etude_Max" else column
            values = base[column].dropna()
            field = {"name": column, "label": LABELS.get(column, column)}
            if COLONNES.get(column) == "catégorie" or column == "Niveau_Etude_Max" or not pd.api.types.is_numeric_dtype(values):
                uniques = list(dict.fromkeys(values.tolist()))
                if column == "Niveau_Etude_Max":
                    rangs = dict(zip(uniques, rang_etude(pd.Series(uniques, dtype=object))))
                    uniques.sort(key=lambda v: (pd.isna(rangs[v]), 0 if pd.isna(rangs[v]) else rangs[v], str(v)))
                elif column == "Performance_N1" and set(map(str, uniques)) <= set(ORDRE_PERFORMANCE):
                    uniques.sort(key=lambda v: ORDRE_PERFORMANCE.index(str(v)))
                elif column == "Positionnement_9BOX" and set(map(str, uniques)) <= set(ORDRE_9BOX):
                    uniques.sort(key=lambda v: ORDRE_9BOX.index(str(v)))
                else:
                    uniques.sort(key=lambda v: (not isinstance(v, (int, float)), v if isinstance(v, (int, float)) else str(v)))
                # key : « 2 » et 2.0 désignent la même case, comme pour le métier et le niveau.
                options = {key(v): v for v in uniques}
                # Une case vide dans le fichier (une catégorie d'école inconnue...) : le modèle a appris un
                # effet « Inconnu » pour elle ; la page peut donc aussi la choisir.
                if base[column].isna().any():
                    options["Inconnu"] = None
                field.update(kind="choice", options=options)
            else:
                entiers = bool((values % 1 == 0).all())
                field.update(kind="number", min=float(values.min()), max=float(values.max()), step=1 if entiers else 0.01)
            fields.append(field)
        return fields

    def _train_regression(self):
        """Le modèle de régression et le tableau sur lequel il a appris. Pourquoi ce tableau : le modèle
        lit aussi le Mid de la grille, le ratio grille / marché et le rang du diplôme, que le fichier des
        salariés n'a pas. On les ajoute comme preparer_employes (src/anomaly_pretraitement.py). Si le
        modèle ne peut pas apprendre (pas de grille...), pas de salaire prédit (None)."""
        keys = ["Job_Family", "Niveau"]
        grille = self.bands[keys + ["Mid"]].assign(Mid=lambda t: pd.to_numeric(t.Mid, errors="coerce"))
        base = self.employees.merge(grille, on=keys, how="left")
        if self.market is not None:
            marche = self.market[keys + ["Median"]].assign(Median=lambda t: pd.to_numeric(t.Median, errors="coerce"))
            base = base.merge(marche, on=keys, how="left")
            base["Ratio_Grille_Marche"] = base.Mid / base.pop("Median").replace(0, np.nan)
        base = ajouter_diplomes(base)
        try:
            return entrainer(base)[0], base
        except (ValueError, KeyError):
            return None, base

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
        return cls(read("employes.xlsx"), read("bands.xlsx"), market, rules)

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

    def _peers(self, profile):
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
        salaries = peers.Fixe_Annuel_MAD
        median = float(salaries.median())
        mad = float((salaries - median).abs().median())
        std = float(salaries.std())
        # Même calcul que robust_zscore (src/anomaly_cohortes.py), mais sur les collègues seuls : le
        # salaire envisagé n'en fait pas partie.
        center, scale = (median, mad / .6745) if mad > 0 else (float(salaries.mean()), std)
        return {"count": len(peers), "available": True, "scope": scope, "median": median,
                "q25": float(salaries.quantile(.25)), "q75": float(salaries.quantile(.75)),
                "center": center, "scale": scale}

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
        peers = self._peers(profile)
        # Le plancher du niveau (règle du salaire minimum), ou None si le fichier de règles n'en donne pas.
        floor = self.rules.get("min_salary_by_niveau", {}).get(int(niveau) if niveau.isdigit() else niveau)
        proposal = self._proposal(band, market, peers, niveau, floor)
        status = "review" if proposal["reason"] == "conflict" else (
            "coherent" if proposal["target"] is not None and market and peers["available"] else "insufficient")
        titles = {"coherent": "Proposition de référence", "review": "Points à examiner",
                  "insufficient": "Références incomplètes"}
        return {"profile": profile, "unit": UNIT, "status": status, "title": titles[status],
                "band": band, "market": market,
                "peers": {k: v for k, v in peers.items() if k not in {"center", "scale"}},
                "proposal": proposal, "regression": self._regression(profile, band, market, inputs)}

    def _read_inputs(self, payload):
        """Les champs du salaire prédit saisis dans la page, contrôlés : un choix doit être une valeur du
        fichier des salariés, un nombre doit rester entre ses bornes. Un champ vide est simplement
        absent : la proposition se fait quand même, seul le salaire prédit attend."""
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
        # Repère en plus, qui ne change ni le verdict ni la fourchette proposée : le salaire que le modèle
        # prédit pour le profil saisi, avec la grille et le marché du métier + niveau choisis.
        # missing : les champs encore vides, que la page demande de remplir.
        result = {"predicted": None, "low": None, "high": None, "missing": [], "available": self.regression is not None}
        if self.regression is None:
            return result
        missing = ([] if profile["seniority"] is not None else ["Ancienneté"]) + [
            f["label"] for f in self.fields if f["name"] not in inputs]
        if missing:
            return {**result, "missing": missing}
        ligne = pd.DataFrame([{"Job_Family": profile["job_family"], "Niveau": profile["niveau"],
                               "Mid": band["Mid"] if band else np.nan,
                               "Ratio_Grille_Marche": band["Mid"] / market["Median"] if band and market else np.nan,
                               "Anciennete": profile["seniority"], **inputs}])
        if "Niveau_Etude_Max" in ligne:
            ligne["Rang_Etude_Max"] = rang_etude(ligne["Niveau_Etude_Max"])
        r = predire(ligne, self.regression).iloc[0]
        # Pas de grille pour ce métier + niveau (ou pas de marché) : pas de prédiction.
        if not math.isfinite(r.Salaire_Predit):
            return result
        return {**result, "predicted": round(float(r.Salaire_Predit), 2),
                "low": round(float(r.Fourchette_Basse), 2), "high": round(float(r.Fourchette_Haute), 2)}

    def _proposal(self, band, market, peers, niveau, floor):
        if not band:
            return {"low": None, "high": None, "target": None, "reason": "missing_band"}
        low = max(band["Min"], band["Mid"] * self.rules["compa_ratio_low"])
        high = min(band["Max"], band["Mid"] * self.rules["compa_ratio_high"])
        if market:
            low = max(low, market["Median"] * self.rules["market_low"])
            high = min(high, market["Median"] * self.rules["market_high"])
        if peers["available"]:
            low, high = max(low, peers["q25"]), min(high, peers["q75"])
            if peers["scale"] > 0:
                # Le seuil d'alerte est inclusif : la proposition doit rester à l'intérieur.
                margin = (self.peer_threshold - 1e-9) * peers["scale"]
                low = max(low, peers["center"] - margin)
                high = min(high, peers["center"] + margin)
            else:
                low, high = max(low, peers["median"]), min(high, peers["median"])
        # La fourchette ne descend jamais sous le salaire minimum du niveau.
        if floor is not None:
            low = max(low, floor)
        # Montants saisissables avec deux décimales ; arrondir les bornes vers l'intérieur.
        low = math.ceil((low - 1e-10) * 100) / 100
        high = math.floor((high + 1e-10) * 100) / 100
        # Si les repères se contredisent (ex. la grille impose plus que ce que tolère le marché), la
        # fourchette est vide : on le signale ("conflict") au lieu d'inventer un montant.
        if low > high:
            return {"low": None, "high": None, "target": None, "reason": "conflict"}
        target = peers["median"] if peers["available"] else band["Mid"]
        target = min(high, max(low, round(target, 2)))
        # Dernière vérification : la cible repasse dans les cinq règles du programme principal. Si elle
        # déclenchait elle-même une alerte, on ne propose rien plutôt qu'un montant contradictoire.
        if any(c["status"] == "review" for c in self._checks(target, band, market, peers, niveau)):
            return {"low": None, "high": None, "target": None, "reason": "conflict"}
        return {"low": low, "high": high, "target": target, "reason": "available"}

    def _checks(self, salary, band, market, peers, niveau):
        # Pourquoi PeerZ : les cinq règles de src/anomaly_regles.py en ont besoin, dont celle des collègues.
        # Pourquoi Niveau et Fixe_Annuel_MAD : la règle du salaire minimum les lit. Le niveau est remis en
        # nombre, comme dans le fichier de règles (min_salary_by_niveau : 5 et non « 5 »).
        ratios = {"CompaRatio": salary / band["Mid"] if band else np.nan,
                  "RangePenetration": (salary - band["Min"]) / (band["Max"] - band["Min"])
                  if band and band["Max"] > band["Min"] else np.nan,
                  "MarketRatio": salary / market["Median"] if market else np.nan,
                  "PeerZ": (salary - peers["center"]) / peers["scale"]
                  if peers["available"] and peers["scale"] > 0 else np.nan,
                  "Niveau": int(niveau) if niveau.isdigit() else niveau, "Fixe_Annuel_MAD": salary}
        for column, bounds in [("CompaRatio", ("compa_ratio_low", "compa_ratio_high")),
                               ("MarketRatio", ("market_low", "market_high"))]:
            for bound in bounds:
                if math.isclose(ratios[column], self.rules[bound], rel_tol=1e-12, abs_tol=1e-12):
                    ratios[column] = self.rules[bound]
        flags = apply_rulebook(pd.DataFrame([ratios]), self.rules).iloc[0].Rule_Flags
        # Pourquoi OUT_OF_BAND : même règle que le programme principal, avec sa petite marge sous le Min.
        # Comme là-bas, un salaire au-dessus du Max ne lève plus d'alerte (comité du 15/10/2026). La
        # fourchette proposée, elle, reste toujours entre Min et Max.
        results = {"Grille interne": "OUT_OF_BAND" not in flags if band else None,
                   "Position dans la grille": "COMPA_RATIO" not in flags if band else None,
                   "Marché": "MARKET_GAP" not in flags if market else None,
                   # Sans plancher pour ce niveau dans le fichier de règles, le contrôle est indisponible.
                   "Salaire minimum": "MIN_SALARY" not in flags
                   if niveau.isdigit() and int(niveau) in self.rules.get("min_salary_by_niveau", {}) else None}
        if not peers["available"]:
            results["Collègues comparables"] = None
        elif peers["scale"] > 0:
            results["Collègues comparables"] = "PEER_OUTLIER" not in flags
        else:
            # Tous les collègues ont le même salaire : être payé moins qu'eux est à examiner. Être payé
            # plus ne l'est plus, comme dans la règle des collègues (comité du 15/10/2026).
            results["Collègues comparables"] = salary >= peers["median"] or math.isclose(salary, peers["median"])
        # Pourquoi seulement un nom et un statut : ces contrôles vérifient la cible proposée, mais ne sont
        # pas affichés un par un (la règle « Positionnement » montre déjà les repères).
        return [{"name": name, "status": "unavailable" if ok is None else "ok" if ok else "review"}
                for name, ok in results.items()]
