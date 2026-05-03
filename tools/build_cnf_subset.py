#!/usr/bin/env python3
"""Extrait un sous-ensemble du CNF (Santé Canada) pour les ingrédients utilisés.

Lit data/ingredients.yml pour identifier les FoodIDs nécessaires, puis extrait
les valeurs nutritionnelles + facteurs de conversion correspondants depuis les
CSV CNF.

Les CSV sont téléchargés automatiquement dans /tmp/cnf/ depuis le miroir GitHub
STAT231-S24/CanadianNutrient (dérivé du Fichier canadien des éléments
nutritifs 2015 de Santé Canada). Pour forcer un re-téléchargement, supprimer
/tmp/cnf/.

Usage : python3 tools/build_cnf_subset.py
"""
import csv
import json
import sys
import urllib.request
from pathlib import Path

import yaml

CNF_DIR = Path("/tmp/cnf")
CNF_FILES = [
    "FOOD_NAME.csv",
    "NUTRIENT_AMOUNT.csv",
    "NUTRIENT_NAME.csv",
    "CONVERSION_FACTOR.csv",
    "MEASURE_NAME.csv",
]
CNF_BASE_URL = (
    "https://raw.githubusercontent.com/STAT231-S24/CanadianNutrient/main/data-raw"
)

REPO = Path(__file__).parent.parent
ING_YML = REPO / "data" / "ingredients.yml"
OUT = REPO / "data" / "cnf_foods.json"

NUTR = {"208": "kcal", "203": "prot", "204": "lip", "205": "gluc"}


def ensure_cnf_files():
    """Télécharge les CSV CNF dans /tmp/cnf/ s'ils sont absents."""
    CNF_DIR.mkdir(parents=True, exist_ok=True)
    missing = [f for f in CNF_FILES if not (CNF_DIR / f).exists()]
    if not missing:
        return
    print(f"Téléchargement de {len(missing)} fichier(s) CNF dans {CNF_DIR}...")
    for fname in missing:
        url = f"{CNF_BASE_URL}/{fname}"
        dest = CNF_DIR / fname
        print(f"  {fname} ...", end="", flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            print(f" {dest.stat().st_size // 1024} KB")
        except Exception as e:
            sys.exit(f"\nErreur lors du téléchargement de {url} : {e}")


def main():
    ensure_cnf_files()
    if not ING_YML.exists():
        sys.exit(f"Erreur : {ING_YML} introuvable.")

    data = yaml.safe_load(ING_YML.read_text(encoding="utf-8"))
    food_ids = {
        str(spec["cnf_id"])
        for spec in data["ingredients"].values()
        if spec.get("cnf_id") and not spec.get("skip")
    }
    print(f"Extraction de {len(food_ids)} aliments du CNF...")

    # 1. FOOD_NAME : descriptions FR
    descriptions = {}
    with open(CNF_DIR / "FOOD_NAME.csv", encoding="cp1252") as f:
        for r in csv.DictReader(f):
            if r["FoodID"] in food_ids:
                descriptions[r["FoodID"]] = r["FoodDescriptionF"]

    missing = food_ids - set(descriptions)
    if missing:
        print(f"  ATTENTION : FoodIDs introuvables : {sorted(missing)}", file=sys.stderr)

    # 2. NUTRIENT_AMOUNT : valeurs nutritionnelles
    nutrients = {fid: {} for fid in descriptions}
    with open(CNF_DIR / "NUTRIENT_AMOUNT.csv", encoding="cp1252") as f:
        for r in csv.DictReader(f):
            if r["FoodID"] in nutrients and r["NutrientID"] in NUTR:
                nutrients[r["FoodID"]][NUTR[r["NutrientID"]]] = float(r["NutrientValue"])

    # 3. MEASURE_NAME : descriptions des mesures
    measures = {}
    with open(CNF_DIR / "MEASURE_NAME.csv", encoding="cp1252") as f:
        for r in csv.DictReader(f):
            measures[r["MeasureID"]] = r["MeasureDescriptionF"]

    # 4. CONVERSION_FACTOR : facteurs (par FoodID)
    conv = {fid: [] for fid in descriptions}
    with open(CNF_DIR / "CONVERSION_FACTOR.csv", encoding="cp1252") as f:
        for r in csv.DictReader(f):
            if r["FoodID"] in conv:
                mid = r["MeasureID"]
                conv[r["FoodID"]].append({
                    "measure_id": mid,
                    "desc": measures.get(mid, "?"),
                    "cf": float(r["ConversionFactorValue"]),
                })

    out = {}
    for fid, desc in descriptions.items():
        out[fid] = {
            "name_fr": desc,
            **{k: round(nutrients[fid].get(k, 0), 3) for k in NUTR.values()},
            "measures": sorted(conv[fid], key=lambda m: m["desc"]),
        }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Écrit {OUT.relative_to(REPO)} ({OUT.stat().st_size // 1024} KB, {len(out)} aliments)")


if __name__ == "__main__":
    main()
