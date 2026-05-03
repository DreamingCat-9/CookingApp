#!/usr/bin/env python3
"""Génère index.html à partir des recettes markdown dans recipes/.

Pour chaque recette, calcule aussi la ventilation des macros par ingrédient
en utilisant le mapping data/ingredients.yml + les valeurs CNF dans
data/cnf_foods.json.

Usage: python3 build.py
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

REPO = Path(__file__).parent
RECIPES_DIR = REPO / "recipes"
TEMPLATE = REPO / "template.html"
OUTPUT = REPO / "index.html"
ING_YML = REPO / "data" / "ingredients.yml"
CNF_JSON = REPO / "data" / "cnf_foods.json"

# Conversions simples
G_PER_KG = 1000.0
G_PER_OZ = 28.3495
G_PER_LB = 453.592
ML_PER_L = 1000.0
ML_PER_TASSE = 250.0
ML_PER_CSOUPE = 15.0
ML_PER_CTHE = 5.0


def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    return strip_accents(s.lower()).strip()


# === Parser ===

NUM_PART = r"\d+(?:[.,]\d+)?"
FRAC_PART = rf"(?:{NUM_PART}\s+\d+/\d+|{NUM_PART}/\d+|{NUM_PART})"

# Capture leading "<qty> <unit>" — la partie après est le reste de la ligne
# \b après l'unité pour éviter de matcher "g" dans "gousses".
LEAD_QTY_UNIT_RE = re.compile(
    rf"^\s*({FRAC_PART})\s*(kg|g|oz|lb|ml|l|litres?|tasses?|c\.\s*[àa]\s*soupe|c\.\s*[àa]\s*th[ée]|pinc[éeèê]es?)\b\s*",
    re.IGNORECASE,
)
# Variante sans unité (juste le compte) — utilisée en fallback
LEAD_COUNT_ONLY_RE = re.compile(
    rf"^\s*({FRAC_PART})\s+(?=\S)",
)

# « 1 boîte de 540 ml » / « 1 sac de 600 g » / « 1 paquet de 340 g »
# « 2 paquets de 200 g chacun de nouilles udon » / « 1 conserve de haricots noirs de 540 ml »
PACKAGE_RE = re.compile(
    rf"^\s*({FRAC_PART})?\s*(?:bo[iî]tes?|sacs?|paquets?|barquette|conserves?|cont(?:enants?|enance)?|pot|botte)\s+de\s+({NUM_PART})\s*(kg|g|oz|lb|ml|l)\b",
    re.IGNORECASE,
)
# Pattern « ... de N (kg|g|ml|l) » à la fin (1 conserve de haricots noirs de 540 ml)
PACKAGE_TRAIL_RE = re.compile(
    rf"^\s*({FRAC_PART})?\s*(?:bo[iî]tes?|sacs?|paquets?|barquette|conserves?|cont(?:enants?|enance)?|pot|botte)\s+de\s+(.+?)\s+de\s+({NUM_PART})\s*(kg|g|oz|lb|ml|l)\b",
    re.IGNORECASE,
)

# « 4 poitrines de poulet (200 g chacune) » → extraire 200g × 4
PER_UNIT_WEIGHT_RE = re.compile(
    rf"\(([^()]*?({NUM_PART})\s*(kg|g|oz|lb)\s*chacun(?:e|es)?[^()]*)\)",
    re.IGNORECASE,
)

# « 4 poitrines (environ 200 g chacune) » / « 1 botte d'asperges (325 g) »
ENVIRON_WEIGHT_RE = re.compile(
    rf"\(([^()]*?(?:environ\s*)?({NUM_PART})\s*(kg|g|oz|lb)\b[^()]*)\)",
    re.IGNORECASE,
)
# « ... de 900 g » / « ... de 450 g » à l'intérieur d'une ligne
INLINE_DE_WEIGHT_RE = re.compile(
    rf"\bde\s+({NUM_PART})\s*(kg|g|oz|lb|ml|l)\b",
    re.IGNORECASE,
)
# « Jus de N citron(s)/lime(s)/orange(s) » et « Le jus de ... »
JUS_DE_RE = re.compile(
    rf"^\s*(?:le\s+)?jus\s+(?:de|d'?)\s+({FRAC_PART})\s+(citron|lime|orange)s?\b",
    re.IGNORECASE,
)
# « Le zeste de ... » / « Zeste de ... » → on traite comme zéro macro
ZESTE_RE = re.compile(r"^\s*(?:le\s+)?zeste\b", re.IGNORECASE)

PARENS_RE = re.compile(r"\([^()]*\)")


def parse_qty(text: str) -> float:
    """Parse '4 1/2', '1 1/2', '125', '0,5', '1/2' → float."""
    text = text.strip().replace(",", ".")
    if " " in text and "/" in text:
        whole, frac = text.split(" ", 1)
        n, d = frac.split("/")
        return float(whole) + float(n) / float(d)
    if "/" in text:
        n, d = text.split("/")
        return float(n) / float(d)
    return float(text)


def normalize_unit(u: str) -> str | None:
    """Retourne une unité canonique : g, ml, ou None (count)."""
    if not u:
        return None
    u = norm(u).rstrip("s.")
    if u in {"g", "kg", "oz", "lb"}:
        return u
    if u in {"ml", "l", "litre"}:
        return "l" if u in {"l", "litre"} else "ml"
    if u in {"tasse"}:
        return "tasse"
    if "soupe" in u:
        return "csoupe"
    if "the" in u:
        return "cthe"
    if "pinc" in u:
        return "pincee"
    return None


ML_DESC_RE = re.compile(r"^(\d+)\s*ml\b", re.IGNORECASE)


def get_ml_density(food: dict | None) -> float | None:
    """Densité (g/ml) déduite de n'importe quelle mesure ml-based du CNF.

    CNF : `ConversionFactorValue × 100 = grammes par mesure`. Donc pour une
    mesure « N ml », densité = CF × 100 / N.
    """
    if not food:
        return None
    for m in food.get("measures", []):
        match = ML_DESC_RE.match(m["desc"].strip())
        if match:
            ml_val = int(match.group(1))
            if ml_val > 0:
                return m["cf"] * 100 / ml_val
    return None


def to_grams_from_unit(qty: float, unit: str, food: dict | None) -> float | None:
    """Convertit (qty, unit) en grammes pour un aliment CNF donné.
    Pour les volumes, déduit la densité via les mesures ml-based du CNF.
    """
    if unit == "g":
        return qty
    if unit == "kg":
        return qty * G_PER_KG
    if unit == "oz":
        return qty * G_PER_OZ
    if unit == "lb":
        return qty * G_PER_LB
    if unit == "pincee":
        return 0.5  # négligeable

    # Volumes → ml
    ml = None
    if unit == "ml":
        ml = qty
    elif unit == "l":
        ml = qty * ML_PER_L
    elif unit == "tasse":
        ml = qty * ML_PER_TASSE
    elif unit == "csoupe":
        ml = qty * ML_PER_CSOUPE
    elif unit == "cthe":
        ml = qty * ML_PER_CTHE

    if ml is None:
        return None

    density = get_ml_density(food)
    if density is None:
        density = 1.0  # fallback : eau
    return ml * density


def find_per_unit_weight(line: str) -> tuple[float, str] | None:
    """Cherche un pattern « (200 g chacune) » ou « (environ 200 g) » dans la ligne.
    Retourne (poids, unité) ou None.
    """
    m = PER_UNIT_WEIGHT_RE.search(line)
    if not m:
        m = ENVIRON_WEIGHT_RE.search(line)
    if m:
        return parse_qty(m.group(2)), m.group(3).lower()
    return None


def find_package_weight(text: str) -> tuple[float, str] | None:
    """Cherche « X g » ou « X ml » dans une ligne package après nettoyage."""
    m = re.search(rf"({NUM_PART})\s*(kg|g|oz|lb|ml|l)\b", text, re.IGNORECASE)
    if m:
        return parse_qty(m.group(1)), m.group(2).lower()
    return None


def find_canonical(stripped_name: str, ingredients: dict) -> tuple[str, dict] | None:
    """Cherche le meilleur match canonique dans le dict d'ingrédients.
    Préfère les aliases plus spécifiques (plus longs).
    """
    target = norm(stripped_name)
    best = None
    best_len = 0
    for key, spec in ingredients.items():
        for alias in spec.get("aliases", []):
            a_norm = norm(alias)
            if a_norm in target and len(a_norm) > best_len:
                best = (key, spec)
                best_len = len(a_norm)
    return best


def is_skip(stripped_name: str, skip_keywords: list[str]) -> bool:
    target = norm(stripped_name)
    for kw in skip_keywords:
        if norm(kw) == target:
            return True
    return False


def compute_ingredient_macros(line: str, ingredients: dict, cnf_foods: dict,
                               skip_keywords: list[str]) -> dict:
    """Calcule les macros pour une ligne d'ingrédient."""
    raw = line.strip().lstrip("-").strip()
    out = {"raw": raw, "grams": 0.0, "kcal": 0.0, "prot": 0.0, "gluc": 0.0, "lip": 0.0,
           "canonical": None, "status": "no_match"}

    # 0a) Zeste → skip (négligeable)
    if ZESTE_RE.match(raw):
        out["status"] = "skip"
        return out

    # 0b) « Jus de N citron(s) » → traite comme jus
    jus_m = JUS_DE_RE.match(raw)
    if jus_m:
        n_fruits = parse_qty(jus_m.group(1))
        fruit = jus_m.group(2).lower()
        # ml de jus par fruit (estimations)
        ml_per_fruit = {"citron": 30, "lime": 25, "orange": 70}.get(fruit, 30)
        canonical_key = {"citron": "citron_jus", "lime": "lime_jus", "orange": "orange_jus"}[fruit]
        spec = ingredients.get(canonical_key)
        if spec:
            food = cnf_foods.get(str(spec["cnf_id"]))
            if food:
                ml = n_fruits * ml_per_fruit
                grams = ml * (get_ml_density(food) or 1.0)
                factor = grams / 100.0
                out.update({
                    "grams": round(grams, 1),
                    "kcal": round(food.get("kcal", 0) * factor, 1),
                    "prot": round(food.get("prot", 0) * factor, 2),
                    "gluc": round(food.get("gluc", 0) * factor, 2),
                    "lip": round(food.get("lip", 0) * factor, 2),
                    "canonical": canonical_key,
                    "status": "ok",
                })
                return out

    # 0c) Skip pur (sel, eau, ...) — vérifié sur body après strip qty/unit
    name_clean = PARENS_RE.sub("", raw).strip().rstrip(",.").strip()

    # 1) Détecter package
    package_m = PACKAGE_RE.match(raw)
    package_trail_m = PACKAGE_TRAIL_RE.match(raw)
    # Detect "(200 g chacune)" pour le cas count + per-unit weight
    per_unit = find_per_unit_weight(raw)
    # Quantité de tête : essaye qty+unit d'abord, sinon count seul
    lead_qty = None
    lead_unit = None
    lead_match_re = None
    qu_m = LEAD_QTY_UNIT_RE.match(raw)
    if qu_m:
        lead_qty = parse_qty(qu_m.group(1))
        lead_unit = normalize_unit(qu_m.group(2))
        lead_match_re = LEAD_QTY_UNIT_RE
    else:
        c_m = LEAD_COUNT_ONLY_RE.match(raw)
        if c_m:
            lead_qty = parse_qty(c_m.group(1))
            lead_unit = None
            lead_match_re = LEAD_COUNT_ONLY_RE

    # Strip le début de ligne pour obtenir le body (nom)
    body = PARENS_RE.sub("", raw).strip()
    if package_trail_m:
        body = package_trail_m.group(2).strip().rstrip(",.").strip()
    elif package_m:
        body = re.sub(
            rf"^\s*({FRAC_PART})?\s*(?:bo[iî]tes?|sacs?|paquets?|barquette|conserves?|cont(?:enants?|enance)?|pot|botte)\s+de\s+({NUM_PART})\s*(kg|g|oz|lb|ml|l)\b(?:\s+chacuns?)?\s*(?:de\s+)?",
            "", body, flags=re.IGNORECASE)
    elif lead_match_re:
        body = lead_match_re.sub("", body, count=1)
    # Strip leading "de " / "d'" left over (e.g., "1/2 c. à thé de sel" → "sel")
    body = re.sub(r"^(?:de|d')\s*", "", body, flags=re.IGNORECASE).strip().rstrip(",.").strip()

    # Vérification skip après extraction du body
    if is_skip(body, skip_keywords) or is_skip(name_clean, skip_keywords):
        out["status"] = "skip"
        return out

    # 2) Trouver canonical
    found = find_canonical(body, ingredients)
    if not found:
        # Re-tente avec le raw complet (sans parens)
        found = find_canonical(name_clean, ingredients)
    if not found:
        return out

    key, spec = found
    out["canonical"] = key

    if spec.get("skip"):
        out["status"] = "skip"
        return out

    cnf_id = str(spec["cnf_id"])
    food = cnf_foods.get(cnf_id)
    if food is None:
        out["status"] = "no_food"
        return out

    # 3) Résoudre les grammes
    grams = None

    if per_unit and lead_qty is not None and lead_unit is None:
        pu_qty, pu_unit = per_unit
        unit_g = to_grams_from_unit(pu_qty, pu_unit, food)
        if unit_g is not None:
            grams = lead_qty * unit_g
    elif package_trail_m:
        pkg_qty = parse_qty(package_trail_m.group(3))
        pkg_unit = package_trail_m.group(4).lower()
        n_pkg = parse_qty(package_trail_m.group(1)) if package_trail_m.group(1) else 1
        unit_g = to_grams_from_unit(pkg_qty, pkg_unit, food)
        if unit_g is not None:
            grams = n_pkg * unit_g
    elif package_m:
        pkg_qty = parse_qty(package_m.group(2))
        pkg_unit = package_m.group(3).lower()
        n_pkg = parse_qty(package_m.group(1)) if package_m.group(1) else 1
        unit_g = to_grams_from_unit(pkg_qty, pkg_unit, food)
        if unit_g is not None:
            grams = n_pkg * unit_g
    elif lead_qty is not None and lead_unit is not None:
        grams = to_grams_from_unit(lead_qty, lead_unit, food)
    elif lead_qty is not None and lead_unit is None:
        # Compte : essaye d'abord poids embarqué.
        # Si « (N g) » sans « chacune », c'est un TOTAL, pas un per-unit.
        env = ENVIRON_WEIGHT_RE.search(raw)
        if env and "chacun" not in env.group(1).lower():
            unit_g = to_grams_from_unit(parse_qty(env.group(2)), env.group(3).lower(), food)
            if unit_g is not None:
                grams = unit_g  # total, pas multiplié
        if grams is None:
            inline = INLINE_DE_WEIGHT_RE.search(raw)
            if inline:
                # Inline « ... de N g » : aussi un total (rôti de 900 g, filet de 450 g)
                unit_g = to_grams_from_unit(parse_qty(inline.group(1)), inline.group(2).lower(), food)
                if unit_g is not None:
                    grams = unit_g
        if grams is None:
            cnt_g = spec.get("count_g")
            if cnt_g is not None:
                grams = lead_qty * cnt_g
    else:
        # Aucune quantité au début — chercher un "X g" n'importe où
        any_w = find_package_weight(raw)
        if any_w:
            grams = to_grams_from_unit(any_w[0], any_w[1], food)

    if grams is None or grams <= 0:
        out["status"] = "no_qty"
        return out

    factor = grams / 100.0
    out["grams"] = round(grams, 1)
    out["kcal"] = round(food.get("kcal", 0) * factor, 1)
    out["prot"] = round(food.get("prot", 0) * factor, 2)
    out["gluc"] = round(food.get("gluc", 0) * factor, 2)
    out["lip"] = round(food.get("lip", 0) * factor, 2)
    out["status"] = "ok"
    return out


