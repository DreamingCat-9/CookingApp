#!/usr/bin/env python3
"""Génère index.html à partir des recettes markdown dans recipes/.

Usage: python3 build.py
"""
import json
from pathlib import Path

REPO = Path(__file__).parent
RECIPES_DIR = REPO / "recipes"
TEMPLATE = REPO / "template.html"
OUTPUT = REPO / "index.html"


def main():
    recipes = []
    for md_file in sorted(RECIPES_DIR.rglob("*.md")):
        if md_file.name.startswith("_"):
            continue
        rel = md_file.relative_to(RECIPES_DIR)
        folder = rel.parts[0] if len(rel.parts) > 1 else "Autres"
        recipes.append({
            "folder": folder,
            "filename": md_file.name,
            "id": str(rel).replace("/", "__").replace(".md", ""),
            "raw": md_file.read_text(encoding="utf-8"),
        })

    template = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(recipes, ensure_ascii=False)
    output = template.replace("/*__RECIPES_DATA__*/", data_json)
    OUTPUT.write_text(output, encoding="utf-8")
    print(f"Built {OUTPUT.relative_to(REPO)} avec {len(recipes)} recettes.")


if __name__ == "__main__":
    main()
