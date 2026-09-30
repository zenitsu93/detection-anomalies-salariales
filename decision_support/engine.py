"""Comparaisons explicables sur des références fixes, sans modifier les sources."""

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

from anomaly_pretraitement import bucket_anciennete
from anomaly_regles import apply_rulebook

# Même unité que les CSV : aucune conversion.
UNIT = "kMAD / an"
# Le périmètre d'un groupe de collègues, écrit en clair colonne par colonne.
SCOPE = {"Grade": "même grade", "Job_Family": "même métier", "Anciennete_Bucket": "ancienneté {} ans"}


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
                                    ["Grade|Job_Family|Anciennete_Bucket", "Grade|Job_Family", "Grade"])
        for lo, hi, defaults in [("compa_ratio_low", "compa_ratio_high", (.85, 1.15)),
                                  ("market_low", "market_high", (.9, 1.2))]:
            low = number(self.rules.get(lo, defaults[0]), lo, strict=True)
            high = number(self.rules.get(hi, defaults[1]), hi, strict=True)
            if low >= high:
                raise ValueError(f"{lo} doit être inférieur à {hi}.")
            self.rules.update({lo: low, hi: high})
        self.peer_threshold = number(self.rules.get("peer_z_threshold_minor", 2),
                                     "peer_z_threshold_minor", strict=True)
        keys = ["Job_Family", "Grade"]
        self.employees = self._prepare(employees, keys + ["Fixe_Annuel_MAD"], "Employés")
        # Pourquoi drop_duplicates : un métier + grade en double garde sa première ligne, comme dans
        # src/anomaly_pretraitement.py.
        self.bands = self._prepare(bands, keys + ["Min", "Mid", "Max"], "Grille").drop_duplicates(keys)
        self.market = (self._prepare(market, keys + ["Median"], "Marché").drop_duplicates(keys)
                       if market is not None else None)
        if "Matricule" in self.employees:
            # Pourquoi : un matricule en double garde lui aussi sa première ligne.
            self.employees = self.employees.drop_duplicates(subset="Matricule")
            self.employees["Matricule"] = self.employees.Matricule.map(key)
            self.known_ids = set(self.employees.Matricule) - {""}
        else:
            self.known_ids = set()
        pay = pd.to_numeric(self.employees.Fixe_Annuel_MAD, errors="coerce")
        # Un salaire illisible, nul ou négatif n'est pas comparé.
        valid = np.isfinite(pay) & pay.gt(0)
        self.employees = self.employees.loc[valid].copy()
        self.employees["Fixe_Annuel_MAD"] = pay.loc[valid]
        # Pourquoi ce nom de colonne : c'est celui des groupes de collègues (cohort_widening_steps).
        self.employees["Anciennete_Bucket"] = (self.employees.Anciennete.map(bucket_anciennete)
                                               if "Anciennete" in self.employees else "NA")

    @staticmethod
    def _prepare(table, columns, label):
        missing = set(columns) - set(table.columns)
        if missing:
            raise ValueError(f"{label} : colonnes absentes : {', '.join(sorted(missing))}.")
        result = table.copy(deep=True)
        result["Job_Family"] = result.Job_Family.map(key)
        result["Grade"] = result.Grade.map(key)
        return result

    @classmethod
    def from_project(cls, root=ROOT):
        root = Path(root)
        rules = yaml.safe_load((root / "config" / "rules.yaml").read_text(encoding="utf-8"))["rules"]

        # Même lecture que src/anomaly_pretraitement.py : séparateur « ; », encodage Windows cp1252.
        def read(name):
            return pd.read_csv(root / "input" / name, sep=";", encoding="cp1252")

        market = read("market.csv") if (root / "input" / "market.csv").exists() else None
        return cls(read("employes.csv"), read("bands.csv"), market, rules)

    def metadata(self):
        pairs = self.bands.loc[self.bands.Job_Family.ne("") & self.bands.Grade.ne(""), ["Job_Family", "Grade"]]
        jobs = {job: sorted(group.Grade.unique().tolist()) for job, group in pairs.groupby("Job_Family")}
        return {"jobs": jobs, "unit": UNIT, "minimum_peers": self.minimum_peers,
                "employees": len(self.employees)}

    def _reference(self, table, profile, columns):
        # Rend les montants de la grille ou du marché pour ce métier + grade, ou None s'ils manquent ou
        # sont inutilisables (absents, nuls, négatifs, ou Min / Mid / Max dans le désordre).
        if table is None:
            return None
        rows = table.loc[(table.Job_Family == profile["job_family"]) & (table.Grade == profile["grade"]), columns]
        # Pourquoi une seule ligne : les doublons de métier + grade sont déjà retirés.
        if rows.empty:
            return None
        result = {c: float(v) for c, v in pd.to_numeric(rows.iloc[0], errors="coerce").items()}
        if not all(math.isfinite(v) and v > 0 for v in result.values()):
            return None
        if columns == ["Min", "Mid", "Max"] and not result["Min"] <= result["Mid"] <= result["Max"]:
            return None
        return result

    def _peers(self, profile):
        values = {"Job_Family": profile["job_family"], "Grade": profile["grade"],
                  "Anciennete_Bucket": None if profile["seniority"] is None else bucket_anciennete(profile["seniority"])}
        others = self.employees
        if profile["employee_id"]:
            others = others.loc[others.Matricule != profile["employee_id"]]
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
        mode = payload.get("mode", "evaluate")
        if mode not in {"evaluate", "propose"}:
            raise ValueError("Mode inconnu.")
        job, grade = key(payload.get("job_family", "")), key(payload.get("grade", ""))
        if not job or not grade:
            raise ValueError("Le métier et le grade sont obligatoires.")
        seniority = number(payload.get("seniority"), "Ancienneté", optional=True)
        employee_id = key(payload.get("employee_id", ""))
        if employee_id and employee_id not in self.known_ids:
            raise ValueError("Matricule absent du fichier employés. Vérifier la saisie ou laisser le champ vide.")
        profile = {"job_family": job, "grade": grade, "seniority": seniority, "employee_id": employee_id}
        salary = number(payload.get("salary"), "Salaire envisagé", strict=True) if mode == "evaluate" else None
        band = self._reference(self.bands, profile, ["Min", "Mid", "Max"])
        market = self._reference(self.market, profile, ["Median"])
        peers = self._peers(profile)
        proposal = self._proposal(band, market, peers)
        checks = self._checks(salary, band, market, peers) if salary is not None else []
        if salary is not None:
            status = "review" if any(c["status"] == "review" for c in checks) else (
                "coherent" if band and market and peers["available"] else "insufficient")
        else:
            status = "review" if proposal["reason"] == "conflict" else (
                "coherent" if proposal["target"] is not None and market and peers["available"] else "insufficient")
        titles = {"coherent": "Cohérent avec les repères disponibles" if mode == "evaluate" else "Proposition de référence",
                  "review": "Points à examiner", "insufficient": "Références incomplètes"}
        return {"mode": mode, "profile": profile, "salary": salary, "unit": UNIT,
                "status": status, "title": titles[status], "band": band, "market": market,
                "peers": {k: v for k, v in peers.items() if k not in {"center", "scale"}},
                "checks": checks, "proposal": proposal}

    def _proposal(self, band, market, peers):
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
        # Montants saisissables avec deux décimales ; arrondir les bornes vers l'intérieur.
        low = math.ceil((low - 1e-10) * 100) / 100
        high = math.floor((high + 1e-10) * 100) / 100
        # Si les repères se contredisent (ex. la grille impose plus que ce que tolère le marché), la
        # fourchette est vide : on le signale ("conflict") au lieu d'inventer un montant.
        if low > high:
            return {"low": None, "high": None, "target": None, "reason": "conflict"}
        target = peers["median"] if peers["available"] else band["Mid"]
        target = min(high, max(low, round(target, 2)))
        # Dernière vérification : la cible repasse dans les mêmes contrôles que l'évaluation. Si elle
        # déclenchait elle-même une alerte, on ne propose rien plutôt qu'un montant contradictoire.
        if any(c["status"] == "review" for c in self._checks(target, band, market, peers)):
            return {"low": None, "high": None, "target": None, "reason": "conflict"}
        return {"low": low, "high": high, "target": target, "reason": "available"}

    def _checks(self, salary, band, market, peers):
        # Pourquoi PeerZ : les quatre règles de src/anomaly_regles.py en ont besoin, dont celle des collègues.
        ratios = {"CompaRatio": salary / band["Mid"] if band else np.nan,
                  "RangePenetration": (salary - band["Min"]) / (band["Max"] - band["Min"])
                  if band and band["Max"] > band["Min"] else np.nan,
                  "MarketRatio": salary / market["Median"] if market else np.nan,
                  "PeerZ": (salary - peers["center"]) / peers["scale"]
                  if peers["available"] and peers["scale"] > 0 else np.nan}
        for column, bounds in [("CompaRatio", ("compa_ratio_low", "compa_ratio_high")),
                               ("MarketRatio", ("market_low", "market_high"))]:
            for bound in bounds:
                if math.isclose(ratios[column], self.rules[bound], rel_tol=1e-12, abs_tol=1e-12):
                    ratios[column] = self.rules[bound]
        flags = apply_rulebook(pd.DataFrame([ratios]), self.rules).iloc[0].Rule_Flags
        # Pourquoi OUT_OF_BAND : même règle que le programme principal, avec sa petite marge autour du
        # Min et du Max. La fourchette proposée, elle, reste toujours entre Min et Max.
        results = {"Grille interne": "OUT_OF_BAND" not in flags if band else None,
                   "Position dans la grille": "COMPA_RATIO" not in flags if band else None,
                   "Marché": "MARKET_GAP" not in flags if market else None}
        if not peers["available"]:
            results["Collègues comparables"] = None
        elif peers["scale"] > 0:
            results["Collègues comparables"] = "PEER_OUTLIER" not in flags
        else:
            # Tous les collègues ont le même salaire : tout écart à ce salaire est à examiner.
            results["Collègues comparables"] = math.isclose(salary, peers["median"])
        # Pourquoi seulement un nom et un statut : ces contrôles décident du verdict et vérifient la cible
        # proposée, mais ne sont pas affichés un par un (la règle « Positionnement » montre déjà les repères).
        return [{"name": name, "status": "unavailable" if ok is None else "ok" if ok else "review"}
                for name, ok in results.items()]