# === Extraction d'ingrédients d'un .md ===

def extract_ingredient_lines(text: str) -> list[str]:
    m = re.search(r"##\s*Ingr[ée]dients\s*\n(.*?)\n##\s*Pr[ée]paration", text, re.DOTALL)
    if not m:
        return []
    return [ln.lstrip("-").strip()
            for ln in m.group(1).splitlines()
            if ln.strip().startswith("-")]


# === Build ===

def main():
    if not ING_YML.exists() or not CNF_JSON.exists():
        sys.exit(f"Erreur : il manque {ING_YML} ou {CNF_JSON}.")

    yml = yaml.safe_load(ING_YML.read_text(encoding="utf-8"))
    skip_kw = yml.get("skip_keywords", [])
    ingredients = yml.get("ingredients", {})
    cnf_foods = json.loads(CNF_JSON.read_text(encoding="utf-8"))

    # Compteurs pour rapport de couverture
    n_lines = 0
    n_ok = 0
    n_skip = 0
    n_unmatched = 0

    recipes = []
    for md_file in sorted(RECIPES_DIR.rglob("*.md")):
        if md_file.name.startswith("_"):
            continue
        rel = md_file.relative_to(RECIPES_DIR)
        folder = rel.parts[0] if len(rel.parts) > 1 else "Autres"
        text = md_file.read_text(encoding="utf-8")

        # Calcul des macros par ingrédient
        macros = []
        for line in extract_ingredient_lines(text):
            n_lines += 1
            r = compute_ingredient_macros(line, ingredients, cnf_foods, skip_kw)
            macros.append(r)
            if r["status"] == "ok":
                n_ok += 1
            elif r["status"] == "skip":
                n_skip += 1
            else:
                n_unmatched += 1

        recipes.append({
            "folder": folder,
            "filename": md_file.name,
            "id": str(rel).replace("/", "__").replace(".md", ""),
            "raw": text,
            "macros_par_ingredient": macros,
        })

    template = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(recipes, ensure_ascii=False)
    output = template.replace("/*__RECIPES_DATA__*/", data_json)
    OUTPUT.write_text(output, encoding="utf-8")

    pct_ok = 100 * n_ok / n_lines if n_lines else 0
    pct_skip = 100 * n_skip / n_lines if n_lines else 0
    pct_un = 100 * n_unmatched / n_lines if n_lines else 0
    print(f"Built {OUTPUT.relative_to(REPO)} avec {len(recipes)} recettes.")
    print(f"  Lignes d'ingrédients : {n_lines}")
    print(f"    Macros calculées : {n_ok} ({pct_ok:.0f}%)")
    print(f"    Ignorées (skip)  : {n_skip} ({pct_skip:.0f}%)")
    print(f"    Non résolues     : {n_unmatched} ({pct_un:.0f}%)")


if __name__ == "__main__":
    main()
