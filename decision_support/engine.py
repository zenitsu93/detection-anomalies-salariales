"""Comparaisons explicables sur des références fixes, sans modifier les sources."""

from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.anomaly_core import apply_rulebook, bucket_anciennete
from src.anomaly_io import read_csv_guess_sep


ROOT = Path(__file__).resolve().parent.parent


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
    def __init__(self, employees, bands, market, rules, unit="unité source / an", provenance=None):
        self.rules = dict(rules)
        self.unit = unit
        self.provenance = provenance or {}
        self.minimum_peers = int(self.rules.get("cohort_min_size", 5))
        if self.minimum_peers < 2:
            raise ValueError("cohort_min_size doit être au moins égal à 2.")
        for lo, hi, defaults in [("compa_ratio_low", "compa_ratio_high", (.85, 1.15)),
                                  ("market_low", "market_high", (.9, 1.2))]:
            low = number(self.rules.get(lo, defaults[0]), lo, strict=True)
            high = number(self.rules.get(hi, defaults[1]), hi, strict=True)
            if low >= high:
                raise ValueError(f"{lo} doit être inférieur à {hi}.")
            self.rules.update({lo: low, hi: high})
        self.peer_threshold = number(self.rules.get("peer_z_threshold_minor", 2),
                                     "peer_z_threshold_minor", strict=True)
        self.messages = []
        self.employees = self._prepare(employees, ["Job_Family", "Grade", "Fixe_Annuel_MAD"], "Employés")
        self.bands = self._prepare(bands, ["Job_Family", "Grade", "Min", "Mid", "Max"], "Grille")
        self.market = self._prepare(market, ["Job_Family", "Grade", "Median"], "Marché") if market is not None else None
        if "Matricule" in self.employees:
            self.employees["Matricule"] = self.employees.Matricule.map(key)
            repeated = self.employees.Matricule.ne("") & self.employees.Matricule.duplicated(keep=False)
            self.known_ids = set(self.employees.Matricule) - {""}
            if repeated.any():
                self.messages.append(f"{int(repeated.sum())} lignes à matricule dupliqué exclues des comparaisons.")
                self.employees = self.employees.loc[~repeated].copy()
        else:
            self.known_ids = set()
            self.messages.append("Matricule absent : impossible d'exclure automatiquement un salarié existant.")
        pay = pd.to_numeric(self.employees.Fixe_Annuel_MAD, errors="coerce")
        valid = np.isfinite(pay) & pay.gt(0)
        if (~valid).any():
            self.messages.append(f"{int((~valid).sum())} salaires invalides exclus des comparaisons.")
        self.employees = self.employees.loc[valid].copy()
        self.employees["Fixe_Annuel_MAD"] = pay.loc[valid]
        self.employees["_bucket"] = (self.employees.Anciennete.map(bucket_anciennete)
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
        paths = {"employés": root / "input/employes.csv", "grille": root / "input/bands.csv",
                 "marché": root / "input/market.csv", "règles": root / "config/rules.yaml",
                 "paramètres": root / "decision_support/settings.yaml"}
        rules = yaml.safe_load(paths["règles"].read_text(encoding="utf-8"))["rules"]
        settings = yaml.safe_load(paths["paramètres"].read_text(encoding="utf-8")) or {}
        provenance = {"loaded_at": datetime.now(timezone.utc).isoformat(), "files": {
            name: {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in paths.items() if path.exists()}}
        return cls(read_csv_guess_sep(paths["employés"]), read_csv_guess_sep(paths["grille"]),
                   read_csv_guess_sep(paths["marché"]) if paths["marché"].exists() else None,
                   rules, settings.get("salary_unit", "unité source / an"), provenance)

    def metadata(self):
        pairs = self.bands.loc[self.bands.Job_Family.ne("") & self.bands.Grade.ne(""), ["Job_Family", "Grade"]]
        jobs = {job: sorted(group.Grade.unique().tolist()) for job, group in pairs.groupby("Job_Family")}
        return {"jobs": jobs, "unit": self.unit, "minimum_peers": self.minimum_peers,
                "employees": len(self.employees), "provenance": self.provenance,
                "messages": self.messages}

    def _reference(self, table, profile, columns, label, warnings):
        if table is None:
            warnings.append(f"{label} indisponible.")
            return None
        rows = table.loc[(table.Job_Family == profile["job_family"]) & (table.Grade == profile["grade"]), columns]
        values = rows.apply(pd.to_numeric, errors="coerce").drop_duplicates()
        if len(values) != 1:
            warnings.append(f"{label} : {'références contradictoires' if len(values) > 1 else 'aucune correspondance'}.")
            return None
        result = {c: float(values.iloc[0][c]) for c in columns}
        if not all(math.isfinite(v) and v > 0 for v in result.values()):
            warnings.append(f"{label} : montants invalides.")
            return None
        if columns == ["Min", "Mid", "Max"] and not result["Min"] <= result["Mid"] <= result["Max"]:
            warnings.append("Grille interne : ordre Min / Mid / Max incohérent.")
            return None
        if len(rows) > 1:
            warnings.append(f"{label} : lignes identiques regroupées.")
        return result

    def _peers(self, profile, warnings):
        peers = self.employees.loc[(self.employees.Job_Family == profile["job_family"]) &
                                   (self.employees.Grade == profile["grade"])]
        if profile["employee_id"]:
            peers = peers.loc[peers.Matricule != profile["employee_id"]]
        scope = "Même métier et même grade"
        if profile["seniority"] is not None:
            bucket = bucket_anciennete(profile["seniority"])
            narrow = peers.loc[peers._bucket == bucket]
            if len(narrow) >= self.minimum_peers:
                peers = narrow
                scope += f", ancienneté {bucket} ans"
            else:
                warnings.append("Groupe d'ancienneté trop petit : comparaison élargie au même métier et grade.")
        if len(peers) < self.minimum_peers:
            warnings.append(f"Pairs insuffisants : {len(peers)} disponibles, {self.minimum_peers} requis.")
            return {"count": len(peers), "available": False, "scope": scope}
        salaries = peers.Fixe_Annuel_MAD
        median = float(salaries.median())
        mad = float((salaries - median).abs().median())
        std = float(salaries.std())
        # Même convention que robust_zscore, estimée sur les références seules.
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
        warnings = list(self.messages)
        band = self._reference(self.bands, profile, ["Min", "Mid", "Max"], "Grille interne", warnings)
        market = self._reference(self.market, profile, ["Median"], "Marché", warnings)
        peers = self._peers(profile, warnings)
        if band and market and math.isclose(band["Mid"], market["Median"]):
            warnings.append("Le milieu de grille et la médiane marché sont identiques : ce ne sont pas deux repères indépendants.")
        proposal = self._proposal(band, market, peers)
        checks = self._checks(salary, band, market, peers) if salary is not None else []
        if salary is not None:
            status = "review" if any(c["status"] == "review" for c in checks) else (
                "coherent" if band and market and peers["available"] else "insufficient")
        else:
            status = "review" if proposal["reason"] == "conflict" else (
                "coherent" if proposal["target"] is not None and market and peers["available"] else "insufficient")
        if proposal["reason"] == "conflict":
            warnings.append("Les références ne donnent pas de fourchette commune. Un arbitrage métier est nécessaire.")
        titles = {"coherent": "Cohérent avec les repères disponibles" if mode == "evaluate" else "Proposition de référence",
                  "review": "Points à examiner", "insufficient": "Références incomplètes"}
        return {"mode": mode, "profile": profile, "salary": salary, "unit": self.unit,
                "status": status, "title": titles[status], "band": band, "market": market,
                "peers": {k: v for k, v in peers.items() if k not in {"center", "scale"}},
                "checks": checks, "proposal": proposal, "warnings": warnings,
                "method": "Fourchette interne croisée avec les seuils CompaRatio, le marché et les quartiles des pairs disponibles. Cible : médiane des pairs, sinon milieu de grille, ramenée dans cette fourchette.",
                "limits": "Repères de comparaison pour une revue RH. La proposition n'est ni un salaire optimal démontré ni une validation automatique.",
                "provenance": self.provenance}

    def _proposal(self, band, market, peers):
        if not band:
            return {"low": None, "high": None, "target": None, "reason": "missing_band", "basis": []}
        low = max(band["Min"], band["Mid"] * self.rules["compa_ratio_low"])
        high = min(band["Max"], band["Mid"] * self.rules["compa_ratio_high"])
        basis = ["Grille interne et seuils CompaRatio"]
        if market:
            low = max(low, market["Median"] * self.rules["market_low"])
            high = min(high, market["Median"] * self.rules["market_high"])
            basis.append("Tolérances marché")
        if peers["available"]:
            low, high = max(low, peers["q25"]), min(high, peers["q75"])
            basis.append("Moitié centrale des salaires des pairs (P25–P75)")
            if peers["scale"] > 0:
                # Le seuil d'alerte est inclusif : la proposition doit rester à l'intérieur.
                margin = (self.peer_threshold - 1e-9) * peers["scale"]
                low = max(low, peers["center"] - margin)
                high = min(high, peers["center"] + margin)
                basis.append("Absence d'alerte statistique entre pairs")
            else:
                low, high = max(low, peers["median"]), min(high, peers["median"])
        # Montants saisissables avec deux décimales ; arrondir les bornes vers l'intérieur.
        low = math.ceil((low - 1e-10) * 100) / 100
        high = math.floor((high + 1e-10) * 100) / 100
        # Si les repères se contredisent (ex. la grille impose plus que ce que tolère le marché), la
        # fourchette est vide : on le signale ("conflict") au lieu d'inventer un montant.
        if low > high:
            return {"low": None, "high": None, "target": None, "reason": "conflict", "basis": basis}
        target = peers["median"] if peers["available"] else band["Mid"]
        target = min(high, max(low, round(target, 2)))
        # Dernière vérification : la cible repasse dans les mêmes contrôles que l'évaluation. Si elle
        # déclenchait elle-même une alerte, on ne propose rien plutôt qu'un montant contradictoire.
        if any(c["status"] == "review" for c in self._checks(target, band, market, peers)):
            return {"low": None, "high": None, "target": None, "reason": "conflict", "basis": basis}
        return {"low": low, "high": high, "target": target, "reason": "available", "basis": basis}

    def _checks(self, salary, band, market, peers):
        checks = []
        def add(name, ok, detail, value=None):
            checks.append({"name": name, "status": "unavailable" if ok is None else "ok" if ok else "review",
                           "detail": detail, "value": value})
        ratios = {"CompaRatio": salary / band["Mid"] if band else np.nan,
                  "RangePenetration": (salary - band["Min"]) / (band["Max"] - band["Min"])
                  if band and band["Max"] > band["Min"] else np.nan,
                  "MarketRatio": salary / market["Median"] if market else np.nan}
        for column, bounds in [("CompaRatio", ("compa_ratio_low", "compa_ratio_high")),
                               ("MarketRatio", ("market_low", "market_high"))]:
            for bound in bounds:
                if math.isclose(ratios[column], self.rules[bound], rel_tol=1e-12, abs_tol=1e-12):
                    ratios[column] = self.rules[bound]
        flags = apply_rulebook(pd.DataFrame([ratios]), self.rules).iloc[0].Rule_Flags
        add("Grille interne", band["Min"] <= salary <= band["Max"] if band else None,
            "Comparaison stricte au minimum et au maximum de la grille, sans marge de dépassement.")
        add("Position dans la grille", "COMPA_RATIO" not in flags if band else None,
            f"Salaire / milieu de grille ; intervalle {self.rules['compa_ratio_low']:g}–{self.rules['compa_ratio_high']:g}.",
            ratios["CompaRatio"] if band else None)
        add("Marché", "MARKET_GAP" not in flags if market else None,
            f"Salaire / médiane marché ; intervalle {self.rules['market_low']:g}–{self.rules['market_high']:g}.",
            ratios["MarketRatio"] if market else None)
        if not peers["available"]:
            add("Collègues comparables", None, "Effectif insuffisant pour conclure.")
        elif peers["scale"] > 0:
            z = (salary - peers["center"]) / peers["scale"]
            add("Collègues comparables", abs(z) < self.peer_threshold,
                f"Écart standardisé sur les références seules ; alerte à partir de |Z| = {self.peer_threshold:g}.", z)
        else:
            add("Collègues comparables", math.isclose(salary, peers["median"]),
                "Tous les pairs ont le même salaire : tout écart est à examiner, sans score statistique.")
        return checks
